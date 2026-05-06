import socket
# On importe app ET socketio depuis ton fichier principal
from main import main, socketio 

def get_local_ip():
    """Petite fonction magique pour trouver la vraie adresse IP de ton PC sur le Wifi"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # N'envoie rien sur internet, sert juste à déterminer la carte réseau utilisée
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

if __name__ == '__main__':
    ip_locale = get_local_ip()
    
    print("\n" + "="*55)
    print("🚀 KIOSQUE PRO EN PRODUCTION (TEMPS RÉEL ACTIF) 🚀")
    print("="*55)
    print(f"💻 Accessible sur ce PC   : http://127.0.0.1:5000")
    print(f"📱 À scanner (TV/Mobiles) : http://{ip_locale}:5000")
    print("\n⚠️  Ne fermez pas cette fenêtre noire pendant le travail.")
    print("="*55 + "\n")
    
    # SocketIO remplace Waitress pour gérer parfaitement les WebSockets !
    socketio.run(main, host='0.0.0.0', port=5000)