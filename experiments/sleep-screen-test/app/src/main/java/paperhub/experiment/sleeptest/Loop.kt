package paperhub.experiment.sleeptest

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Notification
import android.os.SystemClock
import kotlin.concurrent.thread

/**
 * The update loop. A timer wakes only the processor; the frame is checked with its ETag; only a
 * changed frame turns the screen on, and the dashboard then redraws and puts the device straight
 * back to sleep. The Boox's Transparent screensaver keeps whatever was last on screen.
 */
object Loop {
    /** When the loop last asked for the screen to come on for a redraw; 0 when none is waiting. */
    @Volatile var redrawRequestedAt = 0L

    /** The dashboard is what's on screen, or was when the device fell asleep. */
    @Volatile var dashboardShown = false

    /** Set while the dashboard is visible, so a change can redraw it in place. */
    @Volatile var onChange: (() -> Unit)? = null

    private val main = Handler(Looper.getMainLooper())

    fun start(context: Context) {
        Settings(context).updating = true
        Recorder(context).add("loop_start", "every_min=${Settings(context).intervalMinutes}")
        schedule(context)
    }

    fun stop(context: Context) {
        Settings(context).updating = false
        context.getSystemService(AlarmManager::class.java).cancel(tickIntent(context))
        Recorder(context).add("loop_stop")
    }

    fun schedule(context: Context) {
        if (!Settings(context).updating) return
        val alarms = context.getSystemService(AlarmManager::class.java)
        val at = SystemClock.elapsedRealtime() + Settings(context).intervalMinutes * 60_000L
        // Android 12 and later ask the person before an app may set exact alarms; without it, close enough.
        val exact = android.os.Build.VERSION.SDK_INT < 31 || alarms.canScheduleExactAlarms()
        if (exact) alarms.setExactAndAllowWhileIdle(AlarmManager.ELAPSED_REALTIME_WAKEUP, at, tickIntent(context))
        else alarms.setAndAllowWhileIdle(AlarmManager.ELAPSED_REALTIME_WAKEUP, at, tickIntent(context))
    }

    private fun tickIntent(context: Context) = PendingIntent.getBroadcast(
        context, 1, Intent(context, TickReceiver::class.java),
        PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
    )

    /** One check. Runs off the main thread, with the processor held awake by the caller. */
    fun tick(context: Context, reason: String) {
        val settings = Settings(context)
        val log = Recorder(context)
        val power = context.getSystemService(PowerManager::class.java)
        try {
            val address = settings.frameUrl
            val changed: Boolean
            val detail: String
            if (address.isBlank()) {
                changed = true                      // the test card shows the time, so it always changes
                detail = "result=testcard"
            } else {
                val r = FrameFetcher.check(context, address, settings.etag) { settings.etag = it }
                changed = r.outcome == FrameFetcher.Outcome.CHANGED
                val code = when (r.outcome) {
                    FrameFetcher.Outcome.CHANGED -> "200"
                    FrameFetcher.Outcome.UNCHANGED -> "304"
                    FrameFetcher.Outcome.FAILED -> "error"
                }
                detail = "result=$code fetch_ms=${r.ms} bytes=${r.bytes}" + (r.error?.let { " error=$it" } ?: "")
            }
            val screenOn = power.isInteractive
            log.add("check", "reason=$reason $detail screen=${if (screenOn) "on" else "off"} dashboard=$dashboardShown")
            if (changed && dashboardShown) {
                if (screenOn) {
                    main.post { onChange?.invoke() }
                } else {
                    // Every check asks again; a request that never turned into a drawing doesn't
                    // hold up the next one.
                    redrawRequestedAt = System.currentTimeMillis()
                    Redraw.request(context)
                    log.add("redraw_request")
                }
            }
        } catch (e: Exception) {
            log.add("check", "reason=$reason failed=${e.javaClass.simpleName}")
        } finally {
            if (reason == "timer") schedule(context)
        }
    }
}

/** The timer's alarm. Holds the processor awake for the length of one check. */
class TickReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val app = context.applicationContext
        val pending = goAsync()
        val cpu = app.getSystemService(PowerManager::class.java)
            .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "paperhub:check")
            .apply { acquire(30_000) }
        thread(name = "paperhub-check") {
            try {
                Loop.tick(app, "timer")
            } finally {
                if (cpu.isHeld) cpu.release()
                pending.finish()
            }
        }
    }
}

/**
 * Turning the screen on for a redraw, the way alarm clocks do: a notification whose full-screen
 * intent opens the dashboard. On the Boox the screen is never woken (Onyx refuses), but once its
 * own sleep screen has ended, the dashboard comes to the front and its drawing still reaches the
 * e-ink while the device stays asleep. That's what this tests.
 *
 * Every request is a new notification: Android only opens a full-screen intent for a new post,
 * not for an update to one still showing, and Onyx blocks the timeout that would remove it.
 */
object Redraw {
    const val EXTRA = "redraw"
    private const val CHANNEL = "redraw"

    fun request(context: Context) {
        val nm = context.getSystemService(NotificationManager::class.java)
        if (nm.getNotificationChannel(CHANNEL) == null) {
            nm.createNotificationChannel(
                NotificationChannel(CHANNEL, "Redraws", NotificationManager.IMPORTANCE_HIGH).apply {
                    description = "Briefly wakes the screen to draw a new frame."
                    setSound(null, null)
                    enableVibration(false)
                    setShowBadge(false)
                }
            )
        }
        val open = PendingIntent.getActivity(
            context, 2,
            Intent(context, DashboardActivity::class.java)
                .putExtra(EXTRA, true)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        val n = Notification.Builder(context, CHANNEL)
            .setSmallIcon(android.R.drawable.ic_popup_sync)
            .setContentTitle("Updating the dashboard")
            .setCategory(Notification.CATEGORY_ALARM)
            .setWhen(System.currentTimeMillis())
            .setFullScreenIntent(open, true)
            .setContentIntent(open)
            .setAutoCancel(true)
            .build()
        // Only this app's notifications; a new ID each time, so it's always a new post,
        // even if the process was restarted in between.
        nm.cancelAll()
        nm.notify((System.currentTimeMillis() / 1000 % 1_000_000).toInt(), n)
    }

    fun done(context: Context) = context.getSystemService(NotificationManager::class.java).cancelAll()
}
