package com.exdpi.android.ui

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.border
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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.exdpi.android.R
import com.exdpi.android.data.Strategy
import com.exdpi.android.service.ExDpiVpnService

@Composable
fun MainScreen(
    state: UiState,
    onMasterToggle: (Boolean) -> Unit,
    onStrategyChange: (Strategy) -> Unit,
    onApplyToAllChange: (Boolean) -> Unit,
    @Suppress("UNUSED_PARAMETER") onSelectedAppsChange: (Set<String>) -> Unit,
    onPort80Change: (Boolean) -> Unit,
    onPort443Change: (Boolean) -> Unit,
    onPickApps: () -> Unit,
) {
    val scroll = rememberScrollState()
    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Bg)
            .verticalScroll(scroll)
            .padding(horizontal = 20.dp, vertical = 28.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        // Header
        Text(
            text = stringResForLocale(R.string.app_name),
            color = TextPrimary,
            fontWeight = FontWeight.Bold,
            fontSize = 26.sp,
        )
        Spacer(Modifier.height(4.dp))
        Text(
            text = "tg + youtube + discord · обход DPI",
            color = TextSecondary,
            fontSize = 13.sp,
        )

        Spacer(Modifier.height(36.dp))

        BigToggle(
            checked = state.vpnState == ExDpiVpnService.Companion.State.RUNNING,
            starting = state.vpnState == ExDpiVpnService.Companion.State.STARTING,
            onChange = onMasterToggle,
        )

        Spacer(Modifier.height(20.dp))

        StatusLine(state = state)

        Spacer(Modifier.height(36.dp))

        // Apps section
        SectionCard {
            SectionHeader(stringResForLocale(R.string.apps_selection))
            Spacer(Modifier.height(8.dp))
            Text(
                text = stringResForLocale(R.string.apps_selection_subtitle),
                color = TextSecondary,
                fontSize = 13.sp,
                modifier = Modifier.fillMaxWidth(),
            )
            Spacer(Modifier.height(14.dp))

            ToggleRow(
                title = stringResForLocale(R.string.apply_to_all),
                checked = state.settings.applyToAll,
                onChange = onApplyToAllChange,
            )

            Spacer(Modifier.height(8.dp))

            if (!state.settings.applyToAll) {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(12.dp))
                        .background(BgCardHi)
                        .clickable { onPickApps() }
                        .padding(horizontal = 14.dp, vertical = 14.dp),
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text(
                                stringResForLocale(R.string.apply_to_selected),
                                color = TextPrimary,
                                fontWeight = FontWeight.SemiBold,
                                fontSize = 15.sp,
                            )
                            Spacer(Modifier.height(2.dp))
                            Text(
                                "${state.settings.selectedApps.size} приложений выбрано",
                                color = TextSecondary,
                                fontSize = 13.sp,
                            )
                        }
                        Text(
                            "выбрать ›",
                            color = Accent,
                            fontWeight = FontWeight.SemiBold,
                            fontSize = 14.sp,
                        )
                    }
                }
            }
        }

        Spacer(Modifier.height(16.dp))

        // Strategy section
        SectionCard {
            SectionHeader(stringResForLocale(R.string.bypass_section))
            Spacer(Modifier.height(8.dp))
            Text(
                text = stringResForLocale(R.string.strategy_label),
                color = TextSecondary,
                fontSize = 13.sp,
            )
            Spacer(Modifier.height(10.dp))
            StrategyOption(
                title = stringResForLocale(R.string.strategy_clienthello_split),
                selected = state.settings.strategy == Strategy.CLIENTHELLO_SPLIT,
                onClick = { onStrategyChange(Strategy.CLIENTHELLO_SPLIT) },
            )
            StrategyOption(
                title = stringResForLocale(R.string.strategy_ttl_decoy),
                selected = state.settings.strategy == Strategy.TTL_DECOY,
                onClick = { onStrategyChange(Strategy.TTL_DECOY) },
            )
            StrategyOption(
                title = stringResForLocale(R.string.strategy_desync),
                selected = state.settings.strategy == Strategy.DESYNC,
                onClick = { onStrategyChange(Strategy.DESYNC) },
            )

            Spacer(Modifier.height(18.dp))

            Text(
                text = stringResForLocale(R.string.ports_label),
                color = TextSecondary,
                fontSize = 13.sp,
            )
            Spacer(Modifier.height(2.dp))
            Text(
                text = stringResForLocale(R.string.ports_hint),
                color = TextMuted,
                fontSize = 11.sp,
            )
            Spacer(Modifier.height(10.dp))

            ToggleRow(
                title = stringResForLocale(R.string.port_443),
                checked = state.settings.port443,
                onChange = onPort443Change,
            )
            Spacer(Modifier.height(8.dp))
            ToggleRow(
                title = stringResForLocale(R.string.port_80),
                checked = state.settings.port80,
                onChange = onPort80Change,
            )
        }

        Spacer(Modifier.height(28.dp))

        Text(
            stringResForLocale(R.string.footer_author),
            color = TextMuted,
            fontSize = 12.sp,
        )
        Text(
            stringResForLocale(R.string.footer_version),
            color = TextMuted,
            fontSize = 11.sp,
        )
        Spacer(Modifier.height(20.dp))
    }
}

