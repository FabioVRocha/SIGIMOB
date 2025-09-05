from caixa_banco import db

def init_app(app):
    # Ensure models are registered and tables created
    from . import models  # noqa: F401
    with app.app_context():
        db.create_all()