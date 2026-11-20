from app.geometry.engine import WallInput, ElementInput, build_geometry, PointMM

def walls_and_elements_from_room(room, walls, elements):
    w_inputs = []
    for w in walls:
        # if coordinates are zero-zero, treat as no coords
        has_coords = not (w.start_x_mm == 0 and w.start_y_mm == 0 and w.end_x_mm == 0 and w.end_y_mm == 0)
        start = PointMM(w.start_x_mm, w.start_y_mm) if has_coords else None
        end = PointMM(w.end_x_mm, w.end_y_mm) if has_coords else None
        w_inputs.append(WallInput(
            id=w.id,
            label=w.label,
            length_mm=w.length_mm,
            height_mm=w.height_mm,
            start=start,
            end=end,
        ))
    e_inputs = []
    for e in elements:
        e_inputs.append(ElementInput(
            id=e.id,
            wall_id=e.wall_id,
            label=e.label,
            kind=e.kind,
            offset_mm=e.offset_mm,
            width_mm=e.width_mm,
            height_mm=e.height_mm,
            sill_mm=e.sill_mm,
            depth_mm=e.depth_mm,
        ))
    return build_geometry(w_inputs, e_inputs)
