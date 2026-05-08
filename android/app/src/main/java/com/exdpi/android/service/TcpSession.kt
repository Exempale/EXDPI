package com.exdpi.android.service

import android.util.Log
import com.exdpi.android.data.Strategy
import java.io.IOException
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.Socket
import java.util.concurrent.atomic.AtomicLong
import java.util.concurrent.locks.ReentrantLock
import kotlin.concurrent.withLock
import kotlin.random.Random

/**
 * Состояние одной TCP-сессии, проксируемой через userspace NAT.
 *
 * Жизненный цикл:
 *  1. tun_in: SYN  → создаём Socket() к dst, протектим через VpnService.protect.
 *     После TCP-handshake'а с реальным сервером отвечаем клиенту SYN+ACK.
 *  2. tun_in: ACK  → handshake завершён, открыты потоки данных.
 *  3. tun_in: payload → пишем в реальный сокет. На первом payload'е
 *                       применяем split (см. [DpiBypassEngine]).
 *  4. real socket: data → формируем TCP-сегменты обратно в tun.
 *  5. FIN/RST → закрываем обе стороны.
 *
 * Это упрощённая реализация — без window scaling, без SACK, без congestion
 * control. Зато минимальная и достаточная для HTTPS/HTTP трафика.
 */
class TcpSession(
    val key: TcpKey,
    val tun: TunWriter,
    val protect: (Socket) -> Boolean,
    val strategy: Strategy,
) {
    enum class State { SYN_RECV, ESTABLISHED, FIN_WAIT, CLOSED }

    private val tag = "TcpSession"
    private val lock = ReentrantLock()
    private var state: State = State.SYN_RECV
    private var socket: Socket? = null

    // Sequence numbers
    private var localSeq: Long = (Random.nextInt() and 0x7FFFFFFF).toLong()
    private var clientSeq: Long = 0
    private var clientWin: Int = 65535

    private val firstPayloadSent = AtomicLong(0)

    @Volatile private var closedFlag = false
    fun isClosed(): Boolean = closedFlag

    /**
     * Обрабатывает входящий TCP-сегмент из tun.
     */
    @Suppress("UNUSED_PARAMETER")
    fun onTunSegment(
        flags: Int,
        seq: Long,
        ack: Long,
        win: Int,
        payload: ByteArray,
        payloadOffset: Int,
        payloadLength: Int,
    ) {
        if (closedFlag) return

        when {
            PacketUtils.isTcpSyn(flags) && state == State.SYN_RECV -> handleSyn(seq, win)
            PacketUtils.isTcpRst(flags) -> closeSession()
            PacketUtils.isTcpFin(flags) -> handleFin(seq, payloadLength)
            payloadLength > 0 && state == State.ESTABLISHED ->
                handlePayload(seq, payload, payloadOffset, payloadLength)
            // pure ACK — игнор, у нас нет окна для отправки/буфера retx
        }
    }

    private fun handleSyn(seq: Long, win: Int) = lock.withLock {
        clientSeq = (seq + 1) and 0xFFFFFFFFL
        clientWin = win
        // Подключаемся к реальному dst в фоне.
        Thread {
            val dstAddr = key.dstIpString()
            val s = Socket()
            try {
                s.tcpNoDelay = true
                if (!protect(s)) {
                    Log.w(tag, "VpnService.protect() returned false for $dstAddr:${key.dstPort}")
                    sendRst()
                    return@Thread
                }
                s.connect(InetSocketAddress(InetAddress.getByName(dstAddr), key.dstPort), 8000)
                lock.withLock {
                    socket = s
                    state = State.ESTABLISHED
                }
                // Отвечаем клиенту SYN+ACK
                tun.writeTcpSegment(
                    key = key.reversed(),
                    seq = localSeq,
                    ack = clientSeq,
                    flags = 0x12, // SYN+ACK
                    payload = null,
                )
                localSeq = (localSeq + 1) and 0xFFFFFFFFL
                // Стартуем поток чтения с реального сокета
                Thread(::pumpFromUpstream, "exdpi-up-${key.shortId()}").apply {
                    isDaemon = true
                    start()
                }
            } catch (e: IOException) {
                Log.w(tag, "connect to ${key.dstIpString()}:${key.dstPort} failed: $e")
                sendRst()
            }
        }.start()
    }

    private fun handlePayload(
        seq: Long,
        payload: ByteArray,
        payloadOffset: Int,
        payloadLength: Int,
    ) {
        // ACK клиенту — данные приняли.
        clientSeq = (seq + payloadLength) and 0xFFFFFFFFL
        tun.writeTcpSegment(
            key = key.reversed(),
            seq = localSeq,
            ack = clientSeq,
            flags = 0x10, // ACK
            payload = null,
        )

        val s = socket ?: return
        try {
            val out = s.getOutputStream()
            if (firstPayloadSent.compareAndSet(0, 1)) {
                DpiBypassEngine.writeFirstClientPayload(
                    out, payload, payloadOffset, payloadLength, strategy,
                )
            } else {
                out.write(payload, payloadOffset, payloadLength)
                out.flush()
            }
        } catch (e: IOException) {
            Log.w(tag, "upstream write failed: $e")
            closeSession()
        }
    }

    private fun handleFin(seq: Long, payloadLength: Int) = lock.withLock {
        clientSeq = (seq + payloadLength + 1) and 0xFFFFFFFFL
        tun.writeTcpSegment(
            key = key.reversed(),
            seq = localSeq,
            ack = clientSeq,
            flags = 0x10, // ACK
            payload = null,
        )
        // Полузакрытие: продолжаем читать с upstream, но пишем дальше нельзя.
        try {
            socket?.shutdownOutput()
        } catch (_: Throwable) {}
        state = State.FIN_WAIT
    }

    private fun pumpFromUpstream() {
        val s = socket ?: return
        val buf = ByteArray(2048)
        try {
            val input = s.getInputStream()
            while (!closedFlag) {
                val n = input.read(buf)
                if (n <= 0) break
                tun.writeTcpSegment(
                    key = key.reversed(),
                    seq = localSeq,
                    ack = clientSeq,
                    flags = 0x18, // PSH+ACK
                    payload = buf.copyOfRange(0, n),
                )
                localSeq = (localSeq + n) and 0xFFFFFFFFL
            }
            // EOF — отправляем FIN клиенту
            tun.writeTcpSegment(
                key = key.reversed(),
                seq = localSeq,
                ack = clientSeq,
                flags = 0x11, // FIN+ACK
                payload = null,
            )
            localSeq = (localSeq + 1) and 0xFFFFFFFFL
        } catch (_: IOException) {
            sendRst()
        } finally {
            closeSession()
        }
    }

    private fun sendRst() {
        try {
            tun.writeTcpSegment(
                key = key.reversed(),
                seq = localSeq,
                ack = clientSeq,
                flags = 0x14, // RST+ACK
                payload = null,
            )
        } catch (_: Throwable) {}
        closeSession()
    }

    fun closeSession() {
        if (closedFlag) return
        closedFlag = true
        state = State.CLOSED
        try { socket?.close() } catch (_: Throwable) {}
    }
}
