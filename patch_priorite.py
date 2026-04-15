from app import app, db
from sqlalchemy import text
def maj_priorite():
    with app.app_context():
        try:
            db.session.execute(text("ALTER TABLE ticket ADD COLUMN is_priority BOOLEAN DEFAULT 0"))
            db.session.commit()
            print("✅ BINGO ! L'option Urgence a été ajoutée.")
        except Exception as e:
            print("Déjà fait !")
if __name__ == '__main__': maj_priorite()