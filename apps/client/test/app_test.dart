import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:cabinet_survey_ai/main.dart';
import 'package:cabinet_survey_ai/core/controller.dart';
import 'package:cabinet_survey_ai/core/store.dart';
void main() {
  testWidgets('Persian RTL shell switches to English and captures offline', (tester) async {
    sqfliteFfiInit();
    final db=await LocalStore.open(testFactory:databaseFactoryFfi,path:inMemoryDatabasePath);
    await tester.pumpWidget(ProviderScope(overrides:[databaseProvider.overrideWith((ref) async => db)],
      child:const CabinetSurveyApp()));
    await tester.pumpAndSettle();
    expect(find.text('ورود'),findsOneWidget);
    expect(Directionality.of(tester.element(find.text('ورود'))),TextDirection.rtl);
    await tester.tap(find.byIcon(Icons.translate)); await tester.pumpAndSettle();
    expect(find.text('Sign in'),findsOneWidget);
    await tester.tap(find.text('Capture offline')); await tester.pumpAndSettle();
    await tester.tap(find.text('New project')); await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextFormField).first,'Offline kitchen');
    await tester.tap(find.text('Save')); await tester.pumpAndSettle();
    expect(find.text('Offline kitchen'),findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
    await db.close();
  });
}
