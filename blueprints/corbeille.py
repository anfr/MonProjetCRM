from flask import Blueprint, render_template, session, redirect, url_for, current_app
import os
from extensions import db
from models import Operation, Contrat

# Création du Blueprint 'corbeille'
corbeille_bp = Blueprint('corbeille', __name__)

@corbeille_bp.route('/corbeille')
def vue_corbeille():
    if session.get('role') != 'admin':
        return redirect(url_for('dashboard.accueil'))
    
    operations_supprimees = Operation.query.filter_by(archive=True).all()
    contrats_supprimes = Contrat.query.filter_by(archive=True).all()
    
    return render_template('corbeille.html', operations=operations_supprimees, contrats=contrats_supprimes)

@corbeille_bp.route('/restaurer_operation/<int:id_op>', methods=['POST'])
def restaurer_operation(id_op):
    if session.get('role') == 'admin':
        op = Operation.query.get_or_404(id_op)
        op.archive = False
        db.session.commit()
    return redirect(url_for('corbeille.vue_corbeille'))

@corbeille_bp.route('/detruire_operation/<int:id_op>', methods=['POST'])
def detruire_operation(id_op):
    if session.get('role') == 'admin':
        op = Operation.query.get_or_404(id_op)
        try:
            # Destruction des reçus (Note : On utilise current_app.config ici !)
            for photo in op.photos:
                chemin = os.path.join(current_app.config['UPLOAD_FOLDER'], photo.nom_fichier)
                if os.path.exists(chemin):
                    os.remove(chemin)
                    
            if op.photo_recu:
                ancien_chemin = os.path.join(current_app.config['UPLOAD_FOLDER'], op.photo_recu)
                if os.path.exists(ancien_chemin):
                    os.remove(ancien_chemin)

            db.session.delete(op)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Erreur lors de la destruction : {e}")
            
    return redirect(url_for('corbeille.vue_corbeille'))

@corbeille_bp.route('/restaurer_contrat/<int:id_contrat>', methods=['POST'])
def restaurer_contrat(id_contrat):
    if session.get('role') == 'admin':
        contrat = Contrat.query.get_or_404(id_contrat)
        contrat.archive = False
        db.session.commit()
    return redirect(url_for('corbeille.vue_corbeille'))

@corbeille_bp.route('/detruire_contrat/<int:id_contrat>', methods=['POST'])
def detruire_contrat(id_contrat):
    if session.get('role') == 'admin':
        contrat = Contrat.query.get_or_404(id_contrat)
        db.session.delete(contrat)
        db.session.commit()
    return redirect(url_for('corbeille.vue_corbeille'))