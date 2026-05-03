import os
from dotenv import load_dotenv
# 1. ON CHARGE LE COFFRE-FORT EN TOUT PREMIER ! 
# (Avant même d'importer le reste ou de créer l'app)
load_dotenv()
from flask_wtf.csrf import CSRFProtect
import urllib.parse
from werkzeug.utils import secure_filename
from PIL import Image
import shutil
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
from sqlalchemy import func, or_
from datetime import datetime, timedelta
import csv
import io
from flask import Flask, render_template, request, redirect, session, url_for, jsonify, send_file, make_response 
from flask_migrate import Migrate
from flask_socketio import SocketIO
from models import db, Utilisateur, Client, Operation, Service, Ticket, ConfigSysteme, BoutonRapide, PhotoRecu, Contrat

# Initialisation de l'application Flask
app = Flask(__name__)

# On récupère la clé depuis le fichier .env, et on met une clé de secours bidon par défaut si le fichier manque
app.secret_key = os.environ.get("SECRET_KEY", "cle_secours_si_env_introuvable")

# On active la protection globale !
csrf = CSRFProtect(app)

sessions_versions = {}


# Configuration de l'application

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///base.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads/recus'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# On initialise la base de données et les extensions
db.init_app(app)
migrate = Migrate(app, db)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading', ping_timeout=60, ping_interval=25)
app.socketio = socketio 

# On importe les Blueprints à la fin pour éviter les problèmes de dépendances circulaires
from routes.clients import clients_bp
from routes.queue import queue_bp
from routes.caisse import caisse_bp
app.register_blueprint(clients_bp)
app.register_blueprint(queue_bp)
app.register_blueprint(caisse_bp)

from werkzeug.security import generate_password_hash, check_password_hash
import time

# ==========================================
# CACHE MÉMOIRE GLOBAL (Fini les Freezes !)
# ==========================================
# On stocke les alertes dans la RAM du serveur, pas dans les cookies.
CACHE_NOTIFS = {'data': [], 'count': 0, 'last_update': 0}

def get_cached_notifs():
    now = time.time()
    # Cache de 5 secondes pour soulager la base de données
    if now - CACHE_NOTIFS['last_update'] > 5:
        try:
            notifs = []
            # Alerte 1 : Attente
            nb_attente = Operation.query.filter_by(statut='En attente', archive=False).count()
            if nb_attente > 0:
                notifs.append({'titre': 'Opérations', 'message': f'{nb_attente} en attente', 'lien': '/', 'couleur': 'orange'})
            
            # Alerte 2 : Dettes (Recouvrement)
            ops_dettes = Operation.query.filter(Operation.statut == 'Terminé', Operation.montant_total > Operation.montant_avance, Operation.archive == False).all()
            total_dettes = sum((op.montant_total - op.montant_avance) for op in ops_dettes if op.montant_total is not None)
            if total_dettes > 0:
                notifs.append({'titre': 'Recouvrement', 'message': f'Attention, {total_dettes} DH de dettes.', 'lien': '/clients/dettes', 'couleur': 'red'})

            CACHE_NOTIFS['data'] = notifs
            CACHE_NOTIFS['count'] = len(notifs)
            CACHE_NOTIFS['last_update'] = now
        except Exception:
            pass
    return CACHE_NOTIFS['data'], CACHE_NOTIFS['count']


# ==========================================
# 1. SÉCURITÉ & VÉRIFICATION DE SESSION
# ==========================================
def is_public_route(endpoint):
    """Vérifie si la page est accessible sans mot de passe"""
    if not endpoint: return True
    publiques = ['login', 'queue.public_view', 'queue.borne_qr', 'queue.mobile_portail', 'queue.mobile_generer', 'queue.mobile_ticket']
    return endpoint in publiques

