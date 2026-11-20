import 'package:flutter/material.dart';
import '../core/l10n.dart';
import '../domain/survey.dart';

/// Controllers belong to the dialog route, including its exit animation.
class MeasurementForm extends StatefulWidget {
  final String title;
  final Map<String,String> fields;
  final Json? initial;
  final Set<String> numeric,optional,signed,zero;
  const MeasurementForm({super.key,required this.title,required this.fields,this.initial,
    this.numeric=const {},this.optional=const {},this.signed=const {},this.zero=const {}});
  @override
  State<MeasurementForm> createState() => _MeasurementFormState();
}
class _MeasurementFormState extends State<MeasurementForm> {
  final key=GlobalKey<FormState>();
  late final Map<String,TextEditingController> controllers;
  @override
  void initState() {
    super.initState();
    controllers={for(final key in widget.fields.keys) key:TextEditingController(text:'${widget.initial?[key]??''}')};
  }
  @override
  void dispose() { for(final c in controllers.values) { c.dispose(); } super.dispose(); }
  String? validate(String key,String? value) {
    if((value??'').trim().isEmpty) return widget.optional.contains(key)?null:tr(context,'Required');
    if(widget.numeric.contains(key)) {
      try { parse(key,value!.trim()); }
      catch(_) { return tr(context,'Enter an integer dimension in mm'); }
    }
    return null;
  }
  int parse(String key,String text) {
    if(widget.signed.contains(key) && text.startsWith('-')) return -millimetres(text.substring(1),allowZero:true);
    return millimetres(text,allowZero:widget.signed.contains(key)||widget.zero.contains(key));
  }
  void save() {
    if(!key.currentState!.validate()) return;
    final value=<String,dynamic>{};
    for(final entry in controllers.entries) {
      final text=entry.value.text.trim();
      value[entry.key]=text.isEmpty && widget.optional.contains(entry.key) ? null :
        widget.numeric.contains(entry.key) ? parse(entry.key,text) : text;
    }
    Navigator.pop(context,value);
  }
  @override
  Widget build(BuildContext context) => AlertDialog(title:Text(tr(context,widget.title)),
    content:SizedBox(width:480,child:Form(key:key,child:SingleChildScrollView(child:Column(mainAxisSize:MainAxisSize.min,
      children:[for(final entry in widget.fields.entries) Padding(padding:const EdgeInsets.only(bottom:12),child:TextFormField(
        controller:controllers[entry.key],obscureText:entry.key=='password',
        keyboardType:widget.numeric.contains(entry.key)?const TextInputType.numberWithOptions(signed:true):TextInputType.text,
        decoration:InputDecoration(labelText:tr(context,entry.value),border:const OutlineInputBorder()),
        validator:(value) => validate(entry.key,value)))])))),
    actions:[TextButton(onPressed:() => Navigator.pop(context),child:Text(tr(context,'Cancel'))),
      FilledButton(onPressed:save,child:Text(tr(context,'Save')))]);
}
