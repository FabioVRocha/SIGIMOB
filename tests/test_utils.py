from backend.app.utils import validate_cpf_cnpj


def test_validate_cpf():
    assert validate_cpf_cnpj('11144477735')


def test_validate_cnpj():
    assert validate_cpf_cnpj('11444777000161')
from backend.app.utils import hash_password, check_password


def test_password_hash():
    p = 'secret'
    h = hash_password(p)
    assert h != p
    assert check_password('secret', h)