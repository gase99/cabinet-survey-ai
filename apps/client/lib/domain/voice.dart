import 'survey.dart';

/// One spoken measurement proposal extracted from a transcript.
///
/// Proposals are never measurements: they only become wall/element values
/// after the user edits and saves them through the normal confirm-first form,
/// which keeps approval state, revision history, and `source_observation_id`
/// provenance intact through to sync.
class VoiceProposal {
  final String label;
  final String? kind;
  final int valueMm;
  final String sourceText;
  final String intent;
  final bool conflict;
  final String? candidateId;
  final double? confidence;

  const VoiceProposal({
    required this.label,
    required this.kind,
    required this.valueMm,
    required this.sourceText,
    required this.intent,
    required this.conflict,
    this.candidateId,
    this.confidence,
  });

  factory VoiceProposal.fromJson(Json observation, {required bool conflict}) {
    final rawId = observation['candidate_id'] ?? observation['id'];
    return VoiceProposal(
      label: '${observation['label'] ?? 'measurement'}',
      kind: observation['kind'] as String?,
      valueMm: observation['value_mm'] as int,
      sourceText: '${observation['source_text'] ?? observation['value_raw'] ?? ''}',
      intent: '${observation['intent'] ?? 'statement'}',
      conflict: conflict,
      candidateId: rawId is String && rawId.isNotEmpty ? rawId : null,
      confidence: (observation['confidence'] as num?)?.toDouble(),
    );
  }

  bool get isCorrection => intent == 'correction';

  /// Wall fields this proposal can prefill, or null when it maps to an element
  /// or stays display-only.
  String? get wallField {
    final tag = (kind ?? label).toLowerCase().trim();
    return switch (tag) {
      'wall_length' || 'length' || 'wall length' => 'length_mm',
      'wall_height' || 'height' || 'wall height' => 'height_mm',
      _ => null,
    };
  }

  /// Element kind this proposal can prefill (window / door), or null.
  String? get elementKind {
    final tag = (kind ?? label).toLowerCase().trim();
    if (tag == 'window' || tag.startsWith('window ')) return 'window';
    if (tag == 'door' || tag.startsWith('door ')) return 'door';
    return null;
  }

  bool get isApplicable => wallField != null || elementKind != null;

  /// Confirm-first prefill: the target form still requires the user to review,
  /// complete and save. Voice-sourced values never skip that form, and carry
  /// `candidate_id` as `source_observation_id` to sync.
  Json prefill() {
    final field = wallField;
    if (field != null) {
      return <String, dynamic>{
        field: valueMm,
        'source': 'voice_ai',
        if (confidence != null) 'confidence': confidence,
        if (candidateId != null) 'source_observation_id': candidateId,
      };
    }
    final elemKind = elementKind;
    if (elemKind != null) {
      return <String, dynamic>{
        'kind': elemKind,
        'width_mm': valueMm,
        'source': 'voice_ai',
        if (confidence != null) 'confidence': confidence,
        if (candidateId != null) 'source_observation_id': candidateId,
      };
    }
    return <String, dynamic>{};
  }
}

/// Build a confirm-first form prefill from an AI sketch observation while
/// carrying `candidate_id` -> `source_observation_id` through to sync.
Json sketchCandidatePrefill(Json observation, {required bool asElement}) {
  final rawId = observation['candidate_id'] ?? observation['id'];
  final candidateId = rawId is String && rawId.isNotEmpty ? rawId : null;
  final confidence = (observation['confidence'] as num?)?.toDouble();
  final value = observation['value_mm'];
  final label = observation['label'];
  final kind = '${observation['kind'] ?? ''}'.toLowerCase();
  if (asElement) {
    final elemKind = kind == 'door' ? 'door' : 'window';
    return <String, dynamic>{
      '_target': 'element',
      if (label is String && label.isNotEmpty) 'label': label,
      'kind': elemKind,
      if (value is int && value > 0) 'width_mm': value,
      'source': 'sketch_ai',
      if (confidence != null) 'confidence': confidence,
      if (candidateId != null) 'source_observation_id': candidateId,
    };
  }
  return <String, dynamic>{
    '_target': 'wall',
    if (label is String && label.isNotEmpty) 'label': label,
    if (value is int && value > 0)
      (kind.contains('height') ? 'height_mm' : 'length_mm'): value,
    'source': 'sketch_ai',
    if (confidence != null) 'confidence': confidence,
    if (candidateId != null) 'source_observation_id': candidateId,
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
        VoiceProposal.fromJson(
          observation,
          conflict: observation['kind'] != null &&
              (valuesByKind['${observation['kind']}']?.length ?? 0) > 1,
        ),
  ];
}

/// Ambiguity and clarification strings shown next to the proposals; the user
/// must resolve them manually, never the parser.
List<String> spokenQuestions(Json extraction) => [
  for (final question in extraction['clarification_questions'] as List? ?? []) '$question',
  for (final ambiguity in extraction['ambiguities'] as List? ?? []) '$ambiguity',
];