@app.before_request
def verifier_connexion():
    # Optimisation : On ignore Socket.IO et les fichiers statiques
    if request.path.startswith('/socket.io') or request.path.startswith('/static'):
        return

    if not is_public_route(request.endpoint):
        # Sécurité 1 : Non connecté
        if not session.get('connecte'): 
            return redirect(url_for('login'))
        
        # Sécurité 2 : Traçage et Expiration (Changement d'appareil)
        user_id = session.get('user_id')
        if session.get('auth_version') != sessions_versions.get(user_id, 1):
            session.clear()
            return redirect(url_for('login', expire='1'))


# ==========================================
# 2. CONTEXT PROCESSOR OPTIMISÉ
# ==========================================
@app.context_processor
def injecter_variables_globales():
    # On n'injecte rien sur les routes d'API, statiques ou login (Gain de vitesse)
    if request.path.startswith('/api/') or request.path.startswith('/static/') or request.endpoint == 'login':
        return {}

    config = ConfigSysteme.query.first()
    liste_boutons = BoutonRapide.query.all()

    if not session.get('connecte'):
        return dict(notifs=[], nb_notifs=0, liste_boutons=liste_boutons, config=config)

    # Récupération depuis la RAM (instantané)
    notifs, nb_notifs = get_cached_notifs()
    return dict(notifs=notifs, nb_notifs=nb_notifs, liste_boutons=liste_boutons, config=config)

# --- BOUTONS RAPIDES ---
# Route pour ajouter un bouton rapide (accessible uniquement aux admins) 
@app.route('/ajouter_bouton_rapide', methods=['POST'])
def ajouter_bouton_rapide():
    if not session.get('connecte'):
        return jsonify({'success': False, 'message': 'Session expirée'}), 403

    lettre = request.form.get('lettre')
    nom_bouton = request.form.get('nom_bouton')

    if not lettre or not nom_bouton:
        return jsonify({'success': False, 'message': 'Veuillez remplir tous les champs.'}), 400

    try:
        # Fais attention ici au nom de la colonne dans ta base de données
        # (Parfois c'est nom_bouton, parfois c'est nom_service selon ton modèle)
        nouveau_raccourci = BoutonRapide(
            lettre=lettre.upper()[:1],
            nom_service=nom_bouton.strip() 
        )
        db.session.add(nouveau_raccourci)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Raccourci ajouté avec succès !'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Erreur lors de l\'ajout du raccourci.'}), 500

# Route pour supprimer un bouton rapide (accessible uniquement aux admins)
@app.route('/supprimer_bouton_rapide/<int:id_bouton>', methods=['POST'])
def supprimer_bouton_rapide(id_bouton):
    if session.get('role') == 'admin':
        bouton = BoutonRapide.query.get_or_404(id_bouton)
        db.session.delete(bouton)
        db.session.commit()
    return redirect(url_for('parametres'))

