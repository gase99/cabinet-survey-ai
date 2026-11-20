import math
import xml.etree.ElementTree as ET
import pytest
from app.geometry.engine import WallInput,ElementInput,PointMM,build_geometry


def room(points):
    return [WallInput(id=str(i),label=str(i),length_mm=round(math.dist(p,points[(i+1)%len(points)])),height_mm=2700,
        start=PointMM(*p),end=PointMM(*points[(i+1)%len(points)])) for i,p in enumerate(points)]


def test_self_intersection_and_degenerate_room_are_not_exportable_geometry():
    crossing=room([(0,0),(4000,3000),(0,3000),(4000,0)])
    assert 'self_intersection' in {e.code for e in build_geometry(crossing).errors}
    assert 'insufficient_walls' in {e.code for e in build_geometry(room([(0,0),(3000,0)])).errors}


def test_even_one_mm_disconnected_corner_is_rejected():
    walls=room([(0,0),(3000,0),(3000,2000),(0,2000)])
    walls[0].end=PointMM(2999,0)
    assert 'disconnected_walls' in {e.code for e in build_geometry(walls).errors}


def test_vertical_bounds_and_separated_objects():
    walls=room([(0,0),(3000,0),(3000,2000),(0,2000)])
    bad=ElementInput(id='bad',wall_id='0',label='Fixture',kind='window',offset_mm=200,width_mm=900,height_mm=1000,sill_mm=2000)
    assert 'height_exceeds_wall' in {e.code for e in build_geometry(walls,[bad]).errors}
    a=ElementInput(id='a',wall_id='0',label='Lower',kind='socket',offset_mm=100,width_mm=100,height_mm=100,sill_mm=100)
    b=ElementInput(id='b',wall_id='0',label='Upper',kind='socket',offset_mm=100,width_mm=100,height_mm=100,sill_mm=1000)
    assert not build_geometry(walls,[a,b]).errors


def test_plan_and_elevation_share_reference_offsets_on_vertical_wall():
    walls=room([(0,0),(3000,0),(3000,2000),(0,2000)])
    for offset in [100,500]:
        window=ElementInput(id='window',wall_id='1',label='Window',kind='window',offset_mm=offset,width_mm=600,height_mm=500,sill_mm=800)
        result=build_geometry(walls,[window]);assert not result.errors
        plan=ET.fromstring(result.svg_plan);elev=ET.fromstring(result.elevations['1'])
        ns={'s':'http://www.w3.org/2000/svg'}
        marker=next(e for e in plan.findall('s:line',ns) if e.get('stroke')=='#d32f2f')
        assert float(marker.get('x1'))==3000 and float(marker.get('x2'))==3000
        assert float(marker.get('y1'))==offset and float(marker.get('y2'))==offset+600
        rect=next(e for e in elev.findall('s:rect',ns) if e.get('stroke')=='#d32f2f')
        assert int(rect.get('x'))==offset and int(rect.get('width'))==600
        assert int(rect.get('y'))==2700-800-500


@pytest.mark.parametrize('value',[1.5,True,'3000'])
def test_only_integer_mm_reaches_geometry(value):
    walls=room([(0,0),(3000,0),(3000,2000),(0,2000)])
    walls[0].length_mm=value
    with pytest.raises(ValueError,match='integer'):build_geometry(walls)
