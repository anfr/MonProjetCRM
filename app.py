from flask import Flask, render_template, request, redirect, session, Response, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta

import csv
import io
import os      # Indispensable pour créer des dossiers et chemins
import uuid    # Indispensable pour générer des noms de fichiers uniques
from werkzeug.utils import secure_filename
from PIL import Image

app = Flask(__name__)

# ==========================================
# 📂 CONFIGURATION DES DOSSIERS
# ==========================================
# On définit le dossier où seront rangées les photos
UPLOAD_FOLDER = 'static/uploads/recus'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def compresser_et_sauvegarder_image(file, chemin_sauvegarde):
    """
    Prend une image lourde, la redimensionne si elle est immense,
    et la compresse intelligemment avant de la sauvegarder.
    """
    # 1. Ouvrir l'image envoyée par le téléphone
    img = Image.open(file)
    
    # 2. Convertir en mode RGB (nécessaire si l'image est un PNG transparent)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
        
    # 3. Réduire la taille maximale (ex: 1200px de large maximum)
    # C'est largement suffisant pour lire du texte sur un reçu, et ça tue le poids !
    taille_max = (1200, 1200)
    img.thumbnail(taille_max, Image.Resampling.LANCZOS)
    
    # 4. Sauvegarder l'image optimisée (format JPEG, qualité 80% = invisible à l'œil nu)
    img.save(chemin_sauvegarde, format='JPEG', optimize=True, quality=80)

# On s'assure que le dossier existe, sinon on le crée
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.secret_key = "cle_secrete_super_robuste"
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///ma_base.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ==========================================
# 🗄️ NOS TABLEAUX (MODÈLES) - AVEC RÔLES !
# ==========================================

class Utilisateur(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    nom = db.Column(db.String(100))        # NOUVEAU
    prenom = db.Column(db.String(100))     # NOUVEAU
    email = db.Column(db.String(120))      # NOUVEAU
    telephone = db.Column(db.String(20))   # NOUVEAU
    password = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), default='caissier')
    operations_faites = db.relationship('Operation', backref='caissier', lazy=True)

class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(100), nullable=False)
    prenom = db.Column(db.String(100), nullable=False)
    telephone = db.Column(db.String(20), nullable=False)
    adresse = db.Column(db.String(200))
    notes = db.Column(db.Text, nullable=True)
    archive = db.Column(db.Boolean, default=False)
    contrats = db.relationship('Contrat', backref='client', lazy=True, cascade="all, delete")
    operations = db.relationship('Operation', backref='client', lazy=True, cascade="all, delete")

class Service(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nom_service = db.Column(db.String(50), nullable=False)
    contrats = db.relationship('Contrat', backref='service', lazy=True, cascade="all, delete")

class Contrat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    numero_contrat = db.Column(db.String(100), nullable=False)
    nom_proprietaire = db.Column(db.String(150), nullable=False)
    notes = db.Column(db.Text, nullable=True) # <--- NOUVEAU CHAMP : Notes sur le contrat
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey('service.id'), nullable=False)

class Operation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date_operation = db.Column(db.DateTime, default=datetime.now)
    montant_avance = db.Column(db.Float, default=0.0)
    montant_total = db.Column(db.Float, nullable=True)
    statut = db.Column(db.String(20), default='En attente')
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    utilisateur_id = db.Column(db.Integer, db.ForeignKey('utilisateur.id'), nullable=False) 
    photo_recu = db.Column(db.String(255), nullable=True) 


# ==========================================
# 🔒 SÉCURITÉ GLOBALE
# ==========================================

@app.before_request
def verifier_connexion():
    pages_publiques = ['/login']
    if request.path not in pages_publiques and not request.path.startswith('/static'):
        if not session.get('connecte'):
            return redirect('/login')

