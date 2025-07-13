import re
import hashlib
from validate_docbr import CPF, CNPJ


cpf_validator = CPF()
cnpj_validator = CNPJ()


def validate_cpf_cnpj(value: str) -> bool:
    value = re.sub(r'\D', '', value)
    if len(value) == 11:
        return cpf_validator.validate(value)
    if len(value) == 14:
        return cnpj_validator.validate(value)
    return False


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def check_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed