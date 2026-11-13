import 'dart:math' as math;

typedef Json = Map<String, dynamic>;

/// Integers only: no rounding of user measurements, including Persian numerals.
int millimetres(String text, {bool allowZero = false}) {
  var normalized = text.trim();
  const persian = '۰۱۲۳۴۵۶۷۸۹';
  const arabic = '٠١٢٣٤٥٦٧٨٩';
  for (var i = 0; i < 10; i++) {
    normalized = normalized.replaceAll(persian[i], '$i').replaceAll(arabic[i], '$i');
  }
  final value = int.tryParse(normalized);
  if (value == null || value < (allowZero ? 0 : 1)) {
    throw const FormatException('Enter an integer dimension in mm');
  }
  return value;
}

class SurveyWall {
  final String id, label;
  final int length, height, x1, y1, x2, y2;
  const SurveyWall({required this.id, required this.label, required this.length,
    required this.height, required this.x1, required this.y1,
    required this.x2, required this.y2});
  factory SurveyWall.fromJson(Json j) => SurveyWall(id: j['id'] as String,
    label: j['label'] as String, length: j['length_mm'] as int,
    height: j['height_mm'] as int, x1: j['start_x_mm'] as int,
    y1: j['start_y_mm'] as int, x2: j['end_x_mm'] as int,
    y2: j['end_y_mm'] as int);
}

/// Coordinates are explicitly entered, never inferred from a sketch or a default.
List<String> validateRoom(List<SurveyWall> walls, List<Json> elements) {
  final errors = <String>[];
  if (walls.length < 3) errors.add('A closed room requires at least three walls');
  for (var i = 0; i < walls.length; i++) {
    final w = walls[i];
    if (w.length <= 0 || w.height <= 0) errors.add('${w.label}: invalid dimension');
    final actual = math.sqrt(math.pow(w.x2-w.x1, 2) + math.pow(w.y2-w.y1, 2));
    if ((actual-w.length).abs() > 1) errors.add('${w.label}: coordinate/length mismatch');
    final next = walls[(i+1) % walls.length];
    if (w.x2 != next.x1 || w.y2 != next.y1) errors.add('${w.label}: disconnected corner');
    final own = elements.where((e) => e['wall_id'] == w.id).toList();
    for (var k = 0; k < own.length; k++) {
      final e = own[k];
      final offset = e['offset_mm'] as int;
      final width = e['width_mm'] as int;
      final sill = e['sill_mm'] as int? ?? 0;
      final height = e['height_mm'] as int?;
      if (offset < 0 || width <= 0 || offset+width > w.length ||
          sill < 0 || (height != null && (height <= 0 || sill+height > w.height))) {
        errors.add('${e['label']}: outside wall bounds');
      }
      for (var j = k+1; j < own.length; j++) {
        final b = own[j];
        final left = b['offset_mm'] as int;
        final right = left + (b['width_mm'] as int);
        final bottom = b['sill_mm'] as int? ?? 0;
        final top = bottom + (b['height_mm'] as int? ?? w.height);
        if (offset < right && left < offset+width &&
            sill < top && bottom < sill+(height ?? w.height)) {
          errors.add('${e['label']}: overlaps ${b['label']}');
        }
      }
    }
  }
  // Reject proper segment crossings and collinear overlaps between non-neighbours.
  int cross(int ax, int ay, int bx, int by) => ax*by-ay*bx;
  for (var i = 0; i < walls.length; i++) {
    for (var j = i+1; j < walls.length; j++) {
      if (j == i+1 || (i == 0 && j == walls.length-1)) continue;
      final a = walls[i], b = walls[j];
      final c1 = cross(a.x2-a.x1, a.y2-a.y1, b.x1-a.x1, b.y1-a.y1);
      final c2 = cross(a.x2-a.x1, a.y2-a.y1, b.x2-a.x1, b.y2-a.y1);
      final c3 = cross(b.x2-b.x1, b.y2-b.y1, a.x1-b.x1, a.y1-b.y1);
      final c4 = cross(b.x2-b.x1, b.y2-b.y1, a.x2-b.x1, a.y2-b.y1);
      final boundsOverlap = math.max(math.min(a.x1,a.x2), math.min(b.x1,b.x2)) <=
          math.min(math.max(a.x1,a.x2), math.max(b.x1,b.x2)) &&
          math.max(math.min(a.y1,a.y2), math.min(b.y1,b.y2)) <=
          math.min(math.max(a.y1,a.y2), math.max(b.y1,b.y2));
      if (c1*c2 <= 0 && c3*c4 <= 0 && boundsOverlap) errors.add('Room edges intersect');
    }
  }
  if (walls.length >= 3 && areaMm2(walls) == 0) errors.add('Room has zero area');
  return errors;
}

int areaMm2(List<SurveyWall> walls) =>
    (walls.fold<int>(0, (sum, w) => sum + w.x1*w.y2-w.x2*w.y1).abs() ~/ 2);
