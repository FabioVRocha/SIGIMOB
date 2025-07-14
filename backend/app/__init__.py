import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager


db = SQLAlchemy()
jwt = JWTManager()


def create_app():
    static_folder = os.path.join(os.path.dirname(__file__), '..', '..', 'frontend')
    app = Flask(__name__, static_folder=static_folder, static_url_path='')
    app.config.from_mapping(
        SQLALCHEMY_DATABASE_URI="postgresql://postgres:postgres@45.161.184.156:5433/sigimob",
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