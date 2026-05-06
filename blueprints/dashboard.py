from flask import Blueprint, render_template, session, redirect, url_for
from extensions import db
from models import Operation
from sqlalchemy import func
from datetime import datetime, timedelta

# Création du Blueprint 'dashboard'
dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/')
@dashboard_bp.route('/dashboard')
def accueil():
    if not session.get('connecte'):
        return redirect(url_for('auth.login'))

    aujourdhui = datetime.now().date()
    hier = aujourdhui - timedelta(days=1)
    
    labels_jours, donnees_ca = [], []
    for i in range(6, -1, -1):
        date_cible = aujourdhui - timedelta(days=i)
        labels_jours.append(date_cible.strftime('%a %d'))
        
        ca_du_jour = db.session.query(func.sum(Operation.montant_avance)).filter(
            func.date(Operation.date_operation) == date_cible, 
            Operation.statut == 'Terminé',
            Operation.archive == False
        ).scalar() or 0
        donnees_ca.append(float(ca_du_jour))

    ops_en_attente = Operation.query.filter_by(statut='En attente', archive=False).order_by(Operation.date_operation.asc()).all()
    ops_du_jour = Operation.query.filter(func.date(Operation.date_operation) == aujourdhui, Operation.archive == False).all()
    
    ca_jour = sum((op.montant_avance or 0) for op in ops_du_jour if op.statut == 'Terminé')
    
    ca_hier = db.session.query(func.sum(Operation.montant_avance)).filter(
        func.date(Operation.date_operation) == hier, 
        Operation.statut == 'Terminé',
        Operation.archive == False
    ).scalar() or 0

    evolution_ca = ((ca_jour - ca_hier) / ca_hier) * 100 if ca_hier > 0 else (100.0 if ca_jour > 0 else 0.0)

    total_dettes = db.session.query(func.sum(Operation.montant_total - Operation.montant_avance)).filter(
        Operation.statut == 'Terminé',
        Operation.montant_total > Operation.montant_avance, 
        Operation.archive == False
    ).scalar() or 0

    return render_template('dashboard.html', 
        operations_en_attente=ops_en_attente, 
        total_operations_jour=len(ops_du_jour), 
        ca_jour=round(ca_jour, 2), 
        evolution_ca=evolution_ca,
        total_dettes=round(total_dettes, 2), 
        benefice_estime="--", 
        labels_jours=labels_jours, 
        donnees_ca=donnees_ca
    )