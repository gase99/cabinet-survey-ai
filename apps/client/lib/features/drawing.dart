import 'dart:math' as math;
import 'package:flutter/material.dart';
import '../domain/survey.dart';
import '../core/l10n.dart';

class DrawingView extends StatefulWidget {
  final List<Json> walls, elements;
  final void Function(Json) edit;
  const DrawingView({super.key, required this.walls, required this.elements, required this.edit});
  @override
  State<DrawingView> createState() => _DrawingViewState();
}
class _DrawingViewState extends State<DrawingView> {
  String? selected;
  @override
  Widget build(BuildContext context) {
    final walls = widget.walls.map(SurveyWall.fromJson).toList();
    final errors = validateRoom(walls, widget.elements);
    final chosen = walls.where((w) => w.id == selected).firstOrNull;
    return Column(children: [
      Text(tr(context,'Local preview — not a certified drawing')),
      Wrap(spacing: 8, children: [ChoiceChip(label: Text(tr(context,'Plan')), selected: selected == null,
        onSelected: (_) => setState(() => selected = null)),
        for (final w in walls) ChoiceChip(label: Text(w.label), selected: selected == w.id,
          onSelected: (_) => setState(() => selected = w.id))]),
      if (errors.isNotEmpty) Text(errors.join('\n'), style: TextStyle(color: Theme.of(context).colorScheme.error)),
      Text('${areaMm2(walls)} mm²'),
      SizedBox(height: 380, child: InteractiveViewer(minScale: .2, maxScale: 20,
        child: CustomPaint(size: const Size(640,360), painter: SurveyPainter(walls, widget.elements, chosen)))),
      if (chosen != null) FilledButton(onPressed: () => widget.edit(widget.walls.firstWhere((w) => w['id'] == chosen.id)),
        child: Text('${tr(context,'Review')} ${chosen.label}')),
      Text(tr(context,'Select a wall to edit its measurements')),
    ]);
  }
}

/// Both views project the exact same integer-mm wall/element model.
class SurveyPainter extends CustomPainter {
  final List<SurveyWall> walls;
  final List<Json> elements;
  final SurveyWall? elevation;
  SurveyPainter(this.walls, this.elements, this.elevation);
  @override
  void paint(Canvas canvas, Size size) {
    if (walls.isEmpty) return;
    final wall = elevation;
    var minX = 0.0, minY = 0.0, maxX = 1.0, maxY = 1.0;
    if (wall != null) { maxX = wall.length.toDouble(); maxY = wall.height.toDouble(); }
    else {
      for (final w in walls) {
        minX = math.min(minX, math.min(w.x1,w.x2).toDouble());
        minY = math.min(minY, math.min(w.y1,w.y2).toDouble());
        maxX = math.max(maxX, math.max(w.x1,w.x2).toDouble());
        maxY = math.max(maxY, math.max(w.y1,w.y2).toDouble());
      }
    }
    final scale = math.min((size.width-100)/(maxX-minX), (size.height-100)/(maxY-minY));
    Offset point(num x,num y) => Offset(50+(x-minX)*scale, 50+(maxY-y)*scale);
    final line = Paint()..color = Colors.blueGrey..strokeWidth = 3..style = PaintingStyle.stroke;
    void label(String text, Offset at) {
      final painter = TextPainter(text: TextSpan(text:text, style: const TextStyle(color: Colors.black, fontSize: 12)), textDirection: TextDirection.ltr)..layout();
      painter.paint(canvas,at);
    }
    if (wall != null) {
      canvas.drawRect(Rect.fromPoints(point(0,0),point(wall.length,wall.height)),line);
      label('${wall.label} ${wall.length} × ${wall.height} mm', const Offset(50,10));
    } else {
      for (final w in walls) {
        canvas.drawLine(point(w.x1,w.y1),point(w.x2,w.y2),line);
        label('${w.label}: ${w.length} mm',point((w.x1+w.x2)/2,(w.y1+w.y2)/2)+const Offset(4,4));
      }
    }
    for (final e in elements) {
      final matching = walls.where((w) => w.id == e['wall_id']).firstOrNull;
      if (matching == null || (wall != null && matching.id != wall.id)) continue;
      final offset = e['offset_mm'] as int;
      final width = e['width_mm'] as int;
      final paint = Paint()..color = e['review_status'] == 'approved' ? Colors.teal : Colors.orange..strokeWidth = 6;
      if (wall != null) {
        final sill = e['sill_mm'] as int?;
        final height = e['height_mm'] as int?;
        if (height != null && sill != null) {
          paint.style = PaintingStyle.stroke;
          canvas.drawRect(Rect.fromPoints(point(offset,sill),point(offset+width,sill+height)),paint);
          label('${e['label']} $offset / $width mm',point(offset,sill)+const Offset(2,-18));
        } else {
          final index=elements.indexOf(e);
          label('${e['label']}: height ${height ?? '?'} mm, sill ${sill ?? '?'} mm (unpositioned)',Offset(50,size.height-15-index*14));
        }
      } else {
        Offset onWall(int distance) => point(matching.x1+(matching.x2-matching.x1)*distance/matching.length,
          matching.y1+(matching.y2-matching.y1)*distance/matching.length);
        canvas.drawLine(onWall(offset),onWall(offset+width),paint);
      }
    }
  }
  @override
  bool shouldRepaint(covariant SurveyPainter oldDelegate) => true;
}
