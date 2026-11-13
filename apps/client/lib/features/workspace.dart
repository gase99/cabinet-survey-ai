import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:file_saver/file_saver.dart';
import '../core/controller.dart';
import '../core/store.dart';
import '../core/l10n.dart';
import '../domain/survey.dart';
import 'drawing.dart';
import 'sketch_review.dart';

class Workspace extends StatefulWidget {
  final SurveyController controller;
  final VoidCallback toggleLocale;
  const Workspace({super.key, required this.controller, required this.toggleLocale});
  @override
  State<Workspace> createState() => _WorkspaceState();
}
class _WorkspaceState extends State<Workspace> {
  SurveyController get c => widget.controller;
  String? projectId, roomId;
  String search = '';
  bool busy = false;
  List<Json> projects = [], rooms = [], walls = [], elements = [], photos = [], queue = [];
  final undo = <Json>[], redo = <Json>[];
  @override
  void initState() { super.initState(); initialize(); }
  Future<void> initialize() async { await c.restore(); await reload(); }
  Future<void> reload() async {
    final p = await c.store.list('project');
    final r = await c.store.list('room');
    final w = await c.store.list('wall');
    final e = await c.store.list('element');
    final q = await c.store.queue();
    final images = projectId == null ? <Json>[] : await c.store.photos(projectId!);
    if (!mounted) return;
    setState(() {
      projects=p; rooms=r.where((v) => v['project_id']==projectId).toList();
      walls=w.where((v) => v['room_id']==roomId).toList();
      elements=e.where((v) => walls.any((wall) => wall['id']==v['wall_id'])).toList();
      photos=images; queue=q;
    });
  }
  Future<void> run(Future<void> Function() work) async {
    if (busy) return;
    setState(() => busy=true);
    try { await work(); await reload(); }
    catch (error) { if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content:Text('$error'))); }
    finally { if (mounted) setState(() => busy=false); }
  }
  Future<Json?> form(String title, Map<String,String> fields, {Json? initial, Set<String> numeric = const {},
      Set<String> optional = const {}, Set<String> signed = const {}, Set<String> zero = const {}}) async {
    final key=GlobalKey<FormState>();
    final controllers = {for(final entry in fields.entries) entry.key: TextEditingController(text:'${initial?[entry.key] ?? ''}')};
    try {
      return await showDialog<Json>(context:context, builder:(dialog) => AlertDialog(
        title:Text(tr(context,title)), content:SizedBox(width:480,child:Form(key:key,child:SingleChildScrollView(
          child:Column(mainAxisSize:MainAxisSize.min,children:[for(final entry in fields.entries)
            Padding(padding:const EdgeInsets.only(bottom:12),child:TextFormField(
              controller:controllers[entry.key], obscureText:entry.key=='password', decoration:InputDecoration(labelText:tr(context,entry.value),border:const OutlineInputBorder()),
              keyboardType:numeric.contains(entry.key) ? const TextInputType.numberWithOptions(signed:true) : TextInputType.text,
              validator:(value) {
                if ((value??'').trim().isEmpty) return optional.contains(entry.key) ? null : tr(context,'Required');
                if (numeric.contains(entry.key)) {
                  try {
                    if (signed.contains(entry.key)) {
                      final s=value!.trim(); millimetres(s.startsWith('-') ? s.substring(1) : s,allowZero:true);
                    } else { millimetres(value!,allowZero:zero.contains(entry.key)); }
                  } catch (_) { return tr(context,'Enter an integer dimension in mm'); }
                }
                return null;
              }))])))),
        actions:[TextButton(onPressed:() => Navigator.pop(dialog),child:Text(tr(context,'Cancel'))),
          FilledButton(onPressed:() {
            if(!key.currentState!.validate()) return;
            final value=<String,dynamic>{};
            for(final entry in controllers.entries) {
              final text=entry.value.text.trim();
              if(text.isEmpty && optional.contains(entry.key)) { value[entry.key]=null; continue; }
              if(numeric.contains(entry.key)) {
                value[entry.key]=text.startsWith('-') && signed.contains(entry.key)
                  ? -millimetres(text.substring(1),allowZero:true) : millimetres(text,allowZero:zero.contains(entry.key));
              } else { value[entry.key]=text; }
            }
            Navigator.pop(dialog,value);
          },child:Text(tr(context,'Save')))]));
    } finally { for(final ctrl in controllers.values) { ctrl.dispose(); } }
  }
  Future<void> login(bool register) async {
    final values=await form(register?'Register':'Sign in',{
      if(register) 'name':'Name','email':'Email','password':'Password'});
    if(values==null) return;
    await run(() async {
      await c.login(values['email'] as String,values['password'] as String,name:values['name'] as String?);
      projectId=null; roomId=null; undo.clear(); redo.clear();
    });
  }
  Future<void> editProject([Json? project]) async {
    final value=await form(project==null?'New project':'Review',{'title':'Title','site_notes':'Notes'},initial:project,optional:{'site_notes'});
    if(value==null) return;
    await run(() => c.store.save('project', {...?project,...value,'id':project?['id']??uuid.v4(),'status':project?['status']??'draft'}));
  }
  Future<void> customer(Json project) async {
    final old=project['customer_id']==null ? null : await c.store.get(project['customer_id'] as String);
    if(!mounted) return;
    final value=await form('Customer name',{'name':'Customer name','phone':'Phone','address':'Address'},initial:old,optional:{'phone','address'});
    if(value==null) return;
    await run(() async {
      final id=old?['id']??uuid.v4();
      await c.store.save('customer', {...?old,...value,'id':id});
      await c.store.save('project',{...project,'customer_id':id});
    });
  }
  Future<void> addRoom() async {
    final value=await form('Add room',{'label':'Label'});
    if(value==null) return;
    await run(() => c.store.save('room', {...value,'id':uuid.v4(),'project_id':projectId,'room_type':'irregular'}));
  }
  Future<void> editWall([Json? wall]) async {
    final value=await form(wall==null?'Add wall':'Review',{
      'label':'Label','length_mm':'Length (mm)','height_mm':'Height (mm)',
      'start_x_mm':'Start X (mm)','start_y_mm':'Start Y (mm)',
      'end_x_mm':'End X (mm)','end_y_mm':'End Y (mm)'},initial:wall,
      numeric:{'length_mm','height_mm','start_x_mm','start_y_mm','end_x_mm','end_y_mm'},
      signed:{'start_x_mm','start_y_mm','end_x_mm','end_y_mm'});
    if(value==null) return;
    await run(() async {
      final next={...?wall,...value,'id':wall?['id']??uuid.v4(),'room_id':roomId,
        'source':wall?['source']??'manual','review_status':wall==null?'approved':'needs_review'};
      final candidate=SurveyWall.fromJson(next);
      if(candidate.length>50000 || candidate.height>10000) throw const FormatException('Wall dimensions exceed supported bounds');
      if(wall!=null) {undo.add({'kind':'wall','before':wall,'after':next}); redo.clear();}
      await c.store.save('wall',next);
    });
  }
  Future<void> editElement(Json wall,[Json? element]) async {
    final value=await form(element==null?'Add element':'Review',{
      'label':'Label','kind':'Kind','offset_mm':'Offset (mm)','width_mm':'Width (mm)',
      'height_mm':'Height (mm)','sill_mm':'Sill (mm)'},initial:element,
      numeric:{'offset_mm','width_mm','height_mm','sill_mm'},optional:{'height_mm','sill_mm'},zero:{'offset_mm','sill_mm'});
    if(value==null) return;
    await run(() async {
      const kinds=['window','door','column','beam','gas_pipe','water_pipe','drain','electrical','switch','socket','ventilation','recess','protrusion','custom'];
      if(!kinds.contains(value['kind'])) throw FormatException('Kind: ${kinds.join(', ')}');
      final next={...?element,...value,'id':element?['id']??uuid.v4(),'wall_id':wall['id'],
        'source':element?['source']??'manual','review_status':element==null?'approved':'needs_review'};
      final errors=validateRoom([SurveyWall.fromJson(wall)], [
        ...elements.where((e) => e['id']!=next['id']),next])
        .where((e) => e.contains('bounds') || e.contains('overlaps')).toList();
      if(errors.isNotEmpty) throw FormatException(errors.join('\n'));
      if(element!=null) {undo.add({'kind':'element','before':element,'after':next}); redo.clear();}
      await c.store.save('element',next);
    });
  }
  Future<void> history(bool forward) async {
    final source=forward?redo:undo, target=forward?undo:redo;
    if(source.isEmpty) return;
    final edit=source.last;
    await run(() async {
      final value=Map<String,dynamic>.from(edit[forward?'after':'before'] as Json);
      value['review_status']='needs_review';
      await c.store.save(edit['kind'] as String,value);
      source.removeLast(); target.add(edit);
    });
  }
  Future<void> photo(ImageSource source) async {
    await run(() async {
      final picked=await ImagePicker().pickImage(source:source,maxWidth:4096,maxHeight:4096);
      if(picked!=null) await c.store.photo(projectId!,picked.name,await picked.readAsBytes());
    });
  }
  Future<void> export(Json project) async {
    final value=await form('Export',{'format':'PDF / PNG','layout':'A4 / A3'},initial:{'format':'pdf','layout':'A4'});
    if(value==null) return;
    await run(() async {
      if(c.api.token==null) throw StateError('Sign in and synchronize before exporting');
      await c.sync();
      if((await c.store.queue()).any((r) => r['state']!='applied' && r['state']!='resolved')) throw StateError('Resolve pending changes before exporting');
      final format=(value['format'] as String).toLowerCase(), layout=(value['layout'] as String).toUpperCase();
      if(!['pdf','png'].contains(format) || !['A4','A3'].contains(layout)) throw const FormatException('Choose pdf/png and A4/A3');
      final job=await c.api.request('POST','exports/${project['id']}',{'format':format,'layout':layout}) as Json;
      final bytes=await c.api.bytes('exports/${job['id']}/download');
      await FileSaver.instance.saveFile(name:'survey-${project['id']}',bytes:bytes,ext:format,
        mimeType:format=='pdf'?MimeType.pdf:MimeType.png);
    });
  }
  Future<void> telegram() async {
    await run(() async {
      final status=await c.api.request('GET','telegram/link-status') as Json;
      final Json response=status['linked']==true ? status : await c.api.request('POST','telegram/pairing-code',{}) as Json;
      if(!mounted) return;
      await showDialog<void>(context:context,builder:(d) => AlertDialog(title:const Text('Telegram'),
        content:SelectableText(status['linked']==true ? 'Linked: ${response['telegram_username']??response['telegram_chat_id']}'
          : 'Send /pair ${response['code']} to your workshop bot.\nExpires: ${response['expires_at']}'),
        actions:[TextButton(onPressed:() => Navigator.pop(d),child:const Text('OK'))]));
    });
  }
  Future<void> sendTelegram(Json project) async {
    await run(() async {
      final jobs=await c.api.request('GET','exports?project_id=${project['id']}') as List;
      if(!mounted) return;
      final selected=await showDialog<String>(context:context,builder:(d) => SimpleDialog(title:const Text('Send approved export to Telegram'),
        children:[for(final raw in jobs) if((raw as Json)['status']=='done') SimpleDialogOption(
          onPressed:() => Navigator.pop(d,raw['id'] as String),child:Text('${raw['format']} ${raw['layout']} · ${raw['created_at']}'))]));
      if(selected==null) return;
      final receipt=await c.api.request('POST','telegram/send',{'export_job_id':selected});
      if(mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content:Text('$receipt')));
    });
  }
  @override
  Widget build(BuildContext context) {
    final active=c.email!=null || c.offline;
    final project=projects.where((p) => p['id']==projectId).firstOrNull;
    return Scaffold(appBar:AppBar(title:Text(project?['title'] as String? ?? tr(context,'Cabinet Survey AI')),
      leading:projectId==null?null:IconButton(icon:const Icon(Icons.arrow_back),onPressed:() async {
        setState(() {if(roomId!=null) {roomId=null;} else {projectId=null;} undo.clear(); redo.clear();}); await reload();}),
      actions:[IconButton(onPressed:widget.toggleLocale,icon:const Icon(Icons.translate)),
        if(active) IconButton(tooltip:tr(context,'Sign out'),onPressed:busy?null:() => run(() async {await c.logout(); projectId=null; roomId=null;}),icon:const Icon(Icons.logout))]),
      body:AbsorbPointer(absorbing:busy,child:Column(children:[if(busy) const LinearProgressIndicator(),
        Expanded(child:Center(child:ConstrainedBox(constraints:const BoxConstraints(maxWidth:1100),child:
          !active ? loginScreen() : ListView(padding:const EdgeInsets.all(20),children:[
            Text(c.email??tr(context,'Offline device workspace')),
            if(projectId==null) ...dashboard()
            else if(project!=null && roomId==null) ...projectScreen(project)
            else if(roomId!=null) ...roomScreen(),
          ]))))])));
  }
  Widget loginScreen() => SingleChildScrollView(padding:const EdgeInsets.all(32),child:Column(mainAxisSize:MainAxisSize.min,children:[
    const Icon(Icons.architecture,size:72),const SizedBox(height:24),
    FilledButton(onPressed:() => login(false),child:Text(tr(context,'Sign in'))),
    TextButton(onPressed:() => login(true),child:Text(tr(context,'Register'))),
    OutlinedButton(onPressed:() {c.captureOffline(); reload();},child:Text(tr(context,'Capture offline'))),
    const SizedBox(height:24),Text(tr(context,'AI candidates require review; no dimensions are inferred from pixels.'))]));
  List<Widget> dashboard() => [
    Row(children:[Expanded(child:Text(tr(context,'Projects'),style:Theme.of(context).textTheme.headlineMedium)),
      FilledButton.icon(onPressed:() => editProject(),icon:const Icon(Icons.add),label:Text(tr(context,'New project')))]),
    TextField(decoration:InputDecoration(labelText:tr(context,'Search'),prefixIcon:const Icon(Icons.search)),onChanged:(v) => setState(() => search=v)),
    const SizedBox(height:16),
    if(projects.isEmpty) Text(tr(context,'No projects yet')),
    for(final p in projects.where((p) => '${p['title']}'.toLowerCase().contains(search.toLowerCase())))
      Card(child:ListTile(title:Text(p['title'] as String),subtitle:Text('${p['status']} · v${p['version']}'),
        onTap:() async {projectId=p['id'] as String; roomId=null; await reload();},
        trailing:IconButton(icon:const Icon(Icons.edit_outlined),onPressed:() => editProject(p)))),
    const Divider(),
    FilledButton.tonalIcon(onPressed:c.api.token==null?null:() => run(c.sync),icon:const Icon(Icons.sync),label:Text(tr(context,'Sync'))),
    OutlinedButton(onPressed:c.api.token==null?null:telegram,child:const Text('Telegram')) ,
    Text('${tr(context,'Pending changes')}: ${queue.where((q) => q['state']!='applied' && q['state']!='resolved').length}'),
    for(final row in queue.where((q) => q['state']=='conflict' || q['state']=='failed'))
      Card(child:Padding(padding:const EdgeInsets.all(12),child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
        SelectableText('${row['state']}\n${row['operation']}\n${row['response']}'),
        if(row['state']=='conflict') TextButton(onPressed:() async {
          final yes=await showDialog<bool>(context:context,builder:(d) => AlertDialog(title:Text(tr(context,'Keep server')),
            content:const Text('Local measurements will be preserved in revision history. Replace this entity with the server version?'),
            actions:[TextButton(onPressed:() => Navigator.pop(d,false),child:Text(tr(context,'Cancel'))),
              FilledButton(onPressed:() => Navigator.pop(d,true),child:Text(tr(context,'Keep server')))]));
          if(yes==true) await run(() => c.store.keepServer(row));
        },child:Text(tr(context,'Keep server'))),
      ]))),
  ];
  List<Widget> projectScreen(Json project) => [
    Wrap(spacing:8,children:[OutlinedButton(onPressed:() => editProject(project),child:Text(tr(context,'Review'))),
      OutlinedButton(onPressed:() => customer(project),child:Text(tr(context,'Customer name'))),
      OutlinedButton(onPressed:() => run(() => c.store.save('project',{...project,'status':project['status']=='archived'?'draft':'archived'})),
        child:Text(tr(context,project['status']=='archived'?'Restore':'Archive'))),
      OutlinedButton(onPressed:() => export(project),child:Text(tr(context,'Export'))),
      OutlinedButton(onPressed:c.api.token==null?null:() => sendTelegram(project),child:const Text('Telegram'))]),
    Text('${project['site_notes']??''}'),
    ListTile(title:Text(tr(context,'Rooms')),trailing:IconButton(onPressed:addRoom,icon:const Icon(Icons.add))),
    for(final room in rooms) Card(child:ListTile(title:Text(room['label'] as String),onTap:() async {roomId=room['id'] as String; await reload();})),
    const Divider(),Text(tr(context,'Photos')),
    Wrap(spacing:8,children:[OutlinedButton.icon(onPressed:() => photo(ImageSource.camera),icon:const Icon(Icons.camera_alt),label:Text(tr(context,'Camera'))),
      OutlinedButton.icon(onPressed:() => photo(ImageSource.gallery),icon:const Icon(Icons.photo_library),label:Text(tr(context,'Gallery')))]),
    Text(tr(context,'AI candidates require review; no dimensions are inferred from pixels.')),
    for(final image in photos) Card(child:Column(children:[
      Image.memory(image['bytes'] as Uint8List,height:240,fit:BoxFit.contain),
      TextButton(onPressed:() => Navigator.push(context,MaterialPageRoute<void>(builder:(_) => SketchReview(controller:c,photo:image))),
        child:Text(tr(context,'Review')))])),
  ];
  List<Widget> roomScreen() => [
    Wrap(spacing:8,children:[FilledButton.icon(onPressed:() => editWall(),icon:const Icon(Icons.add),label:Text(tr(context,'Add wall'))),
      IconButton(tooltip:tr(context,'Undo'),onPressed:undo.isEmpty?null:() => history(false),icon:const Icon(Icons.undo)),
      IconButton(tooltip:tr(context,'Redo'),onPressed:redo.isEmpty?null:() => history(true),icon:const Icon(Icons.redo))]),
    if(walls.isEmpty) Text(tr(context,'No walls yet')),
    for(final wall in walls) Card(child:Padding(padding:const EdgeInsets.all(12),child:Column(children:[
      ListTile(title:Text('${wall['label']} · ${wall['length_mm']} × ${wall['height_mm']} mm'),subtitle:Text('${wall['review_status']}'),
        trailing:IconButton(onPressed:() => editWall(wall),icon:const Icon(Icons.edit))),
      if(wall['review_status']!='approved') TextButton(onPressed:() => run(() => c.store.save('wall',{...wall,'review_status':'approved'})),child:Text(tr(context,'Approve'))),
      for(final e in elements.where((e) => e['wall_id']==wall['id'])) ListTile(title:Text('${e['label']} (${e['kind']})'),
        subtitle:Text('${e['offset_mm']} / ${e['width_mm']} mm · ${e['review_status']}'),
        onTap:() => editElement(wall,e),trailing:e['review_status']=='approved'?null:TextButton(
          onPressed:() => run(() => c.store.save('element',{...e,'review_status':'approved'})),child:Text(tr(context,'Approve')))),
      OutlinedButton(onPressed:() => editElement(wall),child:Text(tr(context,'Add element'))),
    ]))),
    const Divider(),DrawingView(walls:walls,elements:elements,edit:editWall),
  ];
}
