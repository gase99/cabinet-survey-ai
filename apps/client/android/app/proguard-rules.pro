# Keep Flutter embedding and plugin registration entry points discovered by reflection.
-keep class io.flutter.** { *; }
-keep class com.cabinetsurvey.client.MainActivity { *; }
# Plugin-provided consumer rules are packaged by Flutter/AGP. Do not blanket-keep all libraries.
# This app has no deferred components and does not bundle Play Core. Flutter's
# embedding retains optional references to it; suppress only that missing API.
-dontwarn com.google.android.play.core.**
