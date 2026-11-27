import 'package:flutter_test/flutter_test.dart';
import 'package:cabinet_survey_ai/core/api.dart';

void main() {
  test('workflow URL uses the same debug validation as the app', () {
    const supplied = String.fromEnvironment('DISPATCH_API_URL');
    // Ordinary test runs have no dispatch input. CI passes one explicitly.
    if (const bool.fromEnvironment('DISPATCH_VALIDATE')) {
      validateApiBase(supplied, release: false);
    }
  });
}
