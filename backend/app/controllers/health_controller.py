from flask import jsonify
from database.db import db 
from sqlalchemy import text 
from datetime import datetime 

class HealthController:

    @staticmethod 
    def check_health():

        db_status = 'disconnected'

        try:
            db.session.execute(text('SELECT 1'))
            db_status = 'connected'
        except Exception:
            db_status = 'disconnected'

        if db_status == 'disconnected':
            return jsonify({
                'status': 'error',
                'database': 'disconnected',
                'message': 'Database is unavalable'
            }), 500

        return jsonify({
            'status': 'ok',
            'database': 'connected',
            'timestamp': datetime.utcnow().isoformat()
        }), 200
        