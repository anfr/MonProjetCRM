from app import app, db
from sqlalchemy import text
def maj_categories():
    with app.app_context():
        try:
            db.session.execute(text("ALTER TABLE service ADD COLUMN lettre VARCHAR(2) DEFAULT 'A'"))
            db.session.execute(text("ALTER TABLE ticket ADD COLUMN lettre VARCHAR(2) DEFAULT 'A'"))
            db.session.commit()
            print("✅ BINGO ! Les lettres ont été ajoutées.")
        except Exception as e:
            print("Déjà fait !")
if __name__ == '__main__': maj_categories()