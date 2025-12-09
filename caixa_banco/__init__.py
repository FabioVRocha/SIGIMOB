from flask_sqlalchemy import SQLAlchemy
from db_utils import decode_psycopg_unicode_error

# Instância compartilhada do ORM
# Será inicializada pelo aplicativo principal

db = SQLAlchemy()


def init_app(app):
    """Inicializa a extensão e registra as rotas."""
    db.init_app(app)

    # Importa e registra o blueprint apenas após init_app para evitar
    # problemas de importação circular
    from .routes import bp as caixa_banco_bp
    app.register_blueprint(caixa_banco_bp, url_prefix="/api")

    # Garante que as tabelas existam
    with app.app_context():
        try:
            db.create_all()
        except UnicodeDecodeError as exc:
            message = decode_psycopg_unicode_error(exc)
            raise RuntimeError(f'Database initialization failed: {message}') from exc