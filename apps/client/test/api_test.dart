import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:cabinet_survey_ai/core/api.dart';
void main() {
  test('authenticated request uses header, never token URL',() async {
    final api=Api(baseUrl:'https://example.invalid/api/v1/',client:MockClient((request) async {
      expect(request.url.toString(),'https://example.invalid/api/v1/projects');
      expect(request.headers['Authorization'],'Bearer secret-test-token');
      return http.Response(jsonEncode([]),200);
    }));
    api.token='secret-test-token';
    expect(await api.request('GET','projects'),isEmpty);
    api.close();
  });
  test('HTTP validation errors surface to UI',() async {
    final api=Api(baseUrl:'https://example.invalid/api/v1/',client:MockClient((_) async =>
      http.Response('{"detail":"Invalid dimensions"}',422)));
    await expectLater(api.request('POST','rooms',{}),throwsA(isA<ApiException>().having((e) => e.status,'status',422)));
    api.close();
  });
}
