from flask import Blueprint, render_template, request, redirect, url_for, session
from werkzeug.security import check_password_hash
from extensions import db
from models import Utilisateur

# Création du Blueprint 'auth'
auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    erreur = "Votre session a été fermée depuis un autre appareil." if request.args.get('expire') else None
    
    if request.method == 'POST':
        user = Utilisateur.query.filter_by(username=request.form.get('username', '').strip()).first()
        mot_de_passe_fourni = request.form.get('password', '')

        if user and (user.password == mot_de_passe_fourni or check_password_hash(user.password, mot_de_passe_fourni)):
            session.update({
                'connecte': True, 
                'user_id': user.id,
                'username': user.username, 
                'role': user.role, 
                'guichet': getattr(user, 'guichet', '1'), 
                'auth_version': user.auth_version
            })
            # ⚠️ Redirection vers le blueprint 'dashboard'
            return redirect(url_for('dashboard.accueil'))
            
        erreur = "Identifiant ou mot de passe incorrect."
        
    return render_template('login.html', erreur=erreur)

@auth_bp.route('/logout')
def logout():
    if session.get('user_id'): 
        user = Utilisateur.query.get(session['user_id'])
        if user:
            user.auth_version += 1
            db.session.commit()
    
    session.clear()
    return redirect(url_for('auth.login'))

@auth_bp.route('/profil', methods=['GET', 'POST'])
def profil():
    user = Utilisateur.query.filter_by(username=session.get('username')).first()
    if not user: 
        return redirect(url_for('auth.login'))
    return render_template('profil.html', user=user, erreur=None, succes=None)