📖 Documentation Technique : Kiosque Multiservices CRM
1. Présentation du Projet
L'application Kiosque Multiservices est un CRM (Customer Relationship Management) couplé à un système de caisse (Point of Sale). Elle permet la gestion des clients, le suivi de leurs contrats (eau, électricité, etc.), l'enregistrement des paiements (avances et soldes), la gestion des dettes, et l'archivage numérique des reçus de paiement.

🛠️ Stack Technique (Technologies utilisées)
Backend : Python 3

Framework Web : Flask

Base de données : SQLite (via l'ORM Flask-SQLAlchemy)

Traitement d'images : Pillow (PIL)

Sécurité des fichiers : Werkzeug (secure_filename)

Génération d'identifiants : module uuid natif

2. Configuration et Architecture
📂 Gestion des Fichiers (Uploads)
L'application intègre un système d'archivage de photos (reçus de paiement).

Dossier cible : static/uploads/recus (créé automatiquement au démarrage si inexistant).

Optimisation : Fonction compresser_et_sauvegarder_image() :

Redimensionnement proportionnel (Max 1200x1200px) via Image.Resampling.LANCZOS.

Conversion automatique en RGB (pour gérer les PNG transparents).

Export forcé au format .JPG avec une qualité de 80% et une optimisation activée pour réduire drastiquement le poids (de plusieurs Mo à ~150 Ko) sans perte visible.

🔒 Sécurité Globale
La clé secrète de session Flask est définie (app.secret_key).

Intercepteur de requêtes (@app.before_request) : Bloque l'accès à toutes les routes (sauf /login et les fichiers statiques) si l'utilisateur n'a pas de variable de session connecte valide.

3. Schéma de la Base de Données (Modèles SQLAlchemy)
La base de données relationnelle est composée de 5 tables principales :

Utilisateur (Gestion de l'équipe)
Gère les accès au logiciel.

Champs : id, username, nom, prenom, email, telephone, password, role.

Rôles : admin (accès total) ou caissier (accès restreint, ne peut pas supprimer d'éléments ni accéder aux paramètres).

Relation : operations_faites (Lien 1-N vers Operation).

Client (Base de données clients)
Champs : id, nom, prenom, telephone, adresse, notes (confidentielles), archive (booléen pour désactiver un client inactif).

Relations : contrats (1-N) et operations (1-N). Supression en cascade activée.

Service (Catalogue des types d'abonnements)
Champs : id, nom_service (ex: Eau, Électricité, Internet).

Relation : contrats (1-N).

Contrat (Abonnements d'un client)
Champs : id, numero_contrat (N° de police/compteur), nom_proprietaire (titulaire légal), notes (détails spécifiques au compteur/contrat), client_id (FK), service_id (FK).

Operation (Transactions financières)
Le cœur de la comptabilité.

Champs : * id, date_operation (Timestamp auto).

montant_avance (Argent laissé par le client le matin).

montant_total (Coût réel de la facture payée).

statut (Valeurs possibles : En attente ou Terminé).

photo_recu (Nom du fichier image compressé stocké sur le serveur).

client_id (FK - Le client concerné).

utilisateur_id (FK - Le caissier qui a initié l'opération : Traçabilité).

4. Routes et Logique Métier (API)
L'application est divisée en plusieurs modules fonctionnels :

📊 Tableau de Bord (/)
Calcule de manière dynamique les statistiques : Chiffre d'Affaires (CA) du jour, CA du mois en cours, et CA total historique.

Récupère les données pour la génération d'un graphique d'évolution sur les 7 derniers jours.

Détecte et calcule la somme totale des dettes en cours pour afficher l'Alerte de Recouvrement.

👥 Gestion Clients (/clients, /client/<id>)
Moteur de recherche multicritères intégré (Nom, Prénom, Téléphone).

La fiche client (/client/<id>) aggrège : les données du client, ses contrats liés, ses notes privées, et un historique complet trié par date décroissante.

📄 Opérations et Cycle de vie (/nouvelle_operation, /cloturer_operation)
Le cycle d'une transaction est asynchrone :

Démarrage (/nouvelle_operation) : Enregistre une avance. Le statut passe en En attente.

Clôture (/cloturer_operation) : Saisie du montant réel de la facture, attachement éventuel d'une photo du reçu via compresser_et_sauvegarder_image(). Le statut passe à Terminé.

Dettes : Si montant_total > montant_avance, la différence est basculée dans la route /dettes. La route /regler_reste permet de solder cette dette.

⚙️ Administration et Outils (/parametres)
(Réservé au rôle admin)

Gestion de l'équipe (Ajout/Suppression de caissiers).

Gestion du catalogue des services.

Exports CSV : Routes /exporter_donnees (Opérations) et /exporter_clients utilisant la bibliothèque csv native et io.StringIO pour générer un fichier téléchargeable à la volée.

Archivage automatique (/archiver_inactifs) : Parcourt la base clients et passe archive=True pour les clients n'ayant aucune opération dans les 180 derniers jours.

🪪 Outils Externes
Génération de fiches d'identification imprimables avec intégration dynamique d'une API externe pour les QR Codes (https://api.qrserver.com/).

Gestion des erreurs personnalisée (@app.errorhandler(404)).

5. Moteur d'Initialisation
Au démarrage (if __name__ == '__main__':) :

La base de données et les tables sont créées automatiquement si elles n'existent pas (db.create_all()).

Injection des données de base si la base est vierge : création des services par défaut (Eau, Électricité...) et d'un utilisateur "Super Admin" (admin / admin123).
