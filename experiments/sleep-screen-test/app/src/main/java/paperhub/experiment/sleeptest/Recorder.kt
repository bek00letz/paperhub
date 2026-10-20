package paperhub.experiment.sleeptest

import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.BatteryManager
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** One look at the battery. The charge counter is in microamp-hours, straight from the fuel gauge. */
data class BatteryReading(val levelPct: Int, val chargeUah: Int, val plugged: Boolean) {
    val chargeMah: Int get() = chargeUah / 1000

    fun describe() = "Battery $levelPct % · ${"%,d".format(chargeMah)} mAh" + if (plugged) " · charging" else ""

    companion object {
        fun read(context: Context): BatteryReading {
            val bm = context.getSystemService(BatteryManager::class.java)
            val level = bm.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY)
            val charge = bm.getIntProperty(BatteryManager.BATTERY_PROPERTY_CHARGE_COUNTER)
            val sticky = context.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
            val plugged = (sticky?.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0) ?: 0) != 0
            return BatteryReading(level, charge, plugged)
        }
    }
}

/** The settings the app, the dashboard and the update loop all read. */
class Settings(context: Context) {
    private val prefs = context.getSharedPreferences("settings", Context.MODE_PRIVATE)

    var intervalMinutes: Int
        get() = prefs.getInt("interval_min", 15)
        set(v) = prefs.edit().putInt("interval_min", v).apply()

    var frameUrl: String
        get() = prefs.getString("frame_url", "") ?: ""
        set(v) {
            if (v.trim() != frameUrl) prefs.edit().putString("frame_url", v.trim()).remove("etag").apply()
        }

    /** Whether the timed updates are switched on. */
    var updating: Boolean
        get() = prefs.getBoolean("updating", false)
        set(v) = prefs.edit().putBoolean("updating", v).apply()

    /** Keep the screen on instead of sleeping, so touch always works (the third test). */
    var stayAwake: Boolean
        get() = prefs.getBoolean("stay_awake", false)
        set(v) = prefs.edit().putBoolean("stay_awake", v).apply()

    /** The frame's ETag, so an unchanged frame costs a short "not modified" answer and no redraw. */
    var etag: String?
        get() = prefs.getString("etag", null)
        set(v) = prefs.edit().putString("etag", v).apply()

    /** What the sleep screen component was before the first experiment changed it. */
    var previousDozeComponent: String?
        get() = prefs.getString("previous_doze", null)
        set(v) = prefs.edit().putString("previous_doze", v).apply()
}

/**
 * Every event, with the battery at that moment, appended to a CSV file the Mac can read:
 *   adb shell cat /sdcard/Android/data/paperhub.experiment.sleeptest/files/sleep-log.csv
 */
class Recorder(private val context: Context) {
    val file: File = File(context.getExternalFilesDir(null), "sleep-log.csv")
    private val stamp = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.ROOT)

    @Synchronized
    fun add(event: String, detail: String = "") {
        val b = BatteryReading.read(context)
        val isNew = !file.exists()
        file.appendText(buildString {
            if (isNew) append("time,event,level_pct,charge_uah,plugged,detail\n")
            append(stamp.format(Date())).append(',')
            append(event).append(',')
            append(b.levelPct).append(',')
            append(b.chargeUah).append(',')
            append(if (b.plugged) 1 else 0).append(',')
            append(detail.replace(',', ';').replace('\n', ' '))
            append('\n')
        })
    }

    fun lines(): List<String> = if (file.exists()) file.readLines().drop(1) else emptyList()

    /** Keeps the old log next to the new one, so starting over is never a loss. */
    fun startOver() {
        if (file.exists()) file.renameTo(File(file.parentFile, "sleep-log.previous.csv"))
    }

    /**
     * The latest stretch on battery: how long, how much charge it used, and what the loop did.
     * The device being unplugged is what makes the figure mean anything.
     */
    fun summary(): String {
        val rows = lines().map { it.split(',', limit = 6) }.filter { it.size == 6 }
        if (rows.isEmpty()) return "Nothing recorded yet."
        val lastPlugged = rows.indexOfLast { it[4] == "1" }
        val run = rows.drop(lastPlugged + 1)
        if (run.size < 2) {
            return if (rows.last()[4] == "1") "It's plugged in. Unplug it to measure the battery."
            else "Recording on battery. Check back in an hour or more."
        }
        val hours = (parse(run.last()[0]) - parse(run.first()[0])) / 3_600_000.0
        val usedMah = (run.first()[3].toLong() - run.last()[3].toLong()) / 1000.0
        val checks = run.count { it[1] == "check" }
        val unchanged = run.count { it[1] == "check" && it[5].contains("result=304") }
        val redraws = run.filter { it[1] == "redraw" }
        val awake = redraws.mapNotNull { Regex("awake_ms=(\\d+)").find(it[5])?.groupValues?.get(1)?.toLong() }
        val userWakes = run.count { it[1] == "wake_user" }
        if (hours < 0.25) return "$checks checks so far on battery. Leave it for at least an hour."
        return buildString {
            append(String.format(Locale.getDefault(), "On battery for %.1f h: used %.0f mAh, about %.1f mAh per hour.", hours, usedMah, usedMah / hours))
            append(String.format(Locale.getDefault(), "\n%d checks, %d unchanged. %d redraws", checks, unchanged, redraws.size))
            if (awake.isNotEmpty()) append(String.format(Locale.getDefault(), ", %.1f s awake each", awake.average() / 1000))
            append(". Woken by hand $userWakes ${if (userWakes == 1) "time" else "times"}.")
        }
    }

    private fun parse(s: String): Long = try { stamp.parse(s)?.time ?: 0L } catch (e: Exception) { 0L }
}
