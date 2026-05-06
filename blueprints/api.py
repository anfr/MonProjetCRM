from flask import Blueprint, request, jsonify, session, redirect, url_for
from sqlalchemy import or_
from extensions import db
from models import BoutonRapide, Client, Contrat

# Création du Blueprint 'api'
api_bp = Blueprint('api', __name__)

@api_bp.route('/ajouter_bouton_rapide', methods=['POST'])
def ajouter_bouton_rapide():
    if not session.get('connecte'): return jsonify({'success': False, 'message': 'Session expirée'}), 403
    lettre = request.form.get('lettre')
    nom_bouton = request.form.get('nom_bouton')
    if not lettre or not nom_bouton: return jsonify({'success': False, 'message': 'Veuillez remplir tous les champs.'}), 400

    try:
        nouveau_raccourci = BoutonRapide(lettre=lettre.upper()[:1], nom_service=nom_bouton.strip())
        db.session.add(nouveau_raccourci)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Raccourci ajouté avec succès !'})
    except Exception:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Erreur serveur.'}), 500

@api_bp.route('/supprimer_bouton_rapide/<int:id_bouton>', methods=['POST'])
def supprimer_bouton_rapide(id_bouton):
    if session.get('role') == 'admin':
        bouton = BoutonRapide.query.get_or_404(id_bouton)
        db.session.delete(bouton)
        db.session.commit()
    return redirect(url_for('admin.parametres'))

@api_bp.route('/api/recherche')
def api_recherche():
    if not session.get('connecte'): return jsonify([])
    q = request.args.get('q', '').strip()
    if len(q) < 2: return jsonify([])
    
    search = f"%{q}%"
    results = []
    
    clients = Client.query.filter(or_(Client.nom.ilike(search), Client.prenom.ilike(search), Client.telephone.ilike(search)), Client.archive == False).limit(6).all()
    for c in clients:
        results.append({'titre': f"{c.nom.upper()} {c.prenom.capitalize()}", 'sous_titre': f"Client • {c.telephone or 'Sans numéro'}", 'url': url_for('clients.fiche_client', id_client=c.id), 'icone': 'ph-user'})
        
    contrats = Contrat.query.filter(Contrat.numero_contrat.ilike(search), Contrat.archive == False).limit(4).all()
    client_ids_trouves = [c.id for c in clients]
    for ct in contrats:
        if ct.client_id not in client_ids_trouves:
            results.append({'titre': f"Contrat : {ct.numero_contrat}", 'sous_titre': f"Titulaire : {ct.nom_proprietaire} ({ct.service.nom_service})", 'url': url_for('clients.fiche_client', id_client=ct.client_id), 'icone': 'ph-file-text'})
            client_ids_trouves.append(ct.client_id)
            
    return jsonify(results)