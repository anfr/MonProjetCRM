import os
import urllib.parse
from werkzeug.utils import secure_filename
from PIL import Image

from sqlalchemy import func
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, session, url_for, jsonify
from flask_migrate import Migrate
from flask_socketio import SocketIO
from models import db, Utilisateur, Client, Operation, Service, Ticket, ParametreTV, BoutonRapide, PhotoRecu

app = Flask(__name__)
# --- NOUVEAU : Mémoire pour les déconnexions globales ---
sessions_versions = {}

# ==========================================
# CONFIGURATION DE L'APPLICATION
# ==========================================
app.secret_key = "cle_secrete_super_robuste"
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///base.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads/recus'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ==========================================
# INITIALISATION (Base de données & WebSockets)
# ==========================================
db.init_app(app)
migrate = Migrate(app, db)
# Modifie cette ligne vers le haut du fichier
socketio = SocketIO(app, 
                    cors_allowed_origins="*", 
                    async_mode='threading', 
                    ping_timeout=60, 
                    ping_interval=25)
app.socketio = socketio # Attache socketio à l'app pour y accéder depuis les blueprints

# ==========================================
# IMPORT & ENREGISTREMENT DES MODULES (Blueprints)
# ==========================================
from routes.clients import clients_bp
from routes.queue import queue_bp
app.register_blueprint(clients_bp)
app.register_blueprint(queue_bp)

# --- CRÉATION SÉCURISÉE DES TABLES MANQUANTES ---
# Ce code va juste vérifier s'il manque une table et la créer sans toucher au reste
with app.app_context():
    db.create_all()

# ==========================================
# SÉCURITÉ GLOBALE (Vérification de connexion)
# ==========================================
@app.before_request
def verifier_connexion():
    # 1. On liste TOUTES les pages qui n'ont pas besoin de mot de passe
    pages_publiques = [
        'login', 
        'static', 
        'queue.public_view',      # L'écran TV
        'queue.borne_qr',         # L'affiche du QR Code
        'queue.mobile_portail',   # Le menu sur le téléphone du client
        'queue.mobile_generer',   # Le clic pour générer le ticket
        'queue.mobile_ticket'     # Le ticket virtuel sur le téléphone
    ]

    # 2. Si la page demandée n'est pas publique
    if request.endpoint and request.endpoint not in pages_publiques:
        # Si pas connecté du tout -> Dehors
        if not session.get('connecte'):
            return redirect(url_for('login'))
            
        # --- NOUVEAU : Vérification de la version (Déconnexion réseau) ---
        user_id = session.get('user_id')
        version_navigateur = session.get('auth_version')
        version_serveur = sessions_versions.get(user_id, 1)
        
        # Si le numéro de version ne correspond plus (déconnecté depuis un autre PC)
        if version_navigateur != version_serveur:
            session.clear()
            return redirect(url_for('login', expire='1')) # expire=1 affiche le message d'erreur !

# ==========================================
# NOTIFICATIONS GLOBALES (En-tête)
# ==========================================

# ==========================================
# VARIABLES GLOBALES (Notifications & Menus)
# ==========================================
@app.context_processor
def injecter_variables_globales():
    if not session.get('connecte'):
        # On essaie quand même de récupérer tv_config pour les pages publiques comme la Borne
        return dict(notifs=[], nb_notifs=0, liste_boutons=BoutonRapide.query.all(), tv_config=ParametreTV.query.first())
    
    try:
        nb_attente = Operation.query.filter_by(statut='En attente').count()
        notifs_list = []
        if nb_attente > 0:
            notifs_list.append({'titre': 'Opérations', 'message': f'{nb_attente} en attente', 'lien': '/', 'couleur': 'orange'})
            
        return dict(
            notifs=notifs_list, 
            nb_notifs=len(notifs_list), 
            liste_boutons=BoutonRapide.query.all(),
            tv_config=ParametreTV.query.first() # 👈 Ajout crucial : disponible pour TOUTES les pages
        )
    except Exception:
        return dict(notifs=[], nb_notifs=0, liste_boutons=[], tv_config=None)

# --- AJOUTER UN BOUTON RAPIDE ---
@app.route('/ajouter_bouton_rapide', methods=['POST'])
def ajouter_bouton_rapide():
    if session.get('role') == 'admin':
        lettre = request.form.get('lettre', 'A').upper()[:1] # On récupère 1 seule lettre majuscule
        nom = request.form.get('nom_bouton')
        if nom:
            nouveau = BoutonRapide(nom_service=nom, lettre=lettre)
            db.session.add(nouveau)
            db.session.commit()
    return redirect(url_for('parametres'))

