from app.core.security import create_access_token, decode_token, hash_password, verify_password


def test_password_hash_and_verify():
    raw = 'SenhaForte@123'
    hashed = hash_password(raw)
    assert hashed != raw
    assert verify_password(raw, hashed) is True
    assert verify_password('outra', hashed) is False



def test_access_token_structure():
    token = create_access_token(subject='user-1', tenant_id=None, roles=['admin_platform'])
    payload = decode_token(token)
    assert payload['sub'] == 'user-1'
    assert payload['type'] == 'access'
    assert payload['roles'] == ['admin_platform']
