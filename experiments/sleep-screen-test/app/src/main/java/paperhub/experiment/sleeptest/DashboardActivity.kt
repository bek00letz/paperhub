package paperhub.experiment.sleeptest

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.WindowInsets
import android.view.WindowManager
import android.view.WindowInsetsController
import java.text.DateFormat
import java.util.Date
import kotlin.concurrent.thread

/**
 * The dashboard: full screen, the frame (or the test card), nothing else. It's what the Boox's
 * Transparent screensaver keeps on screen while asleep.
 *
 * Two ways it comes to the front: the loop turned the screen on to redraw (draw, then sleep
 * again at once), or a person woke the device (stay until a minute passes without a touch).
 * Touch and hold opens the settings.
 */
class DashboardActivity : Activity() {
    private lateinit var card: SleepCard
    private lateinit var settings: Settings
    private lateinit var log: Recorder
    private val main = Handler(Looper.getMainLooper())
    private var shownAt = 0L
    private val idleSleep = Runnable { sleep("idle") }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        settings = Settings(this)
        log = Recorder(this)
        card = SleepCard(this).apply {
            isLongClickable = true
            setOnLongClickListener {
                startActivity(Intent(this@DashboardActivity, MainActivity::class.java))
                true
            }
        }
        setContentView(card)
        window.setDecorFitsSystemWindows(false)
        window.insetsController?.apply {
            hide(WindowInsets.Type.systemBars())
            systemBarsBehavior = WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        }
    }

    override fun onResume() {
        super.onResume()
        shownAt = System.currentTimeMillis()
        Loop.dashboardShown = true
        if (settings.stayAwake) window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        else window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        Loop.onChange = { draw() }
        draw()

        val requested = Loop.redrawRequestedAt
        val sinceRequest = System.currentTimeMillis() - requested
        // A redraw request only counts while it's fresh; an old one must never pass for a person.
        val fromLoop = intent.getBooleanExtra(Redraw.EXTRA, false) && requested > 0 && sinceRequest < 60_000
        intent.removeExtra(Redraw.EXTRA)
        val interactive = getSystemService(android.os.PowerManager::class.java).isInteractive

        if (!interactive) {
            // In front while the device is asleep: the drawing may still reach the e-ink.
            // Nothing to put back to sleep, and nobody is here.
            Redraw.done(this)
            Loop.redrawRequestedAt = 0L
            main.postDelayed({
                log.add("drawn_asleep", "since_request_ms=$sinceRequest from_loop=$fromLoop")
            }, SETTLE_MS)
        } else if (fromLoop) {
            // The screen really came on for this. Let the e-ink finish, then sleep again.
            Redraw.done(this)
            main.postDelayed({
                val awake = System.currentTimeMillis() - requested
                Loop.redrawRequestedAt = 0L
                val slept = !settings.stayAwake && Sleeper.sleepNow(this)
                log.add("redraw", "awake_ms=$awake slept=$slept")
                if (!slept) scheduleIdle()
            }, SETTLE_MS)
        } else {
            log.add("wake_user")
            scheduleIdle()
            // Someone is looking: get the latest now rather than at the next timer.
            if (settings.updating && settings.frameUrl.isNotBlank()) {
                val app = applicationContext
                thread(name = "paperhub-wake-check") { Loop.tick(app, "wake") }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
    }

    override fun onPause() {
        main.removeCallbacks(idleSleep)
        Loop.onChange = null
        super.onPause()
    }

    override fun onUserInteraction() {
        super.onUserInteraction()
        scheduleIdle()
    }

    override fun onUserLeaveHint() {
        Loop.dashboardShown = false
        super.onUserLeaveHint()
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        Loop.dashboardShown = false
        @Suppress("DEPRECATION")
        super.onBackPressed()
    }

    private fun scheduleIdle() {
        main.removeCallbacks(idleSleep)
        if (!settings.stayAwake) main.postDelayed(idleSleep, IDLE_MS)
    }

    private fun sleep(reason: String) {
        val awake = System.currentTimeMillis() - shownAt
        if (Sleeper.sleepNow(this)) log.add("sleep", "reason=$reason awake_ms=$awake")
    }

    private fun draw() {
        val clock = DateFormat.getTimeInstance(DateFormat.SHORT)
        val usesFrame = settings.frameUrl.isNotBlank()
        card.frame = if (usesFrame) FrameFetcher.cached(this) else null
        card.headline = clock.format(Date())
        card.lines = listOf(
            BatteryReading.read(this).describe(),
            if (settings.updating) "Updates every ${settings.intervalMinutes} min" else "Timed updates are off",
            if (settings.stayAwake) "Stays awake" else "Sleeps a minute after the last touch",
            "Touch and hold for settings",
        )
        card.note = when {
            settings.updating && Background.restricted(this) -> "The device is freezing this app, so timed updates can't run."
            !settings.stayAwake && !Sleeper.allowed(this) -> "Not allowed to sleep yet, so it stays awake until the screen times out."
            usesFrame && card.frame == null -> "No frame downloaded yet."
            else -> null
        }
        card.invalidate()
    }

    companion object {
        /** Time for the e-ink refresh to finish before the screen is put to sleep. */
        private const val SETTLE_MS = 1500L
        /** How long the dashboard stays awake after the last touch. */
        private const val IDLE_MS = 60_000L
    }
}
