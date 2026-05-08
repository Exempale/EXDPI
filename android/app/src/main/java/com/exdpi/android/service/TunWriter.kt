package com.exdpi.android.service

import java.io.FileOutputStream
import java.nio.ByteBuffer
import java.util.concurrent.locks.ReentrantLock
import kotlin.concurrent.withLock

/**
 * Пишет TCP-сегменты обратно в tun-устройство (от лица "удалённого сервера",
 * чтобы клиентское приложение видело привычное TCP-соединение).
 *
 * Только IPv4 для упрощения. Сегменты не фрагментируются (DF=1, без options).
 */
class TunWriter(private val out: FileOutputStream) {

    private val lock = ReentrantLock()
    private val buf = ByteArray(4096)

    fun writeTcpSegment(
        key: TcpKey,
        seq: Long,
        ack: Long,
        flags: Int,
        payload: ByteArray?,
    ) {
        val payloadLen = payload?.size ?: 0
        val totalLen = 20 + 20 + payloadLen // IPv4 hdr + TCP hdr + payload
        if (totalLen > buf.size) return

        lock.withLock {
            // IPv4 header
            buf[0] = 0x45 // version=4, IHL=5
            buf[1] = 0x00 // TOS
            buf[2] = ((totalLen ushr 8) and 0xFF).toByte()
            buf[3] = (totalLen and 0xFF).toByte()
            // identification
            val id = (System.nanoTime() and 0xFFFF).toInt()
            buf[4] = ((id ushr 8) and 0xFF).toByte()
            buf[5] = (id and 0xFF).toByte()
            buf[6] = 0x40 // flags=DF
            buf[7] = 0x00 // fragment offset
            buf[8] = 64 // TTL
            buf[9] = 6 // TCP
            buf[10] = 0; buf[11] = 0 // checksum placeholder
            // src ip = key.srcIp (это уже "от сервера" — ключ reversed)
            buf[12] = ((key.srcIp ushr 24) and 0xFF).toByte()
            buf[13] = ((key.srcIp ushr 16) and 0xFF).toByte()
            buf[14] = ((key.srcIp ushr 8) and 0xFF).toByte()
            buf[15] = (key.srcIp and 0xFF).toByte()
            // dst ip = key.dstIp
            buf[16] = ((key.dstIp ushr 24) and 0xFF).toByte()
            buf[17] = ((key.dstIp ushr 16) and 0xFF).toByte()
            buf[18] = ((key.dstIp ushr 8) and 0xFF).toByte()
            buf[19] = (key.dstIp and 0xFF).toByte()

            // TCP header
            val t = 20
            buf[t] = ((key.srcPort ushr 8) and 0xFF).toByte()
            buf[t + 1] = (key.srcPort and 0xFF).toByte()
            buf[t + 2] = ((key.dstPort ushr 8) and 0xFF).toByte()
            buf[t + 3] = (key.dstPort and 0xFF).toByte()
            // seq
            buf[t + 4] = ((seq ushr 24) and 0xFF).toByte()
            buf[t + 5] = ((seq ushr 16) and 0xFF).toByte()
            buf[t + 6] = ((seq ushr 8) and 0xFF).toByte()
            buf[t + 7] = (seq and 0xFF).toByte()
            // ack
            buf[t + 8] = ((ack ushr 24) and 0xFF).toByte()
            buf[t + 9] = ((ack ushr 16) and 0xFF).toByte()
            buf[t + 10] = ((ack ushr 8) and 0xFF).toByte()
            buf[t + 11] = (ack and 0xFF).toByte()
            // data offset (5*4=20) + flags
            buf[t + 12] = (5 shl 4).toByte()
            buf[t + 13] = (flags and 0xFF).toByte()
            // window
            buf[t + 14] = 0xFF.toByte()
            buf[t + 15] = 0xFF.toByte()
            // checksum placeholder
            buf[t + 16] = 0; buf[t + 17] = 0
            // urgent pointer
            buf[t + 18] = 0; buf[t + 19] = 0

            if (payload != null && payloadLen > 0) {
                System.arraycopy(payload, 0, buf, 40, payloadLen)
            }

            // checksums
            recomputeChecksums(buf, totalLen)

            try {
                out.write(buf, 0, totalLen)
            } catch (_: Throwable) {
                // tun closed
            }
        }
    }

    private fun recomputeChecksums(packet: ByteArray, length: Int) {
        // IPv4 header checksum
        packet[10] = 0; packet[11] = 0
        var sum = 0L
        for (i in 0 until 20 step 2) {
            sum += ((packet[i].toInt() and 0xFF) shl 8) or (packet[i + 1].toInt() and 0xFF)
        }
        while (sum ushr 16 != 0L) sum = (sum and 0xFFFFL) + (sum ushr 16)
        val ipSum = (sum.inv().toInt() and 0xFFFF)
        packet[10] = ((ipSum ushr 8) and 0xFF).toByte()
        packet[11] = (ipSum and 0xFF).toByte()

        // TCP checksum
        packet[36] = 0; packet[37] = 0
        var tcpSum = 0L
        // pseudo header: src ip + dst ip + zero + protocol(6) + tcp length
        for (i in 12..19 step 2) {
            tcpSum += ((packet[i].toInt() and 0xFF) shl 8) or (packet[i + 1].toInt() and 0xFF)
        }
        tcpSum += 6L
        val tcpLen = length - 20
        tcpSum += tcpLen.toLong()
        var i = 20
        while (i + 1 < length) {
            tcpSum += ((packet[i].toInt() and 0xFF) shl 8) or (packet[i + 1].toInt() and 0xFF)
            i += 2
        }
        if (i < length) {
            tcpSum += (packet[i].toInt() and 0xFF) shl 8
        }
        while (tcpSum ushr 16 != 0L) tcpSum = (tcpSum and 0xFFFFL) + (tcpSum ushr 16)
        val finalTcp = (tcpSum.inv().toInt() and 0xFFFF)
        packet[36] = ((finalTcp ushr 8) and 0xFF).toByte()
        packet[37] = (finalTcp and 0xFF).toByte()
    }

    @Suppress("unused")
    fun unusedByteBufferRef(b: ByteBuffer) = b.capacity()
}
