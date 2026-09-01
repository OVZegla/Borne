plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "fr.symps.borne"
    compileSdk = 34

    defaultConfig {
        applicationId = "fr.symps.borne"
        // Android 8 : les tablettes de borne vendues aujourd'hui sont toutes
        // au-dela, et cela permet une icone entierement vectorielle.
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = "1.0.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

// Aucune dependance : ni AndroidX, ni bibliotheque tierce. L'application tient
// dans une WebView et un socket UDP, et pese quelques dizaines de kilo-octets.
dependencies {
}
