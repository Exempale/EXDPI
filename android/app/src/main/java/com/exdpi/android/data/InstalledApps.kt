package com.exdpi.android.data

import android.content.Context
import android.content.pm.ApplicationInfo
import android.content.pm.PackageManager
import android.graphics.drawable.Drawable
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

data class InstalledApp(
    val packageName: String,
    val label: String,
    val icon: Drawable?,
    val isSystem: Boolean,
)

/**
 * Сканер установленных приложений (только те, у которых есть LAUNCHER intent —
 * иначе список превращается в кашу из 700 системных компонентов).
 */
object InstalledApps {

    suspend fun list(context: Context, includeSystem: Boolean = false): List<InstalledApp> =
        withContext(Dispatchers.IO) {
            val pm = context.packageManager
            val launchable = pm
                .getInstalledApplications(PackageManager.GET_META_DATA)
                .asSequence()
                .filter { info ->
                    if (info.packageName == context.packageName) return@filter false
                    val isSystem = info.flags and ApplicationInfo.FLAG_SYSTEM != 0
                    val isUpdatedSystem =
                        info.flags and ApplicationInfo.FLAG_UPDATED_SYSTEM_APP != 0
                    if (isSystem && !isUpdatedSystem && !includeSystem) {
                        return@filter false
                    }
                    pm.getLaunchIntentForPackage(info.packageName) != null
                }
                .map { info ->
                    InstalledApp(
                        packageName = info.packageName,
                        label = pm.getApplicationLabel(info).toString(),
                        icon = runCatching { pm.getApplicationIcon(info) }.getOrNull(),
                        isSystem = info.flags and ApplicationInfo.FLAG_SYSTEM != 0,
                    )
                }
                .sortedBy { it.label.lowercase() }
                .toList()
            launchable
        }
}