# --- BAGUETTE MAGIQUE POUR METTRE A JOUR LA TABLE (SANS SUPPRIMER LES CLIENTS) ---
@app.route('/maj_table')
def maj_table():
    if session.get('role') == 'admin':
        # On supprime UNIQUEMENT la petite table des boutons (qui est vide ou presque)
        BoutonRapide.__table__.drop(db.engine)
        # On la recrée immédiatement avec la nouvelle colonne "lettre"
        db.create_all()
        return redirect(url_for('parametres'))
    return "Accès refusé"

# --- SUPPRIMER UN BOUTON RAPIDE ---
@app.route('/supprimer_bouton_rapide/<int:id_bouton>')
def supprimer_bouton_rapide(id_bouton):
    if session.get('role') == 'admin':
        bouton = BoutonRapide.query.get_or_404(id_bouton)
        db.session.delete(bouton)
        db.session.commit()
    return redirect(url_for('parametres'))



# ==========================================
# TABLEAU DE BORD (Accueil)
# ==========================================
@app.route('/')
@app.route('/dashboard')
def accueil():
    aujourdhui = datetime.now().date()
    labels_jours = []
    donnees_ca = []
    
    for i in range(6, -1, -1):
        date_cible = aujourdhui - timedelta(days=i)
        labels_jours.append(date_cible.strftime('%a %d'))
        ca_du_jour = db.session.query(func.sum(Operation.montant_avance)).filter(
            func.date(Operation.date_operation) == date_cible
        ).scalar() or 0
        donnees_ca.append(float(ca_du_jour))

    ops_en_attente = Operation.query.filter_by(statut='En attente').order_by(Operation.date_operation.asc()).all()
    ops_du_jour = Operation.query.filter(func.date(Operation.date_operation) == aujourdhui).all()
    ca_jour = sum((op.montant_avance or 0) for op in ops_du_jour)
    ops_jour_count = len(ops_du_jour)
    
    total_clients = Client.query.count()
    total_attente = len(ops_en_attente)
    ca_total = db.session.query(func.sum(Operation.montant_avance)).scalar() or 0
    
    # 🚀 L'OPTIMISATION EST ICI : On demande à SQL de faire le calcul, pas à Python !
    total_dettes = db.session.query(
        func.sum(Operation.montant_total - Operation.montant_avance)
    ).filter(
        Operation.montant_total > Operation.montant_avance
    ).scalar() or 0

    dernieres_ops = Operation.query.filter_by(statut='Terminé').order_by(Operation.date_operation.desc()).limit(5).all()

    return render_template('dashboard.html', 
                           operations=ops_en_attente, total_clients=total_clients,
                           total_attente=total_attente, ca_jour=ca_jour,
                           ops_jour_count=ops_jour_count, ca_mois=ca_jour,
                           chiffre_affaires=ca_total, total_dettes=round(total_dettes, 2),
                           dernieres_operations=dernieres_ops, labels_jours=labels_jours, 
                           donnees_ca=donnees_ca)

# ==========================================
# AUTHENTIFICATION & PROFIL
# ==========================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    erreur = None
    
    # Message si on a été déconnecté par un autre PC
    if request.args.get('expire'):
        erreur = "Votre session a été fermée depuis un autre appareil."
        
    if request.method == 'POST':
        username_saisi = request.form.get('username', '').strip()
        password_saisi = request.form.get('password', '')
        
        user = Utilisateur.query.filter_by(username=username_saisi).first()
        
        if user and user.password == password_saisi:
            # On donne la version actuelle à l'appareil qui se connecte (1 par défaut)
            version_actuelle = sessions_versions.get(user.id, 1)
            
            session.update({
                'connecte': True, 
                'user_id': user.id, 
                'username': user.username, 
                'role': user.role,
                'guichet': getattr(user, 'guichet', '1'),
                'auth_version': version_actuelle  # 👈 La clé magique !
            })
            return redirect(url_for('accueil'))
        else:
            erreur = "Identifiant ou mot de passe incorrect."
            
    return render_template('login.html', erreur=erreur)

@app.route('/logout')
def logout():
    # --- NOUVEAU : Le Kill Switch pour les autres PC ---
    user_id = session.get('user_id')
    if user_id:
        # On passe à la version supérieure. Tous les autres PC ont l'ancienne version !
        sessions_versions[user_id] = sessions_versions.get(user_id, 1) + 1

    # 1. On vide la session locale de ce PC
    session.clear()
    
    # 2. On prépare la redirection
    reponse = redirect(url_for('login'))
    
    # 3. Anti-cache (pour être sûr que la page login s'affiche bien)
    reponse.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    reponse.headers["Pragma"] = "no-cache"
    reponse.headers["Expires"] = "0"
    
    return reponse

