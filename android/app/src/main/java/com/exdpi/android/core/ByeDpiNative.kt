package com.exdpi.android.core

/**
 * JNI-обёртка вокруг встроенного byedpi (модифицированный ciadpi).
 *
 * byedpi — локальный SOCKS5-сервер, который применяет десинхронизацию
 * первого TLS/HTTP-пакета (split / disorder / fake / oob), чтобы пройти
 * через DPI-фильтры Роскомнадзора и аналогов. Запускается фоновым потоком
 * внутри процесса приложения, останавливается shutdown'ом listening-сокета.
 *
 * Все опции передаются строками — точно так же, как в командной строке
 * настольной версии. См. [DEFAULT_ARGS] про дефолтный профиль.
 */
object ByeDpiNative {

    init {
        System.loadLibrary("byedpi")
    }

    /**
     * Запустить byedpi в фоне. argv не должен содержать имя бинарника на
     * нулевой позиции — мы сами добавляем "byedpi".
     *
     * @return 0 если успешно стартовал, -2 если уже запущен, прочее < 0 — ошибка.
     */
    @JvmStatic
    external fun nativeStart(argv: Array<String>): Int

    /**
     * Остановить byedpi (shutdown listening-сокета + ожидание потока).
     */
    @JvmStatic
    external fun nativeStop(): Int

    @JvmStatic
    external fun nativeIsRunning(): Boolean

    /**
     * Сборка argv: имя бинарника + опции. Имя нужно потому, что getopt
     * ожидает argv[0] как имя программы (даже если оно не используется).
     */
    fun buildArgv(host: String, port: Int, extra: List<String> = DEFAULT_DESYNC_OPTS): Array<String> {
        val args = mutableListOf<String>()
        args += "byedpi"
        args += "-i"
        args += host
        args += "-p"
        args += port.toString()
        args += extra
        return args.toTypedArray()
    }

    /**
     * Профиль десинка по умолчанию. Подобран как «работает в большинстве
     * случаев в России»: TLS-record split + disorder на SNI, плюс fake
     * на TLS, по аналогии с zapret-Android.
     *
     * Эти опции применяются только к TLS/HTTP/UDP (см. -K). Остальной
     * трафик идёт без модификации.
     */
    val DEFAULT_DESYNC_OPTS: List<String> = listOf(
        "-K", "1",                  // протоколы: tls (= 1)
        "-A", "torst,ssl_err",      // авто-фолбэк, если первая попытка не зашла
        "-r", "1+s",                // tlsrec: разбить ClientHello на 2 TLS-записи в районе SNI
        "-s", "1+s",                // split: разбить TCP-payload на смещении SNI+1
        "-d", "3+s",                // disorder: послать 3 байта SNI «вне порядка»
    )
}
