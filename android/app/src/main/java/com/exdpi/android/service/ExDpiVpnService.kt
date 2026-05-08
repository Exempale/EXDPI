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
import com.exdpi.android.data.AppSettings
import com.exdpi.android.data.SettingsRepository
import com.exdpi.android.data.Strategy
import com.exdpi.android.ui.MainActivity
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import java.io.FileInputStream
import java.io.FileOutputStream

/**
 * Главный VpnService.
 *
 * При запуске:
 *   1. Читает текущие настройки.
 *   2. Создаёт tun-устройство (10.0.0.1/30, route 0.0.0.0/0).
 *   3. Если applyToAll == false — добавляет только выбранные приложения через
 *      addAllowedApplication(packageName).
 *   4. Поднимает [TcpNat] и читает IP-пакеты в цикле.
 */
class ExDpiVpnService : VpnService() {

    private val tag = "ExDpiVpn"
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    private var tun: ParcelFileDescriptor? = null
    private var nat: TcpNat? = null
    private var pumpJob: Job? = null
    private var settings: AppSettings = AppSettings()

    companion object {
        const val ACTION_START = "com.exdpi.android.action.START"
        const val ACTION_STOP = "com.exdpi.android.action.STOP"
        private const val NOTIF_ID = 11
        private const val CHANNEL_ID = "exdpi_vpn"

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
                settings = repo.settings.first()
                val builder = Builder()
                    .setSession(getString(R.string.app_name))
                    .addAddress("10.0.0.1", 30)
                    .addRoute("0.0.0.0", 0)
                    .addDnsServer("1.1.1.1")
                    .addDnsServer("8.8.8.8")
                    .setMtu(1500)
                    .setBlocking(true)

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
                        // Чтобы не туннелировать вообще ничего и не убить весь интернет —
                        // если выбранных приложений нет, возвращаемся.
                        Log.w(tag, "No selected apps installed — VPN not started")
                        _state.value = State.IDLE
                        stopForegroundCompat()
                        stopSelf()
                        return@launch
                    }
                } else {
                    // Исключаем сами себя из туннеля во избежание петли.
                    try {
                        builder.addDisallowedApplication(packageName)
                    } catch (_: PackageManager.NameNotFoundException) {}
                }

                val pfd = builder.establish() ?: run {
                    Log.e(tag, "Builder.establish() returned null — нет согласия пользователя?")
                    _state.value = State.IDLE
                    stopForegroundCompat()
                    stopSelf()
                    return@launch
                }
                tun = pfd

                val tunIn = FileInputStream(pfd.fileDescriptor)
                val tunOut = FileOutputStream(pfd.fileDescriptor)
                val writer = TunWriter(tunOut)
                val tcpNat = TcpNat(
                    tunWriter = writer,
                    protect = { socket -> protect(socket) },
                    strategyProvider = { settings.strategy },
                    portsProvider = {
                        val ports = mutableSetOf<Int>()
                        if (settings.port443) ports += 443
                        if (settings.port80) ports += 80
                        if (ports.isEmpty()) ports += 443
                        ports
                    },
                )
                nat = tcpNat
                _state.value = State.RUNNING

                pumpJob = scope.launch {
                    val buf = ByteArray(32768)
                    try {
                        while (true) {
                            val n = tunIn.read(buf)
                            if (n <= 0) break
                            try {
                                tcpNat.handlePacket(buf, n)
                            } catch (t: Throwable) {
                                Log.w(tag, "handlePacket failed: $t")
                            }
                        }
                    } catch (_: Throwable) {
                        // tun closed
                    } finally {
                        Log.i(tag, "tun pump exited")
                    }
                }
            } catch (t: Throwable) {
                Log.e(tag, "VPN start failed", t)
                _state.value = State.IDLE
                stopForegroundCompat()
                stopSelf()
            }
        }
    }

    private fun stopVpn() {
        if (_state.value == State.IDLE || _state.value == State.STOPPING) return
        _state.value = State.STOPPING
        try {
            pumpJob?.cancel()
            nat?.closeAll()
            tun?.close()
        } catch (t: Throwable) {
            Log.w(tag, "stopVpn cleanup error: $t")
        } finally {
            tun = null
            nat = null
            pumpJob = null
            _state.value = State.IDLE
        }
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

    @Suppress("UNUSED")
    private val unusedStrategyRef: Strategy = Strategy.CLIENTHELLO_SPLIT
}
