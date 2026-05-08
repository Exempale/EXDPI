package com.exdpi.android.service

import android.util.Log
import com.exdpi.android.data.Strategy
import java.net.Socket
import java.util.concurrent.ConcurrentHashMap

/**
 * Реестр активных TCP-сессий + диспетчер входящих сегментов из tun.
 *
 * Один пакет → разбираем (IPv4 + TCP) → находим/создаём [TcpSession] → отдаём ему.
 */
class TcpNat(
    private val tunWriter: TunWriter,
    private val protect: (Socket) -> Boolean,
    private val strategyProvider: () -> Strategy,
    private val portsProvider: () -> Set<Int>,
) {

    private val tag = "TcpNat"
    private val sessions = ConcurrentHashMap<TcpKey, TcpSession>()

    @Volatile var bytesUp: Long = 0
    @Volatile var bytesDown: Long = 0

    /** Запросить количество активных сессий — для UI. */
    val activeCount: Int get() = sessions.count { !it.value.isClosed() }

    fun handlePacket(packet: ByteArray, length: Int) {
        if (length < 20) return
        if (PacketUtils.ipVersion(packet) != 4) return // IPv6 пока не поддерживаем
        val protocol = PacketUtils.ipv4Protocol(packet)
        if (protocol != 6) return // не TCP
        val ihl = PacketUtils.ipv4HeaderLength(packet)
        if (ihl > length) return
        val tcpOffset = ihl
        if (tcpOffset + 20 > length) return

        val srcPort = PacketUtils.tcpSrcPort(packet, tcpOffset)
        val dstPort = PacketUtils.tcpDstPort(packet, tcpOffset)
        val srcIp = PacketUtils.ipv4Source(packet)
        val dstIp = PacketUtils.ipv4Destination(packet)
        val flags = PacketUtils.tcpFlags(packet, tcpOffset)
        val tcpHdrLen = PacketUtils.tcpHeaderLength(packet, tcpOffset)
        val payloadOffset = tcpOffset + tcpHdrLen
        val payloadLength = length - payloadOffset
        val seq = readU32(packet, tcpOffset + 4)
        val ack = readU32(packet, tcpOffset + 8)
        val win = ((packet[tcpOffset + 14].toInt() and 0xFF) shl 8) or
            (packet[tcpOffset + 15].toInt() and 0xFF)

        val key = TcpKey(srcIp, srcPort, dstIp, dstPort)
        val ports = portsProvider()
        val isMatchingPort = ports.contains(dstPort)

        val session = sessions.getOrPut(key) {
            if (!PacketUtils.isTcpSyn(flags)) {
                Log.d(tag, "ignoring non-SYN for unknown flow ${key.shortId()} flags=$flags")
                return
            }
            // Если порт не в списке — пропускаем (создавать сессию = делать reset).
            if (!isMatchingPort) {
                // Пользователь не выбрал этот порт; не вмешиваемся в трафик.
                return@getOrPut TcpSession(key, tunWriter, protect, strategyProvider())
            }
            TcpSession(key, tunWriter, protect, strategyProvider())
        }

        bytesUp += payloadLength.toLong()
        session.onTunSegment(flags, seq, ack, win, packet, payloadOffset, payloadLength)

        if (session.isClosed()) {
            sessions.remove(key, session)
        }
    }

    fun closeAll() {
        for (s in sessions.values) {
            s.closeSession()
        }
        sessions.clear()
    }

    private fun readU32(packet: ByteArray, offset: Int): Long =
        ((packet[offset].toLong() and 0xFFL) shl 24) or
            ((packet[offset + 1].toLong() and 0xFFL) shl 16) or
            ((packet[offset + 2].toLong() and 0xFFL) shl 8) or
            (packet[offset + 3].toLong() and 0xFFL)
}