# ==========================================
# 🔔 NOTIFICATIONS GLOBALES (POUR TOUTES LES PAGES)
# ==========================================
@app.context_processor
def injecter_notifications():
    # Si l'utilisateur n'est pas connecté, on n'affiche rien
    if not session.get('connecte'):
        return dict(notifs=[], nb_notifs=0)

    notifs = []
    
    # Alerte 1 : Opérations en attente (Oubli de clôture ?)
    nb_attente = Operation.query.filter_by(statut='En attente').count()
    if nb_attente > 0:
        notifs.append({
            'titre': 'Opérations en attente',
            'message': f'Vous avez {nb_attente} client(s) en file d\'attente.',
            'lien': '/',
            'couleur': 'orange',
            'icone': '<path stroke-linecap="round" stroke-linejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" />'
        })

    # Alerte 2 : Trou dans la caisse (Dettes)
    ops_dettes = Operation.query.filter(Operation.statut == 'Terminé', Operation.montant_total > Operation.montant_avance).all()
    total_dettes = sum((op.montant_total - op.montant_avance) for op in ops_dettes if op.montant_total is not None)
    if total_dettes > 0:
        notifs.append({
            'titre': 'Recouvrement',
            'message': f'Attention, vous avez {total_dettes} DH de dettes dehors.',
            'lien': '/dettes',
            'couleur': 'red',
            'icone': '<path stroke-linecap="round" stroke-linejoin="round" d="M12 6v12m-3-2.818l.879.659c1.171.879 3.07.879 4.242 0 1.172-.879 1.172-2.303 0-3.182C13.536 12.219 12.768 12 12 12c-.725 0-1.45-.22-2.003-.659-1.106-.879-1.106-2.303 0-3.182s2.9-.879 4.006 0l.415.33M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />'
        })

    return dict(notifs=notifs, nb_notifs=len(notifs))

@app.route('/login', methods=['GET', 'POST'])
def login():
    erreur = None
    if request.method == 'POST':
        username_saisi = request.form.get('username', 'admin')
        mdp_saisi = request.form.get('password')
        
        user = Utilisateur.query.filter_by(username=username_saisi).first()
        
        if user and mdp_saisi == user.password:
            session['connecte'] = True
            session['user_id'] = user.id
            session['role'] = user.role
            session['username'] = user.username
            return redirect('/')
        else:
            erreur = "Identifiants incorrects !"
            
    return render_template('login.html', erreur=erreur)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')


# ==========================================
# 📊 TABLEAU DE BORD PRINCIPAL
# ==========================================

@app.route('/')
def accueil():
    # 1. Les données de base
    operations_en_cours = Operation.query.filter_by(statut='En attente').all()
    total_clients = Client.query.filter_by(archive=False).count()
    total_attente = Operation.query.filter_by(statut='En attente').count()
    operations_terminees = Operation.query.filter_by(statut='Terminé').all()
    
    # 2. Les dates utiles pour les stats
    aujourd_hui = datetime.now().date()
    debut_mois = aujourd_hui.replace(day=1)
    
    # 3. Calculs des Statistiques (Aujourd'hui, Mois, Total)
    chiffre_affaires_total = 0
    ca_jour = 0
    ca_mois = 0
    ops_jour_count = 0
    
    for op in operations_terminees:
        if op.montant_total is not None:
            chiffre_affaires_total += op.montant_total
            op_date = op.date_operation.date()
            
            # Si c'est ce mois-ci
            if op_date >= debut_mois:
                ca_mois += op.montant_total
            
            # Si c'est aujourd'hui
            if op_date == aujourd_hui:
                ca_jour += op.montant_total
                ops_jour_count += 1
                
    # 4. Calcul des dettes (L'Alerte Rouge !)
    operations_dettes = Operation.query.filter(Operation.statut == 'Terminé', Operation.montant_total > Operation.montant_avance).all()
    total_dettes = sum((op.montant_total - op.montant_avance) for op in operations_dettes if op.montant_total is not None)
    
    # 5. Mini-historique : Les 5 dernières opérations terminées
    dernieres_operations = Operation.query.filter_by(statut='Terminé').order_by(Operation.date_operation.desc()).limit(5).all()
    
    # 6. Données pour le Graphique (inchangé)
    labels_jours = []
    donnees_ca = []
    
    for i in range(6, -1, -1):
        jour_cible = aujourd_hui - timedelta(days=i)
        labels_jours.append(jour_cible.strftime('%d/%m'))
        
        debut_jour = datetime.combine(jour_cible, datetime.min.time())
        fin_jour = datetime.combine(jour_cible, datetime.max.time())
        
        ops_du_jour = Operation.query.filter(
            Operation.statut == 'Terminé',
            Operation.date_operation >= debut_jour,
            Operation.date_operation <= fin_jour
        ).all()
        
        ca_du_jour = sum(op.montant_total for op in ops_du_jour if op.montant_total is not None)
        donnees_ca.append(ca_du_jour)
        
    return render_template('dashboard.html', 
                           operations=operations_en_cours, 
                           total_clients=total_clients, 
                           total_attente=total_attente, 
                           chiffre_affaires=chiffre_affaires_total, 
                           ca_jour=ca_jour,
                           ca_mois=ca_mois,
                           ops_jour_count=ops_jour_count,
                           total_dettes=total_dettes,
                           dernieres_operations=dernieres_operations,
                           labels_jours=labels_jours, 
                           donnees_ca=donnees_ca)


