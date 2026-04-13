import re


def normalize_phone(phone: str | None) -> str:
    if not phone:
        return ''
    digits = re.sub(r'\D', '', phone)
    if digits.startswith('55'):
        return digits
    if len(digits) >= 10:
        return f'55{digits}'
    return digits
