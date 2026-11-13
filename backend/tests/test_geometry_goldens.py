import hashlib
import json
from pathlib import Path
import pytest
from app.geometry.engine import WallInput, ElementInput, PointMM, build_geometry

FIXTURES=Path(__file__).parents[2]/'test_fixtures'/'geometry'


@pytest.mark.parametrize('path',sorted(FIXTURES.glob('*.json')),ids=lambda p:p.stem)
def test_canonical_geometry_goldens(path):
    case=json.loads(path.read_text())
    points=case['points']
    walls=[WallInput(id=f'w{i}',label=f'Wall {i}',length_mm=case['lengths'][i],height_mm=2700,
        start=PointMM(*point),end=PointMM(*points[(i+1)%len(points)])) for i,point in enumerate(points)]
    result=build_geometry(walls,[ElementInput(**e) for e in case['elements']])
    assert result.errors==[]
    assert result.area_mm2==case['area_mm2']
    assert result.perimeter_mm==case['perimeter_mm']
    assert hashlib.sha256(result.svg_plan.encode()).hexdigest()==case['plan_sha256']
    assert {k:hashlib.sha256(v.encode()).hexdigest() for k,v in result.elevations.items()}==case['elevations_sha256']


def test_lengths_alone_never_invent_room_topology():
    result=build_geometry([WallInput(id=str(i),label=str(i),length_mm=3000,height_mm=2700) for i in range(4)])
    assert any(e.code=='missing_coordinates' for e in result.errors)
    assert result.area_mm2==0


def test_untrusted_svg_labels_are_text_not_markup_and_missing_height_stays_unknown():
    import xml.etree.ElementTree as ET
    wall=WallInput(id='wall',label='<script>alert(1)</script>',length_mm=3000,height_mm=2700,
        start=PointMM(0,0),end=PointMM(3000,0))
    element=ElementInput(id='pipe',wall_id='wall',label='</text><image href="file:///etc/passwd"/>',
        kind='gas_pipe',offset_mm=400,width_mm=50,height_mm=None,sill_mm=None)
    from app.geometry.engine import generate_elevation_svg,generate_plan_svg
    elevation=generate_elevation_svg(wall,[element])
    assert 'height ? mm; sill ? mm (unpositioned)' in elevation
    assert 'height="800"' not in elevation
    for svg in [elevation,generate_plan_svg([PointMM(0,0),PointMM(3000,0),PointMM(0,3000)],[wall],[element])]:
        root=ET.fromstring(svg)
        assert not root.findall('.//{http://www.w3.org/2000/svg}script')
        assert not root.findall('.//{http://www.w3.org/2000/svg}image')
        assert '&lt;script&gt;' in svg
