import 'package:flutter_test/flutter_test.dart';
import 'package:cabinet_survey_ai/domain/survey.dart';

SurveyWall wall(String id,int x1,int y1,int x2,int y2,int length) => SurveyWall(
  id:id,label:id,length:length,height:2700,x1:x1,y1:y1,x2:x2,y2:y2);
void main() {
  test('Persian and Arabic numerals stay exact integer mm',() {
    expect(millimetres('۳۲۰۰'),3200);
    expect(millimetres('٣٢٠٠'),3200);
    expect(() => millimetres('3.2'),throwsFormatException);
    expect(() => millimetres('-1'),throwsFormatException);
    expect(() => millimetres('0'),throwsFormatException);
    expect(millimetres('۰',allowZero:true),0);
  });
  final rectangle=[wall('A',0,0,4000,0,4000),wall('B',4000,0,4000,3000,3000),
    wall('C',4000,3000,0,3000,4000),wall('D',0,3000,0,0,3000)];
  test('rectangular room area and topology',() {
    expect(areaMm2(rectangle),12000000);
    expect(validateRoom(rectangle,[]),isEmpty);
  });
  test('L shaped golden area',() {
    final walls=[wall('A',0,0,4000,0,4000),wall('B',4000,0,4000,2000,2000),
      wall('C',4000,2000,2000,2000,2000),wall('D',2000,2000,2000,4000,2000),
      wall('E',2000,4000,0,4000,2000),wall('F',0,4000,0,0,4000)];
    expect(areaMm2(walls),12000000);
    expect(validateRoom(walls,[]),isEmpty);
  });
  test('bounds and overlap are rejected',() {
    final elements=<Json>[
      {'wall_id':'A','label':'Window','offset_mm':100,'width_mm':1200,'sill_mm':900,'height_mm':1000},
      {'wall_id':'A','label':'Door','offset_mm':200,'width_mm':900,'height_mm':2100},
      {'wall_id':'B','label':'Outside','offset_mm':2800,'width_mm':400}];
    expect(validateRoom(rectangle,elements).where((e) => e.contains('overlaps')),isNotEmpty);
    expect(validateRoom(rectangle,elements).where((e) => e.contains('bounds')),isNotEmpty);
  });
  test('contradictory coordinates never become approved geometry',() {
    expect(validateRoom([wall('A',0,0,100,0,500)],[]),contains('A: coordinate/length mismatch'));
  });
}
