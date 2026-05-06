import os
import shutil
import atexit
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

def sauvegarder_bdd():
    """Crée une copie de la base de données et ne garde que les 7 plus récentes."""
    os.makedirs('backups', exist_ok=True)
    
    # Vérifie où se trouve la base de données selon l'environnement
    chemin_db = 'instance/base.db' if os.path.exists('instance/base.db') else 'base.db'
    
    if os.path.exists(chemin_db):
        nom_fichier = f"sauvegarde_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        shutil.copy2(chemin_db, os.path.join('backups', nom_fichier))
        
        # Nettoyage des vieux backups (Garde les 7 derniers jours)
        fichiers_backup = sorted([os.path.join('backups', f) for f in os.listdir('backups')])
        while len(fichiers_backup) > 7: 
            os.remove(fichiers_backup.pop(0))
            
        print(f"✅ [Système] Backup automatique réalisé : {nom_fichier}")

def demarrer_taches_de_fond():
    """Initialise et lance le planificateur de tâches."""
    scheduler = BackgroundScheduler()
    # Déclenchement tous les soirs à 23h59
    scheduler.add_job(func=sauvegarder_bdd, trigger="cron", hour=23, minute=59)
    scheduler.start()
    
    # S'assure que le planificateur s'arrête proprement si on coupe le serveur
    atexit.register(lambda: scheduler.shutdown())