package com.exdpi.android.service

import java.nio.ByteBuffer

/**
 * Минимальный парсер IPv4/IPv6 + TCP. Считает контрольные суммы заново
 * после изменения payload (нужно для split TLS ClientHello).
 *
 * Мы умышленно не обрабатываем UDP — DPI на Android в основном бьёт по TCP/443.
 * QUIC шифрован целиком и DPI без TLS-фингерпринта его не трогает (а если
 * трогает, то блокирует факт-наличие — это вне нашего радара).
 */
object PacketUtils {

    fun ipVersion(packet: ByteArray): Int = (packet[0].toInt() ushr 4) and 0x0F

    fun ipv4HeaderLength(packet: ByteArray): Int = (packet[0].toInt() and 0x0F) * 4

    fun ipv4TotalLength(packet: ByteArray): Int =
        ((packet[2].toInt() and 0xFF) shl 8) or (packet[3].toInt() and 0xFF)

    fun setIpv4TotalLength(packet: ByteArray, value: Int) {
        packet[2] = ((value ushr 8) and 0xFF).toByte()
        packet[3] = (value and 0xFF).toByte()
    }

    fun ipv4Protocol(packet: ByteArray): Int = packet[9].toInt() and 0xFF

    fun ipv6Protocol(packet: ByteArray): Int = packet[6].toInt() and 0xFF

    fun ipv4Identification(packet: ByteArray): Int =
        ((packet[4].toInt() and 0xFF) shl 8) or (packet[5].toInt() and 0xFF)

    fun setIpv4Identification(packet: ByteArray, value: Int) {
        packet[4] = ((value ushr 8) and 0xFF).toByte()
        packet[5] = (value and 0xFF).toByte()
    }

    fun setIpv4Ttl(packet: ByteArray, ttl: Int) {
        packet[8] = (ttl and 0xFF).toByte()
    }

    fun ipv4Source(packet: ByteArray): Int =
        ((packet[12].toInt() and 0xFF) shl 24) or
            ((packet[13].toInt() and 0xFF) shl 16) or
            ((packet[14].toInt() and 0xFF) shl 8) or
            (packet[15].toInt() and 0xFF)

    fun ipv4Destination(packet: ByteArray): Int =
        ((packet[16].toInt() and 0xFF) shl 24) or
            ((packet[17].toInt() and 0xFF) shl 16) or
            ((packet[18].toInt() and 0xFF) shl 8) or
            (packet[19].toInt() and 0xFF)

    /** TCP source port (offset = ip_header_length). */
    fun tcpSrcPort(packet: ByteArray, tcpOffset: Int): Int =
        ((packet[tcpOffset].toInt() and 0xFF) shl 8) or
            (packet[tcpOffset + 1].toInt() and 0xFF)

    fun tcpDstPort(packet: ByteArray, tcpOffset: Int): Int =
        ((packet[tcpOffset + 2].toInt() and 0xFF) shl 8) or
            (packet[tcpOffset + 3].toInt() and 0xFF)

    fun tcpHeaderLength(packet: ByteArray, tcpOffset: Int): Int =
        ((packet[tcpOffset + 12].toInt() ushr 4) and 0x0F) * 4

    fun tcpFlags(packet: ByteArray, tcpOffset: Int): Int = packet[tcpOffset + 13].toInt() and 0xFF

    fun isTcpSyn(flags: Int): Boolean = (flags and 0x02) != 0
    fun isTcpAck(flags: Int): Boolean = (flags and 0x10) != 0
    fun isTcpPsh(flags: Int): Boolean = (flags and 0x08) != 0
    fun isTcpFin(flags: Int): Boolean = (flags and 0x01) != 0
    fun isTcpRst(flags: Int): Boolean = (flags and 0x04) != 0

    /** Считает 16-битную one's complement сумму по чётному числу байт. */
    private fun checksum16(buf: ByteBuffer, offset: Int, length: Int, initial: Long = 0L): Int {
        var sum = initial
        var i = 0
        while (i + 1 < length) {
            sum += ((buf.get(offset + i).toInt() and 0xFF) shl 8) or
                (buf.get(offset + i + 1).toInt() and 0xFF)
            i += 2
        }
        if (i < length) {
            sum += (buf.get(offset + i).toInt() and 0xFF) shl 8
        }
        while (sum ushr 16 != 0L) {
            sum = (sum and 0xFFFFL) + (sum ushr 16)
        }
        return (sum.inv().toInt() and 0xFFFF)
    }

