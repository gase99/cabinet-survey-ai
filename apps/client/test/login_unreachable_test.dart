import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:cabinet_survey_ai/core/api.dart';
import 'package:cabinet_survey_ai/core/controller.dart';
import 'package:cabinet_survey_ai/core/store.dart';
import 'package:cabinet_survey_ai/features/workspace.dart';

void main() {
  testWidgets('login shows endpoint and friendly error for an unreachable server', (tester) async {
    FlutterSecureStorage.setMockInitialValues({});
    sqfliteFfiInit();
    final db = await LocalStore.open(testFactory:databaseFactoryFfiNoIsolate,path:inMemoryDatabasePath);
    final api = Api(baseUrl:'http://127.0.0.1:8000/api/v1/', client:MockClient((_) async {
      throw http.ClientException('sensitive raw socket error');
    }));
    final controller = SurveyController(db, api:api);
    await tester.pumpWidget(MaterialApp(home:Workspace(controller:controller,toggleLocale:() {})));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Sign in'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextFormField).at(0), 'owner@example.com');
    await tester.enterText(find.byType(TextFormField).at(1), 'StrongPassword1!');
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Server unreachable. Start the server and try again.'), findsOneWidget);
    expect(find.textContaining('http://127.0.0.1:8000/api/v1/'), findsOneWidget);
    expect(find.textContaining('sensitive raw socket error'), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
    api.close();
    await db.close();
  });
}
