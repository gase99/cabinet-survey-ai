import pytest


@pytest.fixture
def wall(client,auth_headers):
    p=client.post('/api/v1/projects',headers=auth_headers,json={'title':'Integrity fixture'}).json()['id']
    r=client.post(f'/api/v1/projects/{p}/rooms',headers=auth_headers,json={'label':'Fixture'}).json()['id']
    return client.post(f'/api/v1/rooms/{r}/walls',headers=auth_headers,json={'label':'A','length_mm':3000,'height_mm':2700}).json()['id']


def test_rest_create_rejects_invalid_vertical_bounds_and_resize_preserves_elements(client,auth_headers,wall):
    url=f'/api/v1/walls/{wall}/elements'
    data={'label':'Fixture window','kind':'window','offset_mm':100,'width_mm':1000,'height_mm':1000,'sill_mm':2000}
    assert client.post(url,headers=auth_headers,json=data).status_code==400
    data.update(offset_mm=1800,sill_mm=900)
    assert client.post(url,headers=auth_headers,json=data).status_code==201
    assert client.put(f'/api/v1/walls/{wall}',headers=auth_headers,json={'length_mm':2000}).status_code==400
    assert client.get(f'/api/v1/walls/{wall}',headers=auth_headers).json()['length_mm']==3000


@pytest.mark.parametrize('value',[None,True,1.5,'3000',2**80])
def test_invalid_dimensions_do_not_corrupt_wall_or_crash(client,auth_headers,wall,value):
    assert client.put(f'/api/v1/walls/{wall}',headers=auth_headers,json={'length_mm':value}).status_code==422
    assert client.get(f'/api/v1/walls/{wall}',headers=auth_headers).json()['length_mm']==3000
