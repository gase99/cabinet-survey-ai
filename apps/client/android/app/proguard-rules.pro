# Keep Flutter embedding and plugin registration entry points discovered by reflection.
-keep class io.flutter.** { *; }
-keep class com.cabinetsurvey.client.MainActivity { *; }
# Plugin-provided consumer rules are packaged by Flutter/AGP. Do not blanket-keep all libraries.
