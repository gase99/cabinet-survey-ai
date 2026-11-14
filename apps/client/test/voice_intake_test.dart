import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:cabinet_survey_ai/core/api.dart';
import 'package:cabinet_survey_ai/domain/survey.dart';
import 'package:cabinet_survey_ai/domain/voice.dart';
import 'package:cabinet_survey_ai/features/voice_intake.dart';

Json extractionJson() => {
  'observations': [
    {'label': 'wall length', 'kind': 'wall_length', 'value_mm': 3200, 'unit': 'mm',
      'source_text': 'سه متر و بیست سانتی متر', 'intent': 'statement',
      'needs_review': true, 'confidence': 0.9},
    {'label': 'wall length', 'kind': 'wall_length', 'value_mm': 3000, 'unit': 'mm',
      'source_text': 'سه متر', 'intent': 'statement', 'needs_review': true,
      'confidence': 0.9},
  ],
  'ambiguities': [{'type': 'conflicting_values', 'detail': 'resolve the conflict'}],
  'clarification_questions': ['Wall height not specified — please provide wall height(s).'],
  'provider': 'deterministic_spoken', 'disclaimer': 'proposals only',
};

void main() {
  Future<VoiceProposal?> pumpAndApply(WidgetTester tester, {required bool authenticated}) async {
    VoiceProposal? applied;
    final api = Api(baseUrl: 'https://example.invalid/api/v1/', client: MockClient((request) async {
      expect(request.url.toString(), 'https://example.invalid/api/v1/ai/parse-text');
      return http.Response(jsonEncode(extractionJson()), 200);
    }));
    if (authenticated) api.token = 'secret-test-token';
    await tester.pumpWidget(MaterialApp(home: Builder(builder: (context) => Scaffold(body: TextButton(
      onPressed: () async {
        applied = await Navigator.push<VoiceProposal>(context,
          MaterialPageRoute<VoiceProposal>(builder: (_) => VoiceIntake(api: api)));
      },
      child: const Text('Open'))))));
    await tester.tap(find.text('Open'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'طول دیوار سه متر و بیست سانتی‌متر');
    await tester.tap(find.text('Analyze'));
    await tester.pumpAndSettle();
    return applied;
  }

  testWidgets('transcript analysis shows proposals, conflicts and questions; nothing auto-applies',
      (tester) async {
    final applied = await pumpAndApply(tester, authenticated: true);
    expect(find.textContaining('3200'), findsOneWidget);
    expect(find.textContaining('3000'), findsOneWidget);
    // Conflict cards are visible, not silently resolved.
    expect(find.textContaining('Conflicting spoken values'), findsNWidgets(2));
    expect(find.textContaining('Wall height not specified'), findsOneWidget);
    // Apply only pops with the proposal; the screen never writes survey data.
    await tester.tap(find.widgetWithText(FilledButton, 'Apply').first);
    await tester.pumpAndSettle();
    expect(applied!.valueMm, 3200);
    expect(applied!.wallField, 'length_mm');
    expect(find.byType(VoiceIntake), findsNothing);
  });

  testWidgets('requires sign-in before server analysis; empty analysis is an error, not a value',
      (tester) async {
    final api = Api(baseUrl: 'https://example.invalid/api/v1/', client: MockClient((_) async =>
      throw StateError('network must not be reached')));
    await tester.pumpWidget(MaterialApp(home: VoiceIntake(api: api)));
    await tester.enterText(find.byType(TextField), 'طول دیوار سه متر');
    await tester.tap(find.text('Analyze'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Sign in'), findsOneWidget);
  });
}
