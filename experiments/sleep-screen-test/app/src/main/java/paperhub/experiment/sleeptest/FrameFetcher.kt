package paperhub.experiment.sleeptest

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import java.io.File
import java.net.HttpURLConnection
import java.net.URL

/** Downloads the frame, asking first whether it changed. Runs off the main thread; never throws. */
object FrameFetcher {
    enum class Outcome { CHANGED, UNCHANGED, FAILED }

    data class Result(val outcome: Outcome, val error: String?, val ms: Long, val bytes: Int)

    /** The last good frame, kept on disk so the dashboard can draw it at any time. */
    fun cacheFile(context: Context) = File(context.filesDir, "frame.png")

    fun cached(context: Context): Bitmap? =
        cacheFile(context).takeIf { it.exists() }?.let { BitmapFactory.decodeFile(it.path) }

    fun check(context: Context, address: String, etag: String?, saveEtag: (String?) -> Unit): Result {
        val started = System.nanoTime()
        fun elapsed() = (System.nanoTime() - started) / 1_000_000
        return try {
            val conn = URL(address).openConnection() as HttpURLConnection
            conn.connectTimeout = 8000
            conn.readTimeout = 8000
            conn.useCaches = false
            if (etag != null && cacheFile(context).exists()) conn.setRequestProperty("If-None-Match", etag)
            try {
                when (conn.responseCode) {
                    304 -> Result(Outcome.UNCHANGED, null, elapsed(), 0)
                    200 -> {
                        val body = conn.inputStream.use { it.readBytes() }
                        if (BitmapFactory.decodeByteArray(body, 0, body.size) == null) {
                            Result(Outcome.FAILED, "The frame address didn't return an image.", elapsed(), body.size)
                        } else {
                            val tmp = File(context.filesDir, "frame.png.tmp")
                            tmp.writeBytes(body)
                            tmp.renameTo(cacheFile(context))
                            saveEtag(conn.getHeaderField("ETag"))
                            Result(Outcome.CHANGED, null, elapsed(), body.size)
                        }
                    }
                    else -> Result(Outcome.FAILED, "The frame address answered ${conn.responseCode}.", elapsed(), 0)
                }
            } finally {
                conn.disconnect()
            }
        } catch (e: Exception) {
            Result(Outcome.FAILED, "Couldn't reach the frame address (${e.javaClass.simpleName}).", elapsed(), 0)
        }
    }

    /** One-off download for the old sleep-screen experiment. */
    fun fetch(address: String): Pair<Bitmap?, String?> = try {
        val conn = URL(address).openConnection() as HttpURLConnection
        conn.connectTimeout = 8000
        conn.readTimeout = 8000
        val body = conn.inputStream.use { it.readBytes() }
        conn.disconnect()
        BitmapFactory.decodeByteArray(body, 0, body.size) to null
    } catch (e: Exception) {
        null to "Couldn't reach the frame address (${e.javaClass.simpleName})."
    }
}
