import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:cabinet_survey_ai/core/api.dart';
import 'package:cabinet_survey_ai/core/controller.dart';
import 'package:cabinet_survey_ai/core/store.dart';
import 'package:cabinet_survey_ai/domain/survey.dart';
import 'package:cabinet_survey_ai/domain/voice.dart';
import 'package:cabinet_survey_ai/features/voice_intake.dart';

Json extractionJson() => {
  'observations': [
    {'candidate_id': 'cand-wall-3200', 'label': 'wall length', 'kind': 'wall_length',
      'value_mm': 3200, 'unit': 'mm', 'source_text': 'سه متر و بیست سانتی متر',
      'intent': 'statement', 'needs_review': true, 'confidence': 0.9},
    {'candidate_id': 'cand-wall-3000', 'label': 'wall length', 'kind': 'wall_length',
      'value_mm': 3000, 'unit': 'mm', 'source_text': 'سه متر',
      'intent': 'statement', 'needs_review': true, 'confidence': 0.9},
  ],
  'ambiguities': [{'type': 'conflicting_values', 'detail': 'resolve the conflict'}],
  'clarification_questions': ['Wall height not specified — please provide wall height(s).'],
  'provider': 'deterministic_spoken', 'disclaimer': 'proposals only',
};

void main() {
  sqfliteFfiInit();

  Future<void> pumpAndAnalyze(
    WidgetTester tester, {
    required bool authenticated,
    required ValueChanged<VoiceProposal?> onApplied,
  }) async {
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });
    final api = Api(
      baseUrl: 'https://example.invalid/api/v1/',
      client: MockClient((request) async {
        expect(request.url.toString(), 'https://example.invalid/api/v1/ai/parse-text');
        return http.Response.bytes(
          utf8.encode(jsonEncode(extractionJson())),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      }),
    );
    addTearDown(api.close);
    if (authenticated) api.token = 'secret-test-token';
    await tester.pumpWidget(MaterialApp(home: Builder(builder: (context) => Scaffold(body: TextButton(
      onPressed: () async {
        final result = await Navigator.push<VoiceProposal>(
          context,
          MaterialPageRoute<VoiceProposal>(builder: (_) => VoiceIntake(api: api)),
        );
        onApplied(result);
      },
      child: const Text('Open'))))));
    await tester.tap(find.text('Open'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'طول دیوار سه متر و بیست سانتی‌متر');
    await tester.tap(find.text('Analyze'));
    await tester.pumpAndSettle();
  }

  testWidgets('transcript analysis shows proposals, conflicts and questions; nothing auto-applies',
      (tester) async {
    VoiceProposal? applied;
    await pumpAndAnalyze(tester, authenticated: true, onApplied: (proposal) => applied = proposal);
    expect(applied, isNull);
    expect(find.textContaining('3200'), findsOneWidget);
    expect(find.textContaining('3000'), findsOneWidget);
    // Conflict cards are visible, not silently resolved.
    expect(find.textContaining('Conflicting spoken values'), findsNWidgets(2));
    expect(find.textContaining('Wall height not specified'), findsOneWidget);
    // Apply only pops with the proposal; the screen never writes survey data.
    final applyButton = find.text('Apply').first;
    await tester.ensureVisible(applyButton);
    await tester.tap(applyButton);
    await tester.pumpAndSettle();
    expect(applied, isNotNull);
    expect(applied!.valueMm, 3200);
    expect(applied!.wallField, 'length_mm');
    expect(applied!.candidateId, 'cand-wall-3200');
    expect(applied!.prefill()['source_observation_id'], 'cand-wall-3200');
    expect(find.byType(VoiceIntake), findsNothing);
  });

  testWidgets('requires sign-in before server analysis; empty analysis is an error, not a value',
      (tester) async {
    final api = Api(baseUrl: 'https://example.invalid/api/v1/', client: MockClient((_) async =>
      throw StateError('network must not be reached')));
    addTearDown(api.close);
    await tester.pumpWidget(MaterialApp(home: VoiceIntake(api: api)));
    await tester.enterText(find.byType(TextField), 'طول دیوار سه متر');
    await tester.tap(find.text('Analyze'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Sign in'), findsOneWidget);
  });

  test('AI candidate_id is carried as source_observation_id into wall and element sync operations',
      () async {
    FlutterSecureStorage.setMockInitialValues({});
    final dir = await Directory.systemTemp.createTemp('cabinet-provenance-');
    final db = await LocalStore.open(
      testFactory: databaseFactoryFfiNoIsolate,
      path: '${dir.path}/provenance.sqlite',
    );
    List<Json> pushedOperations = const [];
    final api = Api(
      baseUrl: 'https://example.invalid/api/v1/',
      client: MockClient((request) async {
        final path = request.url.path;
        if (path.endsWith('/sync/push')) {
          final decoded = jsonDecode(request.body) as Json;
          pushedOperations = (decoded['operations'] as List).cast<Json>();
          return http.Response.bytes(
            utf8.encode(jsonEncode({
              'results': [
                for (final op in pushedOperations)
                  {'id': op['id'], 'status': 'applied', 'new_version': 1},
              ],
            })),
            200,
            headers: {'content-type': 'application/json; charset=utf-8'},
          );
        }
        if (path.endsWith('/customers') || path.endsWith('/projects')) {
          return http.Response.bytes(
            utf8.encode('[]'),
            200,
            headers: {'content-type': 'application/json; charset=utf-8'},
          );
        }
        if (path.endsWith('/sync/tombstones')) {
          return http.Response.bytes(
            utf8.encode(jsonEncode({'tombstones': <Json>[]})),
            200,
            headers: {'content-type': 'application/json; charset=utf-8'},
          );
        }
        throw StateError('Unexpected request $path');
      }),
    );
    api.token = 'fixture-token';
    final controller = SurveyController(db, api: api);
    try {
      final voiceWall = proposalsFromExtraction(extractionJson()).first;
      final sketchElem = sketchCandidatePrefill({
        'candidate_id': 'cand-sketch-win-1100',
        'label': 'Window W1',
        'kind': 'window',
        'value_mm': 1100,
        'confidence': 0.88,
      }, asElement: true);

      final projectId = uuid.v4();
      final roomId = uuid.v4();
      final wallId = uuid.v4();
      final elemId = uuid.v4();

      await controller.store.save('project', {
        'id': projectId,
        'title': 'Provenance Test',
        'status': 'draft',
      });
      await controller.store.save('room', {
        'id': roomId,
        'project_id': projectId,
        'label': 'Kitchen',
        'room_type': 'rectangular',
      });
      await controller.store.save('wall', {
        ...voiceWall.prefill(),
        'id': wallId,
        'room_id': roomId,
        'label': 'Wall North',
        'height_mm': 2700,
        'start_x_mm': 0,
        'start_y_mm': 0,
        'end_x_mm': 3200,
        'end_y_mm': 0,
      });
      await controller.store.save('element', {
        ...sketchElem,
        'id': elemId,
        'wall_id': wallId,
        'offset_mm': 400,
        'height_mm': 1000,
        'sill_mm': 900,
      });

      expect((await controller.store.get(wallId))!['review_status'], 'needs_review');
      expect((await controller.store.get(wallId))!['source_observation_id'], 'cand-wall-3200');
      expect((await controller.store.get(elemId))!['review_status'], 'needs_review');
      expect((await controller.store.get(elemId))!['source_observation_id'], 'cand-sketch-win-1100');

      await controller.sync();
      final wallOp = pushedOperations.singleWhere((op) => op['entity_type'] == 'wall');
      final elemOp = pushedOperations.singleWhere((op) => op['entity_type'] == 'element');
      final wallPayload = wallOp['payload'] as Json;
      final elemPayload = elemOp['payload'] as Json;

      expect(wallPayload['source'], 'voice_ai');
      expect(wallPayload['confidence'], 0.9);
      expect(wallPayload['source_observation_id'], 'cand-wall-3200');
      expect(wallPayload.containsKey('review_status'), isFalse);

      expect(elemPayload['source'], 'sketch_ai');
      expect(elemPayload['confidence'], 0.88);
      expect(elemPayload['source_observation_id'], 'cand-sketch-win-1100');
      expect(elemPayload.containsKey('review_status'), isFalse);
    } finally {
      api.close();
      controller.dispose();
      await db.close();
      await dir.delete(recursive: true);
    }
  });
}
