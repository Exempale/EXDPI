package com.exdpi.android.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.net.VpnService
import android.os.Build
import android.os.IBinder
import android.os.ParcelFileDescriptor
import android.util.Log
import androidx.core.app.NotificationCompat
import com.exdpi.android.R
import com.exdpi.android.core.ByeDpiNative
import com.exdpi.android.core.Tun2Socks
import com.exdpi.android.data.AppSettings
import com.exdpi.android.data.SettingsRepository
import com.exdpi.android.ui.MainActivity
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import java.io.File
import java.net.ServerSocket

/**
 * Главный VpnService — связка byedpi + hev-socks5-tunnel.
 *
 * Архитектура (как в ByeDPIAndroid / Zapret-Android):
 *   1. Создаём tun-устройство через VpnService.Builder. Если у пользователя
 *      выбран не «для всех» — указываем addAllowedApplication для каждой
 *      выбранной упаковки. Иначе — addDisallowedApplication для самих себя
 *      (чтобы не было петли).
 *   2. Поднимаем встроенный SOCKS5-сервер byedpi на 127.0.0.1:port.
 *      Он применяет TLS-десинк (split + disorder + tlsrec) к первому
 *      пакету каждого соединения.
 *   3. Поднимаем hev-socks5-tunnel: он читает IP-пакеты из tun fd, делает
 *      их NAT'ом и пробрасывает все TCP/UDP-соединения в наш SOCKS5.
 *   4. На стопе: глушим tun2socks, потом byedpi, потом закрываем tun.
 *
 * Никакого ручного TCP state-machine больше нет — tun2socks использует
 * lwIP, который умеет нормальное окно/ретрансмит/SACK.
 */
class ExDpiVpnService : VpnService() {

    private val tag = "ExDpiVpn"
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    private var tun: ParcelFileDescriptor? = null
    private var configFile: File? = null
    private var byedpiStarted = false
    private var tun2socksStarted = false

    companion object {
        const val ACTION_START = "com.exdpi.android.action.START"
        const val ACTION_STOP = "com.exdpi.android.action.STOP"
        private const val NOTIF_ID = 11
        private const val CHANNEL_ID = "exdpi_vpn"

        private const val TUN_ADDRESS_V4 = "198.18.0.1"
        private const val TUN_ADDRESS_V6 = "fc00::1"
        private const val TUN_MTU = 8500
        private const val PROXY_HOST = "127.0.0.1"

        private val _state = MutableStateFlow(State.IDLE)
        val state: StateFlow<State> = _state

        enum class State { IDLE, STARTING, RUNNING, STOPPING }

        fun start(ctx: Context) {
            ctx.startForegroundService(Intent(ctx, ExDpiVpnService::class.java).apply {
                action = ACTION_START
            })
        }

        fun stop(ctx: Context) {
            ctx.startService(Intent(ctx, ExDpiVpnService::class.java).apply {
                action = ACTION_STOP
            })
        }
    }