@app.route('/profil', methods=['GET', 'POST'])
def profil():
    if 'username' not in session:
        return redirect(url_for('login'))

    user = Utilisateur.query.filter_by(username=session['username']).first()
    if not user:
        return "Utilisateur introuvable", 404

    erreur = None
    succes = None

    if request.method == 'POST':
        nouveau_username = request.form.get('username')
        
        if nouveau_username != user.username:
            existant = Utilisateur.query.filter_by(username=nouveau_username).first()
            if existant:
                erreur = "Ce nom d'utilisateur est déjà utilisé par un autre compte."
            else:
                user.username = nouveau_username
                session['username'] = nouveau_username
        
        if not erreur:
            user.prenom = request.form.get('prenom')
            user.nom = request.form.get('nom')
            user.telephone = request.form.get('telephone')
            user.email = request.form.get('email')

            ancien_mdp = request.form.get('ancien_mdp')
            nouveau_mdp = request.form.get('nouveau_mdp')
            confirmer_mdp = request.form.get('confirmer_mdp')

            if ancien_mdp or nouveau_mdp or confirmer_mdp:
                if ancien_mdp != user.password:
                    erreur = "L'ancien mot de passe est incorrect."
                elif nouveau_mdp != confirmer_mdp:
                    erreur = "Les nouveaux mots de passe ne correspondent pas."
                elif len(nouveau_mdp) < 4:
                    erreur = "Le nouveau mot de passe est trop court."
                else:
                    user.password = nouveau_mdp
                    succes = "Profil et mot de passe mis à jour avec succès !"

            if not erreur and not succes:
                succes = "Profil mis à jour avec succès !"
            
            if not erreur:
                db.session.commit()

    return render_template('profil.html', user=user, erreur=erreur, succes=succes)

# ==========================================
# ADMINISTRATION (Paramètres, TV, Équipe, Services)
# ==========================================
@app.route('/parametres', methods=['GET', 'POST'])
def parametres():
    if session.get('role') != 'admin':
        return redirect(url_for('accueil'))
    
    tv_config = ParametreTV.query.first()
    if not tv_config:
        tv_config = ParametreTV()
        db.session.add(tv_config)
        db.session.commit()

    if request.method == 'POST' and 'sauvegarder_tv' in request.form:
        tv_config.whatsapp = request.form.get('whatsapp')
        tv_config.texte_arabe = request.form.get('texte_arabe')
        tv_config.texte_francais = request.form.get('texte_francais')
        tv_config.vitesse_defilement = int(request.form.get('vitesse_defilement', 20))
        tv_config.label_guichet = request.form.get('label_guichet', 'GUICHET')
        tv_config.youtube_id = request.form.get('youtube_id', '5qap5aO4i9A')
        tv_config.service_rapide_id = request.form.get('service_rapide_id')
        tv_config.msg_whatsapp_dette = request.form.get('msg_whatsapp_dette')
        tv_config.msg_whatsapp_monnaie = request.form.get('msg_whatsapp_monnaie')
        tv_config.msg_whatsapp_recu = request.form.get('msg_whatsapp_recu')
        # 👇 NOUVEAU : Sauvegarde des paramètres de la borne
        tv_config.borne_titre_fr = request.form.get('borne_titre_fr')
        tv_config.borne_titre_ar = request.form.get('borne_titre_ar')
        tv_config.borne_sous_titre_fr = request.form.get('borne_sous_titre_fr')
        tv_config.borne_sous_titre_ar = request.form.get('borne_sous_titre_ar')
        tv_config.borne_active_qr = 'borne_active_qr' in request.form
        tv_config.borne_active_impression = 'borne_active_impression' in request.form
        # 👇 AJOUTE CES LIGNES POUR LA BORNE 👇
        tv_config.borne_titre_fr = request.form.get('borne_titre_fr')
        tv_config.borne_titre_ar = request.form.get('borne_titre_ar')
        tv_config.borne_sous_titre_fr = request.form.get('borne_sous_titre_fr')
        tv_config.borne_sous_titre_ar = request.form.get('borne_sous_titre_ar')
        tv_config.borne_active_qr = 'borne_active_qr' in request.form
        tv_config.borne_active_impression = 'borne_active_impression' in request.form

        db.session.commit()
        return redirect(url_for('parametres'))

    return render_template('parametres.html', 
                           services=Service.query.all(), 
                           utilisateurs=Utilisateur.query.all(),
                           tv_config=tv_config)

