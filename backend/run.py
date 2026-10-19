import os

from dotenv import load_dotenv

load_dotenv()

from app import create_app  # noqa: E402

app = create_app(os.getenv('FLASK_CONFIG', 'development'))


if __name__ == '__main__':
    host = os.getenv('HOST', '127.0.0.1')
    port = int(os.getenv('PORT', '5000'))
    debug = os.getenv('DEBUG', 'false').lower() in ('1', 'true', 'yes', 'on')

    app.run(host=host, port=port, debug=debug)