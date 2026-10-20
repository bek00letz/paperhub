package paperhub.experiment.sleeptest

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import android.os.SystemClock
import android.service.dreams.DreamService
import android.view.Display
import java.util.concurrent.Executors

/**
 * The sleep screen. When the device uses this app as its doze component (the role Onyx's own
 * sleep screen has), Android starts this while the device sleeps. It draws, lets the device
 * suspend, and wakes on an alarm to draw again, recording the battery every time.
 *
 * The doze calls (startDozing, setDozeScreenState) aren't public API, so they're made through
 * reflection, and whether they worked is part of what's recorded.
 */
class SleepDream : DreamService() {
    private lateinit var card: SleepCard
    private lateinit var log: Recorder
    private val main = Handler(Looper.getMainLooper())
    private val io = Executors.newSingleThreadExecutor()
    private var running = false
    private var updates = 0
    private var asleepSince = 0L

    private val alarms by lazy { getSystemService(AlarmManager::class.java) }
    private val power by lazy { getSystemService(PowerManager::class.java) }
    private val tick by lazy {
        PendingIntent.getBroadcast(
            this, 0, Intent(ACTION_TICK).setPackage(packageName),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
    }
    private val receiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) = update("timer")
    }

    override fun onAttachedToWindow() {
        super.onAttachedToWindow()
        isInteractive = false
        isFullscreen = true
        isScreenBright = false
        log = Recorder(this)
        card = SleepCard(this)
        setContentView(card)
        if (Build.VERSION.SDK_INT >= 33) {
            registerReceiver(receiver, IntentFilter(ACTION_TICK), Context.RECEIVER_NOT_EXPORTED)
        } else {
            registerReceiver(receiver, IntentFilter(ACTION_TICK))
        }
    }

    override fun onDreamingStarted() {
        super.onDreamingStarted()
        running = true
        asleepSince = System.currentTimeMillis()
        val doze = hidden<Boolean>("canDoze") == true
        val started = if (doze) callHidden("startDozing") else "not a doze dream"
        log.add("sleep_start", "as=${if (doze) "doze" else "dream"} startDozing=$started")
        update("start")
    }

    override fun onDreamingStopped() {
        running = false
        alarms.cancel(tick)
        log.add("sleep_end", "updates=$updates")
        super.onDreamingStopped()
    }

    override fun onDetachedFromWindow() {
        running = false
        alarms.cancel(tick)
        try { unregisterReceiver(receiver) } catch (_: IllegalArgumentException) {}
        io.shutdownNow()
        super.onDetachedFromWindow()
    }

    private fun update(reason: String) {
        if (!running) return
        val wake = power.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "paperhub:sleep-update")
        wake.acquire(20_000)
        val address = Settings(this).frameUrl
        if (address.isBlank()) {
            show(null, null, reason, "test card", wake)
        } else {
            io.execute {
                val (bmp, error) = FrameFetcher.fetch(address)
                main.post { show(bmp, error, reason, "frame", wake) }
            }
        }
    }

    private fun show(
        bmp: android.graphics.Bitmap?, error: String?, reason: String, detail: String, wake: PowerManager.WakeLock
    ) {
        if (!running) { wake.release(); return }
        val awake = setScreenState(Display.STATE_DOZE)
        if (bmp != null) card.frame = bmp
        card.note = error
        updates += 1
        val clock = java.text.DateFormat.getTimeInstance(java.text.DateFormat.SHORT)
        val b = BatteryReading.read(this)
        card.headline = clock.format(java.util.Date())
        card.lines = listOf(
            if (updates == 1) "Updated once while asleep" else "Updated $updates times while asleep",
            "Asleep since ${clock.format(java.util.Date(asleepSince))}",
            b.describe(),
        )
        card.invalidate()
        // Give the e-ink controller time to finish the refresh before letting the display rest.
        main.postDelayed({
            val rest = setScreenState(Display.STATE_DOZE_SUSPEND)
            log.add("update", "reason=$reason $detail${if (error != null) " error=$error" else ""} doze=$awake suspend=$rest")
            schedule()
            if (wake.isHeld) wake.release()
        }, SETTLE_MS)
    }

    private fun schedule() {
        if (!running) return
        val at = SystemClock.elapsedRealtime() + Settings(this).intervalMinutes * 60_000L
        val exact = Build.VERSION.SDK_INT < 31 || alarms.canScheduleExactAlarms()
        if (exact) alarms.setExactAndAllowWhileIdle(AlarmManager.ELAPSED_REALTIME_WAKEUP, at, tick)
        else alarms.setAndAllowWhileIdle(AlarmManager.ELAPSED_REALTIME_WAKEUP, at, tick)
    }

    private fun setScreenState(state: Int): String = callHidden("setDozeScreenState", state)

    @Suppress("UNCHECKED_CAST")
    private fun <T> hidden(name: String): T? = try {
        DreamService::class.java.getMethod(name).invoke(this) as T
    } catch (e: Exception) { null }

    private fun callHidden(name: String, vararg args: Int): String = try {
        val types = args.map { Int::class.javaPrimitiveType!! }.toTypedArray()
        DreamService::class.java.getMethod(name, *types).invoke(this, *args.toTypedArray())
        "ok"
    } catch (e: Exception) {
        "blocked(${(e.cause ?: e).javaClass.simpleName})"
    }

    companion object {
        private const val ACTION_TICK = "paperhub.experiment.sleeptest.TICK"
        private const val SETTLE_MS = 2500L
    }
}
