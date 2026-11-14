import 'survey.dart';

/// One spoken measurement proposal extracted from a transcript.
///
/// Proposals are never measurements: they only become wall/element values
/// after the user edits and saves them through the normal confirm-first form,
/// which keeps approval state and revision history intact.
class VoiceProposal {
  final String label;
  final String? kind;
  final int valueMm;
  final String sourceText;
  final String intent;
  final bool conflict;

  const VoiceProposal({required this.label, required this.kind, required this.valueMm,
    required this.sourceText, required this.intent, required this.conflict});

  factory VoiceProposal.fromJson(Json observation, {required bool conflict}) =>
    VoiceProposal(label: '${observation['label'] ?? 'measurement'}',
      kind: observation['kind'] as String?,
      valueMm: observation['value_mm'] as int,
      sourceText: '${observation['source_text'] ?? observation['value_raw'] ?? ''}',
      intent: '${observation['intent'] ?? 'statement'}',
      conflict: conflict);

  bool get isCorrection => intent == 'correction';

  /// Wall fields this proposal can prefill, or null when it only informs
  /// (cabinet depths belong to elements and stay display-only in this phase).
  String? get wallField => switch (kind) {
    'wall_length' || 'length' => 'length_mm',
    'wall_height' || 'height' => 'height_mm',
    _ => null,
  };

  /// Confirm-first prefill: the target form still requires the user to review,
  /// complete and save. Voice-sourced values never skip that form.
  Json prefill() => {
    if (wallField != null) wallField!: valueMm,
  };
}

/// Deterministic client-side mapping of the backend extraction payload.
///
/// Conflict rule mirrors the backend: the same kind spoken with different
/// values is a conflict and is displayed, never auto-resolved.
List<VoiceProposal> proposalsFromExtraction(Json extraction) {
  final valuesByKind = <String, Set<int>>{};
  final observations = (extraction['observations'] as List? ?? []).cast<Json>();
  for (final observation in observations) {
    if (observation['value_mm'] is! int) continue;
    final kind = '${observation['kind'] ?? ''}';
    if (kind.isEmpty) continue;
    valuesByKind.putIfAbsent(kind, () => <int>{}).add(observation['value_mm'] as int);
  }
  return [
    for (final observation in observations)
      if (observation['value_mm'] is int)
        VoiceProposal.fromJson(observation,
          conflict: observation['kind'] != null &&
            (valuesByKind['${observation['kind']}']?.length ?? 0) > 1),
  ];
}

/// Ambiguity and clarification strings shown next to the proposals; the user
/// must resolve them manually, never the parser.
List<String> spokenQuestions(Json extraction) => [
  for (final question in extraction['clarification_questions'] as List? ?? []) '$question',
  for (final ambiguity in extraction['ambiguities'] as List? ?? []) '$ambiguity',
];