# --- ACCUEIL ---
@app.route('/')
@app.route('/dashboard')
def accueil():
    # Sécurité basique
    if not session.get('connecte'):
        return redirect(url_for('login'))

    aujourdhui = datetime.now().date()
    hier = aujourdhui - timedelta(days=1)
    
    # 1. Préparation du Graphique (7 derniers jours)
    labels_jours, donnees_ca = [], []
    for i in range(6, -1, -1):
        date_cible = aujourdhui - timedelta(days=i)
        # On formate la date en français abrégé (ex: Lun 28)
        labels_jours.append(date_cible.strftime('%a %d'))
        
        ca_du_jour = db.session.query(func.sum(Operation.montant_avance)).filter(
            func.date(Operation.date_operation) == date_cible, 
            Operation.statut == 'Terminé', # On ne compte que l'argent vraiment encaissé
            Operation.archive == False
        ).scalar() or 0
        donnees_ca.append(float(ca_du_jour))

    # 2. Récupération des dossiers
    ops_en_attente = Operation.query.filter_by(statut='En attente', archive=False).order_by(Operation.date_operation.asc()).all()
    ops_du_jour = Operation.query.filter(func.date(Operation.date_operation) == aujourdhui, Operation.archive == False).all()
    
    # 3. Calculs Financiers (Aujourd'hui vs Hier)
    ca_jour = sum((op.montant_avance or 0) for op in ops_du_jour if op.statut == 'Terminé')
    
    ca_hier = db.session.query(func.sum(Operation.montant_avance)).filter(
        func.date(Operation.date_operation) == hier, 
        Operation.statut == 'Terminé',
        Operation.archive == False
    ).scalar() or 0

    # 4. Tendance (Pour la petite flèche verte/rouge)
    if ca_hier > 0:
        evolution_ca = ((ca_jour - ca_hier) / ca_hier) * 100
    else:
        evolution_ca = 100.0 if ca_jour > 0 else 0.0

    # 5. Calcul des dettes globales
    total_dettes = db.session.query(func.sum(Operation.montant_total - Operation.montant_avance)).filter(
        Operation.statut == 'Terminé',
        Operation.montant_total > Operation.montant_avance, 
        Operation.archive == False
    ).scalar() or 0

    # Envoi de TOUTES les variables exactes attendues par dashboard.html
    return render_template('dashboard.html', 
        operations_en_attente=ops_en_attente, 
        total_operations_jour=len(ops_du_jour), 
        ca_jour=round(ca_jour, 2), 
        evolution_ca=evolution_ca,
        total_dettes=round(total_dettes, 2), 
        benefice_estime="--", # Tu pourras mettre une formule ici plus tard si tu as les marges
        labels_jours=labels_jours, 
        donnees_ca=donnees_ca
    )
# --- AUTH ---
# --- AUTHENTIFICATION SÉCURISÉE ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    erreur = "Votre session a été fermée depuis un autre appareil." if request.args.get('expire') else None
    if request.method == 'POST':
        user = Utilisateur.query.filter_by(username=request.form.get('username', '').strip()).first()
        mot_de_passe_fourni = request.form.get('password', '')

        # 💡 Rétrocompatibilité : Accepte les anciens MDP en clair ET les nouveaux hachés
        if user and (user.password == mot_de_passe_fourni or check_password_hash(user.password, mot_de_passe_fourni)):
            session.update({
                'connecte': True, 
                'user_id': user.id, # L'ID est bien stocké pour le traçage
                'username': user.username, 
                'role': user.role, 
                'guichet': getattr(user, 'guichet', '1'), 
                'auth_version': sessions_versions.get(user.id, 1)
            })
            return redirect(url_for('accueil'))
            
        erreur = "Identifiant ou mot de passe incorrect."
    return render_template('login.html', erreur=erreur)

# --- DÉCONNEXION SÉCURISÉE ---
@app.route('/logout')
def logout():
    # Sécurité : On incrémente la version de session pour déconnecter 
    # automatiquement les autres appareils fantômes de cet utilisateur
    if session.get('user_id'): 
        sessions_versions[session['user_id']] = sessions_versions.get(session['user_id'], 1) + 1
    
    session.clear()
    return redirect(url_for('login'))

# --- PROFIL --- explication : Cette route affiche la page de profil de l'utilisateur connecté.
@app.route('/profil', methods=['GET', 'POST'])
def profil():
    user = Utilisateur.query.filter_by(username=session.get('username')).first()
    if not user: return redirect(url_for('login'))
    return render_template('profil.html', user=user, erreur=None, succes=None)

# ==========================================
# ADMINISTRATION V2 (ROUTES AJAX ISOLÉES)
# ==========================================
# Route pour afficher la page des paramètres (accessible uniquement aux admins)
@app.route('/parametres', methods=['GET'])
def parametres():
    if session.get('role') != 'admin': return redirect(url_for('accueil'))
    config = ConfigSysteme.query.first()
    if not config:
        config = ConfigSysteme()
        db.session.add(config)
        db.session.commit()
    return render_template('parametres.html', services=Service.query.all(), utilisateurs=Utilisateur.query.all(), config=config)

