import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:image_picker/image_picker.dart';
import 'package:cabinet_survey_ai/services/photo_importer.dart';

void main() {
  test('picker cache clears on success, cancellation and picker/save errors', () async {
    final dir = await Directory.systemTemp.createTemp('photo-import-test-');
    addTearDown(() => dir.delete(recursive: true));
    final file = File('${dir.path}/test.png');
    await file.writeAsBytes([1, 2, 3]);
    for (final scenario in ['success', 'cancel', 'picker-error', 'save-error']) {
      var cleaned = 0, saved = 0;
      final importer = PhotoImporter(
        pick: (_) async {
          if (scenario == 'picker-error') throw StateError('picker failed');
          if (scenario == 'cancel') return null;
          return XFile(file.path);
        },
        clearCache: () async { cleaned++; },
      );
      Future<void> run() => importer.capture(ImageSource.gallery, (name, bytes) async {
        saved++;
        expect(name, 'test.png');
        expect(bytes, [1, 2, 3]);
        if (scenario == 'save-error') throw StateError('save failed');
      });
      if (scenario.endsWith('error')) {
        await expectLater(run(), throwsStateError);
      } else {
        await run();
      }
      expect(cleaned, 1, reason: scenario);
      expect(saved, scenario == 'success' || scenario == 'save-error' ? 1 : 0);
    }
  });
}
