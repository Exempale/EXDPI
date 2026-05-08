package com.exdpi.android.ui

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.exdpi.android.R
import com.exdpi.android.service.ExDpiVpnService

/**
 * Главный экран — намеренно минималистичный: имя приложения, большой переключатель,
 * статус и кнопка «настройки». Всё остальное (выбор приложений, режим «для всех»)
 * вынесено в [SettingsActivity], как в десктопной версии EXDPI.
 */
@Composable
fun MainScreen(
    state: UiState,
    onMasterToggle: (Boolean) -> Unit,
    onOpenSettings: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Bg)
            .padding(horizontal = 20.dp, vertical = 28.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Top,
    ) {
        // Header row: имя слева, шестерёнка настроек справа.
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Spacer(Modifier.weight(1f))
            Text(
                text = stringResource(R.string.app_name),
                color = TextPrimary,
                fontWeight = FontWeight.Bold,
                fontSize = 28.sp,
            )
            Spacer(Modifier.weight(1f))
            SettingsButton(onClick = onOpenSettings)
        }

        Spacer(Modifier.height(72.dp))

        BigToggle(
            checked = state.vpnState == ExDpiVpnService.Companion.State.RUNNING,
            starting = state.vpnState == ExDpiVpnService.Companion.State.STARTING,
            onChange = onMasterToggle,
        )

        Spacer(Modifier.height(28.dp))

        StatusLine(state = state)
    }
}

@Composable
private fun SettingsButton(onClick: () -> Unit) {
    Box(
        modifier = Modifier
            .size(40.dp)
            .clip(CircleShape)
            .background(BgCardHi)
            .clickable(onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        // Текстовая «шестерёнка» — без иконного шрифта, чтобы не тянуть лишнее.
        Text("⚙", color = TextPrimary, fontSize = 18.sp)
    }
}

@Composable
private fun BigToggle(
    checked: Boolean,
    starting: Boolean,
    onChange: (Boolean) -> Unit,
) {
    val trackWidth = 200.dp
    val trackHeight = 100.dp
    val knobSize = 80.dp

    val targetTrack by animateColorAsState(
        targetValue = if (checked) Accent else TrackOff,
        label = "track",
    )
    val targetKnob by animateColorAsState(
        targetValue = if (checked) Color.White else KnobOff,
        label = "knob",
    )
    val xFraction by animateFloatAsState(
        targetValue = if (checked) 1f else 0f,
        label = "knobX",
    )

    Box(
        modifier = Modifier
            .width(trackWidth)
            .height(trackHeight)
            .clip(RoundedCornerShape(50))
            .background(targetTrack)
            .clickable { onChange(!checked) }
            .padding(10.dp),
        contentAlignment = Alignment.CenterStart,
    ) {
        val travel = trackWidth - knobSize - 20.dp
        Box(
            modifier = Modifier
                .offset(x = travel * xFraction)
                .size(knobSize)
                .clip(CircleShape)
                .background(targetKnob),
            contentAlignment = Alignment.Center,
        ) {
            if (starting) {
                Text("…", color = Color.Black, fontWeight = FontWeight.Bold)
            }
        }
    }
}

@Composable
private fun StatusLine(state: UiState) {
    val running = state.vpnState == ExDpiVpnService.Companion.State.RUNNING
    val starting = state.vpnState == ExDpiVpnService.Companion.State.STARTING
    val statusText = when {
        starting -> stringResource(R.string.status_starting)
        running -> stringResource(R.string.status_on)
        else -> stringResource(R.string.status_off)
    }
    val dotColor by animateColorAsState(
        targetValue = if (running) Accent else TextMuted,
        label = "dot",
    )
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(
            modifier = Modifier
                .size(10.dp)
                .clip(CircleShape)
                .background(dotColor),
        )
        Spacer(Modifier.width(8.dp))
        Text(
            statusText,
            color = TextPrimary,
            fontWeight = FontWeight.Bold,
            fontSize = 16.sp,
        )
    }
}
