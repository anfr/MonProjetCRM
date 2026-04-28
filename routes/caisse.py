from flask import jsonify
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from models import db, SessionCaisse, MouvementCaisse, CategorieMouvement
from datetime import datetime

caisse_bp = Blueprint('caisse', __name__)

@caisse_bp.route('/caisse')
def tableau_caisse():
    # On cherche s'il y a une caisse actuellement ouverte
    session_ouverte = SessionCaisse.query.filter_by(statut='Ouverte').first()
    
    # On calcule l'argent théorique du tiroir
    theorique = 0
    mouvements = [] # On prépare la liste des mouvements

    # NOUVEAU : On récupère toutes les catégories
    categories = CategorieMouvement.query.all()

    if session_ouverte:
        theorique = session_ouverte.fond_initial + session_ouverte.total_entrees - session_ouverte.total_sorties
        # On récupère tous les mouvements de cette session (du plus récent au plus ancien)
        mouvements = MouvementCaisse.query.filter_by(session_id=session_ouverte.id).order_by(MouvementCaisse.id.desc()).all()
        
    return render_template('caisse.html', session_ouverte=session_ouverte, theorique=theorique, mouvements=mouvements, categories=categories)

@caisse_bp.route('/caisse/ouvrir', methods=['POST'])
def ouvrir_caisse():
    # Correction du crash : "or 0" garantit qu'on ne convertit jamais un texte vide
    fond = float(request.form.get('fond_initial') or 0)
    tassh_init = float(request.form.get('tasshilat_initial') or 0) 
    
    nouvelle_session = SessionCaisse(
        fond_initial=fond, 
        tasshilat_initial=tassh_init 
    )
    db.session.add(nouvelle_session)
    db.session.commit()
    flash(f"Caisse ouverte : {fond} DH (Tiroir) et {tassh_init} DH (Tasshilat).", "success")
    return redirect(url_for('caisse.tableau_caisse'))

@caisse_bp.route('/caisse/mouvement', methods=['POST'])
def ajouter_mouvement():
    session_ouverte = SessionCaisse.query.filter_by(statut='Ouverte').first()
    if not session_ouverte: return redirect(url_for('caisse.tableau_caisse'))

    type_mvt = request.form.get('type_mouvement')
    categorie = request.form.get('categorie')
    montant = float(request.form.get('montant') or 0) # Correction du crash
    description = request.form.get('description', '')
    impact_tasshilat = 'impact_tasshilat' in request.form 

    if montant > 0:
        mvt = MouvementCaisse(
            session_id=session_ouverte.id, type_mouvement=type_mvt,
            categorie=categorie, montant=montant, description=description,
            impact_tasshilat=impact_tasshilat 
        )
        db.session.add(mvt)

        # Calcul Tiroir
        if type_mvt == 'Entrée': session_ouverte.total_entrees += montant
        else: session_ouverte.total_sorties += montant

        # Calcul Machine Tasshilat
        if impact_tasshilat:
            if type_mvt == 'Entrée':
                session_ouverte.total_tasshilat_consomme += montant
            else:
                session_ouverte.total_tasshilat_recharge += montant

        db.session.commit()
    return redirect(url_for('caisse.tableau_caisse'))

@caisse_bp.route('/caisse/mouvement/<int:mvt_id>/annuler', methods=['POST'])
def annuler_mouvement(mvt_id):
    mvt = MouvementCaisse.query.get_or_404(mvt_id)
    
    # Si c'est déjà annulé, on ne fait rien
    if mvt.est_annule:
        return redirect(url_for('caisse.tableau_caisse'))

    motif = request.form.get('motif_annulation', 'Erreur de saisie')
    mvt.est_annule = True
    mvt.motif_annulation = motif

    # On met à jour les totaux de la session ouverte
    session_ouverte = SessionCaisse.query.get(mvt.session_id)
    if session_ouverte and session_ouverte.statut == 'Ouverte':
        
        # 1. On annule l'impact sur le Tiroir Physique
        if mvt.type_mouvement == 'Entrée':
            session_ouverte.total_entrees -= mvt.montant
        else:
            session_ouverte.total_sorties -= mvt.montant
            
        # 2. 🪲 CORRECTION DU BUG : On annule l'impact sur la Machine Virtuelle !
        if mvt.impact_tasshilat:
            if mvt.type_mouvement == 'Entrée':
                session_ouverte.total_tasshilat_consomme -= mvt.montant
            else:
                session_ouverte.total_tasshilat_recharge -= mvt.montant

        # On recalcule le montant théorique
        session_ouverte.montant_theorique = session_ouverte.fond_initial + session_ouverte.total_entrees - session_ouverte.total_sorties

    db.session.commit()
    flash(f"Mouvement de {mvt.montant} DH annulé avec succès.", "success")
    return redirect(url_for('caisse.tableau_caisse'))

