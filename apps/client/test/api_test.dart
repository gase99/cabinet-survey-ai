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
  test('parseText posts a form-encoded transcript with auth header',() async {
    String? contentType, body; Uri? url;
    final api=Api(baseUrl:'https://example.invalid/api/v1/',client:MockClient((request) async {
      url=request.url; contentType=request.headers['Content-Type'];
      body=request.body;
      return http.Response(jsonEncode({
        'observations':[{'label':'wall length','kind':'wall_length','value_mm':3200,
          'unit':'mm','source_text':'سه متر و بیست سانتی متر','intent':'statement',
          'needs_review':true,'confidence':0.9}],
        'ambiguities':[],'clarification_questions':[],'provider':'deterministic_spoken',
        'disclaimer':'proposals'}),200);
    }));
    api.token='secret-test-token';
    final result=await api.parseText('طول دیوار سه متر و بیست سانتی‌متر');
    expect(url.toString(),'https://example.invalid/api/v1/ai/parse-text');
    expect(contentType,'application/x-www-form-urlencoded');
    expect(body,contains('text='));
    expect(body!.startsWith('text='),isTrue);
    expect(body,contains('language_hint=fa%2Cen'));
    expect(result['observations'].single['value_mm'],3200);
    api.close();
  });
  test('parseText surfaces backend errors to the caller',() async {
    final api=Api(baseUrl:'https://example.invalid/api/v1/',client:MockClient((_) async =>
      http.Response('{"detail":"Speech recognition is not configured"}',503)));
    await expectLater(api.parseText('x'),throwsA(isA<ApiException>().having((e) => e.status,'status',503)));
    api.close();
  });
}
