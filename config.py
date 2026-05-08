import os

class Config:
    """Configuration de base pour l'application Flask."""
    
    # Sécurité
    SECRET_KEY = os.environ.get("SECRET_KEY", "cle_secours_si_env_introuvable")
    
    # Base de données
    SQLALCHEMY_DATABASE_URI = 'sqlite:///base.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Fichiers statiques et uploads
    UPLOAD_FOLDER = 'static/uploads/recus'
    
    # Informations de l'application
    VERSION_APP = '0.9.131-bêta'

    # Création automatique du dossier d'upload s'il n'existe pas
    @staticmethod
    def init_app(app):
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)