plugins {
    id("com.android.application") version "8.9.1" apply false
    id("org.jetbrains.kotlin.android") version "2.1.0" apply false
    // Firebase: se activa recién cuando exista app/google-services.json.
    // Ver docs/APK_ANDROID.md §2. Sin ese archivo el plugin FALLA la
    // compilación, así que queda comentado hasta entonces.
    // id("com.google.gms.google-services") version "4.4.2" apply false
}
