# Add project specific ProGuard rules here.
# By default, the flags in this file are appended to flags specified
# in /usr/local/Cellar/android-sdk/24.3.3/tools/proguard/proguard-android.txt
# You can edit the include path and order by changing the proguardFiles
# directive in build.gradle.
#
# For more details, see
#   http://developer.android.com/guide/developing/tools/proguard.html

# Add any project specific keep options here:

# Protect JNI boundaries and React Native core from R8 stripping
-keep class com.facebook.jni.** { *; }
-keep class com.facebook.react.turbomodule.** { *; }
-keep class com.facebook.hermes.unicode.** { *; }
-keep class com.swmansion.reanimated.** { *; }

# Prevent stripping of sensor JNI callback interfaces (prevents SIGSEGV)
-keepclasseswithmembers class com.sensors.** {
    native <methods>;
}
-keepclassmembers class com.sensors.** {
    native <methods>;
}

# react-native-ble-plx
-keep class com.polidea.rxandroidble2.** { *; }
-keep class com.polidea.multiplatformbleadapter.** { *; }

# react-native-background-actions
-keep class com.asterinet.reaction.** { *; }
