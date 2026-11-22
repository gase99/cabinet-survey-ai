import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite/sqflite.dart';
import 'package:cabinet_survey_ai/core/controller.dart';
import 'package:cabinet_survey_ai/core/secure_database.dart';
import 'package:cabinet_survey_ai/main.dart';

const retry = 'Try again / تلاش دوباره';
const reset = 'Reset and re-sync / حذف و همگام‌سازی مجدد';

Widget app(Object error, {void Function()? onOpen}) => ProviderScope(
  overrides: [databaseProvider.overrideWith((ref) {
    onOpen?.call();
    return Future<Database>.error(error);
  })],
  child: MaterialApp(home: Bootstrap(toggleLocale: () {})));

void main() {
  group('open failure classification', () {
    test('only "not a database" and "file is encrypted" are reset-immediately', () {
      for (final message in ['DatabaseException(file is not a database)', 'SQLITE_NOTADB: File is encrypted or is not a database']) {
        final result = OpenFailureClassifier.database(message, exists: true);
        expect(result, isA<LocalResetRequired>(), reason: message);
        expect((result as LocalResetRequired).invalidKey, true);
      }
    });
    test('generic open_failed is retryable, not a reset', () {
      expect(OpenFailureClassifier.database(
        'DatabaseException(open_failed /data/user/0/x/databases/cabinet_survey_encrypted.sqlite)', exists: true),
        isA<LocalOpenFailed>());
    });
    test('errors for a database that does not exist yet are rethrown unchanged', () {
      expect(OpenFailureClassifier.database('not a database', exists: false), isNull);
      expect(OpenFailureClassifier.database('open_failed', exists: false), isNull);
      expect(OpenFailureClassifier.key(PlatformException(code: 'WRAPPED_KEY_MISSING'), exists: false), isNull);
    });
    test('unrelated database errors are rethrown unchanged', () {
      expect(OpenFailureClassifier.database('disk I/O error', exists: true), isNull);
    });
    test('missing wrapped key is reset-immediately; other key errors are retryable', () {
      expect(OpenFailureClassifier.key(PlatformException(code: OpenFailureClassifier.wrappedKeyMissing), exists: true),
        isA<LocalResetRequired>());
      expect(OpenFailureClassifier.key(PlatformException(code: 'LOCAL_SECURITY_ERROR'), exists: true),
        isA<LocalOpenFailed>());
    });
  });

  testWidgets('generic open failure shows only "try again" first, reset only after a failed retry', (tester) async {
    var opens = 0;
    var channelCalls = 0;
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      SecureDatabase.channel, (MethodCall call) async { channelCalls++; return null; });
    await tester.pumpWidget(app(const LocalOpenFailed(), onOpen: () => opens++));
    await tester.pump();
    await tester.pump();
    expect(find.text(retry), findsOneWidget);
    expect(find.text(reset), findsNothing);
    expect(opens, 1);
    await tester.tap(find.text(retry));
    await tester.pump();
    await tester.pump();
    expect(opens, 2);
    expect(find.text(retry), findsOneWidget);
    expect(find.text(reset), findsOneWidget);
    // Retrying again remains possible and never deletes anything by itself.
    await tester.tap(find.text(retry));
    await tester.pump();
    await tester.pump();
    expect(opens, 3);
    expect(channelCalls, 0);
  });

  testWidgets('not-a-database / missing wrapped key offers reset immediately', (tester) async {
    await tester.pumpWidget(app(const LocalResetRequired(invalidKey: true)));
    await tester.pump();
    await tester.pump();
    expect(find.text(reset), findsOneWidget);
    expect(find.text(retry), findsNothing);
  });
}
