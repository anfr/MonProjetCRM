from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_socketio import SocketIO
from flask_wtf.csrf import CSRFProtect

# 1. On instancie les extensions (vides pour l'instant)
db = SQLAlchemy()
migrate = Migrate()
socketio = SocketIO()
csrf = CSRFProtect()

# Note : On ne fait PAS "db.init_app(app)" ici. 
# Cela sera fait plus tard dans la fonction create_app() de main.py