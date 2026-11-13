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
