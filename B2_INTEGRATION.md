# 🚀 Backblaze B2 Integration Guide

## 📌 Vue d'ensemble

YTArchive utilise maintenant **Backblaze B2** comme solution de stockage cloud pour les vidéos, permettant une capacité de stockage quasi-illimitée sans surcharger le serveur local.

### ✨ Fonctionnalités

- ☁️ **Stockage cloud** : Toutes les vidéos sont stockées sur Backblaze B2
- 🔒 **Multi-utilisateurs** : Chaque utilisateur a son propre bucket B2
- 📥 **Upload direct** : Les vidéos sont uploadées directement vers B2 après le téléchargement YouTube
- 🎬 **Streaming** : Lecture vidéo directement depuis B2 avec URLs signées
- 🗑️ **Suppression automatique** : Quand vous supprimez une vidéo, elle est aussi supprimée de B2

---

## 🔑 Configuration B2

### Étape 1 : Créer un compte Backblaze B2

1. Rendez-vous sur [backblaze.com/b2/sign-up.html](https://www.backblaze.com/b2/sign-up.html)
2. Créez votre compte (10 GB gratuits !)
3. Vérifiez votre email

### Étape 2 : Créer un bucket

1. Connectez-vous à votre dashboard B2
2. Cliquez sur **"Create a Bucket"**
3. Choisissez un nom unique (ex: `ytarchive-username`)
4. Sélectionnez **"Private"** pour la visibilité
5. Cliquez sur **"Create Bucket"**

### Étape 3 : Générer une Application Key

1. Allez dans **App Keys** dans le menu
2. Cliquez sur **"Add a New Application Key"**
3. Donnez-lui un nom (ex: `ytarchive-key`)
4. Sélectionnez votre bucket
5. Permissions : **Read and Write**
6. Cliquez sur **"Create New Key"**

⚠️ **IMPORTANT** : Notez immédiatement le `keyID` et l'`applicationKey` - ils ne seront plus affichés !

### Étape 4 : Configurer dans YTArchive

1. Connectez-vous à YTArchive
2. Allez dans votre profil (clic sur votre nom en haut à droite)
3. Section **"Backblaze B2 Storage"**
4. Entrez :
   - **Application Key ID** : Votre `keyID`
   - **Application Key** : Votre `applicationKey`
   - **Bucket Name** : Le nom de votre bucket
5. Cliquez sur **"Test & Save B2 Credentials"**

✅ Si tout est correct, vous verrez un badge vert **"Configured"** !

---

## 📦 Architecture Technique

### Fichiers principaux

```
ytarchive/
├── b2_storage.py          # Module de gestion Backblaze B2
├── auth.py                 # Authentification + stockage credentials B2
├── static/profile.html     # Interface de configuration B2
└── requirements.txt        # Dépendances (ajoute aiohttp)
```

### Workflow de téléchargement

```
Utilisateur demande vidéo
        ↓
   yt-dlp télécharge depuis YouTube
        ↓
   Stockage temporaire local
        ↓
   Upload vers Backblaze B2
        ↓
   Suppression fichier local
        ↓
   Métadonnées enregistrées (inclut file_id B2)
```

### Workflow de lecture

```
Utilisateur clique "Play"
        ↓
   Génération URL signée B2 (1h)
        ↓
   Player vidéo HTML5 stream depuis B2
        ↓
   Contrôles vitesse, qualité, etc.
```

---

## 💻 API Endpoints

### Configuration B2

#### `POST /api/auth/me/b2-credentials`
Configure les credentials B2 pour l'utilisateur actuel.

```json
{
  "key_id": "your_key_id",
  "application_key": "your_app_key",
  "bucket_name": "your-bucket"
}
```

**Response:**
```json
{
  "status": "success",
  "message": "B2 credentials configured successfully"
}
```

#### `DELETE /api/auth/me/b2-credentials`
Supprime les credentials B2.

#### `GET /api/auth/me`
Récupère le profil utilisateur (inclut `has_b2_configured`).

---

## 🛠️ Classe B2Storage

### Méthodes principales

```python
from b2_storage import B2Storage

# Initialisation
b2 = B2Storage(key_id, application_key, bucket_name)
await b2.authorize()

# Upload fichier
success, file_id = await b2.upload_file(
    file_path="/tmp/video.mp4",
    b2_filename="videos/username/video_id.mp4"
)

# Générer URL de téléchargement (signée)
url = await b2.get_download_url(
    b2_filename="videos/username/video_id.mp4",
    duration_seconds=3600  # 1 heure
)

# Supprimer fichier
await b2.delete_file(file_id, b2_filename)

# Lister fichiers
files = await b2.list_files(prefix="videos/username/")
```

---

## 📊 Coûts Backblaze B2

### Tarification (Mars 2026)

- **Stockage** : $0.005/GB/mois (~$5 pour 1TB/mois)
- **Téléchargement** : $0.01/GB (premier 3x gratuit)
- **Transactions API** : Gratuites (Class C)
- **Gratuit** : 10 GB de stockage + 1 GB/jour de téléchargement

### Estimation coûts

**Exemple : 100 vidéos de 500 MB**
- Stockage : 50 GB = **$0.25/mois**
- Visionnage : 10 GB/mois = **$0.10/mois** (après quota gratuit)
- **Total : ~$0.35/mois** 💸

---

## ❗ Problèmes courants

### ❌ "Authorization failed"

**Causes possibles :**
- Key ID ou Application Key incorrects
- Bucket n'existe pas
- Permissions insuffisantes sur la clé

**Solutions :**
1. Vérifiez que vous avez copié la clé correctement (pas d'espaces)
2. Vérifiez que le bucket existe et est actif
3. Générez une nouvelle clé avec permissions Read/Write

### ❌ "Upload failed"

**Causes possibles :**
- Quota dépassé
- Fichier trop volumineux
- Problème de connexion

**Solutions :**
1. Vérifiez votre quota B2
2. Essayez une qualité vidéo inférieure
3. Vérifiez votre connexion internet

### ❌ "Cannot play video"

**Causes possibles :**
- URL signée expirée (après 1h)
- Fichier supprimé de B2
- Credentials B2 supprimés

**Solutions :**
1. Rafraîchissez la page
2. Vérifiez que le fichier existe dans votre bucket B2
3. Reconfigurez vos credentials B2

---

## 🔒 Sécurité

### Stockage des credentials

- 🔑 Les credentials B2 sont stockés dans `data/users.json`
- ⚠️ **NE JAMAIS** commiter ce fichier sur Git
- 🛡️ Ajoutez `data/` au `.gitignore`

### URLs signées

- ⏰ Expiration : 1 heure par défaut
- 🔐 Accès temporaire uniquement
- 🎯 Scope limité au fichier demandé

### Bonnes pratiques

1. **Utilisez des buckets privés**
2. **Créez des clés dédiées** (pas de Master Application Key)
3. **Activez le versioning** pour la récupération
4. **Configurez lifecycle rules** pour nettoyer les vieux fichiers

---

## 🚀 Prochaines étapes

### Fonctionnalités à venir

- [ ] Upload avec barre de progression en temps réel
- [ ] Gestion multi-régions B2
- [ ] Statistiques d'utilisation B2 (stockage/bande passante)
- [ ] Migration automatique videos locales → B2
- [ ] Transcoding vidéo avant upload (compression)
- [ ] Backup automatique des métadonnées sur B2

---

## 👥 Support

**Documentation Backblaze B2 :**  
[https://www.backblaze.com/b2/docs/](https://www.backblaze.com/b2/docs/)

**API Reference :**  
[https://www.backblaze.com/b2/docs/b2_api.html](https://www.backblaze.com/b2/docs/b2_api.html)

**YTArchive GitHub :**  
[https://github.com/theo7791l/ytarchive](https://github.com/theo7791l/ytarchive)

---

🎉 **Félicitations !** Vous êtes maintenant prêt à utiliser YTArchive avec Backblaze B2 !
