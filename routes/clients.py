import os
from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify, flash
from sqlalchemy.orm import joinedload
from sqlalchemy import func, or_, and_
from PIL import Image
from flask import current_app
from models import db, Client, Operation, Service, Contrat, PhotoRecu
from datetime import datetime

clients_bp = Blueprint('clients', __name__)

@clients_bp.route('/clients')
def liste_clients():
    if not session.get('connecte'): 
        return redirect(url_for('login'))

    # 1. On récupère la page, la recherche ET le nouveau paramètre de tri
    page = request.args.get('page', 1, type=int)
    q = request.args.get('q', '').strip()
    tri = request.args.get('tri', 'asc') # 'asc' par défaut (A-Z)

    # 2. Requête optimisée (Anti N+1)
    query = Client.query.options(
        joinedload(Client.contrats).joinedload(Contrat.service)
    ).filter(Client.archive == False)

    # 3. La recherche Tolérante
    if q:
        search = f"%{q}%"
        query = query.filter(or_(
            Client.nom.ilike(search),
            Client.prenom.ilike(search),
            Client.telephone.ilike(search)
        ))

    # 4. Le système de Tri
    if tri == 'desc':
        query = query.order_by(Client.nom.desc())
    elif tri == 'recent':
        query = query.order_by(Client.id.desc()) # Les derniers ajoutés en premier
    else:
        query = query.order_by(Client.nom.asc())

    # 5. On passe à 12 ou 16 par page pour que la grille soit bien symétrique
    clients_pagines = query.paginate(page=page, per_page=12, error_out=False)

    return render_template('clients.html', clients=clients_pagines)

# ==========================================
# HISTORIQUE & DETTES (OPTIMISÉS)
# ==========================================

@clients_bp.route('/historique')
def historique():
    if not session.get('connecte'): 
        return redirect(url_for('login'))

    # 1. Récupération des paramètres de l'URL (GET)
    page = request.args.get('page', 1, type=int)
    q_recherche = request.args.get('q', '').strip()
    date_debut = request.args.get('date_debut', '')
    date_fin = request.args.get('date_fin', '')
    statut_filtre = request.args.get('statut', '')

    # 2. Requête de base (Toutes les opérations non archivées)
    query = Operation.query.join(Client).filter(Operation.archive == False)

    # 3. Application des filtres dynamiques
    # -- A. Filtre par texte (Nom, Prénom, Téléphone du client)
    if q_recherche:
        search = f"%{q_recherche}%"
        query = query.filter(or_(
            Client.nom.ilike(search),
            Client.prenom.ilike(search),
            Client.telephone.ilike(search),
            Operation.motif.ilike(search)
        ))

    # -- B. Filtre par Dates
    if date_debut:
        try:
            d_debut = datetime.strptime(date_debut, '%Y-%m-%d').date()
            query = query.filter(func.date(Operation.date_operation) >= d_debut)
        except ValueError: pass

    if date_fin:
        try:
            d_fin = datetime.strptime(date_fin, '%Y-%m-%d').date()
            query = query.filter(func.date(Operation.date_operation) <= d_fin)
        except ValueError: pass

    # -- C. Filtre par Statut (Finances)
    if statut_filtre:
        if statut_filtre == 'en_attente':
            query = query.filter(Operation.statut == 'En attente')
        elif statut_filtre == 'termine':
            query = query.filter(Operation.statut == 'Terminé')
        elif statut_filtre == 'dette':
            query = query.filter(and_(Operation.statut == 'Terminé', Operation.montant_total != None, Operation.montant_total > Operation.montant_avance))
        elif statut_filtre == 'monnaie':
            query = query.filter(and_(Operation.statut == 'Terminé', Operation.montant_total != None, Operation.montant_total < Operation.montant_avance))
        elif statut_filtre == 'solde':
            query = query.filter(and_(Operation.statut == 'Terminé', Operation.montant_total != None, Operation.montant_total == Operation.montant_avance))

    # 4. Tri et Pagination
    operations = query.order_by(Operation.date_operation.desc()).paginate(page=page, per_page=15, error_out=False)

    return render_template('historique.html', operations=operations)