@Composable
private fun BigToggle(
    checked: Boolean,
    starting: Boolean,
    onChange: (Boolean) -> Unit,
) {
    val trackWidth = 168.dp
    val trackHeight = 80.dp
    val knobSize = 64.dp

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
            .padding(8.dp),
        contentAlignment = Alignment.CenterStart,
    ) {
        val travel = trackWidth - knobSize - 16.dp
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
        starting -> stringResForLocale(R.string.status_starting)
        running -> stringResForLocale(R.string.status_on)
        else -> stringResForLocale(R.string.status_off)
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

@Composable
private fun SectionCard(content: @Composable () -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(16.dp))
            .background(BgCard)
            .border(1.dp, Border, RoundedCornerShape(16.dp))
            .padding(16.dp),
    ) {
        content()
    }
}

@Composable
private fun SectionHeader(text: String) {
    Text(
        text = text.uppercase(),
        color = TextSecondary,
        fontWeight = FontWeight.Bold,
        fontSize = 11.sp,
    )
}

@Composable
private fun ToggleRow(
    title: String,
    checked: Boolean,
    onChange: (Boolean) -> Unit,
) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(10.dp))
            .clickable { onChange(!checked) }
            .padding(vertical = 6.dp),
    ) {
        Text(
            title,
            color = TextPrimary,
            fontSize = 14.sp,
            modifier = Modifier.weight(1f),
        )
        Switch(
            checked = checked,
            onCheckedChange = onChange,
            colors = SwitchDefaults.colors(
                checkedTrackColor = Accent,
                checkedThumbColor = Color.White,
                uncheckedTrackColor = TrackOff,
                uncheckedThumbColor = KnobOff,
                uncheckedBorderColor = TrackOff,
            ),
        )
    }
}

@Composable
private fun StrategyOption(
    title: String,
    selected: Boolean,
    onClick: () -> Unit,
) {
    val bg by animateColorAsState(
        targetValue = if (selected) AccentDark else BgCardHi,
        label = "stratBg",
    )
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp)
            .clip(RoundedCornerShape(10.dp))
            .background(bg)
            .border(
                width = if (selected) 1.dp else 0.dp,
                color = if (selected) Accent else Color.Transparent,
                shape = RoundedCornerShape(10.dp),
            )
            .clickable(onClick = onClick)
            .padding(horizontal = 14.dp, vertical = 12.dp),
    ) {
        Box(
            modifier = Modifier
                .size(14.dp)
                .clip(CircleShape)
                .background(if (selected) Accent else TrackOff),
        )
        Spacer(Modifier.width(12.dp))
        Text(
            title,
            color = TextPrimary,
            fontSize = 14.sp,
            fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal,
            modifier = Modifier.weight(1f),
        )
    }
}

@Composable
private fun stringResForLocale(id: Int): String =
    androidx.compose.ui.res.stringResource(id = id)
