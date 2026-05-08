package com.exdpi.android.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

val Bg = Color(0xFF0E1116)
val BgCard = Color(0xFF161B22)
val BgCardHi = Color(0xFF1F2630)
val Border = Color(0xFF222831)
val TextPrimary = Color(0xFFE6EDF3)
val TextSecondary = Color(0xFF8B949E)
val TextMuted = Color(0xFF6E7681)
val Accent = Color(0xFF22C55E)
val AccentDim = Color(0xFF16A34A)
val AccentDark = Color(0xFF14532D)
val Danger = Color(0xFFEF4444)
val TrackOff = Color(0xFF30363D)
val KnobOff = Color(0xFF8B949E)

private val DarkColors = darkColorScheme(
    primary = Accent,
    onPrimary = Color.Black,
    secondary = AccentDim,
    onSecondary = Color.Black,
    background = Bg,
    onBackground = TextPrimary,
    surface = BgCard,
    onSurface = TextPrimary,
    surfaceVariant = BgCardHi,
    onSurfaceVariant = TextSecondary,
    error = Danger,
    outline = Border,
)

@Composable
fun ExDpiTheme(content: @Composable () -> Unit) {
    @Suppress("UNUSED_VARIABLE")
    val isDark = isSystemInDarkTheme()
    MaterialTheme(colorScheme = DarkColors, content = content)
}
