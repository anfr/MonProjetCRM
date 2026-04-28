import socket
from flask import Blueprint, render_template, redirect, request, jsonify, url_for, session, current_app
import win32print
from models import db, Ticket, Client, ConfigSysteme, Service, BoutonRapide
from datetime import datetime

queue_bp = Blueprint('queue', __name__)

def obtenir_ip_locale():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

@queue_bp.route('/queue/gestion')
def gestion_file():
    aujourdhui = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    en_attente = Ticket.query.filter(
        Ticket.date_creation >= aujourdhui, 
        Ticket.statut == 'en_attente'
    ).order_by(Ticket.is_priority.desc(), Ticket.id.asc()).all()
    
    en_pause = Ticket.query.filter(Ticket.statut == 'en_pause').all()
    historique = Ticket.query.filter_by(statut='appele').order_by(Ticket.id.desc()).limit(10).all()
    return render_template('gestion_file.html', en_attente=en_attente, en_pause=en_pause, historique=historique)

@queue_bp.route('/queue/prioriser/<int:id_ticket>')
def prioriser_ticket(id_ticket):
    ticket = Ticket.query.get_or_404(id_ticket)
    ticket.is_priority = True
    db.session.commit()
    current_app.socketio.emit('ticket_maj', {}) 
    return redirect(request.referrer or url_for('queue.gestion_file'))

@queue_bp.route('/queue/appeler/<int:id_ticket>')
def appeler_ticket(id_ticket):
    ticket = Ticket.query.get_or_404(id_ticket)
    ticket.statut = 'appele'
    ticket.guichet = session.get('guichet', '1')
    db.session.commit()
    
    current_app.socketio.emit('nouveau_ticket_affiche', {
        'lettre': ticket.lettre,
        'numero': f"{ticket.numero:03d}",
        'service': ticket.service,
        'guichet': ticket.guichet
    })
    current_app.socketio.emit('ticket_maj', {}) 
    return redirect(request.referrer or url_for('queue.gestion_file'))

@queue_bp.route('/queue/mettre_en_pause/<int:id_ticket>')
def mettre_en_pause(id_ticket):
    ticket = Ticket.query.get_or_404(id_ticket)
    ticket.statut = 'en_pause'
    db.session.commit()
    current_app.socketio.emit('ticket_maj', {}) 
    return redirect(request.referrer or url_for('queue.gestion_file'))

@queue_bp.route('/queue/reinitialiser')
def reinitialiser_file():
    if session.get('role') == 'admin':
        Ticket.query.delete()
        db.session.commit()
        current_app.socketio.emit('reset_tv', {})
        current_app.socketio.emit('ticket_maj', {}) 
    return redirect(url_for('queue.gestion_file'))

@queue_bp.route('/queue/generer/<service_nom>')
def generer_ticket(service_nom):
    service_db = Service.query.filter_by(nom_service=service_nom).first()
    if service_db:
        lettre_service = service_db.lettre
    else:
        bouton_db = BoutonRapide.query.filter_by(nom_service=service_nom).first()
        if bouton_db:
            lettre_service = bouton_db.lettre
        else:
            lettre_service = 'A'
            
    debut_jour = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    dernier = Ticket.query.filter(Ticket.date_creation >= debut_jour).order_by(Ticket.numero.desc()).first()

    nouveau_num = (dernier.numero + 1) if dernier else 1
    nouveau_ticket = Ticket(numero=nouveau_num, lettre=lettre_service, service=service_nom, statut='en_attente')
    db.session.add(nouveau_ticket)
    db.session.commit()
    
    current_app.socketio.emit('ticket_maj', {}) 
    return redirect(request.referrer or url_for('accueil'))

@queue_bp.route('/queue/public')
def public_view():
    ticket_actuel = Ticket.query.filter_by(statut='appele').order_by(Ticket.id.desc()).first()
    tv_config = ConfigSysteme.query.first()
    historique = Ticket.query.filter_by(statut='appele').order_by(Ticket.id.desc()).offset(1).limit(10).all()
    
    debut_jour = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    nb_attente = Ticket.query.filter(Ticket.date_creation >= debut_jour, Ticket.statut == 'en_attente').count()
    temps_attente_initial = nb_attente * 3

    return render_template('public_file.html', 
                           ticket=ticket_actuel, 
                           tv_config=tv_config, 
                           historique=historique,
                           temps_attente=temps_attente_initial)

@queue_bp.route('/api/temps_attente')
def api_temps_attente():
    debut_jour = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    nb_attente = Ticket.query.filter(Ticket.date_creation >= debut_jour, Ticket.statut == 'en_attente').count()
    return jsonify({'temps': nb_attente * 3}) 

