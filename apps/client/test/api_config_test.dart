import 'package:flutter_test/flutter_test.dart';
import 'package:cabinet_survey_ai/core/api.dart';

void main() {
  test('release rejects relative, insecure, credential-bearing and wrong-prefix URLs', () {
    for (final url in ['/api/v1/', '', 'http://api.test/api/v1/',
        'https://user:password@api.test/api/v1/', 'https://api.test/',
        'https://api.test/api/v1/?token=secret', 'ftp://api.test/api/v1/']) {
      expect(() => validateApiBase(url, release: true), throwsArgumentError, reason: url);
    }
    expect(validateApiBase('https://api.test/api/v1/', release: true).resolve('projects').toString(),
        'https://api.test/api/v1/projects');
  });
  test('debug permits emulator HTTP but never relative URLs', () {
    expect(validateApiBase('http://10.0.2.2:8000/api/v1/', release: false).host, '10.0.2.2');
    expect(validateApiBase('http://127.0.0.1:8000/api/v1/', release: false).host, '127.0.0.1');
    expect(validateApiBase('https://example.org/prefix/api/v1/', release: false).scheme, 'https');
    for (final url in ['', '/api/v1/', 'http://user:pass@host/api/v1/',
        'ftp://host/api/v1/', 'http://host/api/v1/?q=1', 'http://host/api/v1/#part',
        'http://host/api/v1']) {
      expect(() => validateApiBase(url, release: false), throwsArgumentError, reason: url);
    }
  });
}