    override fun onBind(intent: Intent?): IBinder? = super.onBind(intent)

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> {
                stopVpn()
                stopForegroundCompat()
                stopSelf()
                return START_NOT_STICKY
            }
            else -> {
                startForegroundCompat()
                startVpn()
                return START_STICKY
            }
        }
    }

    override fun onRevoke() {
        Log.i(tag, "VPN revoked by system")
        stopVpn()
        super.onRevoke()
    }

    override fun onDestroy() {
        stopVpn()
        scope.cancel()
        super.onDestroy()
    }

    private fun startVpn() {
        if (_state.value == State.RUNNING || _state.value == State.STARTING) return
        _state.value = State.STARTING
        scope.launch {
            try {
                val repo = SettingsRepository(applicationContext)
                val settings = repo.settings.first()

                // 1) Свободный порт для byedpi на 127.0.0.1.
                val proxyPort = findFreeLocalPort()

                // 2) Поднимаем byedpi (SOCKS5 + DPI desync).
                val rc = ByeDpiNative.nativeStart(
                    ByeDpiNative.buildArgv(PROXY_HOST, proxyPort),
                )
                if (rc != 0) {
                    throw IllegalStateException("byedpi start failed rc=$rc")
                }
                byedpiStarted = true
                Log.i(tag, "byedpi started on $PROXY_HOST:$proxyPort")

                // 3) Tun-устройство.
                val pfd = buildTun(settings) ?: run {
                    Log.e(tag, "Builder.establish() returned null")
                    onStartFailed()
                    return@launch
                }
                tun = pfd

                // 4) YAML-конфиг для hev-socks5-tunnel.
                val cfg = writeTunnelConfig(proxyPort)
                configFile = cfg

                // 5) Запуск tun2socks.
                Tun2Socks.TProxyStartService(cfg.absolutePath, pfd.fd)
                tun2socksStarted = true
                Log.i(tag, "tun2socks started, fd=${pfd.fd}")

                _state.value = State.RUNNING
            } catch (t: Throwable) {
                Log.e(tag, "VPN start failed", t)
                onStartFailed()
            }
        }
    }

    private fun onStartFailed() {
        cleanupRuntime()
        _state.value = State.IDLE
        stopForegroundCompat()
        stopSelf()
    }

    private fun buildTun(settings: AppSettings): ParcelFileDescriptor? {
        val builder = Builder()
            .setSession(getString(R.string.app_name))
            .setMtu(TUN_MTU)
            .addAddress(TUN_ADDRESS_V4, 30)
            .addAddress(TUN_ADDRESS_V6, 126)
            .addRoute("0.0.0.0", 0)
            .addRoute("::", 0)
            .addDnsServer("1.1.1.1")
            .addDnsServer("8.8.8.8")
            .setBlocking(false)

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            builder.setMetered(false)
        }

        if (!settings.applyToAll) {
            var added = 0
            for (pkg in settings.selectedApps) {
                try {
                    builder.addAllowedApplication(pkg)
                    added++
                } catch (_: PackageManager.NameNotFoundException) {
                    // Приложение не установлено — пропускаем.
                }
            }
            if (added == 0) {
                // Если ни одно из выбранных приложений не установлено — не запускаем
                // VPN, иначе мы бы захватили вообще весь трафик.
                Log.w(tag, "No selected apps installed — VPN not started")
                return null
            }
        } else {
            // Исключаем сами себя, чтобы byedpi мог соединяться с интернетом.
            try {
                builder.addDisallowedApplication(packageName)
            } catch (_: PackageManager.NameNotFoundException) {}
        }

        return builder.establish()
    }

    private fun writeTunnelConfig(proxyPort: Int): File {
        // hev-socks5-tunnel читает YAML с диска — сгенерим минимальный конфиг.
        // tun-name = "tun0", tun уже создан VpnService — параметр не используется
        // при работе через fd, оставляем для совместимости.
        val yaml = """
            tunnel:
              name: tun0
              mtu: $TUN_MTU
              ipv4: $TUN_ADDRESS_V4
              ipv6: '$TUN_ADDRESS_V6'
            socks5:
              port: $proxyPort
              address: $PROXY_HOST
              udp: 'udp'
            misc:
              log-level: warn
              log-file: stderr
              limit-nofile: 65535
        """.trimIndent()
        val dir = File(filesDir, "exdpi")
        dir.mkdirs()
        val file = File(dir, "tun2socks.yaml")
        file.writeText(yaml)
        return file
    }

    private fun findFreeLocalPort(): Int {
        ServerSocket(0).use { return it.localPort }
    }

    private fun stopVpn() {
        if (_state.value == State.IDLE || _state.value == State.STOPPING) return
        _state.value = State.STOPPING
        cleanupRuntime()
        _state.value = State.IDLE
    }

    private fun cleanupRuntime() {
        if (tun2socksStarted) {
            try { Tun2Socks.TProxyStopService() } catch (t: Throwable) {
                Log.w(tag, "TProxyStopService: $t")
            }
            tun2socksStarted = false
        }
        if (byedpiStarted) {
            try { ByeDpiNative.nativeStop() } catch (t: Throwable) {
                Log.w(tag, "byedpi stop: $t")
            }
            byedpiStarted = false
        }
        try { tun?.close() } catch (_: Throwable) {}
        tun = null
        try { configFile?.delete() } catch (_: Throwable) {}
        configFile = null
    }

    private fun startForegroundCompat() {
        ensureChannel()
        val openIntent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
        }
        val flags = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M)
            PendingIntent.FLAG_IMMUTABLE else 0
        val pi = PendingIntent.getActivity(this, 0, openIntent, flags)
        val notif: Notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_lock_lock)
            .setContentTitle(getString(R.string.notif_running_title))
            .setContentText(getString(R.string.notif_running_text))
            .setOngoing(true)
            .setContentIntent(pi)
            .build()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(
                NOTIF_ID,
                notif,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE,
            )
        } else {
            startForeground(NOTIF_ID, notif)
        }
    }

    private fun stopForegroundCompat() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
            stopForeground(STOP_FOREGROUND_REMOVE)
        } else {
            @Suppress("DEPRECATION")
            stopForeground(true)
        }
    }

    private fun ensureChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val nm = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
        if (nm.getNotificationChannel(CHANNEL_ID) != null) return
        val ch = NotificationChannel(
            CHANNEL_ID,
            getString(R.string.notif_channel_name),
            NotificationManager.IMPORTANCE_LOW,
        )
        ch.setShowBadge(false)
        nm.createNotificationChannel(ch)
    }
}