# Route pour sauvegarder les paramètres d'identité de la boutique (accessible uniquement aux admins)
@app.route('/api/parametres/identite', methods=['POST'])
def save_identite():
    if not session.get('connecte') or session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Accès non autorisé'}), 403

    # On utilise ConfigSysteme au lieu de Config
    config = ConfigSysteme.query.first() 
    if not config:
        config = ConfigSysteme()
        db.session.add(config)

    try:
        config.nom_boutique = request.form.get('nom_boutique')
        config.info_siret = request.form.get('info_siret')
        config.info_telephone = request.form.get('info_telephone')
        config.info_adresse = request.form.get('info_adresse')
        config.imprimante_format = request.form.get('imprimante_format')
        
        config.ouverture_tiroir_auto = 'ouverture_tiroir_auto' in request.form

        db.session.commit()
        return jsonify({'success': True, 'message': 'Identité sauvegardée avec succès !'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Erreur serveur lors de la sauvegarde.'}), 500

# Route pour sauvegarder les paramètres de l'écran TV (accessible uniquement aux admins)
@app.route('/api/parametres/tv', methods=['POST'])
def save_tv():
    if not session.get('connecte') or session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Accès non autorisé'}), 403

    # On utilise ConfigSysteme au lieu de Config
    config = ConfigSysteme.query.first()
    if not config:
        config = ConfigSysteme()
        db.session.add(config)

    try:
        config.whatsapp_tv = request.form.get('whatsapp_tv')
        config.label_guichet = request.form.get('label_guichet')
        config.youtube_id = request.form.get('youtube_id')
        config.texte_arabe_tv = request.form.get('texte_arabe_tv')
        config.texte_francais_tv = request.form.get('texte_francais_tv')
        config.vitesse_defilement_tv = request.form.get('vitesse_defilement_tv', type=int)

        db.session.commit()
        return jsonify({'success': True, 'message': 'Écran TV mis à jour !'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Erreur lors de la sauvegarde.'}), 500

# Route pour sauvegarder les paramètres de la borne (accessible uniquement aux admins) 
@app.route('/api/parametres/borne', methods=['POST'])
def save_borne():
    if not session.get('connecte') or session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Accès non autorisé'}), 403

    # On utilise ConfigSysteme au lieu de Config
    config = ConfigSysteme.query.first()
    if not config:
        config = ConfigSysteme()
        db.session.add(config)

    try:
        config.borne_active_qr = 'borne_active_qr' in request.form
        config.borne_active_impression = 'borne_active_impression' in request.form
        
        config.borne_titre_fr = request.form.get('borne_titre_fr')
        config.borne_sous_titre_fr = request.form.get('borne_sous_titre_fr')
        config.borne_titre_ar = request.form.get('borne_titre_ar')
        config.borne_sous_titre_ar = request.form.get('borne_sous_titre_ar')
        
        config.ticket_nom_kiosque = request.form.get('ticket_nom_kiosque')
        config.ticket_sous_titre = request.form.get('ticket_sous_titre')
        config.ticket_message = request.form.get('ticket_message')

        db.session.commit()
        return jsonify({'success': True, 'message': 'Configuration Borne enregistrée !'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Erreur lors de la sauvegarde.'}), 500
# Route pour sauvegarder les modèles de messages WhatsApp (accessible uniquement aux admins) 
@app.route('/api/parametres/whatsapp', methods=['POST'])
def save_whatsapp():
    if not session.get('connecte') or session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Accès non autorisé'}), 403

    config = ConfigSysteme.query.first()
    if not config:
        config = ConfigSysteme()
        db.session.add(config)

    try:
        config.msg_whatsapp_dette = request.form.get('msg_whatsapp_dette')
        config.msg_whatsapp_monnaie = request.form.get('msg_whatsapp_monnaie')
        config.msg_whatsapp_recu = request.form.get('msg_whatsapp_recu')

        db.session.commit()
        return jsonify({'success': True, 'message': 'Modèles WhatsApp mis à jour !'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Erreur lors de la sauvegarde.'}), 500
from werkzeug.security import generate_password_hash
# Route pour ajouter un caissier (accessible uniquement aux admins)
@app.route('/ajouter_caissier', methods=['POST'])
def ajouter_caissier():
    if not session.get('connecte') or session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Accès non autorisé'}), 403

    username = request.form.get('username')
    password = request.form.get('password')
    guichet = request.form.get('guichet')

    if not username or not password:
        return jsonify({'success': False, 'message': 'Veuillez remplir tous les champs.'}), 400

    # Vérifier si l'utilisateur existe déjà
    user_existant = Utilisateur.query.filter_by(username=username).first()
    if user_existant:
        return jsonify({'success': False, 'message': 'Ce nom d\'utilisateur existe déjà.'}), 400

    try:
        # Hachage du mot de passe pour la sécurité
        mot_de_passe_hash = generate_password_hash(password)
        
        nouvel_utilisateur = Utilisateur(
            username=username.strip(),
            password=mot_de_passe_hash,
            role='caissier',
            guichet=guichet
        )
        db.session.add(nouvel_utilisateur)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Caissier ajouté avec succès !'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Erreur lors de l\'ajout du caissier.'}), 500

# Route pour supprimer un caissier (accessible uniquement aux admins) 
@app.route('/supprimer_caissier/<int:id>', methods=['POST'])
def supprimer_caissier(id):
    if session.get('role') == 'admin':
        utilisateur = Utilisateur.query.get_or_404(id)
        if utilisateur.role != 'admin':
            db.session.delete(utilisateur)
            db.session.commit()
    return redirect(url_for('parametres'))

# Route pour ajouter un service (accessible uniquement aux admins)
@app.route('/ajouter_service', methods=['POST'])
def ajouter_service():
    # Sécurité : vérifier si l'utilisateur est connecté
    if not session.get('connecte'):
        return jsonify({'success': False, 'message': 'Session expirée'}), 403

    lettre = request.form.get('lettre')
    nom_service = request.form.get('nom_service')

    if not lettre or not nom_service:
        return jsonify({'success': False, 'message': 'Veuillez remplir tous les champs.'}), 400

    try:
        nouveau_service = Service(
            lettre=lettre.upper()[:1], # On s'assure de n'avoir qu'une majuscule
            nom_service=nom_service.strip()
        )
        db.session.add(nouveau_service)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Service ajouté avec succès !'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Erreur lors de l\'ajout du service.'}), 500
# Route pour supprimer un service (accessible uniquement aux admins)
@app.route('/supprimer_service/<int:id_service>', methods=['POST'])
def supprimer_service(id_service):
    if session.get('role') == 'admin':
        db.session.delete(Service.query.get_or_404(id_service))
        db.session.commit()
    return redirect(url_for('parametres'))

# --- WHATSAPP INTELLIGENT --- explication : Cette route génère un message WhatsApp personnalisé en fonction du type de message demandé (dette, monnaie ou reçu) et des informations de l'opération. Elle utilise les modèles de messages définis dans la configuration du système, remplace les placeholders par les données réelles, et redirige vers l'URL de WhatsApp pour envoyer le message au client.
@app.route('/generer_whatsapp/<type_msg>/<int:id_op>')
def generer_whatsapp(type_msg, id_op):
    op = Operation.query.get_or_404(id_op)
    if not op.client.telephone: return redirect(request.referrer)
    config = ConfigSysteme.query.first()
    
    if type_msg == 'dette': texte_brut, montant = config.msg_whatsapp_dette or "Bonjour [PRENOM], reste: [MONTANT] DH", abs(op.reste_a_payer)
    elif type_msg == 'monnaie': texte_brut, montant = config.msg_whatsapp_monnaie or "Bonjour [PRENOM], monnaie: [MONTANT] DH", abs(op.reste_a_payer)
    elif type_msg == 'recu': texte_brut, montant = config.msg_whatsapp_recu or "Bonjour [PRENOM], reçu: [MONTANT] DH", op.montant_total or 0
    else: return redirect(request.referrer)

    texte_final = texte_brut.replace('[PRENOM]', op.client.prenom.capitalize()).replace('[NOM]', op.client.nom.upper()).replace('[MONTANT]', str(round(montant, 2))).replace('[DATE]', op.date_operation.strftime('%d/%m/%Y')).replace('[NB_RECUS]', str(len(op.photos)))
    tel = op.client.telephone.replace(' ', '').replace('+', '')
    tel = '212' + tel[1:] if tel.startswith('0') else ('212' + tel if not tel.startswith('212') else tel)
    return redirect(f"https://wa.me/{tel}?text={urllib.parse.quote(texte_final)}")

# --- SECURITE & EXPORTS ---
@app.route('/api/securite/backups')
def lister_backups():
    if session.get('role') != 'admin': return jsonify({'error': 'Accès refusé'}), 403
    fichiers = []
    if os.path.exists('backups'):
        for f in os.listdir('backups'):
            if f.endswith('.db'):
                chemin = os.path.join('backups', f)
                fichiers.append({'nom': f, 'taille': round(os.path.getsize(chemin) / 1024, 1), 'date': datetime.fromtimestamp(os.path.getmtime(chemin)).strftime('%d/%m/%Y à %H:%M')})
    fichiers.sort(key=lambda x: x['nom'], reverse=True)
    return jsonify(fichiers)
# Route pour télécharger un backup spécifique explication : On vérifie d'abord que l'utilisateur est admin, puis on construit le chemin complet du fichier demandé en utilisant secure_filename pour éviter les problèmes de sécurité liés aux chemins. Si le fichier existe, on le renvoie en tant que téléchargement ; sinon, on retourne une erreur 404.
@app.route('/api/securite/telecharger_backup/<nom_fichier>')
def telecharger_backup(nom_fichier):
    if session.get('role') != 'admin': return "Accès refusé", 403
    chemin_complet = os.path.join('backups', secure_filename(nom_fichier))
    return send_file(chemin_complet, as_attachment=True) if os.path.exists(chemin_complet) else ("Fichier introuvable", 404)
# Route pour supprimer un backup spécifique explication : On vérifie d'abord que l'utilisateur est admin, puis on construit le chemin complet du fichier à supprimer en utilisant secure_filename pour éviter les problèmes de sécurité liés aux chemins. Si le fichier existe, on le supprime et on retourne un message de succès ; sinon, on retourne une erreur 404.
@app.route('/export_operations_csv')
def export_operations_csv():
    if session.get('role') != 'admin': return redirect(url_for('accueil'))
    si = io.StringIO()
    cw = csv.writer(si, delimiter=';')
    cw.writerow(['ID', 'Date', 'Client', 'Montant Total', 'Avance', 'Reste', 'Statut', 'Caissier'])
    for op in Operation.query.order_by(Operation.date_operation.desc()).all():
        cw.writerow([op.id, op.date_operation.strftime('%Y-%m-%d %H:%M'), f"{op.client.nom} {op.client.prenom}", op.montant_total, op.montant_avance, (op.montant_total or 0) - (op.montant_avance or 0), op.statut, op.utilisateur_id])
    output = make_response(si.getvalue().encode('utf-8-sig'))
    output.headers["Content-Disposition"] = f"attachment; filename=export_caisse_{datetime.now().strftime('%Y%m%d')}.csv"
    output.headers["Content-type"] = "text/csv"
    return output
# Route pour exporter les clients en CSV explication : On vérifie d'abord que l'utilisateur est admin, puis on crée un flux de données en mémoire avec io.StringIO() et un objet csv.writer pour écrire les données des clients. On écrit d'abord la ligne d'en-tête, puis on parcourt tous les clients de la base de données pour écrire leurs informations. Enfin, on prépare la réponse HTTP avec le contenu CSV encodé en UTF-8 et les en-têtes appropriés pour déclencher le téléchargement du fichier.
@app.route('/export_clients_csv')
def export_clients_csv():
    if session.get('role') != 'admin': return redirect(url_for('accueil'))
    si = io.StringIO()
    cw = csv.writer(si, delimiter=';')
    cw.writerow(['ID', 'Nom', 'Prénom', 'Téléphone', 'Adresse', 'Notes'])
    for c in Client.query.all(): cw.writerow([c.id, c.nom, c.prenom, c.telephone, c.adresse, c.notes])
    output = make_response(si.getvalue().encode('utf-8-sig'))
    output.headers["Content-Disposition"] = f"attachment; filename=base_clients_{datetime.now().strftime('%Y%m%d')}.csv"
    output.headers["Content-type"] = "text/csv"
    return output
# Route pour supprimer un backup spécifique 
@app.errorhandler(404)
def page_non_trouvee(e): return render_template('404.html'), 404
# Fonction de sauvegarde de la base de données avec rotation des backups (7 max)
def sauvegarder_bdd():
    os.makedirs('backups', exist_ok=True)
    chemin_db = 'instance/base.db' if os.path.exists('instance/base.db') else 'base.db'
    if os.path.exists(chemin_db):
        shutil.copy2(chemin_db, os.path.join('backups', f"sauvegarde_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"))
        fichiers_backup = sorted([os.path.join('backups', f) for f in os.listdir('backups')])
        while len(fichiers_backup) > 7: os.remove(fichiers_backup.pop(0))

scheduler = BackgroundScheduler()
scheduler.add_job(func=sauvegarder_bdd, trigger="cron", hour=23, minute=59)
scheduler.start()
atexit.register(lambda: scheduler.shutdown())

# --- CORBEILLE (Opérations et Contrats archivés) --- 
@app.route('/corbeille')
def corbeille():
    if session.get('role') != 'admin':
        return redirect(url_for('accueil'))
    
    # On récupère les opérations et contrats marqués comme "archive=True"
    operations_supprimees = Operation.query.filter_by(archive=True).all()
    contrats_supprimes = Contrat.query.filter_by(archive=True).all()
    
    return render_template('corbeille.html', operations=operations_supprimees, contrats=contrats_supprimes)

# --- Routes pour détruire/restaurer depuis la corbeille ---
@app.route('/restaurer_operation/<int:id_op>', methods=['POST'])
def restaurer_operation(id_op):
    if session.get('role') == 'admin':
        op = Operation.query.get_or_404(id_op)
        op.archive = False
        db.session.commit()
    return redirect(url_for('corbeille'))

# Lors de la destruction définitive d'une opération, on supprime d'abord tous les fichiers associés (photos de reçus récents et ancien reçu), puis on supprime l'opération elle-même de la base de données. En cas d'erreur lors de la suppression des fichiers ou de la base de données, on effectue un rollback pour éviter les incohérences.
@app.route('/detruire_operation/<int:id_op>', methods=['POST'])
def detruire_operation(id_op):
    if session.get('role') == 'admin':
        op = Operation.query.get_or_404(id_op)
        
        try:
            # 1. Destruction physique des reçus récents (Pillow/Multiples)
            for photo in op.photos:
                chemin = os.path.join(app.config['UPLOAD_FOLDER'], photo.nom_fichier)
                if os.path.exists(chemin):
                    os.remove(chemin)
                    
            # 2. Destruction physique de l'ancien reçu (Rétrocompatibilité)
            if op.photo_recu:
                ancien_chemin = os.path.join(app.config['UPLOAD_FOLDER'], op.photo_recu)
                if os.path.exists(ancien_chemin):
                    os.remove(ancien_chemin)

            # 3. Destruction totale dans la base de données
            db.session.delete(op)
            db.session.commit()
            
        except Exception as e:
            db.session.rollback()
            print(f"Erreur lors de la destruction définitive : {e}")
            
    return redirect(url_for('corbeille'))
# Les routes pour les contrats sont similaires à celles des opérations, mais sans la partie suppression de fichiers, car les contrats n'ont pas de photos associées. On se contente de changer le champ "archive" pour les restaurer ou de les supprimer définitivement de la base de données.
@app.route('/restaurer_contrat/<int:id_contrat>', methods=['POST'])
def restaurer_contrat(id_contrat):
    if session.get('role') == 'admin':
        contrat = Contrat.query.get_or_404(id_contrat)
        contrat.archive = False
        db.session.commit()
    return redirect(url_for('corbeille'))
# Lors de la destruction définitive d'un contrat, on le supprime simplement de la base de données. En cas d'erreur lors de la suppression, on effectue un rollback pour éviter les incohérences.
@app.route('/detruire_contrat/<int:id_contrat>', methods=['POST'])
def detruire_contrat(id_contrat):
    if session.get('role') == 'admin':
        contrat = Contrat.query.get_or_404(id_contrat)
        db.session.delete(contrat)
        db.session.commit()
    return redirect(url_for('corbeille'))
# --- MOTEUR DE RECHERCHE UNIFIÉ (Clients + Contrats + telephone) ---
@app.route('/api/recherche')
def api_recherche():
    if not session.get('connecte'): 
        return jsonify([])
    
    q = request.args.get('q', '').strip()
    if len(q) < 2: 
        return jsonify([])
    
    search = f"%{q}%"
    results = []
    
    # 1. Recherche dans les Clients (Nom, Prénom, Téléphone)
    clients = Client.query.filter(
        or_(
            Client.nom.ilike(search),
            Client.prenom.ilike(search),
            Client.telephone.ilike(search)
        ),
        Client.archive == False
    ).limit(6).all()
    # On affiche d'abord les clients trouvés, car c'est ce que l'utilisateur recherche le plus souvent. Chaque résultat contient un titre (Nom Prénom), un sous-titre (Client + Téléphone), une URL vers la fiche client, et une icône.
    for c in clients:
        results.append({
            'titre': f"{c.nom.upper()} {c.prenom.capitalize()}",
            'sous_titre': f"Client • {c.telephone or 'Sans numéro'}",
            'url': url_for('clients.fiche_client', id_client=c.id),
            'icone': 'ph-user'
        })
        
    # 2. Recherche dans les Contrats (par Numéro de contrat)
    contrats = Contrat.query.filter(
        Contrat.numero_contrat.ilike(search),
        Contrat.archive == False
    ).limit(4).all()
    
    # On évite d'afficher le client en double s'il a déjà été trouvé à l'étape 1
    client_ids_trouves = [c.id for c in clients]
    for ct in contrats:
        if ct.client_id not in client_ids_trouves:
            results.append({
                'titre': f"Contrat : {ct.numero_contrat}",
                'sous_titre': f"Titulaire : {ct.nom_proprietaire} ({ct.service.nom_service})",
                'url': url_for('clients.fiche_client', id_client=ct.client_id),
                'icone': 'ph-file-text'
            })
            client_ids_trouves.append(ct.client_id)
            
    return jsonify(results)
# Route pour la page de confidentialité
@app.route('/confidentialite')
def confidentialite():
    # Pas besoin d'être connecté pour voir cette page (pratique pour l'afficher à un client à l'accueil)
    return render_template('confidentialite.html')

#  
if __name__ == '__main__':
    with app.app_context(): db.create_all()
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, use_reloader=False, allow_unsafe_werkzeug=True)