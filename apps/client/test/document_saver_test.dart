import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:cabinet_survey_ai/services/document_saver.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  tearDown(() => messenger.setMockMethodCallHandler(DocumentSaver.channel, null));
  test('PDF saves through Android user-selected destination with exact bytes', () async {
    final bytes = Uint8List.fromList([37, 80, 68, 70]);
    messenger.setMockMethodCallHandler(DocumentSaver.channel, (call) async {
      expect(call.method, 'saveDocument');
      expect(call.arguments, {'name': 'survey.pdf', 'bytes': bytes, 'mime': 'application/pdf'});
      return true;
    });
    expect(await const DocumentSaver().save(name: 'survey.pdf', bytes: bytes, pdf: true), isTrue);
  });
  test('picker cancellation is not reported as success', () async {
    messenger.setMockMethodCallHandler(DocumentSaver.channel, (_) async => false);
    expect(await const DocumentSaver().save(name: 'survey.png', bytes: Uint8List.fromList([137, 80]), pdf: false), isFalse);
  });
  test('invalid document never reaches native storage', () async {
    await expectLater(const DocumentSaver().save(name: '../survey.pdf', bytes: Uint8List.fromList([1]), pdf: true),
        throwsArgumentError);
  });
}
