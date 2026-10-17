# PaperHub Native Android Companion Specification

This document outlines the architecture for a dedicated, battery-optimized Android Companion APK for Onyx Boox and Android e-paper readers.

---

## Technical Objectives

1. **Hardware Regal Refresh Integration**: Call Onyx EPD SDK APIs (`EpdController`) directly on view update to achieve crisp, flash-free partial refreshes.
2. **Deep Sleep Between Taps**: Allow Android CPU to enter deep Doze mode while retaining the e-ink image persistently with 0mA static display draw.
3. **Bi-directional Frontlight & Battery Entity Sync**: Expose the dual warm/cold CCT frontlight sliders directly to Home Assistant as a `light` entity.

---

## Onyx EPD Controller Integration

In the native Android companion, when a new PNG bitmap arrives from `/api/devices/{id}/touch` or the SSE event:

```java
import com.onyx.android.sdk.api.device.epd.EpdController;
import com.onyx.android.sdk.api.device.epd.UpdateMode;

public class PaperHubView extends ImageView {
    
    public void updateBitmap(Bitmap newBitmap, boolean isFullRefresh) {
        setImageBitmap(newBitmap);
        
        if (isFullRefresh) {
            // Periodic full refresh to clear residual ghosting
            EpdController.setUpdateMode(this, UpdateMode.GC);
            EpdController.applyApplicationFastMode("paperhub", false, true);
        } else {
            // Ultra-crisp partial Regal update (zero flash)
            EpdController.setUpdateMode(this, UpdateMode.REGAL);
        }
        
        postInvalidate();
    }
}
```

---

## Wake-on-Touch Architecture

To maximize battery life (weeks of remote operation):
1. Use an Android `WakeLock` only during active network transmission (<100ms per tap).
2. Intercept `onTouchEvent(MotionEvent event)`:
   ```kotlin
   override fun onTouchEvent(event: MotionEvent): Boolean {
       if (event.action == MotionEvent.ACTION_UP) {
           val nativeX = (event.x * scaleFactorX).toInt()
           val nativeY = (event.y * scaleFactorY).toInt()
           paperHubClient.sendTouch(nativeX, nativeY)
       }
       return true
   }
   ```
3. After the new frame renders, release the `WakeLock` immediately. The e-ink display maintains the Carta image indefinitely without power.
