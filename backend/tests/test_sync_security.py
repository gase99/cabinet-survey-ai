import uuid
import pytest


def operation(kind, entity_id, payload, action='create', base=None, op_id=None):
    return {'id':op_id or str(uuid.uuid4()), 'entity_type':kind, 'entity_id':entity_id,
            'operation':action, 'payload':payload, 'base_version':base}


def push(client, headers, op):
    response = client.post('/api/v1/sync/push', headers=headers, json={'operations':[op]})
    assert response.status_code == 200, response.text
    return response.json()['results'][0]


@pytest.fixture
def other_headers(client):
    client.post('/api/v1/auth/register', json={'email':'private@example.com','password':'PrivatePass123!','display_name':'Private'})
    token = client.post('/api/v1/auth/login',json={'email':'private@example.com','password':'PrivatePass123!'}).json()['access_token']
    return {'Authorization':f'Bearer {token}'}


def test_nested_create_requires_owned_parent(client, auth_headers, other_headers):
    pid = client.post('/api/v1/projects',headers=other_headers,json={'title':'Private'}).json()['id']
    result = push(client,auth_headers,operation('room',str(uuid.uuid4()),{'project_id':pid,'label':'Attack'}))
    assert result['status'] == 'failed'
    assert client.get(f'/api/v1/projects/{pid}/rooms',headers=other_headers).json() == []


@pytest.mark.parametrize('field,value', [('owner_id','attacker'),('id','replacement'),('version',900),('is_deleted',True)])
def test_sync_rejects_mass_assignment(client,auth_headers,field,value):
    pid = client.post('/api/v1/projects',headers=auth_headers,json={'title':'Safe'}).json()['id']
    assert push(client,auth_headers,operation('project',pid,{field:value},'update',1))['status']=='failed'
    assert client.get(f'/api/v1/projects/{pid}',headers=auth_headers).json()['title']=='Safe'


def test_retry_is_idempotent_and_mutated_operation_id_rejected(client,auth_headers):
    pid = str(uuid.uuid4())
    op = operation('project',pid,{'title':'Original'})
    assert push(client,auth_headers,op)['status']=='applied'
    assert push(client,auth_headers,op)['status']=='applied'
    edit = operation('project',pid,{'title':'Edited'},'update',1)
    assert push(client,auth_headers,edit)['new_version']==2
    assert push(client,auth_headers,edit)['status']=='applied'
    assert client.get(f'/api/v1/projects/{pid}',headers=auth_headers).json()['version']==2
    op['payload']['title']='Changed receipt'
    assert push(client,auth_headers,op)['status']=='failed'


def test_complete_offline_chain_and_explicit_approval(client,auth_headers):
    customer,project,room,wall,element = [str(uuid.uuid4()) for _ in range(5)]
    for kind,id,payload in [
        ('customer',customer,{'name':'Fixture Workshop'}),
        ('project',project,{'title':'Offline chain','customer_id':customer}),
        ('room',room,{'project_id':project,'label':'Kitchen'}),
        ('wall',wall,{'room_id':room,'label':'A','length_mm':3000,'height_mm':2700,'source':'sketch_ai'}),
        ('element',element,{'wall_id':wall,'label':'Window','kind':'window','offset_mm':500,'width_mm':1000,'height_mm':800,'sill_mm':900}),
    ]:
        assert push(client,auth_headers,operation(kind,id,payload))['status']=='applied'
    assert client.get(f'/api/v1/walls/{wall}',headers=auth_headers).json()['review_status']=='needs_review'
    assert push(client,auth_headers,operation('wall',wall,{'length_mm':3200,'review_status':'approved'},'update',1))['status']=='failed'
    assert push(client,auth_headers,operation('wall',wall,{'review_status':'approved'},'update',1))['status']=='applied'
    assert push(client,auth_headers,operation('wall',wall,{'length_mm':3200},'update',2))['status']=='applied'
    assert client.get(f'/api/v1/walls/{wall}',headers=auth_headers).json()['review_status']=='needs_review'


def test_failed_operation_does_not_poison_batch(client,auth_headers):
    ops = [operation('room',str(uuid.uuid4()),{'project_id':'missing','label':'Invalid'}),
           operation('project',str(uuid.uuid4()),{'title':'Valid'})]
    result = client.post('/api/v1/sync/push',headers=auth_headers,json={'operations':ops}).json()['results']
    assert [r['status'] for r in result] == ['failed','applied']


def test_update_requires_base_and_customer_ownership(client,auth_headers,other_headers):
    cust = client.post('/api/v1/customers',headers=other_headers,json={'name':'Private'}).json()['id']
    pid = client.post('/api/v1/projects',headers=auth_headers,json={'title':'Safe'}).json()['id']
    assert push(client,auth_headers,operation('project',pid,{'title':'Unsafe'},'update'))['status']=='failed'
    assert push(client,auth_headers,operation('project',pid,{'customer_id':cust},'update',1))['status']=='failed'
    assert client.get(f'/api/v1/projects/{pid}',headers=auth_headers).json()['customer_id'] is None
