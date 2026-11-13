import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:cabinet_survey_ai/core/controller.dart';
import 'package:cabinet_survey_ai/core/api.dart';
import 'package:cabinet_survey_ai/core/store.dart';
import 'package:cabinet_survey_ai/domain/survey.dart';

const url=String.fromEnvironment('ACCEPTANCE_API_URL');
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  sqfliteFfiInit();
  for(final language in ['en','fa']) {
    test('real HTTP offline/reopen/conflict/drawings/export workflow $language',() async {
      FlutterSecureStorage.setMockInitialValues({}); // OS keystore substitute, not an Android device claim.
      final dir=await Directory.systemTemp.createTemp('cabinet-acceptance-');
      var db=await LocalStore.open(testFactory:databaseFactoryFfiNoIsolate,path:'${dir.path}/survey.sqlite');
      final first=SurveyController(db,api:Api(baseUrl:url));
      final address='qa-${uuid.v4()}@example.com';
      const password='AcceptanceFixture123!';
      await first.login(address,password,name:'QA Fixture');
      final project=uuid.v4(),room=uuid.v4(),window=uuid.v4();
      final ids=List.generate(4,(_) => uuid.v4());
      final title=language=='fa'?'آشپزخانه آزمایشی':'Acceptance kitchen';
      // No network is used for any capture mutation below.
      await first.store.save('project',{'id':project,'title':title,'status':'draft'});
      await first.store.save('room',{'id':room,'project_id':project,'label':title,'room_type':'rectangular'});
      final coords=[[0,0,4000,0,4000],[4000,0,4000,3000,3000],[4000,3000,0,3000,4000],[0,3000,0,0,3000]];
      for(var i=0;i<4;i++) {
        final a=coords[i];
        await first.store.save('wall',{'id':ids[i],'room_id':room,'label':'Wall $i','length_mm':a[4],
          'height_mm':2700,'start_x_mm':a[0],'start_y_mm':a[1],'end_x_mm':a[2],'end_y_mm':a[3],
          'source':'manual','review_status':'approved'});
      }
      await first.store.save('element',{'id':window,'wall_id':ids.first,'label':'Window','kind':'window',
        'offset_mm':500,'width_mm':1000,'height_mm':800,'sill_mm':900,'source':'manual','review_status':'approved'});
      expect(validateRoom((await first.store.list('wall')).map(SurveyWall.fromJson).toList(),await first.store.list('element')),isEmpty);
      expect((await first.store.queue()).length,7);
      first.api.close();first.dispose();await db.close();
      // Reopen a physical SQLite file in a new controller, not an in-memory substitute.
      db=await LocalStore.open(testFactory:databaseFactoryFfiNoIsolate,path:'${dir.path}/survey.sqlite');
      final reopened=SurveyController(db,api:Api(baseUrl:url));
      await reopened.restore();
      expect((await reopened.store.get(project))!['title'],title);
      expect((await reopened.store.queue()).length,7);
      await reopened.sync();
      expect((await reopened.store.queue()).every((r) => r['state']=='applied'),isTrue);
      final local=(await reopened.store.get(window))!;
      await reopened.store.save('element',{...local,'offset_mm':600,'review_status':'needs_review'});
      final other=Api(baseUrl:url);
      final tokens=await other.request('POST','auth/login',{'email':address,'password':password}) as Json;
      other.token=tokens['access_token'] as String;
      await other.request('PUT','elements/$window',{'offset_mm':700});
      await reopened.sync();
      final conflict=(await reopened.store.queue()).singleWhere((r) => r['state']=='conflict');
      expect((await reopened.store.get(window))!['offset_mm'],600);
      expect(conflict['response']['server_payload']['offset_mm'],700);
      await reopened.store.keepLocal(conflict);
      await reopened.sync();
      final resolved=(await reopened.store.get(window))!;
      expect(resolved['review_status'],'needs_review');
      await expectLater(reopened.api.request('POST','exports/$project',{'format':'pdf','layout':'A4'}),
        throwsA(isA<ApiException>().having((e) => e.status,'approval required',409)));
      await reopened.store.save('element',{...resolved,'review_status':'approved'});
      await reopened.sync();
      final plan=await reopened.api.request('GET','drawings/$project/plan') as Json;
      expect(plan['area_mm2'],12000000);expect(plan['errors'],isEmpty);
      expect((plan['elevations'] as Json).length,4);
      for(final format in ['pdf','png']) {
        final job=await reopened.api.request('POST','exports/$project',{'format':format,'layout':'A4'}) as Json;
        final data=await reopened.api.bytes('exports/${job['id']}/download');
        expect(data.length,greaterThan(1000));
        expect(data.first,format=='pdf'?37:137);
      }
      await reopened.logout();
      other.close();reopened.api.close();reopened.dispose();await db.close();await dir.delete(recursive:true);
    },skip:url.isEmpty?'Requires disposable live FastAPI acceptance server':false,timeout:const Timeout(Duration(minutes:3)));
  }
}
