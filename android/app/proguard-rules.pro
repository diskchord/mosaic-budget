# Mosaic has no JavaScript bridge and exposes no methods to WebView content.
# Keep the Activity name stable for manifests produced by downstream packagers.
-keep class com.mosaicbudget.android.MainActivity { *; }
