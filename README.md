# 🎥 YTArchive v2.0 + Backblaze B2

**YTArchive** est un gestionnaire d'archives vidéos YouTube personnel avec stockage cloud **Backblaze B2**. Téléchargez, organisez et regardez vos vidéos YouTube préférées avec un stockage illimité dans le cloud.

---

## ✨ Fonctionnalités principales

### 🚀 Téléchargement et Stockage
- 📹 **Téléchargement YouTube** via yt-dlp
- ☁️ **Stockage cloud Backblaze B2** automatique
- 📊 Barre de progression en temps réel (YouTube → Local → B2)
- 🎬 **Qualités multiples** : 480p, 720p, 1080p, best
- 💾 **Nettoyage automatique** des fichiers locaux après upload

### 📺 Player Avancé
- 🎬 **Streaming direct depuis B2** (URLs signées)
- ⏩ Contrôles de vitesse (0.5x → 2x)
- ⏭️ Skip +/- 10 secondes
- ⏸️ Raccourcis clavier complets
- 🖼️ Mode plein écran
- 🎵 Volume et mute rapides

### 📁 Gestion Bibliothèque
- 🔍 Recherche instantanée
- 🏷️ Filtrage par chaîne
- 📈 Tri multi-critères (date, vues, durée, titre)
- 🖼️ Vue grille / liste
- 👥 **Multi-utilisateurs** (chaque user = son propre bucket B2)

### 📡 Suivi de Chaînes
- ➕ Ajout de chaînes YouTube
- 🤖 **Auto-download** des nouvelles vidéos
- ⏰ Vérification planifiée (toutes les heures)
- 📊 Statistiques par chaîne
- 🎯 Contrôle manuel des mises à jour

### 👤 Système Utilisateur
- 🔐 Authentification JWT
- 👥 Multi-utilisateurs avec rôles (admin/user)
- 🖼️ Upload d'avatars personnalisés
- ⚙️ Page de profil avec changement de mot de passe
- 🔑 **Configuration B2 individuelle** par utilisateur

---

## 💻 Installation

### Prérequis

