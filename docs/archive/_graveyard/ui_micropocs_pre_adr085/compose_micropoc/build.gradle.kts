import org.jetbrains.compose.desktop.application.dsl.TargetFormat

plugins {
    kotlin("jvm") version "2.3.21"
    id("org.jetbrains.kotlin.plugin.compose") version "2.3.21"
    id("org.jetbrains.compose") version "1.11.1"
}

group = "com.atlascore.micropoc"
version = "1.0.0"

repositories {
    mavenCentral()
    google()
    maven("https://maven.pkg.jetbrains.space/public/p/compose/dev")
}

dependencies {
    implementation(compose.desktop.currentOs)
    implementation(compose.foundation)
    implementation(compose.material3)

    implementation("io.ktor:ktor-client-core:3.5.1")
    implementation("io.ktor:ktor-client-cio:3.5.1")
    implementation("io.ktor:ktor-client-websockets:3.5.1")
}

compose.desktop {
    application {
        mainClass = "MainKt"
        nativeDistributions {
            targetFormats(TargetFormat.Deb)
            packageName = "compose_micropoc"
            packageVersion = "1.0.0"
        }
    }
}

kotlin {
    jvmToolchain(21)
}
