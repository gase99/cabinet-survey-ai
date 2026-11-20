import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:cabinet_survey_ai/main.dart';

// Actual Android sqflite/secure-storage plugins, not VM substitutes. No network.
// CI runs capture, force-stops the app, then runs again with VERIFY_REOPEN=true.
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  const reopen = bool.fromEnvironment('VERIFY_REOPEN');
  testWidgets('Android Persian RTL offline capture and process restart', (tester) async {
    await tester.pumpWidget(const ProviderScope(child: CabinetSurveyApp()));
    await tester.pumpAndSettle();
    expect(find.text('ورود'), findsOneWidget);
    expect(Directionality.of(tester.element(find.text('ورود'))), TextDirection.rtl);
    await tester.tap(find.text('برداشت آفلاین'));
    await tester.pumpAndSettle();
    if (!reopen) {
      await tester.tap(find.text('پروژه جدید'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextFormField).first, 'Android device acceptance');
      await tester.tap(find.text('ذخیره'));
      await tester.pumpAndSettle();
    }
    expect(find.text('Android device acceptance'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