@caisse_bp.route('/caisse/cloturer', methods=['POST'])
def cloturer_caisse():
    session_ouverte = SessionCaisse.query.filter_by(statut='Ouverte').first()
    if not session_ouverte: return redirect(url_for('caisse.tableau_caisse'))

    # Correction du crash : Protection contre les champs vides
    montant_reel = float(request.form.get('montant_reel') or 0)
    tasshilat_reel = float(request.form.get('tasshilat_reel') or 0)

    # 1. Bilan Physique (Tiroir)
    theorique_especes = session_ouverte.fond_initial + session_ouverte.total_entrees - session_ouverte.total_sorties
    session_ouverte.montant_theorique = theorique_especes
    session_ouverte.montant_reel = montant_reel
    session_ouverte.ecart = montant_reel - theorique_especes

    # 2. Bilan Virtuel (Machine)
    theorique_tasshilat = session_ouverte.tasshilat_initial - session_ouverte.total_tasshilat_consomme + session_ouverte.total_tasshilat_recharge
    session_ouverte.tasshilat_theorique = theorique_tasshilat
    session_ouverte.tasshilat_reel = tasshilat_reel
    session_ouverte.ecart_tasshilat = tasshilat_reel - theorique_tasshilat

    # Clôture
    session_ouverte.date_cloture = datetime.now()
    session_ouverte.statut = 'Clôturée'
    db.session.commit()
    
    return redirect(url_for('caisse.tableau_caisse'))

# historique des sessions de caisse clôturées, avec possibilité d'imprimer le rapport Z de chaque session (liste des mouvements détaillés) et d'avoir une vision claire de l'évolution du fond de caisse et du solde machine au fil du temps. Accessible uniquement par l'admin pour éviter les confusions chez les caissiers.
@caisse_bp.route('/caisse/historique')
def historique_caisse():
    # Vérification de sécurité : Seul l'admin y a accès
    if session.get('role') != 'admin':
        flash("Accès refusé. Cette page est réservée aux administrateurs.", "error")
        return redirect(url_for('caisse.tableau_caisse'))

    # On récupère toutes les sessions clôturées, de la plus récente à la plus ancienne
    archives = SessionCaisse.query.filter_by(statut='Clôturée').order_by(SessionCaisse.id.desc()).all()
    
    return render_template('historique_caisse.html', archives=archives)

@caisse_bp.route('/caisse/categorie/ajouter_ajax', methods=['POST'])
def ajouter_categorie_ajax():
    nom = request.form.get('nom')
    type_mvt = request.form.get('type_mouvement')
    icone = request.form.get('icone', 'ph-star')
    
    if nom and type_mvt:
        nouvelle_cat = CategorieMouvement(nom=nom, type_mouvement=type_mvt, couleur="indigo", icone=icone)
        db.session.add(nouvelle_cat)
        db.session.commit()
        # On renvoie les infos au navigateur pour qu'il dessine le bouton instantanément
        return jsonify({'success': True, 'id': nouvelle_cat.id, 'nom': nouvelle_cat.nom, 'type_mouvement': nouvelle_cat.type_mouvement, 'icone': nouvelle_cat.icone})
    
    return jsonify({'success': False})


@caisse_bp.route('/caisse/categorie/supprimer_ajax/<int:id_cat>', methods=['POST'])
def supprimer_categorie_ajax(id_cat):
    cat = CategorieMouvement.query.get_or_404(id_cat)
    db.session.delete(cat)
    db.session.commit()
    return jsonify({'success': True})

#action de nettoyage total de la caisse (mode test) - à utiliser avec précaution, supprime TOUT l'historique et les sessions

@caisse_bp.route('/caisse/reinitialiser', methods=['POST'])
def reinitialiser_caisse():
    # Sécurité absolue : réservé à l'admin
    if session.get('role') != 'admin':
        flash("Accès refusé. Réservé aux administrateurs.", "error")
        return redirect(url_for('caisse.tableau_caisse'))

    try:
        # 1. On supprime TOUS les mouvements de caisse
        MouvementCaisse.query.delete()
        
        # 2. On supprime TOUTES les sessions de caisse
        SessionCaisse.query.delete()
        
        # 3. On valide la destruction
        db.session.commit()
        
        flash("🧹 Mode Test : L'historique de la caisse a été entièrement vidé !", "success")
    except Exception as e:
        db.session.rollback()
        print(f"Erreur lors de la réinitialisation : {e}")
        flash("Une erreur est survenue lors du nettoyage.", "error")

    return redirect(url_for('caisse.historique_caisse'))

@caisse_bp.route('/caisse/rapport_z/<int:session_id>')
def rapport_z(session_id):
    # Sécurité admin (optionnel si tu veux que les caissiers puissent imprimer leur Z)
    if session.get('role') != 'admin':
        flash("Accès refusé.", "error")
        return redirect(url_for('caisse.tableau_caisse'))

    # On récupère la session exacte et ses mouvements non annulés
    session_caisse = SessionCaisse.query.get_or_404(session_id)
    mouvements = MouvementCaisse.query.filter_by(
        session_id=session_id, 
        est_annule=False
    ).order_by(MouvementCaisse.id.asc()).all()
    
    return render_template('rapport_z.html', 
                           session_caisse=session_caisse, 
                           mouvements=mouvements)