# ==========================================
# 👥 GESTION DES CLIENTS
# ==========================================

@app.route('/clients')
def liste_clients():
    mot_cle = request.args.get('q')
    if mot_cle:
        tous_les_clients = Client.query.filter(Client.archive == False, ((Client.nom.contains(mot_cle)) | (Client.prenom.contains(mot_cle)) | (Client.telephone.contains(mot_cle)))).all()
    else:
        tous_les_clients = Client.query.filter_by(archive=False).all()
    return render_template('clients.html', clients=tous_les_clients)

@app.route('/ajouter_client', methods=['GET', 'POST'])
def ajouter_client():
    if request.method == 'POST':
        nouveau_client = Client(
            nom=request.form.get('nom'), 
            prenom=request.form.get('prenom'), 
            telephone=request.form.get('telephone'), 
            adresse=request.form.get('adresse')
        )
        db.session.add(nouveau_client)
        db.session.commit()
        return redirect('/clients')
    return render_template('ajouter_client.html')

@app.route('/modifier_client/<int:id_client>', methods=['GET', 'POST'])
def modifier_client(id_client):
    client_a_modifier = Client.query.get_or_404(id_client)
    if request.method == 'POST':
        client_a_modifier.nom = request.form.get('nom')
        client_a_modifier.prenom = request.form.get('prenom')
        client_a_modifier.telephone = request.form.get('telephone')
        client_a_modifier.adresse = request.form.get('adresse')
        db.session.commit()
        return redirect('/clients')
    return render_template('modifier_client.html', client=client_a_modifier)

@app.route('/supprimer_client/<int:id_client>')
def supprimer_client(id_client):
    if session.get('role') != 'admin':
        return redirect('/clients')
        
    client_a_supprimer = Client.query.get_or_404(id_client)
    db.session.delete(client_a_supprimer)
    db.session.commit()
    return redirect('/clients')

@app.route('/client/<int:id_client>')
def fiche_client(id_client):
    client_actuel = Client.query.get_or_404(id_client)
    tous_les_services = Service.query.all()
    
    # On récupère toutes les opérations de ce client précis, de la plus récente à la plus ancienne
    historique_client = Operation.query.filter_by(client_id=id_client).order_by(Operation.date_operation.desc()).all()
    
    return render_template('fiche_client.html', client=client_actuel, services=tous_les_services, historique=historique_client)

@app.route('/maj_notes/<int:id_client>', methods=['POST'])
def maj_notes(id_client):
    client_actuel = Client.query.get_or_404(id_client)
    client_actuel.notes = request.form.get('notes')
    db.session.commit()
    return redirect(f'/client/{id_client}')


# ==========================================
# 📄 GESTION DES CONTRATS & OPÉRATIONS (TERMINAL EXPRESS)
# ==========================================

