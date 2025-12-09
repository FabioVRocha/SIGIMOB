from caixa_banco import db
from sqlalchemy import inspect, text


def init_app(app):
    from .routes import bp as contas_bp
    app.register_blueprint(contas_bp, url_prefix='/api')
    with app.app_context():
        db.create_all()
        db.create_all()

        # Ensure the 'nosso_numero' column exists in older databases
        inspector = inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('contas_a_receber')]
        if 'nosso_numero' not in columns:
            db.session.execute(
                text('ALTER TABLE contas_a_receber ADD COLUMN nosso_numero VARCHAR(20)')
            )
            db.session.commit()

        if 'valor_pendente' not in columns:
            db.session.execute(
                text('ALTER TABLE contas_a_receber ADD COLUMN valor_pendente NUMERIC(10,2) DEFAULT 0')
            )
            db.session.execute(
                text('UPDATE contas_a_receber SET valor_pendente = valor_previsto - COALESCE(valor_pago,0)')
            )
            db.session.commit()