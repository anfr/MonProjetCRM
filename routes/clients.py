import os
from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify, flash
from sqlalchemy import func
from flask import current_app
from models import db, Client, Operation, Service, Contrat, PhotoRecu
from datetime import datetime

clients_bp = Blueprint('clients', __name__)

@clients_bp.route('/clients')
def liste_clients():
    q = request.args.get('q')
    query = Client.query.filter_by(archive=False)
    if q:
        query = query.filter((Client.nom.contains(q)) | (Client.telephone.contains(q)))
    return render_template('clients.html', clients=query.all())

# ==========================================
# HISTORIQUE & DETTES (OPTIMISÉS)
# ==========================================

@clients_bp.route('/historique')
def historique():
    # 1. On récupère le numéro de la page demandé dans l'URL (1 par défaut)
    page = request.args.get('page', 1, type=int)
    
    # 2. Pagination : On charge 20 opérations à la fois au lieu de TOUT charger
    operations_paginees = Operation.query.filter_by(
        statut='Terminé'
    ).order_by(
        Operation.date_operation.desc()
    ).paginate(page=page, per_page=20, error_out=False)
    
    return render_template('historique.html', operations=operations_paginees)

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

@clients_bp.route('/supprimer_client/<int:id_client>')
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
        db.session.delete(contrat)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Erreur lors de la suppression du contrat : {e}")
        
    return redirect(url_for('clients.fiche_client', id_client=id_client))

@clients_bp.route('/nouvelle_operation/<int:id_client>', methods=['POST'])
def nouvelle_operation(id_client):
    montant_t = float(request.form.get('montant_total') or 0)
    montant_a = float(request.form.get('montant_avance') or 0)
    user_id = session.get('user_id') or 1 

    nouvelle_op = Operation(
        montant_total=montant_t,
        montant_avance=montant_a,
        date_operation=datetime.now(),
        statut='En attente',
        client_id=id_client,
        utilisateur_id=user_id       
    )
    
    try:
        db.session.add(nouvelle_op)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Erreur d'insertion : {e}")

    return redirect(url_for('clients.fiche_client', id_client=id_client))

@clients_bp.route('/regler_reste/<int:id_operation>')
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

@clients_bp.route('/supprimer_operation/<int:id_operation>')
def supprimer_operation(id_operation):
    if session.get('role') != 'admin': return redirect(url_for('accueil'))
    
    op = Operation.query.get_or_404(id_operation)
    id_client = op.client_id
    
    # 1. Suppression physique des nouveaux reçus (Multiples)
    for photo in op.photos:
        chemin = os.path.join(current_app.config['UPLOAD_FOLDER'], photo.nom_fichier)
        if os.path.exists(chemin):
            os.remove(chemin)
            
    # 2. Suppression de l'ancien reçu (Si existant dans op.photo_recu)
    if op.photo_recu:
        ancien_chemin = os.path.join(current_app.config['UPLOAD_FOLDER'], op.photo_recu)
        if os.path.exists(ancien_chemin):
            os.remove(ancien_chemin)

    # 3. Suppression dans la base de données
    db.session.delete(op)
    db.session.commit()
    return redirect(url_for('clients.fiche_client', id_client=id_client))

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