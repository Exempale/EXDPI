package com.exdpi.android.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.exdpi.android.data.AppSettings
import com.exdpi.android.data.SettingsRepository
import com.exdpi.android.service.ExDpiVpnService
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.launch

data class UiState(
    val settings: AppSettings = AppSettings(),
    val vpnState: ExDpiVpnService.Companion.State = ExDpiVpnService.Companion.State.IDLE,
    val needsConsent: Boolean = false,
)

class MainViewModel(app: Application) : AndroidViewModel(app) {
    private val repo = SettingsRepository(app)
    private val _needsConsent = MutableStateFlow(false)

    val state: StateFlow<UiState> = combine(
        repo.settings,
        ExDpiVpnService.state,
        _needsConsent,
    ) { settings, vpn, consent ->
        UiState(settings = settings, vpnState = vpn, needsConsent = consent)
    }.stateIn(viewModelScope, SharingStarted.Eagerly, UiState())

    fun setEnabled(value: Boolean) {
        viewModelScope.launch { repo.setEnabled(value) }
    }

    fun setApplyToAll(v: Boolean) {
        viewModelScope.launch { repo.setApplyToAll(v) }
    }

    fun setSelectedApps(apps: Set<String>) {
        viewModelScope.launch { repo.setSelectedApps(apps) }
    }

    fun setNeedsConsent(v: Boolean) {
        _needsConsent.value = v
    }
}
