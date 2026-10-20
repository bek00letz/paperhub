package paperhub.experiment.sleeptest

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Rect
import android.graphics.RectF
import android.graphics.Typeface
import android.util.TypedValue
import android.view.View

/**
 * What the screen shows: the Paperhub frame if there is one, otherwise a test card with a
 * label, one large line (the time it was drawn) and a few lines of detail.
 */
class SleepCard(context: Context) : View(context) {
    var frame: Bitmap? = null
    var label = "Paperhub sleep test"
    var headline = "–"
    var lines: List<String> = emptyList()
    var note: String? = null

    private fun sp(v: Float) = TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_SP, v, resources.displayMetrics)
    private fun dp(v: Float) = TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v, resources.displayMetrics)

    private fun paint(sizeSp: Float, bold: Boolean, color: Int = Color.BLACK) = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        textSize = sp(sizeSp)
        typeface = Typeface.create("sans-serif", if (bold) Typeface.BOLD else Typeface.NORMAL)
        this.color = color
        fontFeatureSettings = "tnum"            // digits line up from one update to the next
    }

    private val labelPaint = paint(16f, true, Color.rgb(68, 68, 68))
    private val big = paint(96f, true).apply { letterSpacing = -0.02f }
    private val body = paint(22f, false)
    private val small = paint(16f, false, Color.rgb(68, 68, 68))
    private val image = Paint(Paint.FILTER_BITMAP_FLAG)

    init {
        contentDescription = "Paperhub sleep test"
    }

    override fun onDraw(canvas: Canvas) {
        canvas.drawColor(Color.WHITE)
        val bmp = frame
        if (bmp != null) drawFrame(canvas, bmp) else drawCard(canvas)
    }

    private fun drawFrame(canvas: Canvas, bmp: Bitmap) {
        val scale = minOf(width / bmp.width.toFloat(), height / bmp.height.toFloat())
        val w = bmp.width * scale
        val h = bmp.height * scale
        val left = (width - w) / 2f
        val top = (height - h) / 2f
        canvas.drawBitmap(bmp, Rect(0, 0, bmp.width, bmp.height), RectF(left, top, left + w, top + h), image)
    }

    private fun drawCard(canvas: Canvas) {
        val margin = dp(32f)
        var y = height * 0.30f
        canvas.drawText(label, margin, y, labelPaint)
        y += big.textSize * 1.05f
        canvas.drawText(headline, margin, y, big)
        y += body.textSize * 2.0f
        for (line in lines) {
            canvas.drawText(line, margin, y, body)
            y += body.textSize * 1.5f
        }
        note?.let { canvas.drawText(it, margin, height - margin, small) }
    }
}
