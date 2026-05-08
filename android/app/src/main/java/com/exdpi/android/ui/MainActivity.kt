package com.exdpi.android.ui

import android.app.Activity
import android.content.Intent
import android.net.VpnService
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.core.view.WindowCompat
import com.exdpi.android.service.ExDpiVpnService

/**
 * Главная Activity. Держит ViewModel и обёртку для VPN consent dialog.
 */
class MainActivity : ComponentActivity() {

    private val vm: MainViewModel by viewModels()

    private val vpnConsent = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        vm.setNeedsConsent(false)
        if (result.resultCode == Activity.RESULT_OK) {
            vm.setEnabled(true)
            ExDpiVpnService.start(this)
        }
    }

    private val notifPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { /* ignore — уведомление не критично */ }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WindowCompat.setDecorFitsSystemWindows(window, true)

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            notifPermission.launch(android.Manifest.permission.POST_NOTIFICATIONS)
        }

        setContent {
            ExDpiTheme {
                val state by vm.state.collectAsState()
                MainScreen(
                    state = state,
                    onMasterToggle = { wantOn ->
                        if (wantOn) requestVpnAndStart() else stopVpn()
                    },
                    onStrategyChange = vm::setStrategy,
                    onApplyToAllChange = vm::setApplyToAll,
                    onSelectedAppsChange = vm::setSelectedApps,
                    onPort80Change = vm::setPort80,
                    onPort443Change = vm::setPort443,
                    onPickApps = {
                        startActivity(Intent(this, AppPickerActivity::class.java))
                    },
                )
            }
        }
    }

    private fun requestVpnAndStart() {
        val intent = VpnService.prepare(this)
        if (intent != null) {
            vm.setNeedsConsent(true)
            vpnConsent.launch(intent)
        } else {
            vm.setEnabled(true)
            ExDpiVpnService.start(this)
        }
    }

    private fun stopVpn() {
        vm.setEnabled(false)
        ExDpiVpnService.stop(this)
    }
}
