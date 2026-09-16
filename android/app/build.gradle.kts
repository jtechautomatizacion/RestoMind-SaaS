plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    // id("com.google.gms.google-services")   // ver build.gradle.kts raíz
}

android {
    namespace = "pe.jtech.restomind"
    compileSdk = 36

    defaultConfig {
        // Este valor tiene que ser EXACTAMENTE el mismo que se registre como
        // "nombre del paquete" en la consola de Firebase. Si no coincide,
        // FCM no entrega nada y tampoco dice por qué.
        applicationId = "pe.jtech.restomind"
        // 26 (Android 8) y no menos, por dos motivos que apuntan al mismo
        // lado: los canales de notificación —obligatorios para que suene una
        // comanda— existen recién desde ahí, y el ícono adaptativo también.
        // Bajar de 26 obligaría a mantener un camino alternativo para las dos
        // cosas, para alcanzar celulares de 2017 que ya no se usan en un
        // salón.
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "1.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
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

dependencies {
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.activity:activity-ktx:1.9.3")

    // Firebase — se descomenta junto con el plugin, cuando exista
    // google-services.json (ver docs/APK_ANDROID.md).
    // implementation(platform("com.google.firebase:firebase-bom:33.7.0"))
    // implementation("com.google.firebase:firebase-messaging-ktx")
}
