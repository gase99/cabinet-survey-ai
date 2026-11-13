def login(client):
    client.post('/api/v1/auth/register',json={'email':'session@example.com','password':'FixturePassword123','display_name':'Fixture'})
    return client.post('/api/v1/auth/login',json={'email':'session@example.com','password':'FixturePassword123'}).json()


def headers(tokens):
    return {'Authorization':'Bearer '+tokens['access_token']}


def test_logout_revokes_access_and_refresh(client):
    tokens=login(client)
    assert client.post('/api/v1/auth/logout',headers=headers(tokens)).status_code==200
    assert client.get('/api/v1/auth/me',headers=headers(tokens)).status_code==401
    assert client.post('/api/v1/auth/refresh',json={'refresh_token':tokens['refresh_token']}).status_code==401


def test_refresh_rotation_and_replay_revoke_session_but_not_other_device(client):
    first=login(client);other=login(client)
    rotated=client.post('/api/v1/auth/refresh',json={'refresh_token':first['refresh_token']})
    assert rotated.status_code==200
    assert rotated.json()['refresh_token']!=first['refresh_token']
    assert client.post('/api/v1/auth/refresh',json={'refresh_token':first['refresh_token']}).status_code==401
    assert client.get('/api/v1/auth/me',headers=headers(rotated.json())).status_code==401
    assert client.get('/api/v1/auth/me',headers=headers(other)).status_code==200


def test_password_change_revokes_all_devices(client):
    first=login(client);second=login(client)
    response=client.post('/api/v1/auth/change-password',headers=headers(first),
        json={'current_password':'FixturePassword123','new_password':'UpdatedFixturePassword123'})
    assert response.status_code==200
    for token in [first,second]:
        assert client.get('/api/v1/auth/me',headers=headers(token)).status_code==401
        assert client.post('/api/v1/auth/refresh',json={'refresh_token':token['refresh_token']}).status_code==401