@clients_bp.route('/dettes')
def liste_dettes():
    # 1. L'OPTIMISATION SQL : Le calcul ultra-rapide du total par la base de données
    total_dettes = db.session.query(
        func.sum(Operation.montant_total - Operation.montant_avance)
    ).filter(
        Operation.montant_total > Operation.montant_avance
    ).scalar() or 0

    # 2. On récupère la liste des opérations impayées
    operations_dettes = Operation.query.filter(
        Operation.montant_total > Operation.montant_avance
    ).order_by(Operation.date_operation.desc()).all()
    
    return render_template('dettes.html', operations=operations_dettes, total_dettes=total_dettes)


# ==========================================
# GESTION DES CLIENTS & OPÉRATIONS
# ==========================================

@clients_bp.route('/client/<int:id_client>')
def fiche_client(id_client):
    c = Client.query.get_or_404(id_client)
    servs = Service.query.all()
    hist = Operation.query.filter_by(client_id=id_client).order_by(Operation.date_operation.desc()).all()
    return render_template('fiche_client.html', client=c, services=servs, historique=hist)

@clients_bp.route('/ajouter_client', methods=['GET', 'POST'])
def ajouter_client():
    if not session.get('connecte'): 
        return redirect(url_for('login'))

    if request.method == 'POST':
        new = Client(
            nom=request.form.get('nom'), 
            prenom=request.form.get('prenom'), 
            telephone=request.form.get('telephone'), 
            adresse=request.form.get('adresse')
        )
        db.session.add(new)
        db.session.commit()
        return redirect(url_for('clients.liste_clients'))
    return render_template('ajouter_client.html')

@clients_bp.route('/supprimer_client/<int:id_client>', methods=['POST'])
def supprimer_client(id_client):
    if session.get('role') != 'admin': return redirect(url_for('accueil'))
    
    client = Client.query.get_or_404(id_client)
    
    # Nettoyage de TOUTES les photos associées à ce client sur le disque
    for op in client.operations:
        for photo in op.photos:
            chemin = os.path.join(current_app.config['UPLOAD_FOLDER'], photo.nom_fichier)
            if os.path.exists(chemin):
                os.remove(chemin)
        if op.photo_recu:
            chemin = os.path.join(current_app.config['UPLOAD_FOLDER'], op.photo_recu)
            if os.path.exists(chemin):
                os.remove(chemin)

    db.session.delete(client)
    db.session.commit()
    return redirect(url_for('clients.liste_clients'))

@clients_bp.route('/ajouter_contrat/<int:id_client>', methods=['POST'])
def ajouter_contrat(id_client):
    # On récupère les données du formulaire
    num_contrat = request.form.get('numero_contrat')
    nom_proprio = request.form.get('nom_proprietaire')
    id_service = request.form.get('service_id')
    notes = request.form.get('notes')

    if num_contrat and id_service:
        nouveau_contrat = Contrat(
            numero_contrat=num_contrat,
            nom_proprietaire=nom_proprio,
            service_id=id_service,
            client_id=id_client,
            notes=notes
        )
        db.session.add(nouveau_contrat)
        db.session.commit()
    
    # On redirige vers la fiche du client pour voir le nouveau contrat
    return redirect(url_for('clients.fiche_client', id_client=id_client))

@clients_bp.route('/supprimer_contrat/<int:id_contrat>')
def supprimer_contrat(id_contrat):
    # Sécurité : Seul l'admin peut supprimer un contrat
    if session.get('role') != 'admin':
        return redirect(url_for('accueil'))
    
    contrat = Contrat.query.get_or_404(id_contrat)
    id_client = contrat.client_id # On garde l'ID pour la redirection
    
    try:
        # ✅ LA CORRECTION EST ICI : On archive au lieu de supprimer
        contrat.archive = True
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Erreur lors de la mise en corbeille du contrat : {e}")
        
    return redirect(url_for('clients.fiche_client', id_client=id_client))


