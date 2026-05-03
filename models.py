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
    guichet = db.Column(db.String(10), default='1')
    operations_faites = db.relationship('Operation', backref='caissier', lazy=True)
    
    # --- PERMISSIONS SPÉCIFIQUES ---
    peut_annuler = db.Column(db.Boolean, default=False)
    peut_cloturer_caisse = db.Column(db.Boolean, default=False)
    peut_voir_stats = db.Column(db.Boolean, default=False)


class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(100), index=True, nullable=False)
    prenom = db.Column(db.String(100), index=True, nullable=False)
    telephone = db.Column(db.String(20), index=True, nullable=True)
    adresse = db.Column(db.Text, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    archive = db.Column(db.Boolean, default=False)
    contrats = db.relationship('Contrat', backref='client', lazy=True, cascade='all, delete')
    operations = db.relationship('Operation', backref='client', lazy=True, cascade='all, delete')

# service_id = db.Column(db.Integer, db.ForeignKey('service.id'), nullable=True)  # Lien direct vers le service préféré du client
class Service(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nom_service = db.Column(db.String(50), nullable=False)
    contrats = db.relationship('Contrat', backref='service', lazy=True, cascade='all, delete')
    lettre = db.Column(db.String(2), default='A')

class Contrat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    numero_contrat = db.Column(db.String(100), nullable=False)
    nom_proprietaire = db.Column(db.String(150), nullable=False)
    notes = db.Column(db.Text, nullable=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey('service.id'), nullable=False)
    est_actif = db.Column(db.Boolean, default=True)
    archive = db.Column(db.Boolean, default=False)

class Operation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date_operation = db.Column(db.DateTime, default=datetime.now)
    
    # 💡 Sécurité : Toujours 0 par défaut, impossible d'être vide
    montant_avance = db.Column(db.Float, nullable=False, default=0.0) 
    montant_total = db.Column(db.Float, nullable=True)
    
    statut = db.Column(db.String(20), default='En attente')
    statut_dossier = db.Column(db.String(50), default='Dossier déposé')
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    utilisateur_id = db.Column(db.Integer, db.ForeignKey('utilisateur.id'), nullable=False) 
    photo_recu = db.Column(db.String(255), nullable=True)
    archive = db.Column(db.Boolean, default=False)
    
    photos = db.relationship('PhotoRecu', backref='operation', lazy=True, cascade='all, delete')
    
    # 💡 Bouclier SQL : Empêche l'insertion de montants illogiques directement au niveau de la base
    __table_args__ = (
        db.CheckConstraint('montant_total >= montant_avance OR montant_total IS NULL', name='check_montant_logique'),
    )
    
    @property
    def reste_a_payer(self):
        total = self.montant_total or 0
        avance = self.montant_avance or 0
        return total - avance

class PhotoRecu(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nom_fichier = db.Column(db.String(255), nullable=False)
    operation_id = db.Column(db.Integer, db.ForeignKey('operation.id'), nullable=False)

class BoutonRapide(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lettre = db.Column(db.String(5), nullable=False, default='A')
    nom_service = db.Column(db.String(100), nullable=False)

# ==========================================
# GESTION CAISSE & MOUVEMENTS
# ==========================================
class SessionCaisse(db.Model):
    __tablename__ = 'session_caisse'
    id = db.Column(db.Integer, primary_key=True)
    date_ouverture = db.Column(db.DateTime, default=datetime.now)
    date_cloture = db.Column(db.DateTime, nullable=True)
    
    fond_initial = db.Column(db.Float, default=0.0)
    total_entrees = db.Column(db.Float, default=0.0)
    total_sorties = db.Column(db.Float, default=0.0)
    montant_theorique = db.Column(db.Float, nullable=True)
    montant_reel = db.Column(db.Float, nullable=True)
    ecart = db.Column(db.Float, nullable=True)

    tasshilat_initial = db.Column(db.Float, default=0.0)
    total_tasshilat_consomme = db.Column(db.Float, default=0.0)
    total_tasshilat_recharge = db.Column(db.Float, default=0.0)
    tasshilat_theorique = db.Column(db.Float, default=0.0)
    tasshilat_reel = db.Column(db.Float, default=0.0)
    ecart_tasshilat = db.Column(db.Float, default=0.0)
    plafond_tasshilat = db.Column(db.Float, nullable=True, default=0.0)
    
    statut = db.Column(db.String(20), default='Ouverte')
    mouvements = db.relationship('MouvementCaisse', backref='session', lazy=True, cascade='all, delete-orphan')

class MouvementCaisse(db.Model):
    __tablename__ = 'mouvement_caisse'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('session_caisse.id'), nullable=False)
    type_mouvement = db.Column(db.String(50))
    categorie = db.Column(db.String(100))
    montant = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(255))
    date_mouvement = db.Column(db.DateTime, default=datetime.now)
    est_annule = db.Column(db.Boolean, default=False)
    motif_annulation = db.Column(db.String(255))
    impact_tasshilat = db.Column(db.Boolean, default=False)

class CategorieMouvement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(100), nullable=False)
    type_mouvement = db.Column(db.String(20), nullable=False)
    couleur = db.Column(db.String(50), default='indigo')
    icone = db.Column(db.String(50), default='ph-tag')

# ==========================================
# CONFIGURATION SYSTEME V2
# ==========================================
class ConfigSysteme(db.Model):
    __tablename__ = 'config_systeme'
    id = db.Column(db.Integer, primary_key=True)
    
    # --- 1. IDENTITÉ & MATÉRIEL ---
    nom_boutique = db.Column(db.String(100), default='Mon Kiosque Pro')
    logo_filename = db.Column(db.String(255), nullable=True)
    info_siret = db.Column(db.String(100), nullable=True)
    info_adresse = db.Column(db.String(255), nullable=True)
    info_telephone = db.Column(db.String(50), nullable=True)
    imprimante_format = db.Column(db.String(20), default='80mm')
    ouverture_tiroir_auto = db.Column(db.Boolean, default=False)

    # --- 2. ÉCRAN PUBLIC (TV) ---
    whatsapp_tv = db.Column(db.String(50), default='212 6 00 00 00 00')
    label_guichet = db.Column(db.String(50), default='GUICHET')
    youtube_id = db.Column(db.String(50), default='5qap5aO4i9A')
    texte_arabe_tv = db.Column(db.String(500), default='مرحباً بكم في كشك الخدمات المتعددة')
    texte_francais_tv = db.Column(db.String(500), default='Bienvenue au Kiosque Multiservices • Horaires : 08h00 - 18h00')
    vitesse_defilement_tv = db.Column(db.Integer, default=20)
    service_rapide_id = db.Column(db.Integer, nullable=True)

    # --- 3. BORNE INTERACTIVE ---
    borne_titre_fr = db.Column(db.String(200), default='Bienvenue !')
    borne_titre_ar = db.Column(db.String(200), default='مرحباً بكم!')
    borne_sous_titre_fr = db.Column(db.String(500), default='Prenez un ticket') 
    borne_sous_titre_ar = db.Column(db.String(500), default='خذ تذكرتك')
    borne_active_qr = db.Column(db.Boolean, default=True)
    borne_active_impression = db.Column(db.Boolean, default=True)

    # --- 4. TICKET PAPIER ---
    ticket_nom_kiosque = db.Column(db.String(100), default='KIOSQUE PRO')
    ticket_sous_titre = db.Column(db.String(100), default='Espace Multiservices')
    ticket_message = db.Column(db.Text, default='Merci de patienter\nVotre tour arrive bientôt !')

    # --- 5. WHATSAPP PRO ---
    msg_whatsapp_dette = db.Column(db.Text, nullable=True)
    msg_whatsapp_monnaie = db.Column(db.Text, nullable=True)
    msg_whatsapp_recu = db.Column(db.Text, nullable=True)