@queue_bp.route('/queue/imprimer/<int:id_ticket>')
def imprimer_ticket(id_ticket):
    ticket = Ticket.query.get_or_404(id_ticket)
    tv_config = ConfigSysteme.query.first()
    return render_template('ticket_impression.html', ticket=ticket, tv_config=tv_config)

@queue_bp.route('/queue/annoncer_urgence/<int:id_ticket>')
def annoncer_urgence(id_ticket):
    ticket = Ticket.query.get_or_404(id_ticket)
    current_app.socketio.emit('afficher_urgence_tv', {
        'lettre': ticket.lettre,
        'numero': f"{ticket.numero:03d}"
    })
    return redirect(request.referrer or url_for('queue.gestion_file'))

@queue_bp.route('/admin_ticket', methods=['GET', 'POST'])
def admin_ticket():
    if session.get('role') != 'admin':
        return redirect(url_for('accueil'))

    config = ParametreTV.query.first()
    
    if request.method == 'POST':
        config.ticket_nom_kiosque = request.form.get('ticket_nom_kiosque', 'KIOSQUE PRO')
        config.ticket_sous_titre = request.form.get('ticket_sous_titre', '')
        config.ticket_message = request.form.get('ticket_message', '')
        db.session.commit()
        return redirect(url_for('queue.admin_ticket'))

    return render_template('admin_ticket.html', config=config)

@queue_bp.route('/mobile')
def mobile_portail():
    boutons = BoutonRapide.query.all()
    return render_template('mobile_portail.html', boutons=boutons)

@queue_bp.route('/mobile/generer/<service_nom>')
def mobile_generer(service_nom):
    bouton_db = BoutonRapide.query.filter_by(nom_service=service_nom).first()
    lettre_service = bouton_db.lettre if bouton_db else 'A'
        
    debut_jour = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    dernier = Ticket.query.filter(Ticket.date_creation >= debut_jour).order_by(Ticket.numero.desc()).first()
    nouveau_num = (dernier.numero + 1) if dernier else 1
    
    nouveau_ticket = Ticket(numero=nouveau_num, lettre=lettre_service, service=service_nom, statut='en_attente')
    db.session.add(nouveau_ticket)
    db.session.commit()
    
    current_app.socketio.emit('ticket_maj', {}) 
    return redirect(url_for('queue.mobile_ticket', id_ticket=nouveau_ticket.id))

@queue_bp.route('/mobile/ticket/<int:id_ticket>')
def mobile_ticket(id_ticket):
    ticket = Ticket.query.get_or_404(id_ticket)
    debut_jour = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    personnes_avant = Ticket.query.filter(
        Ticket.date_creation >= debut_jour,
        Ticket.statut == 'en_attente',
        Ticket.id < ticket.id
    ).count()
    return render_template('mobile_ticket.html', ticket=ticket, personnes_avant=personnes_avant)

@queue_bp.route('/borne_qr')
def borne_qr():
    ip_locale = obtenir_ip_locale()
    port = request.host.split(':')[1] if ':' in request.host else '5000'
    url_portail = f"http://{ip_locale}:{port}{url_for('queue.mobile_portail')}"
    liste_boutons = BoutonRapide.query.all() 
    return render_template('borne_qr.html', url_portail=url_portail, liste_boutons=liste_boutons)

@queue_bp.route('/borne/creer_et_imprimer/<int:id_bouton>', methods=['POST'])
def borne_creer_et_imprimer(id_bouton):
    # --- 1. LE "DÉTECTEUR DE MENSONGE" WINDOWS ---
    try:
        nom_imprimante = win32print.GetDefaultPrinter()
        hPrinter = win32print.OpenPrinter(nom_imprimante)
        
        # On demande le vrai statut physique du matériel
        info = win32print.GetPrinter(hPrinter, 2)
        status = info['Status']
        
        # On vérifie s'il y a des tickets coincés dans la file d'attente Windows
        jobs = win32print.EnumJobs(hPrinter, 0, -1, 1)
        win32print.ClosePrinter(hPrinter)

        # Code d'erreur : 128 (Débranchée), 16 (Plus de papier), 2 (Erreur générale)
        # S'il y a des erreurs OU des tickets bloqués, on déclenche l'alarme
        if (status & (128 | 16 | 2)) or len(jobs) > 0:
            return jsonify({'status': 'error', 'message': 'Imprimante indisponible'})
            
    except Exception as e:
        print(f"Erreur de diagnostic imprimante : {e}")
        return jsonify({'status': 'error', 'message': 'Impossible de joindre l\'imprimante'})

    # --- 2. CRÉATION DU TICKET (Seulement si l'imprimante va bien !) ---
    bouton = BoutonRapide.query.get_or_404(id_bouton)
    debut_jour = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    dernier_ticket = Ticket.query.filter(Ticket.date_creation >= debut_jour).order_by(Ticket.numero.desc()).first()
    
    nouveau_numero = dernier_ticket.numero + 1 if dernier_ticket else 1
    
    nouveau_ticket = Ticket(
        lettre=bouton.lettre,
        numero=nouveau_numero,
        service=bouton.nom_service,
        statut='en_attente'
    )
    db.session.add(nouveau_ticket)
    db.session.commit()
    
    from flask import current_app
    current_app.socketio.emit('ticket_maj')
    
    # --- 3. IMPRESSION ---
    try:
        with current_app.test_request_context():
            imprimer_direct(nouveau_ticket.id)
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@queue_bp.route('/queue/deck')
def mobile_deck():
    aujourdhui = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    ticket_actuel = Ticket.query.filter_by(statut='appele').order_by(Ticket.id.desc()).first()
    prochain = Ticket.query.filter(
        Ticket.date_creation >= aujourdhui, 
        Ticket.statut == 'en_attente'
    ).order_by(Ticket.is_priority.desc(), Ticket.id.asc()).first()
    
    en_attente_count = Ticket.query.filter(
        Ticket.date_creation >= aujourdhui, 
        Ticket.statut == 'en_attente'
    ).count()
    en_pause_count = Ticket.query.filter(Ticket.statut == 'en_pause').count()
    
    return render_template('mobile_deck.html', 
                           ticket_actuel=ticket_actuel, 
                           prochain=prochain,
                           en_attente=en_attente_count,
                           en_pause=en_pause_count)

