package com.smarthelmetnav

import com.chaquo.python.Python
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.bridge.ReactContextBaseJavaModule
import com.facebook.react.bridge.ReactMethod

/**
 * React Native Native Module wrapping the Python sensor-fusion + dead-reckoning
 * bridge via Chaquopy.  All methods are synchronous (isBlockingSynchronousMethod)
 * because they are called on the JS thread at 10 Hz and must complete in < 5 ms.
 *
 * Python state lives in bridge.py module-level singletons for the app lifetime.
 */
class SmartHelmetPythonModule(reactContext: ReactApplicationContext) :
    ReactContextBaseJavaModule(reactContext) {

    override fun getName(): String = "SmartHelmetPython"

    private val bridge by lazy {
        Python.getInstance().getModule("bridge")
    }

    // ── Dead Reckoning ─────────────────────────────────────��──────────────────

    @ReactMethod(isBlockingSynchronousMethod = true)
    fun anchorDr(lat: Double, lon: Double): String? {
        bridge.callAttr("anchor_dr", lat, lon)
        return null
    }

    /** Returns JSON string: {"lat":…,"lon":…,"uncertainty_m":…} or "null". */
    @ReactMethod(isBlockingSynchronousMethod = true)
    fun updateDr(speedMps: Double, headingDeg: Double, timestampS: Double): String {
        return bridge.callAttr("update_dr", speedMps, headingDeg, timestampS).toString()
    }

    /** Returns JSON string: {"lat":…,"lon":…,"uncertainty_m":…} or "null". Read-only. */
    @ReactMethod(isBlockingSynchronousMethod = true)
    fun getDrPosition(): String {
        return bridge.callAttr("get_dr_position").toString()
    }

    @ReactMethod(isBlockingSynchronousMethod = true)
    fun isDrAnchored(): Boolean {
        return bridge.callAttr("is_dr_anchored").toBoolean()
    }

    @ReactMethod(isBlockingSynchronousMethod = true)
    fun resetDr(): String? {
        bridge.callAttr("reset_dr")
        return null
    }

    // ── Heading / Sensor Fusion ───────────────────────────────────────────────

    /** Fuse IMU sample; returns smoothed heading in degrees [0, 360). */
    @ReactMethod(isBlockingSynchronousMethod = true)
    fun updateHeading(
        ax: Double, ay: Double, az: Double,
        gx: Double, gy: Double, gz: Double,
        timestampS: Double,
    ): Double {
        return bridge.callAttr("update_heading", ax, ay, az, gx, gy, gz, timestampS).toDouble()
    }

    @ReactMethod(isBlockingSynchronousMethod = true)
    fun getHeading(): Double {
        return bridge.callAttr("get_heading").toDouble()
    }

    @ReactMethod(isBlockingSynchronousMethod = true)
    fun isHeadingInitialized(): Boolean {
        return bridge.callAttr("is_heading_initialized").toBoolean()
    }

    @ReactMethod(isBlockingSynchronousMethod = true)
    fun isCrashDetected(): Boolean {
        return bridge.callAttr("is_crash_detected").toBoolean()
    }

    @ReactMethod(isBlockingSynchronousMethod = true)
    fun resetHeading(): String? {
        bridge.callAttr("reset_heading")
        return null
    }
}
