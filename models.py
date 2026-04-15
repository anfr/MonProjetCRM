from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.Integer, nullable=False)
    service = db.Column(db.String(50))
    guichet = db.Column(db.Integer, default=1)
    statut = db.Column(db.String(20), default='en_attente')
    is_priority = db.Column(db.Boolean, default=False)
    date_creation = db.Column(db.DateTime, default=datetime.now)
    lettre = db.Column(db.String(2), default='A')

class Utilisateur(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    nom = db.Column(db.String(100))
    prenom = db.Column(db.String(100))
    email = db.Column(db.String(120))
    telephone = db.Column(db.String(20))
    password = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), default='caissier')
    # On enregistre le guichet de l'employé
    guichet = db.Column(db.String(10), default='1')
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
    lettre = db.Column(db.String(2), default='A')

class Contrat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    numero_contrat = db.Column(db.String(100), nullable=False)
    nom_proprietaire = db.Column(db.String(150), nullable=False)
    notes = db.Column(db.Text, nullable=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey('service.id'), nullable=False)

class Operation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date_operation = db.Column(db.DateTime, default=datetime.now)
    montant_avance = db.Column(db.Float, default=0.0)
    montant_total = db.Column(db.Float, nullable=True)
    statut = db.Column(db.String(20), default='En attente')
    statut_dossier = db.Column(db.String(50), default='Dossier déposé')
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    utilisateur_id = db.Column(db.Integer, db.ForeignKey('utilisateur.id'), nullable=False) 
    photo_recu = db.Column(db.String(255), nullable=True)
    # CETTE LIGNE pour lier les photos
    photos = db.relationship('PhotoRecu', backref='operation', lazy=True, cascade="all, delete")
    @property
    def reste_a_payer(self):
        """Calcule automatiquement ce qui manque (positif) ou la monnaie à rendre (négatif)"""
        total = self.montant_total or 0
        avance = self.montant_avance or 0
        return total - avance


class ParametreTV(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    whatsapp = db.Column(db.String(50), default="212 6 00 00 00 00")
    texte_arabe = db.Column(db.String(500), default="مرحباً بكم في كشك الخدمات المتعددة")
    texte_francais = db.Column(db.String(500), default="Bienvenue au Kiosque Multiservices • Horaires : 08h00 - 18h00")
    # --- LES DEUX NOUVELLES COLONNES ---
    vitesse_defilement = db.Column(db.Integer, default=20)
    label_guichet = db.Column(db.String(50), default='GUICHET')
    youtube_id = db.Column(db.String(50), default='5qap5aO4i9A')
    service_rapide_id = db.Column(db.Integer, nullable=True) # <--- Ticket rapide

    msg_whatsapp_dette = db.Column(db.Text, nullable=True)
    msg_whatsapp_monnaie = db.Column(db.Text, nullable=True)
    msg_whatsapp_recu = db.Column(db.Text, nullable=True)

    # 👇 NOUVEAUX CHAMPS POUR LE TICKET PAPIER 👇
    ticket_nom_kiosque = db.Column(db.String(100), default="KIOSQUE PRO")
    ticket_sous_titre = db.Column(db.String(100), default="Espace Multiservices")
    ticket_message = db.Column(db.Text, default="Merci de patienter\nVotre tour arrive bientôt !")

    # --- PARAMÈTRES STUDIO BORNE ---
    borne_titre_fr = db.Column(db.String(200), default="Bienvenue !")
    borne_titre_ar = db.Column(db.String(200), default="مرحباً بكم!")
    borne_sous_titre_fr = db.Column(db.String(500), default="Prenez un ticket")
    borne_sous_titre_ar = db.Column(db.String(500), default="خذ تذكرتك")
    borne_active_qr = db.Column(db.Boolean, default=True)
    borne_active_impression = db.Column(db.Boolean, default=True)

class BoutonRapide(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lettre = db.Column(db.String(5), nullable=False, default='A') # <-- NOUVEAU
    nom_service = db.Column(db.String(100), nullable=False)

class PhotoRecu(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nom_fichier = db.Column(db.String(255), nullable=False)
    operation_id = db.Column(db.Integer, db.ForeignKey('operation.id'), nullable=False)