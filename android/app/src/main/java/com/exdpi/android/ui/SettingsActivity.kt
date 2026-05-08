package com.exdpi.android.ui

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
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

/**
 * Экран настроек: режим «для всех» + кнопка выбора приложений + информация о
 * стратегии (без выбора — она автоматическая, объяснение для пользователя).
 */
class SettingsActivity : ComponentActivity() {
    private val vm: MainViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            ExDpiTheme {
                val state by vm.state.collectAsState()
                SettingsScreen(
                    state = state,
                    onClose = { finish() },
                    onApplyToAllChange = vm::setApplyToAll,
                    onPickApps = {
                        startActivity(Intent(this, AppPickerActivity::class.java))
                    },
                )
            }
        }
    }
}

@Composable
private fun SettingsScreen(
    state: UiState,
    onClose: () -> Unit,
    onApplyToAllChange: (Boolean) -> Unit,
    onPickApps: () -> Unit,
) {
    val scroll = rememberScrollState()
    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Bg)
            .statusBarsPadding(),
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 14.dp, vertical = 12.dp),
        ) {
            Box(
                modifier = Modifier
                    .clip(RoundedCornerShape(10.dp))
                    .clickable { onClose() }
                    .padding(horizontal = 10.dp, vertical = 8.dp),
            ) {
                Text("← ${stringResource(R.string.back)}", color = TextPrimary, fontSize = 14.sp)
            }
            Spacer(Modifier.width(8.dp))
            Text(
                stringResource(R.string.settings),
                color = TextPrimary,
                fontWeight = FontWeight.Bold,
                fontSize = 18.sp,
            )
        }

        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(scroll)
                .padding(horizontal = 16.dp, vertical = 8.dp),
        ) {
            // Apps section
            SectionCard {
                SectionHeader(stringResource(R.string.apps_selection))
                Spacer(Modifier.height(8.dp))
                Text(
                    text = stringResource(R.string.apps_selection_subtitle),
                    color = TextSecondary,
                    fontSize = 13.sp,
                    modifier = Modifier.fillMaxWidth(),
                )
                Spacer(Modifier.height(14.dp))

                ToggleRow(
                    title = stringResource(R.string.apply_to_all),
                    checked = state.settings.applyToAll,
                    onChange = onApplyToAllChange,
                )

                if (!state.settings.applyToAll) {
                    Spacer(Modifier.height(8.dp))
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
                                    stringResource(R.string.apply_to_selected),
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

            // Strategy info section — без выбора, просто объяснение.
            SectionCard {
                SectionHeader(stringResource(R.string.bypass_section))
                Spacer(Modifier.height(8.dp))
                Text(
                    stringResource(R.string.strategy_auto_title),
                    color = TextPrimary,
                    fontSize = 14.sp,
                    fontWeight = FontWeight.SemiBold,
                )
                Spacer(Modifier.height(4.dp))
                Text(
                    stringResource(R.string.strategy_auto_subtitle),
                    color = TextSecondary,
                    fontSize = 12.sp,
                )
            }

            Spacer(Modifier.height(28.dp))

            Text(
                stringResource(R.string.footer_author),
                color = TextMuted,
                fontSize = 12.sp,
                modifier = Modifier.fillMaxWidth(),
            )
            Text(
                stringResource(R.string.footer_version),
                color = TextMuted,
                fontSize = 11.sp,
                modifier = Modifier.fillMaxWidth(),
            )
            Spacer(Modifier.height(20.dp))
        }
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
