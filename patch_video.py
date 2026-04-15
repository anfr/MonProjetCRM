from app import app, db
from sqlalchemy import text
def maj_video():
    with app.app_context():
        try:
            db.session.execute(text("ALTER TABLE parametre_tv ADD COLUMN youtube_id VARCHAR(50) DEFAULT '5qap5aO4i9A'"))
            db.session.commit()
            print("✅ BINGO ! L'option Vidéo a été ajoutée.")
        except Exception as e:
            print("Déjà fait !")
if __name__ == '__main__': maj_video()