@clients_bp.route('/nouvelle_operation/<int:id_client>', methods=['POST'])
def nouvelle_operation(id_client):
    montant_t = float(request.form.get('montant_total') or 0)
    montant_a = float(request.form.get('montant_avance') or 0)
    user_id = session.get('user_id') or 1 

    # --- NOUVEAU : Récupération et fusion des motifs ---
    motifs_coches = request.form.getlist('motifs') # Récupère toutes les cases cochées
    autre_motif = request.form.get('autre_motif', '').strip()
    
    tous_les_motifs = motifs_coches.copy()
    if autre_motif:
        tous_les_motifs.append(autre_motif)
        
    # On crée une belle phrase, ex: "Eau (12345) + Internet (6789) + Photocopie"
    motif_final = " + ".join(tous_les_motifs) if tous_les_motifs else "Non spécifié"

    # 1. Création de l'opération
    nouvelle_op = Operation(
        montant_total=montant_t,
        montant_avance=montant_a,
        date_operation=datetime.now(),
        statut='En attente',
        client_id=id_client,
        utilisateur_id=user_id,
        motif=motif_final   # 👈 AJOUT ICI
    )
    
    try:
        # On sauvegarde d'abord l'opération pour que la base de données lui donne un ID (nouvelle_op.id)
        db.session.add(nouvelle_op)
        db.session.commit()

        # ==========================================
        # 2. MOTEUR MULTI-UPLOAD & OPTIMISATION PILLOW
        # ==========================================
        photos = request.files.getlist('photos')
        
        # S'il y a des photos envoyées dans le formulaire
        if photos and photos[0].filename != '':
            date_str = datetime.now().strftime('%Y%m%d')
            
            for index, photo in enumerate(photos):
                if photo and photo.filename:
                    # A. Nommage propre : FA_YYYYMMDD_Client_Op_Index.jpg
                    nom_fichier = f"FA_{date_str}_{id_client}_{nouvelle_op.id}_{index}.jpg"
                    chemin_complet = os.path.join(current_app.config['UPLOAD_FOLDER'], nom_fichier)

                    # B. Traitement et Compression avec Pillow
                    img = Image.open(photo)
                    if img.mode != 'RGB':
                        img = img.convert('RGB') # Sécurité pour convertir les PNG transparents
                    
                    img.thumbnail((1200, 1200)) # Redimensionnement max 1200px
                    img.save(chemin_complet, "JPEG", optimize=True, quality=80) # Compression à 80%

                    # C. Ajout dans la table PhotoRecu
                    nouvelle_photo = PhotoRecu(nom_fichier=nom_fichier, operation_id=nouvelle_op.id)
                    db.session.add(nouvelle_photo)
            
            # On valide l'ajout des photos dans la base de données
            db.session.commit()

    except Exception as e:
        db.session.rollback()
        print(f"Erreur d'insertion ou d'upload : {e}")

    return redirect(url_for('clients.fiche_client', id_client=id_client))

