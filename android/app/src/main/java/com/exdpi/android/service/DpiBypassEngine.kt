package com.exdpi.android.service

import com.exdpi.android.data.Strategy
import java.io.OutputStream

/**
 * Логика дробления первого application-payload так, чтобы DPI не смог
 * собрать SNI / Host из одной строки.
 *
 * Реальный TCP-relay живёт в [TcpNat]; здесь — только "как именно резать
 * первый писанный наружу payload" в зависимости от стратегии пользователя.
 *
 * Идея простая: DPI обычно ищет SNI = "youtube.com" / Host = "discord.com"
 * как одну строку в первом payload. Если же мы пишем payload в реальный
 * сокет двумя последовательными write() с TCP_NODELAY, ядро отдаёт два
 * отдельных TCP-сегмента, и DPI не считает их за один.
 *
 * Для стратегии `desync` дробим в три захода (1 байт, до splitAt, остальное),
 * чтобы DPI был сбит и на TLS-, и на HTTP-фингерпринтах.
 */
object DpiBypassEngine {

    /**
     * Записать первый клиентский payload в "наверх" (реальный TCP-сокет).
     * После этого все последующие write идут уже без split — DPI
     * проверяет только начало соединения.
     *
     * @return количество записанных байт.
     */
    fun writeFirstClientPayload(
        out: OutputStream,
        payload: ByteArray,
        offset: Int,
        length: Int,
        strategy: Strategy,
    ): Int {
        if (length <= 0) return 0
        val splitAt = pickSplitOffset(payload, offset, length)
        if (splitAt <= 0 || splitAt >= length) {
            out.write(payload, offset, length)
            out.flush()
            return length
        }
        when (strategy) {
            Strategy.CLIENTHELLO_SPLIT -> {
                out.write(payload, offset, splitAt)
                out.flush()
                out.write(payload, offset + splitAt, length - splitAt)
                out.flush()
            }
            Strategy.TTL_DECOY -> {
                // Без RAW-сокета мы не можем играть TTL per-segment, поэтому
                // имитируем агрессивным split: 2 байта первым сегментом,
                // ровно так же DPI теряет фингерпринт.
                val firstChunk = minOf(2, length)
                out.write(payload, offset, firstChunk)
                out.flush()
                if (length > firstChunk) {
                    out.write(payload, offset + firstChunk, length - firstChunk)
                    out.flush()
                }
            }
            Strategy.DESYNC -> {
                // Тройное дробление: 1 байт, до splitAt, остальное.
                out.write(payload, offset, 1)
                out.flush()
                if (splitAt > 1) {
                    out.write(payload, offset + 1, splitAt - 1)
                    out.flush()
                }
                if (length > splitAt) {
                    out.write(payload, offset + splitAt, length - splitAt)
                    out.flush()
                }
            }
        }
        return length
    }

    private fun pickSplitOffset(payload: ByteArray, offset: Int, length: Int): Int {
        if (length < 6) return length / 2
        if (PacketUtils.looksLikeTlsClientHello(payload, offset, length)) {
            val sniSplit = PacketUtils.sniSplitOffset(payload, offset, length)
            if (sniSplit > offset && sniSplit < offset + length) {
                return sniSplit - offset
            }
        }
        // HTTP / прочее — режем посредине Host: header, если он есть.
        val hostIdx = indexOfHostHeader(payload, offset, length)
        if (hostIdx > 0) {
            return hostIdx + 6
        }
        return length / 2
    }

    private fun indexOfHostHeader(payload: ByteArray, offset: Int, length: Int): Int {
        // "\r\nHost:" — фингерпринт plain HTTP.
        val needle = byteArrayOf(
            0x0D, 0x0A, 'H'.code.toByte(), 'o'.code.toByte(),
            's'.code.toByte(), 't'.code.toByte(), ':'.code.toByte()
        )
        outer@ for (i in 0..(length - needle.size)) {
            for (j in needle.indices) {
                if (payload[offset + i + j] != needle[j]) continue@outer
            }
            return i
        }
        return -1
    }
}
