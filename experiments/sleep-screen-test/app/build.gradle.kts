plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "paperhub.experiment.sleeptest"
    compileSdk = 35

    defaultConfig {
        // A throwaway experiment, deliberately not the package name a real Paperhub app would use.
        applicationId = "paperhub.experiment.sleeptest"
        minSdk = 30
        targetSdk = 35
        versionCode = 1
        versionName = "0.1"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}