@app.route('/ajouter_contrat/<int:id_client>', methods=['POST'])
def ajouter_contrat(id_client):
    nouveau_contrat = Contrat(
        numero_contrat=request.form.get('numero_contrat'), 
        nom_proprietaire=request.form.get('nom_proprietaire'), 
        notes=request.form.get('notes'), # <--- NOUVEAU : Enregistrement de la note
        client_id=id_client, 
        service_id=request.form.get('service_id')
    )
    db.session.add(nouveau_contrat)
    db.session.commit()
    return redirect(f'/client/{id_client}')

@app.route('/supprimer_contrat/<int:id_contrat>')
def supprimer_contrat(id_contrat):
    if session.get('role') != 'admin':
        return redirect('/')
        
    contrat_a_supprimer = Contrat.query.get_or_404(id_contrat)
    id_du_client = contrat_a_supprimer.client_id
    db.session.delete(contrat_a_supprimer)
    db.session.commit()
    return redirect(f'/client/{id_du_client}')

@app.route('/nouvelle_operation/<int:id_client>', methods=['POST'])
def nouvelle_operation(id_client):
    mode = request.form.get('mode_operation') # 'attente' ou 'immediat'
    
    avance = request.form.get('montant_avance')
    if not avance: avance = 0.0
    
    nouvelle_op = Operation(
        client_id=id_client, 
        montant_avance=float(avance),
        utilisateur_id=session.get('user_id')
    )

    # Si c'est une clôture immédiate (Le client est devant nous)
    if mode == 'immediat':
        total = request.form.get('montant_total')
        if not total: total = 0.0
        nouvelle_op.montant_total = float(total)
        nouvelle_op.statut = 'Terminé'
        
        # Gestion de la photo
        if 'photo_recu' in request.files:
            file = request.files['photo_recu']
            if file and file.filename != '':
                nom_fichier_photo = f"{uuid.uuid4().hex}_recu.jpg"
                chemin_sauvegarde = os.path.join(app.config['UPLOAD_FOLDER'], nom_fichier_photo)
                compresser_et_sauvegarder_image(file, chemin_sauvegarde)
                nouvelle_op.photo_recu = nom_fichier_photo
    else:
        # Si le client a juste déposé l'argent et est parti
        nouvelle_op.statut = 'En attente'
        
    db.session.add(nouvelle_op)
    db.session.commit()
    return redirect(f'/client/{id_client}')

@app.route('/cloturer_operation/<int:id_op>', methods=['POST'])
def cloturer_operation(id_op):
    op = Operation.query.get_or_404(id_op)
    
    total = request.form.get('montant_total')
    if not total: total = 0.0
    op.montant_total = float(total)
    
    if 'photo_recu' in request.files:
        file = request.files['photo_recu']
        if file and file.filename != '':
            nom_fichier_photo = f"{uuid.uuid4().hex}_recu.jpg"
            chemin_sauvegarde = os.path.join(app.config['UPLOAD_FOLDER'], nom_fichier_photo)
            compresser_et_sauvegarder_image(file, chemin_sauvegarde)
            op.photo_recu = nom_fichier_photo
            
    op.statut = 'Terminé'
    db.session.commit()
    # On redirige vers la page d'où l'utilisateur vient (Dashboard OU Historique)
    return redirect(request.referrer or '/')

@app.route('/supprimer_operation/<int:id_op>')
def supprimer_operation(id_op):
    if session.get('role') != 'admin':
        return redirect(request.referrer or '/')
        
    op_a_supprimer = Operation.query.get_or_404(id_op)
    db.session.delete(op_a_supprimer)
    db.session.commit()
    return redirect(request.referrer or '/')


# ==========================================
# 💰 HISTORIQUE & DETTES
# ==========================================

@app.route('/historique')
def historique():
    operations_terminees = Operation.query.filter_by(statut='Terminé').order_by(Operation.date_operation.desc()).all()
    return render_template('historique.html', operations=operations_terminees)

@app.route('/regler_reste/<int:id_op>')
def regler_reste(id_op):
    op = Operation.query.get_or_404(id_op)
    if op.montant_total is not None:
        op.montant_avance = op.montant_total 
    op.statut = 'Terminé'
    db.session.commit()
    # NOUVEAU : On retourne d'où on vient (Fiche client OU page Dettes)
    return redirect(request.referrer or '/historique')

