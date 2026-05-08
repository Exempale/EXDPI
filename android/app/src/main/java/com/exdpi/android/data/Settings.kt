package com.exdpi.android.data

import android.content.Context
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringSetPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

/**
 * Хранилище настроек.
 *
 * После переезда на byedpi+tun2socks стратегию пользователь не выбирает —
 * мы автоматически используем профиль
 * [com.exdpi.android.core.ByeDpiNative.DEFAULT_DESYNC_OPTS]. Из настроек
 * остались: главный переключатель, режим (для всех / только выбранные)
 * и сам список приложений.
 */
private val Context.dataStore by preferencesDataStore(name = "exdpi_settings")

object SettingsKeys {
    val ENABLED = booleanPreferencesKey("enabled")
    val APPLY_TO_ALL = booleanPreferencesKey("apply_to_all")
    val SELECTED_APPS = stringSetPreferencesKey("selected_apps")
}

data class AppSettings(
    val enabled: Boolean = false,
    val applyToAll: Boolean = false,
    val selectedApps: Set<String> = DEFAULT_SELECTED_APPS,
) {
    companion object {
        /** Полезные дефолты — Telegram, YouTube, Discord и пр. */
        val DEFAULT_SELECTED_APPS: Set<String> = setOf(
            "org.telegram.messenger",
            "org.thunderdog.challegram",
            "com.google.android.youtube",
            "com.google.android.apps.youtube.music",
            "com.discord",
        )
    }
}

class SettingsRepository(private val context: Context) {

    val settings: Flow<AppSettings> = context.dataStore.data.map { prefs ->
        AppSettings(
            enabled = prefs[SettingsKeys.ENABLED] ?: false,
            applyToAll = prefs[SettingsKeys.APPLY_TO_ALL] ?: false,
            selectedApps = prefs[SettingsKeys.SELECTED_APPS]
                ?: AppSettings.DEFAULT_SELECTED_APPS,
        )
    }

    suspend fun setEnabled(value: Boolean) = update { it[SettingsKeys.ENABLED] = value }
    suspend fun setApplyToAll(value: Boolean) = update { it[SettingsKeys.APPLY_TO_ALL] = value }
    suspend fun setSelectedApps(packages: Set<String>) =
        update { it[SettingsKeys.SELECTED_APPS] = packages }

    private suspend fun update(block: (androidx.datastore.preferences.core.MutablePreferences) -> Unit) {
        context.dataStore.edit { block(it) }
    }
}