@clients_bp.route('/cloturer_operation/<int:id>', methods=['POST'])
def cloturer_operation(id):
    # (Si tu es dans app.py, utilise @app.route au lieu de @clients_bp.route)
    
    # 1. Récupération de l'opération
    op = Operation.query.get_or_404(id)
    
    try:
        # 2. Mise à jour des informations financières
        op.montant_total = float(request.form.get('montant_total') or 0)
        op.statut = 'Terminé'
        op.statut_dossier = 'Dossier Validé'
        
        # ==========================================
        # 3. MOTEUR MULTI-UPLOAD & OPTIMISATION PILLOW
        # ==========================================
        photos = request.files.getlist('photos')
        
        # S'il y a des photos sélectionnées
        if photos and photos[0].filename != '':
            date_str = datetime.now().strftime('%Y%m%d')
            index_depart = len(op.photos) # Au cas où il y en a déjà
            
            for index, photo in enumerate(photos):
                if photo and photo.filename:
                    # A. Nommage propre : FA_YYYYMMDD_Client_Op_Index.jpg
                    index_actuel = index_depart + index
                    nom_fichier = f"FA_{date_str}_{op.client_id}_{op.id}_{index_actuel}.jpg"
                    chemin_complet = os.path.join(current_app.config['UPLOAD_FOLDER'], nom_fichier)

                    # B. Traitement et Compression avec Pillow
                    img = Image.open(photo)
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    
                    img.thumbnail((1200, 1200)) # Réduit les photos 4K des téléphones
                    img.save(chemin_complet, "JPEG", optimize=True, quality=80)

                    # C. Sauvegarde en Base de données
                    nouvelle_photo = PhotoRecu(nom_fichier=nom_fichier, operation_id=op.id)
                    db.session.add(nouvelle_photo)

        # On valide le tout (finances + images) en une seule transaction
        db.session.commit()
        
    except Exception as e:
        db.session.rollback()
        print(f"Erreur lors de la clôture ou de l'upload : {e}")

    # Retour au tableau de bord
    return redirect(request.referrer or url_for('accueil'))

@clients_bp.route('/ajouter_recu/<int:id_op>', methods=['POST'])
def ajouter_recu_existant(id_op):
    # On récupère l'opération existante
    op = Operation.query.get_or_404(id_op)
    
    try:
        # ==========================================
        # MOTEUR MULTI-UPLOAD & OPTIMISATION PILLOW
        # ==========================================
        photos = request.files.getlist('photos')
        
        if photos and photos[0].filename != '':
            date_str = datetime.now().strftime('%Y%m%d')
            
            # Compter combien de photos existent déjà pour cette opération pour l'index
            index_depart = len(op.photos)
            
            for index, photo in enumerate(photos):
                if photo and photo.filename:
                    # A. Nommage propre : FA_YYYYMMDD_Client_Op_Index.jpg
                    index_actuel = index_depart + index
                    nom_fichier = f"FA_{date_str}_{op.client_id}_{op.id}_{index_actuel}.jpg"
                    chemin_complet = os.path.join(current_app.config['UPLOAD_FOLDER'], nom_fichier)

                    # B. Traitement et Compression avec Pillow
                    img = Image.open(photo)
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    
                    img.thumbnail((1200, 1200))
                    img.save(chemin_complet, "JPEG", optimize=True, quality=80)

                    # C. Ajout dans la table PhotoRecu
                    nouvelle_photo = PhotoRecu(nom_fichier=nom_fichier, operation_id=op.id)
                    db.session.add(nouvelle_photo)
            
            db.session.commit()
            
    except Exception as e:
        db.session.rollback()
        print(f"Erreur d'upload de reçu : {e}")

    # Retourne sur la page où l'utilisateur se trouvait (Historique, Fiche client, etc.)
    return redirect(request.referrer)

@clients_bp.route('/regler_reste/<int:id_operation>', methods=['POST'])
def regler_reste(id_operation):
    # On récupère l'opération concernée
    op = Operation.query.get_or_404(id_operation)
    
    # On solde le montant : l'avance devient égale au total
    op.montant_avance = op.montant_total
    op.statut = 'Terminé' 
    
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Erreur lors du règlement : {e}")
        
    # On redirige vers la fiche du client
    return redirect(url_for('clients.fiche_client', id_client=op.client_id))



@clients_bp.route('/supprimer_operation/<int:id_operation>', methods=['POST'])
def supprimer_operation(id_operation):
    if session.get('role') != 'admin': 
        return redirect(url_for('accueil'))
    
    op = Operation.query.get_or_404(id_operation)
    
    try:
        # ✅ ÉTAPE 1 : On ne supprime SURTOUT PAS les fichiers physiques ici !
        # On se contente de cacher l'opération dans la corbeille.
        op.archive = True
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Erreur lors de la mise en corbeille : {e}")

    # Retour intelligent (revient sur le Dashboard ou la fiche client selon l'endroit d'où on clique)
    return redirect(request.referrer or url_for('accueil'))

