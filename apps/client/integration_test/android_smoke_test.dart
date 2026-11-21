import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:cabinet_survey_ai/main.dart';
import 'package:cabinet_survey_ai/core/secure_database.dart';
import 'package:cabinet_survey_ai/core/store.dart';

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
    final db = await SecureDatabase.open();
    final projects = await LocalStore(db, 'device-local').list('project');
    debugPrint('Smoke reopen=$reopen database=${db.path} device-local project count=${projects.length}');
    expect(find.text('Android device acceptance'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
