import 'dart:typed_data';
import 'package:flutter/material.dart';
import '../core/controller.dart';
import '../core/l10n.dart';
import '../core/store.dart';
import '../domain/survey.dart';

class SketchReview extends StatefulWidget {
  final SurveyController controller;
  final Json photo;
  const SketchReview({super.key,required this.controller,required this.photo});
  @override
  State<SketchReview> createState() => _SketchReviewState();
}
class _SketchReviewState extends State<SketchReview> {
  Json? result;
  String? error;
  bool loading=false;
  int? selected;
  Future<void> analyze() async {
    setState(() {loading=true;error=null;});
    try {
      if(widget.controller.api.token==null) throw StateError('Sign in to use online sketch analysis');
      final reply=await widget.controller.api.sketch(widget.photo['bytes'] as Uint8List,widget.photo['name'] as String);
      await widget.controller.store.cache('proposal',{'id':uuid.v4(),'photo_id':widget.photo['id'],'result':reply});
      if(mounted) setState(() => result=reply);
    } catch(e) {if(mounted) setState(() => error='$e');}
    finally {if(mounted) setState(() => loading=false);}
  }
  @override
  Widget build(BuildContext context) {
    final observations=(result?['observations'] as List? ?? []).cast<Json>();
    return Scaffold(appBar:AppBar(title:Text(tr(context,'Review'))),body:ListView(padding:const EdgeInsets.all(20),children:[
      Text(tr(context,'AI candidates require review; no dimensions are inferred from pixels.')),
      AspectRatio(aspectRatio:1,child:LayoutBuilder(builder:(context,size) => Stack(fit:StackFit.expand,children:[
        Image.memory(widget.photo['bytes'] as Uint8List,fit:BoxFit.fill),
        for(var i=0;i<observations.length;i++) if(observations[i]['source_bbox'] is List)
          _region(observations[i]['source_bbox'] as List,size,i),
      ]))),
      FilledButton(onPressed:loading?null:analyze,child:Text(loading?tr(context,'Working…'):'Analyze sketch / تحلیل طرح')),
      if(error!=null) SelectableText(error!,style:TextStyle(color:Theme.of(context).colorScheme.error)),
      for(var i=0;i<observations.length;i++) Card(child:ListTile(
        selected:selected==i,onTap:() => setState(() => selected=i),
        title:Text('${observations[i]['label']}: ${observations[i]['value_mm']??'?'} mm'),
        subtitle:SelectableText('${observations[i]['source_text']}\n${observations[i]['uncertainty']??''}\nReview required / نیاز به بازبینی'))),
      for(final question in result?['clarification_questions'] as List? ?? []) Text('• $question'),
      for(final ambiguity in result?['ambiguities'] as List? ?? []) Text('⚠ $ambiguity'),
      // Candidates are never applied automatically. Manual entry remains a separate,
      // explicit measurement form, followed by the normal approval operation.
    ]));
  }
  Widget _region(List bbox,BoxConstraints size,int index) {
    if(bbox.length!=4 || bbox.any((v) => v is! num)) return const SizedBox.shrink();
    final x=(bbox[0] as num).toDouble(),y=(bbox[1] as num).toDouble();
    final right=(bbox[2] as num).toDouble(),bottom=(bbox[3] as num).toDouble();
    return Positioned(left:x*size.maxWidth,top:y*size.maxHeight,width:(right-x)*size.maxWidth,height:(bottom-y)*size.maxHeight,
      child:GestureDetector(onTap:() => setState(() => selected=index),child:Container(decoration:BoxDecoration(
        border:Border.all(color:selected==index?Colors.red:Colors.orange,width:3)))));
  }
}