- Python 3.8+
- Compte [Backblaze B2](https://www.backblaze.com/b2/sign-up.html) (10 GB gratuits)

### Étape 1 : Cloner le repository

```bash
git clone https://github.com/theo7791l/ytarchive.git
cd ytarchive
```

### Étape 2 : Installer les dépendances

```bash
pip install -r requirements.txt
```

### Étape 3 : Lancer le serveur

```bash
python main.py
```

Ou avec uvicorn :

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

L'application sera accessible sur : **http://localhost:8000**

---

## ☁️ Configuration Backblaze B2

### Étape 1 : Créer un compte B2

1. Allez sur [backblaze.com/b2/sign-up.html](https://www.backblaze.com/b2/sign-up.html)
2. Créez votre compte (gratuit jusqu'à 10 GB)
3. Vérifiez votre email

### Étape 2 : Créer un bucket

1. Connectez-vous au dashboard B2
2. Cliquez **"Create a Bucket"**
3. Nom du bucket : `ytarchive-votre-username`
4. Sélectionnez **"Private"**
5. Cliquez **"Create Bucket"**

### Étape 3 : Générer une Application Key

1. Allez dans **App Keys**
2. Cliquez **"Add a New Application Key"**
3. Nom : `ytarchive-key`
4. Sélectionnez votre bucket
5. Permissions : **Read and Write**
6. Cliquez **"Create New Key"**
7. **IMPORTANT** : Notez immédiatement le `keyID` et l'`applicationKey`

### Étape 4 : Configurer dans YTArchive

1. Connectez-vous à YTArchive
2. Allez dans **Profile** (en haut à droite)
3. Section **"Backblaze B2 Storage"**
4. Remplissez :
   - **Application Key ID** : Votre `keyID`
   - **Application Key** : Votre `applicationKey`
   - **Bucket Name** : Le nom de votre bucket
5. Cliquez **"Test & Save B2 Credentials"**
6. ✅ Vous devriez voir le badge **"Configured"** en vert

---

## 🚀 Utilisation

### 1️⃣ Première connexion

**Compte admin par défaut :**
- Username : `admin`
- Password : `admin`

⚠️ **Changez ce mot de passe immédiatement** dans **Profile** > **Change Password**

### 2️⃣ Configurer Backblaze B2

Suivez les étapes de la section **Configuration Backblaze B2** ci-dessus.

### 3️⃣ Télécharger une vidéo

1. Allez dans l'onglet **"Download"**
2. Collez l'URL YouTube
3. Sélectionnez la qualité
4. Cliquez **"Download Video"**
5. Suivez la progression :
   - 📹 Téléchargement depuis YouTube
   - ⏳ Traitement
   - ☁️ Upload vers Backblaze B2
   - ✅ Terminé !

### 4️⃣ Regarder une vidéo

1. Allez dans **"Library"**
2. Cliquez sur **"Play"** sur n'importe quelle vidéo
3. Le player se lance avec streaming depuis B2
4. Utilisez les raccourcis clavier :
   - **Space** : Play/Pause
   - **← / →** : -5s / +5s
   - **↑ / ↓** : Volume
   - **F** : Plein écran
   - **M** : Mute
   - **Esc** : Fermer le player

### 5️⃣ Ajouter une chaîne

1. Allez dans **"Channels"**
2. Cliquez **"Add Channel"**
3. Collez l'URL de la chaîne YouTube
4. Sélectionnez la qualité
5. Activez **"Auto-download"** si désiré
6. Cliquez **"Add Channel"**

Les nouvelles vidéos seront automatiquement téléchargées toutes les heures !

---

## 📊 Coûts Backblaze B2

### Tarification (2026)

- **Stockage** : $0.005/GB/mois (~$5 pour 1TB/mois)
- **Téléchargement** : $0.01/GB (3x gratuit)
- **API** : Gratuit
- **Gratuit** : 10 GB + 1 GB/jour de download

### Exemple : 100 vidéos de 500 MB

- Stockage : 50 GB = **$0.25/mois**
- Visionnage : 10 GB/mois = **$0.10/mois** (après quota gratuit)
- **Total : ~$0.35/mois** 💸

**Conclusion** : B2 est **extrêmement abordable** pour stocker vos vidéos !

---

## 🛠️ Architecture Technique

### Stack

- **Backend** : FastAPI + Python
- **Frontend** : HTML5 + CSS3 + JavaScript vanilla
- **Download** : yt-dlp
- **Storage** : Backblaze B2 (API native)
- **Auth** : JWT tokens
- **Database** : JSON (simple et efficace)

### Structure

```
ytarchive/
├── main.py                 # FastAPI app principale
├── auth.py                 # Authentification + gestion users
├── downloader.py           # Téléchargement + upload B2
├── scheduler.py            # Planificateur chaînes
├── b2_storage.py           # Module Backblaze B2
├── static/
│   ├── index.html          # Page de connexion
│   ├── app.html            # Application principale
│   ├── profile.html        # Page profil + config B2
│   ├── admin.html          # Panel admin
│   ├── css/
│   │   └── app.css         # Styles globaux
│   └── js/
│       └── app.js          # Logique frontend
├── data/
│   ├── users.json          # Base utilisateurs
│   ├── library.json        # Métadonnées vidéos
│   └── channels.json       # Chaînes suivies
├── avatars/                # Avatars utilisateurs
├── requirements.txt
├── B2_INTEGRATION.md      # Doc détaillée B2
└── README.md
```

### Workflow de téléchargement

1. User demande vidéo → WebSocket connect→ JWT verify
2. `yt-dlp` télécharge depuis YouTube → `/videos/` local
3. `B2Storage.authorize()` → connexion API B2
4. `B2Storage.get_upload_url()` → récupère upload URL
5. `B2Storage.upload_file()` → upload vidéo vers B2
6. Suppression fichier local → libération espace
7. Métadonnées stockées avec `file_id` B2

### Workflow de streaming

1. User clique "Play" → `GET /api/video/{id}/stream`
2. Vérification ownership → user peut accéder ?
3. `B2Storage.get_download_url()` → génère URL signée (1h)
4. Player HTML5 stream depuis B2 avec URL
5. URLs expirées après 1h (sécurité)

---

## 🔒 Sécurité

- 🔑 **JWT tokens** pour auth
- 🛡️ **Credentials B2** stockés localement (jamais exposés au client)
- ⏰ **URLs signées** avec expiration (1h par défaut)
- 👥 **Isolation utilisateurs** (chacun accède à son bucket uniquement)
- 🔐 **Buckets privés** recommandés

---

## ❓ FAQ

### Puis-je utiliser un autre provider que B2 ?

Pour l'instant, seul Backblaze B2 est supporté. Le support S3-compatible (AWS, Cloudflare R2, etc.) pourrait être ajouté plus tard.

### Que se passe-t-il si je supprime une vidéo ?

La vidéo est supprimée de B2 **ET** de la base locale. C'est définitif.

### Puis-je partager mes vidéos avec d'autres utilisateurs ?

Pas pour l'instant. Chaque utilisateur a accès **uniquement** à ses propres vidéos.

### Combien de stockage me faut-il ?

- Vidéo 480p : ~200-400 MB
- Vidéo 720p : ~500-800 MB
- Vidéo 1080p : ~1-2 GB

Le plan gratuit B2 (10 GB) = environ **20 vidéos 720p**.

### Puis-je désactiver B2 et utiliser du stockage local ?

Non, B2 est **obligatoire** dans cette version. Le stockage local est trop limité pour gérer beaucoup de vidéos.

---

## 🐛 Problèmes courants

### ❌ "B2 not configured"

➡️ Allez dans **Profile** et configurez vos credentials B2.

### ❌ "Authorization failed"

➡️ Vérifiez :
- Key ID correct
- Application Key correct
- Bucket existe et est accessible
- Permissions Read/Write sur la clé

### ❌ "Failed to upload video to B2"

➡️ Vérifiez :
- Quota B2 non dépassé
- Connexion internet stable
- Fichier pas trop volumineux (< 5 GB recommandé)

### ❌ "Cannot play video"

➡️ Causes possibles :
- URL expirée (après 1h) → Rafraîchissez la page
- Fichier supprimé de B2
- Credentials B2 invalides ou supprimés

---

## 🎉 Contribuer

Les contributions sont les bienvenues ! Ouvrez une issue ou une pull request sur GitHub.

---

## 📝 Licence

MIT License - Libre d'utilisation, modification et distribution.

---

## 👏 Crédits

- **Créé par** : [theo7791l](https://github.com/theo7791l)
- **Téléchargement** : [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- **Stockage** : [Backblaze B2](https://www.backblaze.com/b2/cloud-storage.html)
- **Framework** : [FastAPI](https://fastapi.tiangolo.com/)

---

## 🔗 Liens utiles

- [Documentation Backblaze B2](https://www.backblaze.com/b2/docs/)
- [Guide détaillé B2](./B2_INTEGRATION.md)
- [yt-dlp GitHub](https://github.com/yt-dlp/yt-dlp)
- [FastAPI Docs](https://fastapi.tiangolo.com/)

---

🌟 **Si ce projet vous plaît, donnez-lui une ⭐ sur GitHub !**
