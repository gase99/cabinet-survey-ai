import 'dart:typed_data';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:cabinet_survey_ai/core/store.dart';
void main() {
  sqfliteFfiInit();
  test('atomic local revisions and durable ordered outbox are account scoped',() async {
    final db=await LocalStore.open(testFactory:databaseFactoryFfiNoIsolate,path:inMemoryDatabasePath);
    final store=LocalStore(db,'one'), other=LocalStore(db,'two');
    await store.save('project',{'id':'p','title':'First','status':'draft'});
    await store.save('project',{'id':'p','title':'Second','status':'draft'});
    final queue=await store.queue();
    expect(queue.length,2);
    expect(queue[0]['operation']['operation'],'create');
    expect(queue[1]['operation']['base_version'],1);
    expect(queue[1]['operation']['payload'],{'title':'Second'});
    expect((await store.get('p'))!['version'],2);
    expect(await other.list('project'),isEmpty);
    expect(await other.queue(),isEmpty);
    await db.close();
  });
  test('explicit server resolution preserves local revision history',() async {
    final db=await LocalStore.open(testFactory:databaseFactoryFfiNoIsolate,path:inMemoryDatabasePath);
    final store=LocalStore(db,'one');
    await store.cache('project',{'id':'p','title':'Server','version':1});
    await store.save('project',{'id':'p','title':'Local'});
    var queue=await store.queue();
    await store.result(queue.single['id'] as String,{'status':'conflict',
      'server_payload':{'id':'p','title':'Other device','version':2},'server_version':2});
    queue=await store.queue();
    await store.keepServer(queue.single);
    expect((await store.get('p'))!['title'],'Other device');
    expect((await store.queue()).single['state'],'resolved');
    final revisions=await db.query('revisions');
    expect(revisions.length,2);
    expect(revisions.last['body'],contains('Local'));
    await db.close();
  });
  test('explicit keep-local creates a new rebased operation, preserving receipts',() async {
    final db=await LocalStore.open(testFactory:databaseFactoryFfiNoIsolate,path:inMemoryDatabasePath);
    final store=LocalStore(db,'one');
    await store.cache('project',{'id':'p','title':'Server','version':1});
    await store.save('project',{'id':'p','title':'Local'});
    var rows=await store.queue();
    await store.result(rows.single['id'] as String,{'status':'conflict','server_version':3,
      'server_payload':{'id':'p','title':'Remote','version':3}});
    rows=await store.queue();
    await store.keepLocal(rows.single);
    rows=await store.queue();
    expect(rows.first['state'],'resolved');
    expect(rows.last['state'],'pending');
    expect(rows.last['operation']['base_version'],3);
    expect(rows.last['operation']['payload']['title'],'Local');
    expect(rows.last['id'],isNot(rows.first['id']));
    expect((await store.get('p'))!['version'],4);
    await db.close();
  });

  test('snapshot import never overwrites a newly queued local edit',() async {
    final db=await LocalStore.open(testFactory:databaseFactoryFfiNoIsolate,path:inMemoryDatabasePath);
    final store=LocalStore(db,'one');
    await store.cache('project',{'id':'p','title':'Original','status':'draft','version':1});
    await store.save('project',{'id':'p','title':'Measurement notes'});
    await store.cache('project',{'id':'p','title':'Stale response','status':'archived','version':1});
    expect((await store.get('p'))!['title'],'Measurement notes');
    expect((await store.get('p'))!['status'],'draft');
    await db.close();
  });

  test('manual wall and element saves are never auto-approved and missing dimensions mark incomplete',() async {
    final db=await LocalStore.open(testFactory:databaseFactoryFfiNoIsolate,path:inMemoryDatabasePath);
    final store=LocalStore(db,'one');
    await store.save('wall',{'id':'w1','room_id':'r1','label':'Wall A','length_mm':3000,'height_mm':2700,'start_x_mm':0,'start_y_mm':0,'end_x_mm':3000,'end_y_mm':0,'source':'manual','review_status':'approved'});
    await store.save('element',{'id':'e1','wall_id':'w1','label':'Pipe','kind':'gas_pipe','offset_mm':100,'width_mm':50,'source':'manual'});
    await store.save('element',{'id':'e2','wall_id':'w1','label':'Window','kind':'window','offset_mm':500,'width_mm':1000,'height_mm':800,'sill_mm':900,'source':'manual'});
    expect((await store.get('w1'))!['review_status'],'needs_review');
    expect((await store.get('e1'))!['review_status'],'incomplete');
    expect((await store.get('e2'))!['review_status'],'needs_review');
    await store.save('wall',{'id':'w1','review_status':'approved'});
    expect((await store.get('w1'))!['review_status'],'approved');
    await store.save('wall',{'id':'w1','length_mm':3200});
    expect((await store.get('w1'))!['review_status'],'needs_review');
    await db.close();
  });

  test('SQLite foreign_keys pragma is enabled and FK violations fail',() async {
    final db=await LocalStore.open(testFactory:databaseFactoryFfiNoIsolate,path:inMemoryDatabasePath);
    final store=LocalStore(db,'one');
    final fkPragma=await db.rawQuery('PRAGMA foreign_keys');
    expect(fkPragma.single.values.single,1);
    await expectLater(
      store.photo('missing-project','sketch.png',Uint8List.fromList([1,2,3])),
      throwsA(isA<DatabaseException>()),
    );
    await expectLater(
      db.insert('revisions',{'owner':'one','entity_id':'missing-entity','body':'{}'}),
      throwsA(isA<DatabaseException>()),
    );
    await store.save('project',{'id':'p1','title':'Valid Project','status':'draft'});
    await store.photo('p1','sketch.png',Uint8List.fromList([1,2,3]));
    await store.save('project',{'id':'p1','title':'Updated Valid Project','status':'draft'});
    expect((await store.photos('p1')).length,1);
    await db.close();
  });

  test('soft deletes queue tombstone operations and applyTombstone hides deleted rows',() async {
    final db=await LocalStore.open(testFactory:databaseFactoryFfiNoIsolate,path:inMemoryDatabasePath);
    final store=LocalStore(db,'one');
    await store.cache('customer',{'id':'c1','name':'Client 1','version':1});
    await store.cache('customer',{'id':'c2','name':'Client 2','version':1});
    await store.delete('customer','c1');
    expect(await store.get('c1'),isNull);
    expect((await store.get('c1',includeDeleted:true))!['is_deleted'],isTrue);
    expect((await store.list('customer')).map((c) => c['id']),['c2']);
    final q=await store.queue();
    expect(q.single['operation']['operation'],'delete');
    expect(q.single['operation']['base_version'],1);
    await store.applyTombstone('customer',{'entity_id':'c2','version':2,'deleted_at':'2026-11-20T00:00:00Z'});
    expect(await store.list('customer'),isEmpty);
    expect((await store.tombstones('customer')).length,2);
    await db.close();
  });

}
