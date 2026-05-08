package com.exdpi.android.core

/**
 * JNI к hev-socks5-tunnel: tun -> SOCKS5.
 *
 * Используем готовый бинарный модуль, на нём же построены ByeDPIAndroid
 * и hev-socks5-tunnel-Android. Принимает путь к YAML-конфигу и fd
 * tun-устройства (мы получаем его из VpnService.Builder.establish()).
 *
 * Имена методов фиксированы в hev-jni.c через RegisterNatives, имя
 * пакета и класса задаются макросами PKGNAME/CLSNAME при сборке (см.
 * build.gradle.kts -> ndkBuild arguments).
 */
object Tun2Socks {

    init {
        System.loadLibrary("hev-socks5-tunnel")
    }

    /** Запустить tun2socks. Блокировки нет — всё крутится в native-потоке. */
    @JvmStatic
    external fun TProxyStartService(configPath: String, tunFd: Int)

    /** Остановить tun2socks и дождаться выхода native-потока. */
    @JvmStatic
    external fun TProxyStopService()

    /** Возвращает [tx_packets, tx_bytes, rx_packets, rx_bytes]. */
    @JvmStatic
    external fun TProxyGetStats(): LongArray
}
