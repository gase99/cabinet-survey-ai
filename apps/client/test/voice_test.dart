import 'package:flutter_test/flutter_test.dart';
import 'package:cabinet_survey_ai/domain/survey.dart';
import 'package:cabinet_survey_ai/domain/voice.dart';

Json observation(String kind, int valueMm, {String intent = 'statement'}) => {
  'label': kind, 'kind': kind, 'value_mm': valueMm, 'unit': 'mm',
  'source_text': 'spoken quote', 'intent': intent, 'needs_review': true,
};

void main() {
  test('proposals map spoken kinds to wall fields', () {
    final proposals = proposalsFromExtraction({'observations': [
      observation('wall_length', 3200),
      observation('wall_height', 2700),
      observation('base_cabinet_depth', 600),
    ]});
    expect(proposals.length, 3);
    expect(proposals[0].wallField, 'length_mm');
    expect(proposals[0].prefill(), {'length_mm': 3200});
    expect(proposals[1].wallField, 'height_mm');
    expect(proposals[1].prefill(), {'height_mm': 2700});
    // Cabinet depths stay display-only in this phase; they never prefill a wall.
    expect(proposals[2].wallField, isNull);
    expect(proposals[2].prefill(), isEmpty);
  });

  test('same kind with different values is a conflict on every member', () {
    final proposals = proposalsFromExtraction({'observations': [
      observation('wall_length', 3000), observation('wall_length', 3200),
    ]});
    expect(proposals.every((p) => p.conflict), isTrue);
  });

  test('agreement on the same value is not a conflict', () {
    final proposals = proposalsFromExtraction({'observations': [
      observation('wall_length', 3200), observation('wall_length', 3200),
    ]});
    expect(proposals.every((p) => p.conflict), isFalse);
  });

  test('correction intent is preserved, never silently applied', () {
    final proposals = proposalsFromExtraction({'observations': [
      observation('wall_length', 3400, intent: 'correction'),
    ]});
    expect(proposals.single.isCorrection, isTrue);
  });

  test('proposals without integer values are skipped', () {
    final proposals = proposalsFromExtraction({'observations': [
      {'kind': 'wall_length', 'value_mm': null, 'label': 'x'},
    ]});
    expect(proposals, isEmpty);
  });

  test('spoken questions surface ambiguities and clarifications', () {
    final questions = spokenQuestions({
      'clarification_questions': ['Wall height not specified — please provide wall height(s).'],
      'ambiguities': [{'type': 'elided_tail_unit', 'detail': 'confirm the total'}],
    });
    expect(questions, hasLength(2));
    expect(questions.first, contains('Wall height'));
  });
}
