from app.utils.phone import normalize_phone


def test_normalize_phone_br():
    assert normalize_phone('(11) 99999-1111') == '5511999991111'
    assert normalize_phone('+55 11 98888-2222') == '5511988882222'
    assert normalize_phone(None) == ''
