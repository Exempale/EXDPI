package com.exdpi.android.service

/**
 * Идентификатор TCP-сессии (5-tuple без protocol).
 *
 * Адреса хранятся как Int (network byte order — старший байт первый), это
 * позволяет дёшево сравнивать и хешировать.
 */
data class TcpKey(
    val srcIp: Int,
    val srcPort: Int,
    val dstIp: Int,
    val dstPort: Int,
) {
    fun reversed(): TcpKey = TcpKey(dstIp, dstPort, srcIp, srcPort)

    fun srcIpString(): String = ipToString(srcIp)
    fun dstIpString(): String = ipToString(dstIp)

    fun shortId(): String =
        "${srcIpString()}:${srcPort}->${dstIpString()}:${dstPort}"

    private fun ipToString(ip: Int): String =
        "${(ip ushr 24) and 0xFF}.${(ip ushr 16) and 0xFF}.${(ip ushr 8) and 0xFF}.${ip and 0xFF}"
}