@app.route('/ajouter_caissier', methods=['POST'])
def ajouter_caissier():
    if session.get('role') == 'admin':
        username = request.form.get('username')
        password = request.form.get('password')
        guichet = request.form.get('guichet')
        
        utilisateur_existant = Utilisateur.query.filter_by(username=username).first()
        if utilisateur_existant:
            print(f"Erreur : L'utilisateur {username} existe déjà !")
            return redirect(url_for('parametres'))
        
        nouveau_caissier = Utilisateur(
            username=username, 
            password=password, 
            role='caissier', 
            guichet=guichet
        )
        db.session.add(nouveau_caissier)
        db.session.commit()
        
    return redirect(url_for('parametres'))

@app.route('/supprimer_caissier/<int:id>')
def supprimer_caissier(id):
    if session.get('role') != 'admin':
        return redirect(url_for('accueil'))

    utilisateur = Utilisateur.query.get_or_404(id)
    if utilisateur.role != 'admin':
        db.session.delete(utilisateur)
        db.session.commit()
        
    return redirect(url_for('parametres'))

@app.route('/ajouter_service', methods=['POST'])
def ajouter_service():
    if session.get('role') == 'admin':
        nom = request.form.get('nom_service')
        lettre = request.form.get('lettre', 'A').upper()[:1]
        if nom:
            existant = Service.query.filter_by(lettre=lettre).first()
            if not existant:
                db.session.add(Service(nom_service=nom, lettre=lettre))
                db.session.commit()
                
    return redirect(url_for('parametres'))

@app.route('/supprimer_service/<int:id_service>')
def supprimer_service(id_service):
    if session.get('role') == 'admin':
        try:
            service = Service.query.get_or_404(id_service)
            db.session.delete(service)
            db.session.commit()
        except Exception:
            db.session.rollback()
    return redirect(url_for('parametres'))

# ==========================================
# OPÉRATIONS & RECHERCHE API
# ==========================================
@app.route('/cloturer_operation/<int:id_op>', methods=['POST'])
def cloturer_operation(id_op):
    op = Operation.query.get_or_404(id_op)
    montant_final = request.form.get('montant_total')

    if montant_final:
        op.montant_total = float(montant_final)
        op.statut = 'Terminé'

        # On récupère tous les fichiers envoyés
        files = request.files.getlist('photo_recu')
        
        # Correction du bug : On utilise enumerate pour l'index i et on définit bien 'file'
        for i, file in enumerate(files):
            if file and file.filename != '':
                # Nouveau nom : FA_AAAAMMJJ_IDUSER_IDOP_INDEX.jpg
                date_str = datetime.now().strftime('%Y%m%d')
                user_id = session.get('user_id', 0)
                nom_fichier = f"FA_{date_str}_{user_id}_{op.id}_{i}.jpg"
                
                chemin_complet = os.path.join(app.config['UPLOAD_FOLDER'], nom_fichier)
                
                try:
                    img = Image.open(file)
                    if img.mode in ("RGBA", "P"): img = img.convert("RGB")
                    img.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
                    img.save(chemin_complet, "JPEG", optimize=True, quality=60)
                    
                    # Enregistrement dans la table PhotoRecu
                    nouvelle_photo = PhotoRecu(nom_fichier=nom_fichier, operation_id=op.id)
                    db.session.add(nouvelle_photo)
                except Exception as e:
                    print(f"Erreur compression : {e}")

        db.session.commit()
    return redirect(url_for('accueil'))

@app.route('/api/recherche')
def api_recherche():
    q = request.args.get('q', '').lower()
    if len(q) < 2: return jsonify([])
    resultats = Client.query.filter(
        (Client.nom.ilike(f'%{q}%')) | 
        (Client.prenom.ilike(f'%{q}%')) | 
        (Client.telephone.ilike(f'%{q}%'))
    ).limit(10).all()
    return jsonify([{'titre': f"{c.nom.upper()} {c.prenom.capitalize()} ({c.telephone or 'Sans tel'})", 
                     'url': url_for('clients.fiche_client', id_client=c.id)} for c in resultats])

# --- 1. ROUTE DE MISE À JOUR DE LA BASE (À utiliser une seule fois) ---
@app.route('/maj_whatsapp_db')
def maj_whatsapp_db():
    if session.get('role') == 'admin':
        try:
            with db.engine.connect() as conn:
                conn.execute(db.text('ALTER TABLE parametre_tv ADD COLUMN msg_whatsapp_dette TEXT'))
                conn.execute(db.text('ALTER TABLE parametre_tv ADD COLUMN msg_whatsapp_monnaie TEXT'))
                conn.execute(db.text('ALTER TABLE parametre_tv ADD COLUMN msg_whatsapp_recu TEXT'))
                conn.commit()
            return "Base de données mise à jour avec succès ! Tu peux retourner à l'accueil."
        except Exception as e:
            return f"Erreur ou colonnes déjà existantes : {e}"
    return "Accès refusé"

