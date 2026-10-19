import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _bool_env(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ('1', 'true', 'yes', 'on')


class Config:
    """Base configuration."""

    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-change-me')
    DEBUG = _bool_env('DEBUG', False)

    # By default SQLite file is created inside the Flask instance folder.
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///contextpilot.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
    }

    JSON_SORT_KEYS = False
    JSONIFY_PRETTYPRINT_REGULAR = False

    HOST = os.getenv('HOST', '127.0.0.1')
    PORT = int(os.getenv('PORT', '5000'))


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.getenv('TEST_DATABASE_URL', 'sqlite://')


CONFIGS = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
}


def get_config(name=None):
    """Resolve a config class by name, falling back to the environment."""
    name = name or os.getenv('FLASK_CONFIG', 'development')
    return CONFIGS.get(name.lower(), DevelopmentConfig)