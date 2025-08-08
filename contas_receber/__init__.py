from caixa_banco import db

def init_app(app):
    from .routes import bp as contas_bp
    app.register_blueprint(contas_bp, url_prefix='/api')
    with app.app_context():
        db.create_all()