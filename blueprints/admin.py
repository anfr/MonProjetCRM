from flask import Blueprint, render_template, session, redirect, url_for, request, jsonify
from werkzeug.security import generate_password_hash
from extensions import db
from models import Utilisateur, Service, ConfigSysteme

# Création du Blueprint 'admin'
admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/parametres', methods=['GET'])
def parametres():
    if session.get('role') != 'admin': 
        return redirect(url_for('dashboard.accueil'))
    
    config = ConfigSysteme.query.first()
    if not config:
        config = ConfigSysteme()
        db.session.add(config)
        db.session.commit()
        
    return render_template('pages/parametres/parametres.html', 
                           services=Service.query.all(), 
                           utilisateurs=Utilisateur.query.all(), 
                           config=config)

# --- SAUVEGARDES AJAX ---

@admin_bp.route('/api/parametres/identite', methods=['POST'])
def save_identite():
    if not session.get('connecte') or session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Accès non autorisé'}), 403

    config = ConfigSysteme.query.first() or ConfigSysteme()
    if not config.id: db.session.add(config)

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
        return jsonify({'success': False, 'message': 'Erreur serveur.'}), 500

@admin_bp.route('/api/parametres/tv', methods=['POST'])
def save_tv():
    if not session.get('connecte') or session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Accès non autorisé'}), 403

    config = ConfigSysteme.query.first() or ConfigSysteme()
    if not config.id: db.session.add(config)

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
        return jsonify({'success': False, 'message': 'Erreur serveur.'}), 500

@admin_bp.route('/api/parametres/borne', methods=['POST'])
def save_borne():
    if not session.get('connecte') or session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Accès non autorisé'}), 403

    config = ConfigSysteme.query.first() or ConfigSysteme()
    if not config.id: db.session.add(config)

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
        return jsonify({'success': False, 'message': 'Erreur serveur.'}), 500

@admin_bp.route('/api/parametres/whatsapp', methods=['POST'])
def save_whatsapp():
    if not session.get('connecte') or session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Accès non autorisé'}), 403

    config = ConfigSysteme.query.first() or ConfigSysteme()
    if not config.id: db.session.add(config)

    try:
        config.msg_whatsapp_dette = request.form.get('msg_whatsapp_dette')
        config.msg_whatsapp_monnaie = request.form.get('msg_whatsapp_monnaie')
        config.msg_whatsapp_recu = request.form.get('msg_whatsapp_recu')

        db.session.commit()
        return jsonify({'success': True, 'message': 'Modèles WhatsApp mis à jour !'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Erreur serveur.'}), 500

# --- GESTION DES CAISSIERS ---

@admin_bp.route('/ajouter_caissier', methods=['POST'])
def ajouter_caissier():
    if not session.get('connecte') or session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Accès non autorisé'}), 403

    username = request.form.get('username')
    password = request.form.get('password')
    guichet = request.form.get('guichet')

    if not username or not password:
        return jsonify({'success': False, 'message': 'Veuillez remplir tous les champs.'}), 400

    if Utilisateur.query.filter_by(username=username).first():
        return jsonify({'success': False, 'message': 'Ce nom d\'utilisateur existe déjà.'}), 400

    try:
        nouvel_utilisateur = Utilisateur(
            username=username.strip(),
            password=generate_password_hash(password),
            role='caissier',
            guichet=guichet
        )
        db.session.add(nouvel_utilisateur)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Caissier ajouté avec succès !'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Erreur serveur.'}), 500

@admin_bp.route('/supprimer_caissier/<int:id>', methods=['POST'])
def supprimer_caissier(id):
    if session.get('role') == 'admin':
        utilisateur = Utilisateur.query.get_or_404(id)
        if utilisateur.role != 'admin':
            db.session.delete(utilisateur)
            db.session.commit()
    return redirect(url_for('admin.parametres'))

# --- GESTION DES SERVICES ---

@admin_bp.route('/ajouter_service', methods=['POST'])
def ajouter_service():
    if not session.get('connecte'):
        return jsonify({'success': False, 'message': 'Session expirée'}), 403

    lettre = request.form.get('lettre')
    nom_service = request.form.get('nom_service')

    if not lettre or not nom_service:
        return jsonify({'success': False, 'message': 'Veuillez remplir tous les champs.'}), 400

    try:
        nouveau_service = Service(lettre=lettre.upper()[:1], nom_service=nom_service.strip())
        db.session.add(nouveau_service)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Service ajouté avec succès !'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Erreur serveur.'}), 500

@admin_bp.route('/supprimer_service/<int:id_service>', methods=['POST'])
def supprimer_service(id_service):
    if session.get('role') == 'admin':
        db.session.delete(Service.query.get_or_404(id_service))
        db.session.commit()
    return redirect(url_for('admin.parametres'))