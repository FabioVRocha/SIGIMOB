# config.py
# Este arquivo armazena as configurações da sua aplicação.

import os

# Configurações do Banco de Dados PostgreSQL
# Exemplo: 'postgresql://user:password@host:port/dbname'
# certifique-se de substituir com suas credenciais reais
DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://postgres:postgres@192.168.0.252:5433/sigimob_db')

# Chave secreta para sessões Flask (MUITO IMPORTANTE para segurança)
# Gere uma chave forte e a mantenha em segredo.
SECRET_KEY = os.environ.get('SECRET_KEY', 'sua_chave_secreta_aqui_substitua_por_uma_forte_e_aleatoria')

# Pasta para uploads de arquivos (fotos de imóveis, anexos de contratos, backups)
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')

# Extensões de arquivo permitidas para uploads
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx', 'sql'}
