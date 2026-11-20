import 'package:flutter/services.dart';

/// Android Storage Access Framework: the user chooses the destination. No
/// broad storage permission, public-directory assumption or web download path.
class DocumentSaver {
  static const channel = MethodChannel('com.cabinetsurvey.client/documents');
  const DocumentSaver();

  Future<bool> save({required String name, required Uint8List bytes, required bool pdf}) async {
    if (name.isEmpty || name.contains('/') || name.contains('\\') || bytes.isEmpty) {
      throw ArgumentError('A filename and non-empty document are required');
    }
    final saved = await channel.invokeMethod<bool>('saveDocument', {
      'name': name, 'bytes': bytes, 'mime': pdf ? 'application/pdf' : 'image/png',
    });
    return saved ?? false;
  }
}
