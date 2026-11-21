import 'dart:convert';
import 'dart:typed_data';
import 'package:sqflite/sqflite.dart';
import 'package:uuid/uuid.dart';
import '../domain/survey.dart';

const uuid = Uuid();

/// A mutation and its outbox record always commit in the same transaction.
/// Store one immutable operation per local revision; never drop a failed operation.
class LocalStore {
  final Database db;
  final String owner;
  LocalStore(this.db, this.owner);
  static Future<void> configure(Database db) async {
    await db.execute('PRAGMA foreign_keys = ON');
  }
  static Future<void> create(Database db, int version) async {
    await db.execute('CREATE TABLE records (owner TEXT NOT NULL, id TEXT NOT NULL, kind TEXT NOT NULL, body TEXT NOT NULL, PRIMARY KEY(owner,id))');
    await db.execute('CREATE TABLE outbox (seq INTEGER PRIMARY KEY AUTOINCREMENT, owner TEXT NOT NULL, id TEXT UNIQUE NOT NULL, body TEXT NOT NULL, state TEXT NOT NULL, result TEXT)');
    await db.execute('CREATE TABLE revisions (seq INTEGER PRIMARY KEY AUTOINCREMENT, owner TEXT NOT NULL, entity_id TEXT NOT NULL, body TEXT NOT NULL, FOREIGN KEY(owner, entity_id) REFERENCES records(owner, id))');
    await db.execute('CREATE TABLE photos (owner TEXT NOT NULL, id TEXT NOT NULL, project_id TEXT NOT NULL, name TEXT NOT NULL, bytes BLOB NOT NULL, PRIMARY KEY(owner,id), FOREIGN KEY(owner, project_id) REFERENCES records(owner, id))');
  }
  // The production provider uses SecureDatabase; this factory seam is for VM tests.
  static Future<Database> open({required DatabaseFactory testFactory, String path = 'cabinet_survey.sqlite'}) async {
    return testFactory.openDatabase(path, options: OpenDatabaseOptions(
      version: 1, onConfigure: configure, onCreate: create));
  }
  Future<List<Json>> list(String kind, {bool includeDeleted = false}) async => (await db.query('records',
    where: 'owner=? AND kind=?', whereArgs: [owner, kind]))
      .map((r) => jsonDecode(r['body'] as String) as Json)
      .where((item) => includeDeleted || item['is_deleted'] != true)
      .toList()
      ..sort((a,b) => '${a['created_at'] ?? a['id']}'.compareTo('${b['created_at'] ?? b['id']}'));
  Future<Json?> get(String id, {bool includeDeleted = false}) async {
    final rows = await db.query('records', where: 'owner=? AND id=?', whereArgs: [owner,id]);
    if (rows.isEmpty) return null;
    final decoded = jsonDecode(rows.single['body'] as String) as Json;
    if (!includeDeleted && decoded['is_deleted'] == true) return null;
    return decoded;
  }
  Future<List<Json>> tombstones([String? kind]) async => (await db.query('records',
    where: kind == null ? 'owner=?' : 'owner=? AND kind=?',
    whereArgs: kind == null ? [owner] : [owner, kind]))
      .map((r) => jsonDecode(r['body'] as String) as Json)
      .where((item) => item['is_deleted'] == true)
      .toList();
  Future<void> save(String kind, Json rawValue) async {
    final value = (kind == 'wall' || kind == 'element') &&
            !rawValue.containsKey('source_observation_id') &&
            rawValue['candidate_id'] != null
        ? <String, dynamic>{...rawValue, 'source_observation_id': rawValue['candidate_id']}
        : rawValue;
    await db.transaction((tx) async {
      final old = await tx.query('records', where: 'owner=? AND id=?', whereArgs: [owner,value['id']]);
      final before = old.isEmpty ? null : jsonDecode(old.single['body'] as String) as Json;
      const fields = {
        'customer': ['name','phone','address','notes'],
        'project': ['title','site_notes','status','customer_id'],
        'room': ['label','room_type','project_id'],
        'wall': ['label','length_mm','height_mm','start_x_mm','start_y_mm','end_x_mm','end_y_mm','room_id','source','confidence','source_observation_id','review_status'],
        'element': ['label','kind','offset_mm','width_mm','height_mm','sill_mm','depth_mm','wall_id','source','confidence','source_observation_id','review_status'],
      };
      final payload = <String,dynamic>{};
      for (final key in fields[kind]!) {
        if (!value.containsKey(key)) continue;
        if (before == null) {
          if (key != 'review_status') payload[key] = value[key];
        } else if (value[key] != before[key] && !['source','confidence','project_id','room_id','wall_id'].contains(key)) {
          payload[key] = value[key];
        }
      }
      // All subsequent local edits depend on the preceding revision, even offline.
      final base = before?['version'] as int? ?? 0;
      final merged = {...?before, ...value};
      if (kind == 'wall' || kind == 'element') {
        final incomplete = kind == 'element'
            ? (merged['height_mm'] == null || merged['sill_mm'] == null)
            : (merged['length_mm'] == null || merged['height_mm'] == null);
        if (before == null) {
          merged['review_status'] = incomplete ? 'incomplete' : 'needs_review';
        } else if (incomplete) {
          merged['review_status'] = 'incomplete';
          if (payload.containsKey('review_status')) payload['review_status'] = 'incomplete';
        } else if (payload.keys.any((k) => k != 'review_status')) {
          merged['review_status'] = 'needs_review';
          if (payload['review_status'] == 'approved') payload.remove('review_status');
        }
      }
      final next = {...merged, 'created_at': before?['created_at'] ?? value['created_at'] ?? DateTime.now().toUtc().toIso8601String(), 'version': base+1};
      final operation = {'id': uuid.v4(), 'entity_type': kind, 'entity_id': value['id'],
        'operation': before == null ? 'create' : 'update', 'payload': payload,
        'base_version': base};
      if (before == null) {
        await tx.insert('records', {'owner': owner, 'id': value['id'], 'kind': kind, 'body': jsonEncode(next)});
        await tx.insert('revisions', {'owner': owner, 'entity_id': value['id'], 'body': jsonEncode(value)});
      } else {
        await tx.insert('revisions', {'owner': owner, 'entity_id': value['id'], 'body': jsonEncode(before)});
        await tx.update('records', {'kind': kind, 'body': jsonEncode(next)}, where: 'owner=? AND id=?', whereArgs: [owner, value['id']]);
      }
      await tx.insert('outbox', {'owner': owner, 'id': operation['id'], 'body': jsonEncode(operation), 'state': 'pending'});
    });
  }
  Future<void> delete(String kind, String id) async {
    await db.transaction((tx) async {
      final old = await tx.query('records', where: 'owner=? AND id=?', whereArgs: [owner, id]);
      if (old.isEmpty) throw StateError('Local record missing');
      final before = jsonDecode(old.single['body'] as String) as Json;
      if (before['is_deleted'] == true) return;
      final base = before['version'] as int? ?? 1;
      final deletedAt = DateTime.now().toUtc().toIso8601String();
      final next = {...before, 'is_deleted': true, 'deleted_at': deletedAt, 'version': base + 1};
      final operation = {'id': uuid.v4(), 'entity_type': kind, 'entity_id': id,
        'operation': 'delete', 'payload': <String, dynamic>{}, 'base_version': base};
      await tx.insert('revisions', {'owner': owner, 'entity_id': id, 'body': jsonEncode(before)});
      await tx.update('records', {'kind': kind, 'body': jsonEncode(next)}, where: 'owner=? AND id=?', whereArgs: [owner, id]);
      await tx.insert('outbox', {'owner': owner, 'id': operation['id'], 'body': jsonEncode(operation), 'state': 'pending'});
    });
  }
  Future<List<Json>> queue() async => (await db.query('outbox', where: 'owner=?',
    whereArgs: [owner], orderBy: 'seq')).map((r) => <String,dynamic>{...r,
      'operation': jsonDecode(r['body'] as String),
      'response': r['result'] == null ? null : jsonDecode(r['result'] as String)}).toList();
  Future<void> result(String id, Json result) async {
    await db.update('outbox', {'state': result['status'], 'result': jsonEncode(result)},
      where: 'owner=? AND id=?', whereArgs: [owner,id]);
  }
  Future<void> cache(String kind, Json value) async {
    // Caller must check the queue before importing remote values.
    await db.transaction((tx) async {
      final queued=await tx.query('outbox',where:'owner=? AND state NOT IN (?,?)',whereArgs:[owner,'applied','resolved']);
      if(queued.any((row) => (jsonDecode(row['body'] as String) as Json)['entity_id']==value['id'])) return;
      final existing = await tx.query('records', columns: ['id'], where: 'owner=? AND id=?', whereArgs: [owner, value['id']]);
      if (existing.isEmpty) {
        await tx.insert('records', {'owner': owner, 'id': value['id'], 'kind': kind, 'body': jsonEncode(value)});
      } else {
        await tx.update('records', {'kind': kind, 'body': jsonEncode(value)}, where: 'owner=? AND id=?', whereArgs: [owner, value['id']]);
      }
    });
  }
  Future<void> applyTombstone(String kind, Json tombstone) async {
    final entityId = (tombstone['entity_id'] ?? tombstone['id']) as String;
    await db.transaction((tx) async {
      final queued = await tx.query('outbox', where: 'owner=? AND state NOT IN (?,?)', whereArgs: [owner, 'applied', 'resolved']);
      if (queued.any((row) => (jsonDecode(row['body'] as String) as Json)['entity_id'] == entityId)) return;
      final existing = await tx.query('records', where: 'owner=? AND id=?', whereArgs: [owner, entityId]);
      final before = existing.isEmpty ? null : jsonDecode(existing.single['body'] as String) as Json;
      final next = {...?before, 'id': entityId, 'is_deleted': true,
        'deleted_at': tombstone['deleted_at'],
        'version': tombstone['version'] ?? ((before?['version'] as int? ?? 0) + 1)};
      if (existing.isEmpty) {
        await tx.insert('records', {'owner': owner, 'id': entityId, 'kind': kind, 'body': jsonEncode(next)});
      } else {
        await tx.update('records', {'kind': kind, 'body': jsonEncode(next)}, where: 'owner=? AND id=?', whereArgs: [owner, entityId]);
      }
    });
  }
  Future<void> keepServer(Json row) async {
    final op = row['operation'] as Json;
    final response = row['response'] as Json;
    final server = response['server_payload'] as Json;
    await db.transaction((tx) async {
      final current = await tx.query('records', where: 'owner=? AND id=?', whereArgs: [owner,op['entity_id']]);
      if (current.isNotEmpty) await tx.insert('revisions', {'owner': owner,
        'entity_id': op['entity_id'], 'body': current.single['body']});
      await tx.update('records', {'body': jsonEncode(server)}, where: 'owner=? AND id=?', whereArgs: [owner,op['entity_id']]);
      // Explicit resolution supersedes all dependent operations for this entity.
      final pending = await tx.query('outbox', where: 'owner=?', whereArgs: [owner]);
      for (final item in pending) {
        final operation = jsonDecode(item['body'] as String) as Json;
        if (operation['entity_id'] == op['entity_id'] && item['state'] != 'applied') {
          await tx.update('outbox', {'state': 'resolved'}, where: 'owner=? AND id=?', whereArgs: [owner,item['id']]);
        }
      }
    });
  }
  Future<void> keepLocal(Json row) async {
    final op=row['operation'] as Json;
    final response=row['response'] as Json;
    final current=await get(op['entity_id'] as String, includeDeleted: true);
    if(current==null) throw StateError('Local record missing');
    final kind=op['entity_type'] as String;
    final base=response['server_version'] as int;
    const fields={
      'customer':['name','phone','address','notes'],
      'project':['title','site_notes','customer_id','status'],
      'room':['label','room_type'],
      'wall':['label','length_mm','height_mm','start_x_mm','start_y_mm','end_x_mm','end_y_mm','source_observation_id'],
      'element':['label','kind','offset_mm','width_mm','height_mm','sill_mm','depth_mm','source_observation_id'],
    };
    final isDelete = op['operation'] == 'delete' || current['is_deleted'] == true;
    final payload = isDelete
        ? <String, dynamic>{}
        : <String,dynamic>{for(final key in fields[kind]!) if(current.containsKey(key)) key:current[key]};
    if(!isDelete && (kind=='wall' || kind=='element')) payload['review_status']='needs_review';
    final replacement={'id':uuid.v4(),'entity_type':kind,'entity_id':op['entity_id'],
      'operation': isDelete ? 'delete' : 'update','payload':payload,'base_version':base};
    await db.transaction((tx) async {
      await tx.insert('revisions',{'owner':owner,'entity_id':op['entity_id'],'body':jsonEncode(response['server_payload'])});
      await tx.insert('revisions',{'owner':owner,'entity_id':op['entity_id'],'body':jsonEncode(current)});
      final pending=await tx.query('outbox',where:'owner=?',whereArgs:[owner]);
      for(final item in pending) {
        final operation=jsonDecode(item['body'] as String) as Json;
        if(operation['entity_id']==op['entity_id'] && item['state']!='applied') {
          await tx.update('outbox',{'state':'resolved'},where:'owner=? AND id=?',whereArgs:[owner,item['id']]);
        }
      }
      await tx.update('records',{'body':jsonEncode({...current,'version':base+1,
        if(!isDelete && (kind=='wall' || kind=='element')) 'review_status':'needs_review'})},
        where:'owner=? AND id=?',whereArgs:[owner,op['entity_id']]);
      await tx.insert('outbox',{'owner':owner,'id':replacement['id'],'body':jsonEncode(replacement),'state':'pending'});
    });
  }
  Future<void> photo(String project, String name, Uint8List bytes) async {
    if (bytes.length > 15*1024*1024) throw const FormatException('Image exceeds 15 MB');
    await db.insert('photos', {'owner': owner, 'id': uuid.v4(), 'project_id': project,
      'name': name, 'bytes': bytes});
  }
  Future<List<Json>> photos(String project) async => (await db.query('photos',
    where: 'owner=? AND project_id=?', whereArgs: [owner, project])).map((e) => Map<String,dynamic>.from(e)).toList();
}
