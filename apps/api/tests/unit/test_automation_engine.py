from app.services.automation_service import _conditions_match


def test_conditions_match_true():
    assert _conditions_match({'status': 'pendente'}, {'status': 'pendente', 'a': 1}) is True



def test_conditions_match_false():
    assert _conditions_match({'status': 'confirmada'}, {'status': 'pendente'}) is False
