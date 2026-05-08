package com.exdpi.android.data

import android.content.Context
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.core.stringSetPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

/**
 * Хранилище настроек: главный переключатель, стратегия обхода, список выбранных
 * приложений и режим (для всех / только выбранные).
 */
private val Context.dataStore by preferencesDataStore(name = "exdpi_settings")

object SettingsKeys {
    val ENABLED = booleanPreferencesKey("enabled")
    val STRATEGY = stringPreferencesKey("strategy")
    val APPLY_TO_ALL = booleanPreferencesKey("apply_to_all")
    val SELECTED_APPS = stringSetPreferencesKey("selected_apps")
    val PORT_80 = booleanPreferencesKey("port_80")
    val PORT_443 = booleanPreferencesKey("port_443")
}

enum class Strategy(val key: String) {
    CLIENTHELLO_SPLIT("clienthello_split"),
    TTL_DECOY("ttl_decoy"),
    DESYNC("desync");

    companion object {
        fun fromKey(key: String?): Strategy =
            entries.firstOrNull { it.key == key } ?: CLIENTHELLO_SPLIT
    }
}

data class AppSettings(
    val enabled: Boolean = false,
    val strategy: Strategy = Strategy.CLIENTHELLO_SPLIT,
    val applyToAll: Boolean = false,
    val selectedApps: Set<String> = DEFAULT_SELECTED_APPS,
    val port80: Boolean = false,
    val port443: Boolean = true,
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
            strategy = Strategy.fromKey(prefs[SettingsKeys.STRATEGY]),
            applyToAll = prefs[SettingsKeys.APPLY_TO_ALL] ?: false,
            selectedApps = prefs[SettingsKeys.SELECTED_APPS]
                ?: AppSettings.DEFAULT_SELECTED_APPS,
            port80 = prefs[SettingsKeys.PORT_80] ?: false,
            port443 = prefs[SettingsKeys.PORT_443] ?: true,
        )
    }

    suspend fun setEnabled(value: Boolean) = update { it[SettingsKeys.ENABLED] = value }
    suspend fun setStrategy(value: Strategy) = update { it[SettingsKeys.STRATEGY] = value.key }
    suspend fun setApplyToAll(value: Boolean) = update { it[SettingsKeys.APPLY_TO_ALL] = value }
    suspend fun setSelectedApps(packages: Set<String>) =
        update { it[SettingsKeys.SELECTED_APPS] = packages }

    suspend fun setPort80(value: Boolean) = update { it[SettingsKeys.PORT_80] = value }
    suspend fun setPort443(value: Boolean) = update { it[SettingsKeys.PORT_443] = value }

    private suspend fun update(block: (androidx.datastore.preferences.core.MutablePreferences) -> Unit) {
        context.dataStore.edit { block(it) }
    }
}
