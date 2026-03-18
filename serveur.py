from waitress import serve
from app import app

if __name__ == '__main__':
    print("=====================================================")
    print("🚀 KIOSQUE EN PRODUCTION (MODE SÉCURISÉ) 🚀")
    print("🌐 Accessible sur ce PC : http://127.0.0.1:5000")
    print("🌍 Accessible sur le réseau : http://VOTRE_IP:5000")
    print("Ne fermez pas cette fenêtre noire pendant le travail.")
    print("=====================================================")
    
    # Waitress prend le relais !
    serve(app, host='0.0.0.0', port=5000, threads=6)