@app.route('/dettes')
def liste_dettes():
    operations_dettes = Operation.query.filter(Operation.statut == 'Terminé', Operation.montant_total > Operation.montant_avance).all()
    total_dettes = sum((op.montant_total - op.montant_avance) for op in operations_dettes if op.montant_total is not None)
    return render_template('dettes.html', operations=operations_dettes, total_dettes=total_dettes)


# ==========================================
# ⚙️ PARAMÈTRES & ÉQUIPE
# ==========================================

@app.route('/parametres')
def parametres():
    if session.get('role') != 'admin':
        return redirect('/')
        
    tous_les_services = Service.query.all()
    tous_les_utilisateurs = Utilisateur.query.all()
    
    return render_template('parametres.html', services=tous_les_services, utilisateurs=tous_les_utilisateurs)

@app.route('/ajouter_service', methods=['POST'])
def ajouter_service():
    if session.get('role') != 'admin': return redirect('/')
    nouveau_nom = request.form.get('nom_service')
    if nouveau_nom:
        db.session.add(Service(nom_service=nouveau_nom))
        db.session.commit()
    return redirect('/parametres')

@app.route('/supprimer_service/<int:id_service>')
def supprimer_service(id_service):
    if session.get('role') != 'admin': return redirect('/')
    service_a_supprimer = Service.query.get_or_404(id_service)
    db.session.delete(service_a_supprimer)
    db.session.commit()
    return redirect('/parametres')

@app.route('/profil', methods=['GET', 'POST'])
def profil():
    if not session.get('connecte'): return redirect('/login')
    
    user = Utilisateur.query.get(session.get('user_id'))
    erreur = None
    succes = None
    
    if request.method == 'POST':
        user.username = request.form.get('username')
        user.nom = request.form.get('nom')
        user.prenom = request.form.get('prenom')
        user.email = request.form.get('email')
        user.telephone = request.form.get('telephone')
        
        ancien_mdp = request.form.get('ancien_mdp')
        nouveau_mdp = request.form.get('nouveau_mdp')
        confirmer_mdp = request.form.get('confirmer_mdp')
        
        if ancien_mdp or nouveau_mdp or confirmer_mdp:
            if user.password != ancien_mdp:
                erreur = "L'ancien mot de passe est incorrect."
            elif nouveau_mdp != confirmer_mdp:
                erreur = "Les deux nouveaux mots de passe ne correspondent pas."
            else:
                user.password = nouveau_mdp
                succes = "Profil et mot de passe mis à jour avec succès !"
        else:
            succes = "Profil mis à jour avec succès !"
            
        if not erreur:
            db.session.commit()
            session['username'] = user.username
            
    return render_template('profil.html', user=user, erreur=erreur, succes=succes)

@app.route('/ajouter_caissier', methods=['POST'])
def ajouter_caissier():
    if session.get('role') != 'admin': return redirect('/')
    username = request.form.get('username')
    password = request.form.get('password')
    
    existant = Utilisateur.query.filter_by(username=username).first()
    if not existant and username and password:
        nouveau_caissier = Utilisateur(username=username, password=password, role='caissier')
        db.session.add(nouveau_caissier)
        db.session.commit()
    return redirect('/parametres')

@app.route('/supprimer_caissier/<int:id_user>')
def supprimer_caissier(id_user):
    if session.get('role') != 'admin': return redirect('/')
    user_a_supprimer = Utilisateur.query.get_or_404(id_user)
    
    if user_a_supprimer.role != 'admin':
        db.session.delete(user_a_supprimer)
        db.session.commit()
    return redirect('/parametres')


# ==========================================
# 🗂️ OUTILS AVANCÉS (EXPORTS & CARTES)
# ==========================================

@app.route('/carte_client/<int:id_client>')
def carte_client(id_client):
    client_actuel = Client.query.get_or_404(id_client)
    return render_template('carte_client.html', client=client_actuel)

