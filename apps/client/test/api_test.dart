import 'dart:convert';
import 'dart:typed_data';
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
      return http.Response.bytes(
        utf8.encode(jsonEncode({
          'observations':[{'label':'wall length','kind':'wall_length','value_mm':3200,
            'unit':'mm','source_text':'سه متر و بیست سانتی متر','intent':'statement',
            'needs_review':true,'confidence':0.9}],
          'ambiguities':[],'clarification_questions':[],'provider':'deterministic_spoken',
          'disclaimer':'proposals'})),
        200,
        headers:{'content-type':'application/json; charset=utf-8'});
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
  test('Idempotency-Key header is forwarded on POST requests',() async {
    String? seenKey;
    final api=Api(baseUrl:'https://example.invalid/api/v1/',client:MockClient((request) async {
      seenKey=request.headers['Idempotency-Key'];
      return http.Response(jsonEncode({'id':'job-1','status':'done'}),201);
    }));
    api.token='secret-test-token';
    final res=await api.request('POST','exports/p1',{'format':'pdf','layout':'A4'},{'Idempotency-Key':'idem-123'}) as Map<String,dynamic>;
    expect(seenKey,'idem-123');
    expect(res['id'],'job-1');
    api.close();
  });
  test('sketch upload name always matches the sniffed image type', () async {
    expect(sketchUploadName('IMG_0001.jpg', 'image/png'), 'IMG_0001.png');
    expect(sketchUploadName('scan.PNG', 'image/jpeg'), 'scan.jpg');
    expect(sketchUploadName('../../x', 'image/webp'), 'x.webp');
    expect(sketchUploadName('', 'image/jpeg'), 'sketch.jpg');
    String? body;
    final api=Api(baseUrl:'https://example.invalid/api/v1/',client:MockClient((request) async {
      body=latin1.decode(request.bodyBytes);
      return http.Response('{"observations":[]}',200);
    }));
    final png=[137,80,78,71,13,10,26,10,0,0];
    await api.sketch(Uint8List.fromList(png),'photo.jpg');
    expect(body, contains('filename="photo.png"'));
    expect(body, contains('content-type: image/png'));
    api.close();
  });
  test('exportDocument polls queued -> running -> done, then downloads', () async {
    final calls=<String>[];
    var polls=0;
    final api=Api(baseUrl:'https://example.invalid/api/v1/',client:MockClient((request) async {
      calls.add('${request.method} ${request.url.path}');
      if(request.method=='POST') {
        expect(request.headers['Idempotency-Key'],'idem-exp');
        return http.Response(jsonEncode({'id':'job-9','status':'queued'}),202);
      }
      if(request.url.path.endsWith('/download')) return http.Response.bytes([37,80,68,70],200);
      polls++;
      return http.Response(jsonEncode({'id':'job-9','status':polls==1?'running':'done'}),200);
    }));
    final data=await api.exportDocument('p1',{'format':'pdf','layout':'A4'},idempotencyKey:'idem-exp',
      pollInterval:Duration.zero);
    expect(data,[37,80,68,70]);
    expect(calls,['POST /api/v1/exports/p1','GET /api/v1/exports/job-9','GET /api/v1/exports/job-9',
      'GET /api/v1/exports/job-9/download']);
    api.close();
  });
  test('exportDocument surfaces a failed job and never downloads', () async {
    var downloads=0;
    final api=Api(baseUrl:'https://example.invalid/api/v1/',client:MockClient((request) async {
      if(request.method=='POST') return http.Response(jsonEncode({'id':'job-f','status':'queued'}),202);
      if(request.url.path.endsWith('/download')) { downloads++; return http.Response('',200); }
      return http.Response(jsonEncode({'id':'job-f','status':'failed','error_message':'Drawing rendering failed'}),200);
    }));
    await expectLater(api.exportDocument('p1',{'format':'pdf'},pollInterval:Duration.zero),
      throwsA(isA<ApiException>().having((e) => e.message,'message','Drawing rendering failed')));
    expect(downloads,0);
    api.close();
  });
  test('exportDocument stops polling at the timeout', () async {
    final api=Api(baseUrl:'https://example.invalid/api/v1/',client:MockClient((request) async =>
      http.Response(jsonEncode({'id':'job-s','status':request.method=='POST'?'queued':'running'}),
        request.method=='POST'?202:200)));
    await expectLater(api.exportDocument('p1',{'format':'pdf'},pollInterval:Duration.zero,timeout:Duration.zero),
      throwsA(isA<ApiException>().having((e) => e.status,'status',504)));
    api.close();
  });
}
