import re

from app.core.exceptions import ApiError

PASSWORD_MIN_LENGTH = 10


def validate_password_strength(password: str) -> None:
    issues: list[str] = []
    if len(password) < PASSWORD_MIN_LENGTH:
        issues.append(f'minimo de {PASSWORD_MIN_LENGTH} caracteres')
    if not re.search(r'[A-Z]', password):
        issues.append('ao menos 1 letra maiuscula')
    if not re.search(r'[a-z]', password):
        issues.append('ao menos 1 letra minuscula')
    if not re.search(r'\d', password):
        issues.append('ao menos 1 numero')
    if not re.search(r'[^A-Za-z0-9]', password):
        issues.append('ao menos 1 simbolo especial')
    if re.search(r'\s', password):
        issues.append('sem espacos em branco')

    if issues:
        raise ApiError(
            status_code=400,
            code='PASSWORD_WEAK',
            message='Senha fora da politica de seguranca',
            details={'rules': issues},
        )