@app.route('/exporter_donnees')
def exporter_donnees():
    if session.get('role') != 'admin': return redirect('/')
    
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(['ID Operation', 'Date', 'Nom Client', 'Telephone', 'Montant Avance (DH)', 'Montant Total (DH)', 'Statut', 'Encaissé par'])
    
    operations = Operation.query.all()
    for op in operations:
        date_op = op.date_operation.strftime('%d/%m/%Y %H:%M')
        client_nom = f"{op.client.prenom} {op.client.nom}"
        caissier = op.caissier.username if op.caissier else "Inconnu"
        writer.writerow([op.id, date_op, client_nom, op.client.telephone, op.montant_avance, op.montant_total, op.statut, caissier])
    
    csv_data = output.getvalue().encode('utf-8-sig')
    return Response(csv_data, mimetype="text/csv", headers={"Content-Disposition": "attachment;filename=sauvegarde_kiosque.csv"})

@app.route('/exporter_clients')
def exporter_clients():
    if session.get('role') != 'admin': return redirect('/')
    
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(['ID Client', 'Nom', 'Prénom', 'Téléphone', 'Adresse', 'Notes privées', 'Nombre de contrats'])
    
    tous_les_clients = Client.query.all()
    for c in tous_les_clients:
        nb_contrats = len(c.contrats)
        adresse = c.adresse if c.adresse else ""
        notes = c.notes if c.notes else ""
        writer.writerow([c.id, c.nom, c.prenom, c.telephone, adresse, notes, nb_contrats])
    
    csv_data = output.getvalue().encode('utf-8-sig')
    return Response(csv_data, mimetype="text/csv", headers={"Content-Disposition": "attachment;filename=mes_clients.csv"})

@app.route('/imprimer_toutes_cartes')
def imprimer_toutes_cartes():
    if session.get('role') != 'admin': return redirect('/')
    clients_actifs = Client.query.filter_by(archive=False).all()
    return render_template('toutes_les_cartes.html', clients=clients_actifs)

@app.route('/archiver_inactifs')
def archiver_inactifs():
    if session.get('role') != 'admin': return redirect('/')
    six_mois = datetime.now() - timedelta(days=180)
    tous_les_clients = Client.query.filter_by(archive=False).all()
    
    for c in tous_les_clients:
        derniere_op = Operation.query.filter_by(client_id=c.id).order_by(Operation.date_operation.desc()).first()
        if derniere_op and derniere_op.date_operation < six_mois:
            c.archive = True
            
    db.session.commit()
    return redirect('/parametres')

# ==========================================
# 🚨 GESTION DES ERREURS
# ==========================================
@app.errorhandler(404)
def page_introuvable(e):
    return render_template('404.html'), 404

# ==========================================
# 🔍 API RECHERCHE UNIVERSELLE (COMMAND PALETTE)
# ==========================================
@app.route('/api/recherche')
def api_recherche():
    if not session.get('connecte'):
        return jsonify([])
        
    q = request.args.get('q', '').lower()
    if not q or len(q) < 2:
        return jsonify([])
        
    # On fouille la base de données en direct (Max 8 résultats pour que ce soit ultra rapide)
    clients = Client.query.filter(
        Client.archive == False,
        ((Client.nom.contains(q)) | (Client.prenom.contains(q)) | (Client.telephone.contains(q)))
    ).limit(8).all()
    
    resultats = []
    for c in clients:
        resultats.append({
            'id': c.id,
            'titre': f"{c.prenom.capitalize()} {c.nom.upper()}",
            'sous_titre': c.telephone,
            'url': f"/client/{c.id}",
            'icone': '<path stroke-linecap="round" stroke-linejoin="round" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z" />'
        })
        
    return jsonify(resultats)


# ==========================================
# 🚀 MOTEUR DE DÉMARRAGE
# ==========================================

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        
        if Service.query.count() == 0:
            db.session.add_all([
                Service(nom_service='Eau'), 
                Service(nom_service='Électricité'), 
                Service(nom_service='Internet / Mobile'), 
                Service(nom_service='Impôts & Taxes')
            ])
            db.session.commit()
            
        if Utilisateur.query.count() == 0:
            db.session.add(Utilisateur(username='admin', password='admin123', role='admin'))
            db.session.commit()
            
    app.run(host='0.0.0.0', port=5000, debug=True)