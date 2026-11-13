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

}
