import 'package:flutter/material.dart';
import '../core/api.dart';
import '../core/l10n.dart';
import '../domain/survey.dart';
import '../domain/voice.dart';

/// Voice intake, phase 1: the transcript is typed or pasted (the same manual
/// text fallback required when speech recognition is unavailable). On-device
/// audio capture arrives in a later phase with its own permission posture.
///
/// Every extracted value is displayed as a proposal with its spoken source
/// quote. Applying a proposal only opens the normal confirm-first form;
/// nothing is written to the survey model from this screen.
class VoiceIntake extends StatefulWidget {
  final Api api;
  const VoiceIntake({super.key, required this.api});
  @override
  State<VoiceIntake> createState() => _VoiceIntakeState();
}

class _VoiceIntakeState extends State<VoiceIntake> {
  final transcript = TextEditingController();
  Json? extraction;
  String? error;
  bool loading = false;

  @override
  void dispose() { transcript.dispose(); super.dispose(); }

  Future<void> analyze() async {
    setState(() { loading = true; error = null; });
    try {
      final text = transcript.text.trim();
      if (text.isEmpty) throw const FormatException('Enter the spoken measurements as text');
      if (widget.api.token == null) throw StateError('Sign in to analyze text on the server');
      final result = await widget.api.parseText(text);
      if (mounted) setState(() => extraction = result);
    } catch (e) {
      if (mounted) setState(() => error = '$e');
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(appBar: AppBar(title: Text(tr(context, 'Voice intake'))),
    body: ListView(padding: const EdgeInsets.all(20), children: [
      Text(tr(context, 'Voice intake hint')),
      const SizedBox(height: 12),
      TextField(controller: transcript, maxLines: 5, keyboardType: TextInputType.multiline,
        decoration: InputDecoration(labelText: tr(context, 'Transcript'),
          border: const OutlineInputBorder())),
      const SizedBox(height: 12),
      FilledButton.icon(onPressed: loading ? null : analyze,
        icon: const Icon(Icons.graphic_eq), label: Text(tr(context, 'Analyze'))),
      if (loading) const Padding(padding: EdgeInsets.all(12), child: LinearProgressIndicator()),
      if (error != null) SelectableText(error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
      const SizedBox(height: 8),
      Text(tr(context, 'AI proposals require review; nothing becomes a measurement without your confirmation.')),
      ..._results(),
    ]));

  List<Widget> _results() {
    final extraction = this.extraction;
    if (extraction == null) return const [];
    final proposals = proposalsFromExtraction(extraction);
    final questions = spokenQuestions(extraction);
    return [
      const Divider(),
      if (proposals.isEmpty) Text(tr(context, 'No measurements detected')),
      for (final proposal in proposals) Card(color: proposal.conflict ? Theme.of(context).colorScheme.errorContainer : null,
        child: ListTile(
          title: Text('${proposal.label}: ${proposal.valueMm} mm'
            '${proposal.isCorrection ? ' · ${tr(context, 'Correction')}' : ''}'),
          subtitle: SelectableText('${proposal.sourceText}\n'
            '${tr(context, 'Review required / نیاز به بازبینی')}'
            '${proposal.conflict ? '\n⚠ ${tr(context, 'Conflicting spoken values; resolve manually.')}' : ''}'),
          trailing: proposal.wallField == null ? null :
            FilledButton.tonal(onPressed: () => Navigator.pop(context, proposal),
              child: Text(tr(context, 'Apply'))))),
      for (final question in questions) Text('• $question'),
      if (extraction['disclaimer'] is String) Text('${extraction['disclaimer']}'),
    ];
  }
}