@queue_bp.route('/queue/imprimer_direct/<int:id_ticket>', methods=['POST'])
def imprimer_direct(id_ticket):
    ticket = Ticket.query.get_or_404(id_ticket)
    config = ParametreTV.query.first()
    nom_boutique = config.ticket_nom_kiosque if config and config.ticket_nom_kiosque else "KIOSQUE PRO"
    sous_titre = config.ticket_sous_titre if config and config.ticket_sous_titre else "Espace Multiservices"
    message_fin = config.ticket_message if config and config.ticket_message else "Merci de patienter\nVotre tour arrive bientôt !"
    
    try:
        nom_imprimante = win32print.GetDefaultPrinter()
        hPrinter = win32print.OpenPrinter(nom_imprimante)
        
        try:
            ESC = b'\x1b'
            GS = b'\x1d'
            
            INIT = ESC + b'\x40'
            CENTER = ESC + b'\x61\x01'
            LEFT = ESC + b'\x61\x00'
            BOLD_ON = ESC + b'\x45\x01'
            BOLD_OFF = ESC + b'\x45\x00'
            SIZE_NORMAL = GS + b'\x21\x00'
            SIZE_LARGE = GS + b'\x21\x11'
            SIZE_HUGE = GS + b'\x21\x22'
            CUT = GS + b'\x56\x00'
            
            nom = nom_boutique.encode('cp850', errors='replace')
            s_titre = sous_titre.encode('cp850', errors='replace')
            service = ticket.service.encode('cp850', errors='replace')
            num = f"{ticket.lettre}{ticket.numero:03d}".encode('cp850', errors='replace')
            date_str = ticket.date_creation.strftime('%d/%m/%Y %H:%M').encode('cp850', errors='replace')
            msg = message_fin.replace('\r\n', '\n').encode('cp850', errors='replace')

            data = INIT
            data += CENTER + BOLD_ON + SIZE_LARGE + nom + b'\n'
            data += SIZE_NORMAL + BOLD_OFF + s_titre + b'\n'
            data += b'--------------------------------\n\n'
            data += SIZE_NORMAL + BOLD_OFF + b'SERVICE : ' + BOLD_ON + service + b'\n\n'
            data += SIZE_HUGE + BOLD_ON + num + b'\n\n'
            data += SIZE_NORMAL + BOLD_OFF
            data += b'--------------------------------\n'
            data += date_str + b'\n\n'
            data += msg + b'\n\n\n\n'
            data += CUT

            win32print.StartDocPrinter(hPrinter, 1, ("Ticket Kiosque", None, "RAW"))
            win32print.StartPagePrinter(hPrinter)
            win32print.WritePrinter(hPrinter, data)
            win32print.EndPagePrinter(hPrinter)
            win32print.EndDocPrinter(hPrinter)
            
            return jsonify({'status': 'success'})
            
        finally:
            win32print.ClosePrinter(hPrinter)
            
    except Exception as e:
        print(f"Erreur d'impression : {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@queue_bp.route('/queue/affiche_pdf')
def affiche_pdf():
    ip_locale = obtenir_ip_locale()
    port = request.host.split(':')[1] if ':' in request.host else '5000'
    url_portail = f"http://{ip_locale}:{port}{url_for('queue.mobile_portail')}"
    return render_template('affiche_pdf.html', url_portail=url_portail)