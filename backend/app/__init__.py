from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager


db = SQLAlchemy()
jwt = JWTManager()


def create_app():
    app = Flask(__name__)
    app.config.from_mapping(
        SQLALCHEMY_DATABASE_URI="postgresql://postgres:postgres@45.161.184.156:5433/sigimob_db",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        JWT_SECRET_KEY="change-me",
    )

    db.init_app(app)
    jwt.init_app(app)

    from . import models
    with app.app_context():
        db.create_all()

    from .routes import bp as routes_bp
    app.register_blueprint(routes_bp)

    return app