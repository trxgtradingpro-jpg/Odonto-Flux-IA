import re


def normalize_phone(phone: str | None) -> str:
    if not phone:
        return ''
    raw_value = phone.strip()
    digits = re.sub(r'\D', '', phone)

    if raw_value.startswith('+'):
        return digits
    if raw_value.startswith('00') and len(digits) > 2:
        return digits[2:]
    if digits.startswith('55'):
        return digits
    if 10 <= len(digits) <= 11:
        return f'55{digits}'
    return digits
