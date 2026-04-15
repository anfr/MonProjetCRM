from app import app, db
from sqlalchemy import text
def maj_rapide():
    with app.app_context():
        try:
            db.session.execute(text("ALTER TABLE parametre_tv ADD COLUMN service_rapide_id INTEGER"))
            db.session.commit()
            print("✅ BINGO ! L'option Ticket Rapide a été ajoutée.")
        except Exception as e:
            print("Déjà fait !")
if __name__ == '__main__': maj_rapide()