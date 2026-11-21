import 'dart:convert';
import 'dart:io';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:cabinet_survey_ai/core/api.dart';
import 'package:cabinet_survey_ai/core/controller.dart';
import 'package:cabinet_survey_ai/core/secure_database.dart';
import 'package:cabinet_survey_ai/core/store.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  sqfliteFfiInit();
  test('recovery login imports server records and retains retry marker on failure', () async {
    FlutterSecureStorage.setMockInitialValues({});
    final dir = await Directory.systemTemp.createTemp('recovery-test-');
    final path = '${dir.path}/survey.sqlite';
    final db = await LocalStore.open(testFactory: databaseFactoryFfiNoIsolate, path: path);
    await File('$path.resync-required').writeAsString('required');
    var failSync = true;
    final api = Api(baseUrl:'https://example.invalid/api/v1/', client:MockClient((request) async {
      final p = request.url.path;
      Object reply;
      if (p.endsWith('/auth/login')) {
        reply = {'access_token':'test', 'refresh_token':'refresh'};
      } else if (p.endsWith('/auth/me')) {
        reply = {'id':'owner'};
      } else if (p.endsWith('/customers')) {
        if (failSync) return http.Response('unavailable', 503);
        reply = [];
      } else if (p.endsWith('/projects')) {
        reply = [{'id':'server-project', 'title':'Server copy', 'version':1}];
      } else if (p.endsWith('/rooms')) {
        reply = [];
      } else if (p.endsWith('/sync/pull')) {
        reply = {'tombstones': []};
      } else {
        throw StateError('Unexpected request: $p');
      }
      return http.Response(jsonEncode(reply), 200);
    }));
    final controller = SurveyController(db, api:api);
    await expectLater(controller.login('owner@example.com','password'), throwsA(isA<ApiException>()));
    expect(await SecureDatabase.needsResync(path), true);
    expect(controller.resyncRequired, true);
    failSync = false;
    await controller.sync();
    expect(await SecureDatabase.needsResync(path), false);
    expect((await controller.store.get('server-project'))!['title'], 'Server copy');
    api.close();
    await db.close();
    await dir.delete(recursive:true);
  });
}
