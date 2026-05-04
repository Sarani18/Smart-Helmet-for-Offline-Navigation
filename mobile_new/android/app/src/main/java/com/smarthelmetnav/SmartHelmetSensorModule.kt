package com.smarthelmetnav

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.os.SystemClock
import com.facebook.react.bridge.Arguments
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.bridge.ReactContextBaseJavaModule
import com.facebook.react.bridge.ReactMethod
import com.facebook.react.modules.core.DeviceEventManagerModule

class SmartHelmetSensorModule(
  private val reactContext: ReactApplicationContext
) : ReactContextBaseJavaModule(reactContext), SensorEventListener {

  private val sensorManager =
    reactContext.getSystemService(Context.SENSOR_SERVICE) as SensorManager
  private val accelerometer = sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
  private val gyroscope = sensorManager.getDefaultSensor(Sensor.TYPE_GYROSCOPE)
  private var active = false
  private var intervalUs = 100_000
  private var lastAccelMs = 0L
  private var lastGyroMs = 0L

  override fun getName(): String = "SmartHelmetSensors"

  @ReactMethod
  fun start(updateIntervalMs: Int) {
    intervalUs = (updateIntervalMs.coerceAtLeast(20)) * 1000
    active = true
    accelerometer?.let {
      sensorManager.registerListener(this, it, intervalUs)
    }
    gyroscope?.let {
      sensorManager.registerListener(this, it, intervalUs)
    }
    emitStatus()
  }

  @ReactMethod
  fun stop() {
    active = false
    sensorManager.unregisterListener(this)
    emitStatus()
  }

  @ReactMethod
  fun getStatus() {
    emitStatus()
  }

  @ReactMethod
  fun addListener(eventName: String) {
    // Required by NativeEventEmitter.
  }

  @ReactMethod
  fun removeListeners(count: Int) {
    // Required by NativeEventEmitter.
  }

  override fun onSensorChanged(event: SensorEvent) {
    if (!active) {
      return
    }

    val nowMs = System.currentTimeMillis()
    val lastMs = when (event.sensor.type) {
      Sensor.TYPE_ACCELEROMETER -> lastAccelMs
      Sensor.TYPE_GYROSCOPE -> lastGyroMs
      else -> return
    }
    if (nowMs - lastMs < intervalUs / 1000) {
      return
    }
    when (event.sensor.type) {
      Sensor.TYPE_ACCELEROMETER -> lastAccelMs = nowMs
      Sensor.TYPE_GYROSCOPE -> lastGyroMs = nowMs
    }

    val payload = Arguments.createMap().apply {
      putString(
        "kind",
        if (event.sensor.type == Sensor.TYPE_ACCELEROMETER) "accelerometer" else "gyroscope"
      )
      putDouble("x", event.values[0].toDouble())
      putDouble("y", event.values[1].toDouble())
      putDouble("z", event.values[2].toDouble())
      putDouble("timestamp", sensorTimestampToEpochMilliseconds(event.timestamp))
    }
    emit("SmartHelmetSensorData", payload)
  }

  override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) = Unit

  private fun emitStatus() {
    val payload = Arguments.createMap().apply {
      putBoolean("active", active)
      putBoolean("accelerometer", accelerometer != null)
      putBoolean("gyroscope", gyroscope != null)
    }
    emit("SmartHelmetSensorStatus", payload)
  }

  private fun emit(eventName: String, payload: com.facebook.react.bridge.WritableMap) {
    reactContext
      .getJSModule(DeviceEventManagerModule.RCTDeviceEventEmitter::class.java)
      .emit(eventName, payload)
  }

  private fun sensorTimestampToEpochMilliseconds(elapsedTimeNanos: Long): Double {
    return (
      System.currentTimeMillis() +
        ((elapsedTimeNanos - SystemClock.elapsedRealtimeNanos()) / 1_000_000L)
      ).toDouble()
  }
}
