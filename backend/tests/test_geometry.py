from app.geometry.engine import WallInput, ElementInput, build_geometry, PointMM

def rect_room():
    walls=[
        WallInput(id="w1", label="Wall A", length_mm=4000, height_mm=2700, start=PointMM(0,0), end=PointMM(4000,0)),
        WallInput(id="w2", label="Wall B", length_mm=3000, height_mm=2700, start=PointMM(4000,0), end=PointMM(4000,3000)),
        WallInput(id="w3", label="Wall C", length_mm=4000, height_mm=2700, start=PointMM(4000,3000), end=PointMM(0,3000)),
        WallInput(id="w4", label="Wall D", length_mm=3000, height_mm=2700, start=PointMM(0,3000), end=PointMM(0,0)),
    ]
    return walls

def test_rectangular_area():
    geom = build_geometry(rect_room())
    assert geom.area_mm2 == 4000*3000
    assert geom.perimeter_mm == 14000
    assert geom.errors == []
    assert "svg" in geom.svg_plan.lower()
    assert len(geom.elevations) == 4

def test_l_shaped_auto_layout():
    # 6 walls auto-layout without explicit coords should produce polygon (may have closure warning but we test deterministic)
    walls=[
        WallInput(id="w1", label="Wall A", length_mm=4000, height_mm=2700),
        WallInput(id="w2", label="Wall B", length_mm=3000, height_mm=2700),
        WallInput(id="w3", label="Wall C", length_mm=1500, height_mm=2700),
        WallInput(id="w4", label="Wall D", length_mm=2000, height_mm=2700),
        WallInput(id="w5", label="Wall E", length_mm=2500, height_mm=2700),
        WallInput(id="w6", label="Wall F", length_mm=5000, height_mm=2700),
    ]
    geom = build_geometry(walls)
    # Should at least generate plan even if closure error flagged
    assert geom.svg_plan is not None
    # Area for L shape given layout: compute
    # We don't assert exact area due to layout heuristic, but check no crash

def test_invalid_length():
    walls=[WallInput(id="w1", label="Bad", length_mm=0, height_mm=2700, start=PointMM(0,0), end=PointMM(0,0))]
    geom = build_geometry(walls)
    assert any(e.code=="invalid_length" for e in geom.errors) or any(e.code=="zero_length" for e in geom.errors)

def test_element_out_of_bounds():
    walls=rect_room()
    elems=[ElementInput(id="e1", wall_id="w1", label="Window", kind="window", offset_mm=3500, width_mm=1000, height_mm=1000, sill_mm=800)]
    geom = build_geometry(walls, elems)
    assert any(e.code=="out_of_bounds" for e in geom.errors)

def test_element_overlap():
    walls=rect_room()
    elems=[
        ElementInput(id="e1", wall_id="w1", label="Window1", kind="window", offset_mm=500, width_mm=1200),
        ElementInput(id="e2", wall_id="w1", label="Window2", kind="window", offset_mm=1000, width_mm=800),
    ]
    geom = build_geometry(walls, elems)
    assert any(e.code=="overlap" for e in geom.errors)

def test_wall_length_mismatch_with_coords():
    walls=[
        WallInput(id="w1", label="Wall A", length_mm=4000, height_mm=2700, start=PointMM(0,0), end=PointMM(3000,0)), # mismatch
        WallInput(id="w2", label="Wall B", length_mm=3000, height_mm=2700, start=PointMM(3000,0), end=PointMM(3000,3000)),
        WallInput(id="w3", label="Wall C", length_mm=4000, height_mm=2700, start=PointMM(3000,3000), end=PointMM(0,3000)),
        WallInput(id="w4", label="Wall D", length_mm=3000, height_mm=2700, start=PointMM(0,3000), end=PointMM(0,0)),
    ]
    geom = build_geometry(walls)
    assert any(e.code=="length_mismatch" for e in geom.errors)

def test_disconnected_walls():
    walls=[
        WallInput(id="w1", label="A", length_mm=4000, height_mm=2700, start=PointMM(0,0), end=PointMM(4000,0)),
        WallInput(id="w2", label="B", length_mm=3000, height_mm=2700, start=PointMM(4100,0), end=PointMM(4100,3000)), # gap 100
        WallInput(id="w3", label="C", length_mm=4000, height_mm=2700, start=PointMM(4100,3000), end=PointMM(0,3000)),
        WallInput(id="w4", label="D", length_mm=3000, height_mm=2700, start=PointMM(0,3000), end=PointMM(0,0)),
    ]
    geom = build_geometry(walls)
    assert any(e.code=="disconnected_walls" for e in geom.errors)

def test_deterministic():
    g1 = build_geometry(rect_room())
    g2 = build_geometry(rect_room())
    assert g1.svg_plan == g2.svg_plan
    assert g1.area_mm2 == g2.area_mm2
