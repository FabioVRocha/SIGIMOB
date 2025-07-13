# SIGIMOB

Sistema web para controle de imóveis e aluguéis para imobiliária.

Este repositório contém uma implementação de referência utilizando
Python (Flask) e PostgreSQL. O foco é prover uma base modular que
pode ser expandida conforme os requisitos.

## Estrutura
- `backend/` - aplicação Flask com módulos independentes
- `frontend/` - HTML estático de exemplo
- `scripts/` - scripts auxiliares, como backup
- `tests/` - testes automatizados (pytest)

## Requisitos
- Python 3.12+
- PostgreSQL 9.3+

Para executar a aplicação em modo de desenvolvimento:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
# Linux/Mac
export FLASK_APP=backend.app:create_app
flask run

# Windows PowerShell
# $env:FLASK_APP = 'backend.app:create_app'
# flask run

# Ou use diretamente a opção --app
# flask --app backend.app:create_app run
```

## Backup
Veja `scripts/backup.sh` para exemplo de uso com cron.