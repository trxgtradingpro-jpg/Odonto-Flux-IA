import re


def normalize_cpf(cpf: str | None) -> str:
    if not cpf:
        return ""
    return re.sub(r"\D", "", cpf)

