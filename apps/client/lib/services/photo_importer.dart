import 'dart:typed_data';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';

/// Clears the entire app-private picker cache, including camera originals and
/// resized copies even when no XFile is returned. External originals are untouched.
class PhotoImporter {
  final Future<XFile?> Function(ImageSource source) pick;
  final Future<void> Function() clearCache;
  PhotoImporter({Future<XFile?> Function(ImageSource)? pick, Future<void> Function()? clearCache})
      : pick = pick ?? ((source) => ImagePicker().pickImage(source: source, maxWidth: 4096, maxHeight: 4096)),
        clearCache = clearCache ?? (() => const MethodChannel('com.cabinetsurvey.client/local_security')
            .invokeMethod<void>('clearPickerCache'));

  Future<void> capture(ImageSource source, Future<void> Function(String, Uint8List) save) async {
    try {
      final image = await pick(source);
      if (image != null) await save(image.name, await image.readAsBytes());
    } finally {
      await clearCache();
    }
  }
}
