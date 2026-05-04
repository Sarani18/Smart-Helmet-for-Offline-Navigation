package com.smarthelmetnav

import android.app.Application
<<<<<<< HEAD
import com.chaquo.python.android.AndroidPlatform
import com.chaquo.python.Python
=======
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
import com.facebook.react.PackageList
import com.facebook.react.ReactApplication
import com.facebook.react.ReactHost
import com.facebook.react.ReactNativeHost
import com.facebook.react.ReactPackage
import com.facebook.react.defaults.DefaultNewArchitectureEntryPoint.load
import com.facebook.react.defaults.DefaultReactHost.getDefaultReactHost
import com.facebook.react.defaults.DefaultReactNativeHost
import com.facebook.react.flipper.ReactNativeFlipper
import com.facebook.soloader.SoLoader

class MainApplication : Application(), ReactApplication {

  override val reactNativeHost: ReactNativeHost =
      object : DefaultReactNativeHost(this) {
        override fun getPackages(): List<ReactPackage> =
            PackageList(this).packages.apply {
<<<<<<< HEAD
              add(SmartHelmetPythonPackage())
=======
              // Packages that cannot be autolinked yet can be added manually here, for example:
              // add(MyReactNativePackage())
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
            }

        override fun getJSMainModuleName(): String = "index"

        override fun getUseDeveloperSupport(): Boolean = BuildConfig.DEBUG

        override val isNewArchEnabled: Boolean = BuildConfig.IS_NEW_ARCHITECTURE_ENABLED
        override val isHermesEnabled: Boolean = BuildConfig.IS_HERMES_ENABLED
      }

  override val reactHost: ReactHost
    get() = getDefaultReactHost(this.applicationContext, reactNativeHost)

  override fun onCreate() {
    super.onCreate()
<<<<<<< HEAD
    if (!Python.isStarted()) {
      Python.start(AndroidPlatform(this))
    }
=======
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
    SoLoader.init(this, false)
    if (BuildConfig.IS_NEW_ARCHITECTURE_ENABLED) {
      // If you opted-in for the New Architecture, we load the native entry point for this app.
      load()
    }
    ReactNativeFlipper.initializeFlipper(this, reactNativeHost.reactInstanceManager)
  }
}
