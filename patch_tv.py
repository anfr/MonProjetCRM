from app import app, db
from sqlalchemy import text

def forcer_mise_a_jour_tv():
    with app.app_context():
        try:
            db.session.execute(text("ALTER TABLE parametre_tv ADD COLUMN vitesse_defilement INTEGER DEFAULT 20"))
            db.session.execute(text("ALTER TABLE parametre_tv ADD COLUMN label_guichet VARCHAR(50) DEFAULT 'GUICHET'"))
            db.session.commit()
            print("✅ BINGO ! Base de données mise à jour.")
        except Exception as e:
            print(f"✅ (Déjà à jour) : {e}")

if __name__ == '__main__':
    forcer_mise_a_jour_tv()