    /** Пересчитать IPv4 + TCP контрольные суммы. */
    fun recomputeIpv4AndTcpChecksums(packet: ByteArray, length: Int) {
        // IPv4 header checksum
        val ihl = ipv4HeaderLength(packet)
        packet[10] = 0
        packet[11] = 0
        val ipBuf = ByteBuffer.wrap(packet, 0, length)
        val ipSum = checksum16(ipBuf, 0, ihl)
        packet[10] = ((ipSum ushr 8) and 0xFF).toByte()
        packet[11] = (ipSum and 0xFF).toByte()

        // TCP checksum (с псевдо-заголовком)
        val tcpOffset = ihl
        val tcpLength = length - tcpOffset
        packet[tcpOffset + 16] = 0
        packet[tcpOffset + 17] = 0

        var pseudoSum = 0L
        // src ip (4) + dst ip (4)
        for (i in 12..19 step 2) {
            pseudoSum += ((packet[i].toInt() and 0xFF) shl 8) or
                (packet[i + 1].toInt() and 0xFF)
        }
        // protocol (TCP=6)
        pseudoSum += 6L
        pseudoSum += tcpLength.toLong()

        val tcpSum = checksum16(ipBuf, tcpOffset, tcpLength, pseudoSum)
        packet[tcpOffset + 16] = ((tcpSum ushr 8) and 0xFF).toByte()
        packet[tcpOffset + 17] = (tcpSum and 0xFF).toByte()
    }

    /** Возвращает true, если payload TCP похож на TLS ClientHello (версия + length). */
    fun looksLikeTlsClientHello(packet: ByteArray, payloadOffset: Int, payloadLength: Int): Boolean {
        if (payloadLength < 6) return false
        val recordType = packet[payloadOffset].toInt() and 0xFF
        // Handshake = 0x16
        if (recordType != 0x16) return false
        val major = packet[payloadOffset + 1].toInt() and 0xFF
        val minor = packet[payloadOffset + 2].toInt() and 0xFF
        if (major != 0x03) return false
        if (minor !in 0x01..0x04) return false
        val handshakeType = packet[payloadOffset + 5].toInt() and 0xFF
        // 0x01 = ClientHello
        return handshakeType == 0x01
    }

    /**
     * Найти offset в payload, где заканчивается hostname в SNI extension.
     * Возвращает offset (от начала пакета), на котором безопасно ставить
     * границу split — т.е. внутри SNI hostname. -1, если не найден.
     */
    fun sniSplitOffset(packet: ByteArray, payloadOffset: Int, payloadLength: Int): Int {
        if (payloadLength < 43) return -1
        // TLS record header = 5, handshake header = 4, version = 2, random = 32 = 43
        var p = payloadOffset + 43
        val end = payloadOffset + payloadLength

        if (p >= end) return -1
        // session_id
        val sessionIdLen = packet[p].toInt() and 0xFF
        p += 1 + sessionIdLen
        if (p + 2 > end) return -1
        // cipher_suites
        val csLen = ((packet[p].toInt() and 0xFF) shl 8) or (packet[p + 1].toInt() and 0xFF)
        p += 2 + csLen
        if (p + 1 > end) return -1
        // compression_methods
        val cmLen = packet[p].toInt() and 0xFF
        p += 1 + cmLen
        if (p + 2 > end) return -1
        // extensions length
        val extTotal = ((packet[p].toInt() and 0xFF) shl 8) or (packet[p + 1].toInt() and 0xFF)
        p += 2
        val extEnd = p + extTotal
        if (extEnd > end) return -1

        while (p + 4 <= extEnd) {
            val extType = ((packet[p].toInt() and 0xFF) shl 8) or (packet[p + 1].toInt() and 0xFF)
            val extLen = ((packet[p + 2].toInt() and 0xFF) shl 8) or (packet[p + 3].toInt() and 0xFF)
            val extDataStart = p + 4
            val extDataEnd = extDataStart + extLen
            if (extDataEnd > extEnd) return -1
            if (extType == 0x0000) {
                // SNI extension
                if (extDataStart + 5 > extDataEnd) return -1
                // server_name_list length (2) + name_type (1) + name length (2)
                val nameStart = extDataStart + 5
                if (nameStart >= extDataEnd) return -1
                // Делим примерно посередине hostname — это даёт стабильный split
                // и не задевает ни TLS record header, ни сам тип extension.
                val mid = (nameStart + extDataEnd) / 2
                return mid
            }
            p = extDataEnd
        }
        // Если SNI не нашли — делим на середине payload
        return -1
    }
}
