from flask import Blueprint, render_template, request, redirect, session
from models import db, Utilisateur, Operation

auth_bp = Blueprint('auth', __name__)

# --- SÉCURITÉ GLOBALE ---
# On utilise .before_app_request pour que ça protège TOUS les Blueprints
@auth_bp.before_app_request
def verifier_connexion():
    pages_publiques = ['/login', '/queue/public'] # Ajoute la page publique de la file d'attente ici !
    if request.path not in pages_publiques and not request.path.startswith('/static'):
        if not session.get('connecte'):
            return redirect('/login')

# --- NOTIFICATIONS GLOBALES ---
@auth_bp.app_context_processor
def injecter_notifications():
    if not session.get('connecte'):
        return dict(notifs=[], nb_notifs=0)

    notifs = []
    # Alerte 1 : Opérations en attente
    nb_attente = Operation.query.filter_by(statut='En attente').count()
    if nb_attente > 0:
        notifs.append({
            'titre': 'Opérations en attente',
            'message': f'Vous avez {nb_attente} client(s) en attente.',
            'lien': '/',
            'couleur': 'orange',
            'icone': '...' # Garde ton SVG ici
        })

    # Alerte 2 : Dettes
    ops_dettes = Operation.query.filter(Operation.statut == 'Terminé', Operation.montant_total > Operation.montant_avance).all()
    total_dettes = sum((op.montant_total - op.montant_avance) for op in ops_dettes if op.montant_total is not None)
    if total_dettes > 0:
        notifs.append({
            'titre': 'Recouvrement',
            'message': f'Attention, {total_dettes} DH de dettes.',
            'lien': '/dettes',
            'couleur': 'red',
            'icone': '...' # Garde ton SVG ici
        })

    return dict(notifs=notifs, nb_notifs=len(notifs))

# --- ROUTES LOGIN / LOGOUT ---
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    # ... (ton code de login actuel)
    return render_template('login.html', erreur=erreur)

@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect('/login')