@clients_bp.route('/toutes_les_cartes')
def toutes_les_cartes():
    tous_les_clients = Client.query.filter_by(archive=False).all()
    return render_template('toutes_les_cartes.html', clients=tous_les_clients)

@clients_bp.route('/carte_client/<int:id_client>')
def carte_client(id_client):
    c = Client.query.get_or_404(id_client)
    return render_template('carte_client.html', client=c)

@clients_bp.route('/modifier_client/<int:id_client>', methods=['GET', 'POST'])
def modifier_client(id_client):
    client = Client.query.get_or_404(id_client)
    
    if request.method == 'POST':
        client.nom = request.form.get('nom').upper()
        client.prenom = request.form.get('prenom').capitalize()
        client.telephone = request.form.get('telephone')
        client.adresse = request.form.get('adresse')
        
        try:
            db.session.commit()
            return redirect(url_for('clients.fiche_client', id_client=client.id))
        except Exception as e:
            db.session.rollback()
            print(f"Erreur lors de la modification : {e}")
            
    return render_template('modifier_client.html', client=client)

@clients_bp.route('/imprimer_toutes_cartes')
def imprimer_toutes_cartes():
    clients = Client.query.filter_by(archive=False).all()
    clients_tries = sorted(clients, key=lambda c: len(c.contrats))
    return render_template('toutes_les_cartes.html', clients=clients_tries)

@clients_bp.route('/maj_notes/<int:id_client>', methods=['POST'])
def maj_notes(id_client):
    client = Client.query.get_or_404(id_client)
    client.notes = request.form.get('notes')
    db.session.commit()
    flash("Les notes ont été enregistrées avec succès.", "success")
    return redirect(request.referrer)

from flask import jsonify

# --- Basculer le statut Actif/Inactif d'un contrat (AJAX) ---
@clients_bp.route('/api/contrat/<int:id>/toggle_statut', methods=['POST'])
def toggle_statut_contrat(id):
    # Si le routeur s'appelle app au lieu de clients_bp, modifie le @ 
    contrat = Contrat.query.get_or_404(id)
    contrat.est_actif = not contrat.est_actif
    db.session.commit()
    return jsonify({'success': True, 'est_actif': contrat.est_actif})

# --- Modifier un contrat existant ---
@clients_bp.route('/modifier_contrat/<int:id>', methods=['POST'])
def modifier_contrat(id):
    contrat = Contrat.query.get_or_404(id)
    contrat.service_id = request.form.get('service_id')
    contrat.numero_contrat = request.form.get('numero_contrat')
    contrat.nom_proprietaire = request.form.get('nom_proprietaire')
    contrat.notes = request.form.get('notes')
    db.session.commit()
    return redirect(url_for('clients.fiche_client', id_client=contrat.client_id))


@clients_bp.route('/regler_toutes_dettes/<int:client_id>', methods=['POST']) # Adapte le décorateur si c'est @app.route
def regler_toutes_dettes(client_id):
    if not session.get('connecte'): 
        return redirect(url_for('login'))

    client = Client.query.get_or_404(client_id)
    
    # On cherche toutes les opérations du client qui ont une dette (montant_total > montant_avance)
    operations_endettees = Operation.query.filter(
        Operation.client_id == client_id,
        Operation.statut == 'Terminé',
        Operation.archive == False,
        Operation.montant_total != None,
        Operation.montant_total > Operation.montant_avance
    ).all()
    
    try:
        # On solde chaque opération
        for op in operations_endettees:
            op.montant_avance = op.montant_total
            
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Erreur lors de l'encaissement global : {e}")

    # On redirige vers la page des dettes (ou le profil client)
    return redirect(request.referrer or url_for('clients.liste_dettes'))