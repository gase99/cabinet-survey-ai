import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/services.dart';
import 'package:cabinet_survey_ai/main.dart';
import 'package:cabinet_survey_ai/core/secure_database.dart';

void main() {
  testWidgets('legacy reset warns with counts and cancellation never deletes data', (tester) async {
    var calls = 0;
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      SecureDatabase.channel, (MethodCall call) async { calls++; return null; });
    await tester.pumpWidget(MaterialApp(home: LocalResetScreen(
      warning: const LocalResetRequired(pending: 3, localRecords: 2, photos: 1), onReset: () {})));
    expect(find.textContaining('همگام‌نشده: 3'), findsOneWidget);
    expect(find.textContaining('محلی: 2'), findsOneWidget);
    expect(find.textContaining('ذخیره‌شده: 1'), findsOneWidget);
    await tester.tap(find.text('Reset and re-sync / حذف و همگام‌سازی مجدد'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Cancel / انصراف'));
    await tester.pumpAndSettle();
    expect(calls, 0);
  });
}
