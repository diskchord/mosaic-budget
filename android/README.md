# Mosaic Budget for Android

This directory contains a small, dependency-free Android shell for a remote
Mosaic Budget installation. The native connection screen remembers the server
origin, then the application runs in a hardened platform `WebView`. The budget,
transaction inbox, rules, analytics, and touch drag-and-drop experience are
served by the same Mosaic server as the browser app.

## Requirements

- Android 8.0 (API 26) or newer
- JDK 17 or newer
- Android SDK Platform 36 and current SDK build tools
- Gradle 8.14.3, or the included Gradle wrapper
- A remote Mosaic Budget server available at a stable HTTPS root origin

The app accepts an origin such as `https://budget.example.com` or an explicit
HTTPS port. Paths, query strings, fragments, user information, and credentials
embedded in the URL are rejected. Mosaic must serve its page, API, and static
assets from that origin. Keep redirects on the same scheme, host, and effective
port.

Use a certificate trusted by the Android system. Cleartext HTTP, mixed content,
and certificate-error bypasses are deliberately disabled. For an internet-facing
deployment, follow the repository security guide and set `COOKIE_SECURE=true`.

## Build and install a debug APK

From this directory:

```bash
./gradlew :app:assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

The debug package ID is `com.mosaicbudget.android.debug`, so it can coexist with
a release installation. Open the app, enter the server origin, then use the
normal Mosaic sign-in screen with the email and password created on that
server.

## Sign a release APK

Release signing is enabled only when all four environment variables below are
present. Prefer an absolute path for the keystore and keep the keystore and
passwords outside this repository.

```bash
export MOSAIC_ANDROID_KEYSTORE=/secure/path/mosaic-release.jks
export MOSAIC_ANDROID_KEYSTORE_PASSWORD='...'
export MOSAIC_ANDROID_KEY_ALIAS='mosaic'
export MOSAIC_ANDROID_KEY_PASSWORD='...'
./gradlew :app:assembleRelease
```

The signed artifact is written under `app/build/outputs/apk/release/`. Without
all four values, Gradle can still create an unsigned release artifact. Back up
the release keystore securely; Android updates must use the same signing key.

## Connection and security model

- The native layer stores only the normalized server origin in app-private
  preferences. It never stores an email or password and injects no auth
  headers.
- Credentials are submitted directly to Mosaic's server-rendered sign-in page.
  The resulting first-party secure session cookie remains in the app's private
  WebView storage.
- Third-party cookies, popups, file/content access, mixed content, JavaScript
  bridges, and SSL-error overrides are disabled.
- Navigation on the configured origin stays in the app. Supported external
  links are handed to Android so the user can choose an appropriate app.
- Mosaic is online-first. Financial writes are not queued while disconnected;
  connection problems show a retry/change-server screen instead.

The Activity uses `adjustResize` and applies system-bar and keyboard insets on
current Android versions, so forms remain usable with the on-screen keyboard in
portrait and landscape.