# --- 2. LE MOTEUR D'ENVOI WHATSAPP INTELLIGENT ---
@app.route('/generer_whatsapp/<type_msg>/<int:id_op>')
def generer_whatsapp(type_msg, id_op):
    op = Operation.query.get_or_404(id_op)
    if not op.client.telephone:
        return redirect(request.referrer)

    tv_config = ParametreTV.query.first()
    
    # Modèles par défaut ultra-pro
    def_dette = "Bonjour [PRENOM], il reste un solde de [MONTANT] DH sur votre dossier du [DATE]. Merci de passer au kiosque ! 🙏"
    def_monnaie = "Bonjour [PRENOM], votre monnaie de [MONTANT] DH est prête au Kiosque. 😊"
    def_recu = "Bonjour [PRENOM], vos [NB_RECUS] factures d'un montant total de [MONTANT] DH ont bien été payées le [DATE]. Merci de votre confiance ! ✨"

    if type_msg == 'dette':
        texte_brut = tv_config.msg_whatsapp_dette or def_dette
        montant = abs(op.reste_a_payer)
    elif type_msg == 'monnaie':
        texte_brut = tv_config.msg_whatsapp_monnaie or def_monnaie
        montant = abs(op.reste_a_payer)
    elif type_msg == 'recu':
        texte_brut = tv_config.msg_whatsapp_recu or def_recu
        montant = op.montant_total or 0
    else:
        return redirect(request.referrer)

    # Remplacements intelligents
    texte_final = texte_brut.replace('[PRENOM]', op.client.prenom.capitalize())
    texte_final = texte_final.replace('[NOM]', op.client.nom.upper())
    texte_final = texte_final.replace('[MONTANT]', str(round(montant, 2)))
    texte_final = texte_final.replace('[DATE]', op.date_operation.strftime('%d/%m/%Y'))
    texte_final = texte_final.replace('[NB_RECUS]', str(len(op.photos))) # 👈 Nouvelle variable !

    # Formatage du téléphone
    telephone = op.client.telephone.replace(' ', '').replace('+', '')
    if not telephone.startswith('212'):
        telephone = '212' + telephone[1:] if telephone.startswith('0') else '212' + telephone

    return redirect(f"https://wa.me/{telephone}?text={urllib.parse.quote(texte_final)}")

#==================route temporaire ================================
@app.route('/maj_ticket_db')
def maj_ticket_db():
    if session.get('role') == 'admin':
        try:
            with db.engine.connect() as conn:
                conn.execute(db.text('ALTER TABLE parametre_tv ADD COLUMN ticket_nom_kiosque VARCHAR(100)'))
                conn.execute(db.text('ALTER TABLE parametre_tv ADD COLUMN ticket_sous_titre VARCHAR(100)'))
                conn.execute(db.text('ALTER TABLE parametre_tv ADD COLUMN ticket_message TEXT'))
                conn.commit()
            return "Base de données TICKET mise à jour avec succès !"
        except Exception as e:
            return f"Erreur ou colonnes déjà existantes : {e}"
    return "Accès refusé"


# ==========================================
# ROUTE TEMPORAIRE : MISE À JOUR STUDIO BORNE
# ==========================================
@app.route('/force_synchro_db')
def force_synchro_db():
    if session.get('role') == 'admin':
        try:
            with db.engine.connect() as conn:
                # Création manuelle de la table PhotoRecu si elle n'existe pas
                conn.execute(db.text('''
                    CREATE TABLE IF NOT EXISTS photo_recu (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        nom_fichier VARCHAR(255) NOT NULL,
                        operation_id INTEGER NOT NULL,
                        FOREIGN KEY(operation_id) REFERENCES operation (id)
                    )
                '''))
                conn.commit()
            return "✅ Table PhotoRecu créée ! Les prochains reçus s'afficheront."
        except Exception as e:
            return f"❌ Erreur : {e}"
    return "Accès refusé"

#=================gérer les pages 404 ========================

@app.errorhandler(404)
def page_non_trouvee(e):
    # e contient le message d'erreur original, mais on l'ignore pour afficher notre page
    return render_template('404.html'), 404

# ==========================================
# LANCEMENT DU SERVEUR
# ==========================================
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    
    # use_reloader=False pour éviter le crash sous Windows avec SocketIO
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, use_reloader=False, allow_unsafe_werkzeug=True)


