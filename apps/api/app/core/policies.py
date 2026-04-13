SENSITIVE_FIELDS = {
    'hashed_password',
    'access_token_encrypted',
    'api_secret_key',
    'token_hash',
    'password',
    'authorization',
}


def mask_sensitive(data: dict) -> dict:
    masked = {}
    for key, value in data.items():
        if key.lower() in SENSITIVE_FIELDS:
            masked[key] = '***'
        else:
            masked[key] = value
    return masked
