from flask import Blueprint, session, redirect, url_for, jsonify, send_file, make_response
from werkzeug.utils import secure_filename
import os, csv, io
from datetime import datetime
from models import Operation, Client

# Création du Blueprint 'exports'
exports_bp = Blueprint('exports', __name__)

@exports_bp.route('/api/securite/backups')
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

@exports_bp.route('/api/securite/telecharger_backup/<nom_fichier>')
def telecharger_backup(nom_fichier):
    if session.get('role') != 'admin': return "Accès refusé", 403
    chemin_complet = os.path.join('backups', secure_filename(nom_fichier))
    return send_file(chemin_complet, as_attachment=True) if os.path.exists(chemin_complet) else ("Fichier introuvable", 404)

@exports_bp.route('/export_operations_csv')
def export_operations_csv():
    if session.get('role') != 'admin': return redirect(url_for('dashboard.accueil'))
    si = io.StringIO()
    cw = csv.writer(si, delimiter=';')
    cw.writerow(['ID', 'Date', 'Client', 'Montant Total', 'Avance', 'Reste', 'Statut', 'Caissier'])
    for op in Operation.query.order_by(Operation.date_operation.desc()).all():
        cw.writerow([op.id, op.date_operation.strftime('%Y-%m-%d %H:%M'), f"{op.client.nom} {op.client.prenom}", op.montant_total, op.montant_avance, (op.montant_total or 0) - (op.montant_avance or 0), op.statut, op.utilisateur_id])
    output = make_response(si.getvalue().encode('utf-8-sig'))
    output.headers["Content-Disposition"] = f"attachment; filename=export_caisse_{datetime.now().strftime('%Y%m%d')}.csv"
    output.headers["Content-type"] = "text/csv"
    return output

@exports_bp.route('/export_clients_csv')
def export_clients_csv():
    if session.get('role') != 'admin': return redirect(url_for('dashboard.accueil'))
    si = io.StringIO()
    cw = csv.writer(si, delimiter=';')
    cw.writerow(['ID', 'Nom', 'Prénom', 'Téléphone', 'Adresse', 'Notes'])
    for c in Client.query.all(): cw.writerow([c.id, c.nom, c.prenom, c.telephone, c.adresse, c.notes])
    output = make_response(si.getvalue().encode('utf-8-sig'))
    output.headers["Content-Disposition"] = f"attachment; filename=base_clients_{datetime.now().strftime('%Y%m%d')}.csv"
    output.headers["Content-type"] = "text/csv"
    return output