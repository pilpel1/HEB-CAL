import os

from app import app

if __name__ == '__main__':
    debug = os.getenv('FLASK_DEBUG', '').lower() in {'1', 'true', 'yes', 'on'}
    app.run(debug=debug)