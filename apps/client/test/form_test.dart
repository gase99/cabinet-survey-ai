import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:cabinet_survey_ai/features/measurement_form.dart';
void main() {
  testWidgets('controllers survive route dismissal animation', (tester) async {
    await tester.pumpWidget(MaterialApp(home:Builder(builder:(context) => Scaffold(body:TextButton(
      onPressed:() => showDialog<void>(context:context,builder:(_) => const MeasurementForm(title:'Title',fields:{'title':'Title'})),
      child:const Text('Open'))))));
    await tester.tap(find.text('Open'));await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextFormField),'Kitchen');
    await tester.tap(find.text('Save'));await tester.pumpAndSettle();
    expect(tester.takeException(),isNull);
  });
}
