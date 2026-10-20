package paperhub.experiment.sleeptest

import android.app.admin.DeviceAdminReceiver
import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent

/** The device admin role, used for exactly one thing: putting the device to sleep (lockNow). */
class SleepAdmin : DeviceAdminReceiver()

object Sleeper {
    private fun admin(context: Context) = ComponentName(context, SleepAdmin::class.java)

    fun allowed(context: Context): Boolean =
        context.getSystemService(DevicePolicyManager::class.java).isAdminActive(admin(context))

    /** Android's own screen asking the person to allow it; nothing is granted without them. */
    fun requestIntent(context: Context): Intent =
        Intent(DevicePolicyManager.ACTION_ADD_DEVICE_ADMIN)
            .putExtra(DevicePolicyManager.EXTRA_DEVICE_ADMIN, admin(context))
            .putExtra(
                DevicePolicyManager.EXTRA_ADD_EXPLANATION,
                "Lets the sleep test put the screen to sleep right after it redraws, so the dashboard stays on screen without staying awake."
            )

    /** Sleeps now. Returns false if the app isn't allowed to. */
    fun sleepNow(context: Context): Boolean {
        if (!allowed(context)) return false
        context.getSystemService(DevicePolicyManager::class.java).lockNow()
        return true
    }
}

/**
 * What can stop the timer from running while the device sleeps. Android's battery optimisation
 * delays it; the vendor's own app freezing (Boox's auto-freeze) blocks it outright.
 */
object Background {
    fun restricted(context: Context): Boolean =
        context.getSystemService(android.app.ActivityManager::class.java).isBackgroundRestricted

    fun optimised(context: Context): Boolean =
        !context.getSystemService(android.os.PowerManager::class.java).isIgnoringBatteryOptimizations(context.packageName)

    fun appSettingsIntent(context: Context): Intent =
        Intent(android.provider.Settings.ACTION_APPLICATION_DETAILS_SETTINGS, android.net.Uri.parse("package:${context.packageName}"))

    @android.annotation.SuppressLint("BatteryLife")
    fun exemptIntent(context: Context): Intent =
        Intent(android.provider.Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, android.net.Uri.parse("package:${context.packageName}"))
}
