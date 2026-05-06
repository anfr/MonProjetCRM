from flask import Flask, render_template, request, session, redirect, url_for
from config import Config
from extensions import db, migrate, socketio, csrf
from sqlalchemy import func

# On importe les modèles nécessaires pour les notifications
from models import Utilisateur, ConfigSysteme, BoutonRapide, Operation

def is_public_route(endpoint):
    """Vérifie si la page est accessible sans mot de passe"""
    if not endpoint: return True
    # ⚠️ Note importante : 'login' devient 'auth.login'
    publiques = ['auth.login', 'queue.public_view', 'queue.borne_qr', 'queue.mobile_portail', 'queue.mobile_generer', 'queue.mobile_ticket']
    return endpoint in publiques

def create_app(config_class=Config):
    """L'usine à application (Application Factory)"""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # 1. Initialisation des extensions
    db.init_app(app)
    migrate.init_app(app, db)
    socketio.init_app(app, cors_allowed_origins="*", async_mode='threading')
    csrf.init_app(app)
    app.socketio = socketio

    # 2. Hooks Globaux (Vérification et Variables de session)
    @app.before_request
    def verifier_connexion():
        if request.path.startswith('/socket.io') or request.path.startswith('/static'):
            return
        if not is_public_route(request.endpoint):
            if not session.get('connecte'): 
                return redirect(url_for('auth.login'))
            
            # NOUVEAU CODE (syntaxe moderne SQLAlchemy 2.0) :
            user = db.session.get(Utilisateur, session.get('user_id'))
            if not user or session.get('auth_version') != user.auth_version:
                session.clear()
                return redirect(url_for('auth.login', expire='1'))

    @app.context_processor
    def injecter_variables_globales():
        if request.path.startswith('/api/') or request.path.startswith('/static/') or request.endpoint == 'auth.login':
            return {}

        config = ConfigSysteme.query.first()
        liste_boutons = BoutonRapide.query.all()

        if not session.get('connecte'):
            return dict(notifs=[], nb_notifs=0, liste_boutons=liste_boutons, config=config, version_app=app.config.get('VERSION_APP'))

        notifs = []
        nb_attente = Operation.query.filter_by(statut='En attente', archive=False).count()
        if nb_attente > 0:
            notifs.append({'titre': 'Opérations', 'message': f'{nb_attente} en attente', 'lien': '/', 'couleur': 'orange'})
        
        total_dettes = db.session.query(func.sum(Operation.montant_total - Operation.montant_avance)).filter(
            Operation.statut == 'Terminé', Operation.montant_total > Operation.montant_avance, Operation.archive == False
        ).scalar() or 0

        if total_dettes > 0:
            notifs.append({'titre': 'Recouvrement', 'message': f'Attention, {total_dettes} DH de dettes.', 'lien': url_for('clients.liste_dettes'), 'couleur': 'red'})

        return dict(notifs=notifs, nb_notifs=len(notifs), liste_boutons=liste_boutons, config=config, version_app=app.config.get('VERSION_APP'))

    @app.errorhandler(404)
    def page_non_trouvee(e): 
        return render_template('404.html'), 404

    # 3. Enregistrement des Blueprints === Déclarer les Blueprints
    from routes.clients import clients_bp
    from routes.queue import queue_bp
    from routes.caisse import caisse_bp
    app.register_blueprint(clients_bp)
    app.register_blueprint(queue_bp)
    app.register_blueprint(caisse_bp)

    from blueprints.auth import auth_bp
    from blueprints.dashboard import dashboard_bp
    from blueprints.admin import admin_bp
    app.register_blueprint(admin_bp)
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)

    from blueprints.api import api_bp
    from blueprints.exports import exports_bp
    
    app.register_blueprint(api_bp)
    app.register_blueprint(exports_bp)

    from blueprints.corbeille import corbeille_bp
    from blueprints.communication import comm_bp
    
    app.register_blueprint(corbeille_bp)
    app.register_blueprint(comm_bp)
    
    # 📌 C'EST ICI QU'ON AJOUTERA NOS NOUVEAUX BLUEPRINTS (auth, dashboard, etc.)

    return app

# POINT DE LANCEMENT DU SERVEUR
# ==========================================
def get_local_ip():
    """Fonction magique pour trouver la vraie adresse IP de ton PC sur le réseau local"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"
if __name__ == '__main__':
    from tasks import demarrer_taches_de_fond

    # 1. On crée l'application via notre usine (Factory)
    app = create_app()
    
    # 2. On s'assure que la base de données est prête
    with app.app_context(): 
        db.create_all()
    
    # 3. On lance les sauvegardes automatiques
    demarrer_taches_de_fond() 
    
    # 4. Affichage du panneau de contrôle stylé
    ip_locale = get_local_ip()
    print("\n" + "="*55)
    print("🚀 KIOSQUE PRO EN PRODUCTION (TEMPS RÉEL ACTIF) 🚀")
    print("="*55)
    print(f"💻 Accessible sur ce PC   : http://127.0.0.1:5000")
    print(f"📱 À scanner (TV/Mobiles) : http://{ip_locale}:5000")
    print("\n⚠️  Ne fermez pas cette fenêtre noire pendant le travail.")
    print("="*55 + "\n")
    
    # 5. Lancement du serveur WebSockets !
    # OPTIMISATION : J'ai mis debug=False car tu es en "Production" maintenant
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, use_reloader=False, allow_unsafe_werkzeug=True)