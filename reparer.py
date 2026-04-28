import sqlite3
import os

chemin_db = 'instance/base.db' # Vérifie que c'est bien le bon chemin

if os.path.exists(chemin_db):
    conn = sqlite3.connect(chemin_db)
    # On supprime les tables créées à moitié
    conn.execute('DROP TABLE IF EXISTS mouvement_caisse')
    conn.execute('DROP TABLE IF EXISTS session_caisse')
    # On efface la mémoire des migrations
    conn.execute('DROP TABLE IF EXISTS alembic_version')
    conn.commit()
    conn.close()
    print("✅ Nettoyage parfait. Prêt pour la vraie migration !")
else:
    print("❌ Fichier introuvable.")