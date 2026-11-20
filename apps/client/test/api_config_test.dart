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
    expect(() => validateApiBase('/api/v1/', release: false), throwsArgumentError);
  });
}
