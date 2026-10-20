package paperhub.experiment.sleeptest

import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.text.Editable
import android.text.InputType
import android.text.TextWatcher
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView

/**
 * Setup and results on one screen: let it sleep, start the timed updates, an optional frame
 * address, and what the battery did. Plain black on white, large type, no animation: it's
 * read on e-ink.
 */
class MainActivity : Activity() {
    private lateinit var settings: Settings
    private lateinit var log: Recorder
    private lateinit var root: LinearLayout

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        settings = Settings(this)
        log = Recorder(this)
        root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            val p = dp(24)
            setPadding(p, p, p, p)
        }
        setContentView(ScrollView(this).apply { setBackgroundColor(Color.WHITE); addView(root) })
    }

    override fun onResume() {
        super.onResume()
        build()
    }

    private fun build() {
        root.removeAllViews()
        text("Sleep test", 28f, bold = true)
        text(
            "Keeps a dashboard on screen while the device sleeps. It wakes only to check for a new frame, " +
                "redraws when there is one, and records the battery every time.", 16f, gap = 8
        )
        button("Open the dashboard", primary = true) {
            startActivity(Intent(this, DashboardActivity::class.java))
        }
        text("The Boox's Transparent screensaver keeps it visible while asleep. Touch and hold the dashboard to come back here.", 14f, gap = 8, grey = true)

        // Sleep permission
        section("Going back to sleep")
        if (Sleeper.allowed(this)) {
            text("Allowed. It sleeps right after each redraw, and a minute after the last touch.", 18f)
        } else {
            text("Not allowed yet. Without it the screen stays on until the device's own timeout.", 18f)
            button("Allow it to sleep", primary = false) { startActivity(Sleeper.requestIntent(this)) }
        }

        // Awake or asleep
        section("While nobody's touching it")
        val modes = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        for ((label, awake) in listOf("Sleep" to false, "Stay awake" to true)) {
            modes.addView(
                choice(label, settings.stayAwake == awake) {
                    if (settings.stayAwake != awake) {
                        settings.stayAwake = awake
                        log.add("mode", if (awake) "stay_awake" else "sleep")
                    }
                    build()
                },
                LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f).apply { marginEnd = dp(8) }
            )
        }
        root.addView(modes)
        text(
            if (settings.stayAwake) "The screen stays on, so touch always works, and changes are drawn in place. Turn the front light off for a fair measurement."
            else "It sleeps a minute after the last touch; the power button brings it back.", 14f, gap = 8, grey = true
        )

        // Timed updates
        section("Timed updates")
        if (settings.updating) {
            text("On, every ${settings.intervalMinutes} min.", 18f)
            button("Stop timed updates", primary = false) { Loop.stop(this); build() }
        } else {
            text("Off.", 18f)
            button("Start timed updates", primary = true) { Loop.start(this); build() }
        }
        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(0, dp(12), 0, 0) }
        for (m in listOf(5, 15, 30)) {
            row.addView(
                choice("$m min", settings.intervalMinutes == m) {
                    settings.intervalMinutes = m
                    if (settings.updating) Loop.schedule(this)
                    build()
                },
                LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f).apply { marginEnd = dp(8) }
            )
        }
        root.addView(row)
        if (Background.restricted(this)) {
            text(
                "Blocked: the device is freezing this app, so the timer can't run while it sleeps. " +
                    "On a Boox, turn off auto-freeze for Sleep test.", 16f, gap = 12
            )
            button("Open the app's settings", primary = false) { startActivity(Background.appSettingsIntent(this)) }
        }
        if (Background.optimised(this)) {
            text("Android's battery saving may also hold the timer back while asleep.", 16f, gap = 12)
            button("Let it run while asleep", primary = false) { startActivity(Background.exemptIntent(this)) }
        }

        // Frame address
        section("Frame address")
        root.addView(EditText(this).apply {
            setText(settings.frameUrl)
            hint = "http://homeassistant.local:8099/frame.png"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
            setSingleLine()
            textSize = 16f
            minHeight = dp(48)
            addTextChangedListener(object : TextWatcher {
                override fun afterTextChanged(s: Editable?) { settings.frameUrl = s?.toString() ?: "" }
                override fun beforeTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
                override fun onTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
            })
        })
        text(
            "Empty: a test card that changes every time, so the screen wakes on every check (the worst case). " +
                "With an address: the screen wakes only when the frame changed.", 14f, gap = 4, grey = true
        )

        // Results
        section("Battery")
        text(BatteryReading.read(this).describe(), 18f)
        text(log.summary(), 18f, gap = 12)
        val recent = log.lines().takeLast(8)
        if (recent.isNotEmpty()) {
            mono(recent.joinToString("\n"))
            button("Start a new log", primary = false) { log.startOver(); build() }
            text("The old log is kept as sleep-log.previous.csv.", 14f, gap = 4, grey = true)
        }
    }

    // ---- small view helpers ----

    private fun dp(v: Int) = TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v.toFloat(), resources.displayMetrics).toInt()

    private fun text(s: String, sizeSp: Float, bold: Boolean = false, gap: Int = 0, grey: Boolean = false) {
        root.addView(TextView(this).apply {
            text = s
            textSize = sizeSp
            setTextColor(if (grey) Color.rgb(68, 68, 68) else Color.BLACK)
            if (bold) typeface = Typeface.create("sans-serif", Typeface.BOLD)
            if (bold && sizeSp >= 24f) letterSpacing = -0.01f
            setPadding(0, dp(gap), 0, 0)
        })
    }

    private fun section(title: String) {
        root.addView(View(this).apply { setBackgroundColor(Color.rgb(204, 204, 204)) },
            LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 1).apply { topMargin = dp(24); bottomMargin = dp(16) })
        text(title, 20f, bold = true)
        root.addView(View(this), LinearLayout.LayoutParams(1, dp(8)))
    }

    private fun mono(s: String) {
        root.addView(TextView(this).apply {
            text = s
            textSize = 13f
            typeface = Typeface.MONOSPACE
            setTextColor(Color.BLACK)
            setTextIsSelectable(true)
            setPadding(0, dp(8), 0, dp(8))
        })
    }

    private fun outline(filled: Boolean) = GradientDrawable().apply {
        cornerRadius = dp(12).toFloat()
        setStroke(dp(2), Color.BLACK)
        setColor(if (filled) Color.BLACK else Color.WHITE)
    }

    private fun button(label: String, primary: Boolean, onTap: () -> Unit) {
        root.addView(Button(this).apply {
            text = label
            isAllCaps = false
            textSize = 17f
            minHeight = dp(52)
            background = outline(primary)
            setTextColor(if (primary) Color.WHITE else Color.BLACK)
            stateListAnimator = null
            setOnClickListener { onTap() }
        }, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply { topMargin = dp(12) })
    }

    private fun choice(label: String, selected: Boolean, onTap: () -> Unit) = Button(this).apply {
        text = label
        isAllCaps = false
        textSize = 17f
        minHeight = dp(52)
        gravity = Gravity.CENTER
        background = outline(selected)
        setTextColor(if (selected) Color.WHITE else Color.BLACK)
        stateListAnimator = null
        contentDescription = if (selected) "$label, selected" else label
        setOnClickListener { onTap() }
    }
}
