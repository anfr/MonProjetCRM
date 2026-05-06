from flask import Blueprint, redirect, request
import urllib.parse
from models import Operation, ConfigSysteme

# Création du Blueprint 'communication'
comm_bp = Blueprint('communication', __name__)

@comm_bp.route('/generer_whatsapp/<type_msg>/<int:id_op>')
def generer_whatsapp(type_msg, id_op):
    op = Operation.query.get_or_404(id_op)
    if not op.client.telephone: return redirect(request.referrer)
    config = ConfigSysteme.query.first()
    
    if type_msg == 'dette': 
        texte_brut, montant = config.msg_whatsapp_dette or "Bonjour [PRENOM], reste: [MONTANT] DH", abs(op.reste_a_payer)
    elif type_msg == 'monnaie': 
        texte_brut, montant = config.msg_whatsapp_monnaie or "Bonjour [PRENOM], monnaie: [MONTANT] DH", abs(op.reste_a_payer)
    elif type_msg == 'recu': 
        texte_brut, montant = config.msg_whatsapp_recu or "Bonjour [PRENOM], reçu: [MONTANT] DH", op.montant_total or 0
    else: 
        return redirect(request.referrer)

    texte_final = texte_brut.replace('[PRENOM]', op.client.prenom.capitalize())\
                            .replace('[NOM]', op.client.nom.upper())\
                            .replace('[MONTANT]', str(round(montant, 2)))\
                            .replace('[DATE]', op.date_operation.strftime('%d/%m/%Y'))\
                            .replace('[NB_RECUS]', str(len(op.photos)))
                            
    tel = op.client.telephone.replace(' ', '').replace('+', '')
    tel = '212' + tel[1:] if tel.startswith('0') else ('212' + tel if not tel.startswith('212') else tel)
    
    return redirect(f"https://wa.me/{tel}?text={urllib.parse.quote(texte_final)}")