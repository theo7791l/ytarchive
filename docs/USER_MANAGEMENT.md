# 👥 Système de Gestion des Utilisateurs - YTArchive

## 🎯 Vue d'ensemble

YTArchive v2.0 intègre un système complet de gestion multi-utilisateurs avec :
- **Rôles** : Admin et Membre
- **Authentification JWT** sécurisée
- **Profils utilisateurs** avec avatars
- **Panel d'administration** pour gérer les comptes
- **Upload d'avatars** (images jusqu'à 2MB)

---

## 🚀 Démarrage rapide

### Premier lancement

Après avoir démarré l'application, un compte admin par défaut est créé automatiquement :

```
Username: admin
Password: admin
```

⚠️ **IMPORTANT** : Changez ce mot de passe immédiatement après la première connexion !

### Changer le mot de passe par défaut

1. Connectez-vous avec `admin` / `admin`
2. Accédez à votre profil : `/profile`
3. Section "Changer le mot de passe"
4. Entrez l'ancien mot de passe (`admin`) et un nouveau mot de passe sécurisé

---

## 📊 Structure des rôles

### 🔴 Admin
- **Accès complet** à toutes les fonctionnalités
- **Panel d'administration** (`/admin`)
- Peut créer/modifier/supprimer des utilisateurs
- Peut promouvoir des membres en admin
- Accès aux statistiques globales

### 🟢 Membre
- **Accès standard** à l'application
- Peut télécharger des vidéos
- Peut gérer sa library personnelle
- Peut modifier son propre profil
- **Pas d'accès** au panel admin

---

## 💻 Endpoints API

### 🔐 Authentification

#### `POST /api/auth/login`
Connexion utilisateur

**Request:**
```json
{
  "username": "admin",
  "password": "monmotdepasse"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

---

### 👤 Profil utilisateur

#### `GET /api/auth/me`
Récupérer le profil de l'utilisateur connecté

**Headers:**
```
Authorization: Bearer <token>
```

**Response:**
```json
{
  "username": "admin",
  "email": "admin@example.com",
  "display_name": "Administrator",
  "role": "admin",
  "avatar": "admin_abc123.jpg",
  "created_at": "2026-03-04T16:00:00",
  "last_login": "2026-03-04T17:30:00"
}
```

#### `PUT /api/auth/me`
Mettre à jour son profil

**Request:**
```json
{
  "email": "newemail@example.com",
  "display_name": "Mon Nouveau Nom"
}
```

#### `POST /api/auth/me/avatar`
Upload d'avatar

**Request:** `multipart/form-data`
- `file`: Image (JPEG, PNG, max 2MB)

**Response:**
```json
{
  "avatar": "username_abc123.jpg"
}
```

#### `DELETE /api/auth/me/avatar`
Supprimer son avatar

#### `POST /api/auth/me/change-password`
Changer son mot de passe

**Request:**
```json
{
  "old_password": "ancienmdp",
  "new_password": "nouveaumdp"
}
```

---

### ⚙️ Routes Admin (réservé aux admins)

#### `GET /api/auth/admin/users`
Liste tous les utilisateurs

**Response:**
```json
[
  {
    "username": "admin",
    "email": "admin@example.com",
    "display_name": "Administrator",
    "role": "admin",
    "avatar": "admin_abc.jpg",
    "created_at": "2026-03-04T16:00:00",
    "last_login": "2026-03-04T17:30:00"
  },
  {
    "username": "john",
    "email": "john@example.com",
    "display_name": "John Doe",
    "role": "member",
    "avatar": null,
    "created_at": "2026-03-04T16:15:00",
    "last_login": null
  }
]
```

#### `POST /api/auth/admin/users`
Créer un nouvel utilisateur

**Request:**
```json
{
  "username": "newuser",
  "password": "securepassword123",
  "email": "user@example.com",
  "display_name": "New User",
  "role": "member"
}
```

#### `GET /api/auth/admin/users/{username}`
Détails d'un utilisateur spécifique

#### `PUT /api/auth/admin/users/{username}`
Modifier un utilisateur

**Request:**
```json
{
  "email": "newemail@example.com",
  "display_name": "Nouveau Nom",
  "role": "admin"
}
```

#### `DELETE /api/auth/admin/users/{username}`
Supprimer un utilisateur

⚠️ **Note** : Un admin ne peut pas se supprimer lui-même.

#### `POST /api/auth/admin/users/{username}/reset-password`
Réinitialiser le mot de passe d'un utilisateur

**Request:**
```json
{
  "new_password": "nouveaumotdepasse123"
}
```

---

## 🎨 Interface utilisateur

### Pages disponibles

#### `/` - Page de connexion
- Authentification par nom d'utilisateur et mot de passe
- Stockage du token JWT dans localStorage

#### `/app` - Application principale
- Library de vidéos
- Téléchargement de vidéos
- Gestion des channels
- Accessible à tous les utilisateurs connectés

#### `/profile` - Profil utilisateur
- 📷 Upload/suppression d'avatar
- ✏️ Modification du nom d'affichage et email
- 🔒 Changement de mot de passe
- 🎯 Badge de rôle

#### `/admin` - Panel d'administration
- 📊 Tableau de tous les utilisateurs
- ➕ Création de nouveaux comptes
- ✏️ Modification des utilisateurs
- 🗑️ Suppression de comptes
- 🔄 Changement de rôles (membre ↔ admin)
- **Accès réservé aux admins**

---

## 💾 Base de données

### Structure du fichier `data/users.json`

```json
{
  "admin": {
    "password_hash": "$2b$12$...",
    "role": "admin",
    "email": "admin@example.com",
    "display_name": "Administrator",
    "avatar": "admin_abc123.jpg",
    "created_at": "2026-03-04T16:00:00",
    "last_login": "2026-03-04T17:30:00"
  },
  "john": {
    "password_hash": "$2b$12$...",
    "role": "member",
    "email": "john@example.com",
    "display_name": "John Doe",
    "avatar": null,
    "created_at": "2026-03-04T16:15:00",
    "last_login": null
  }
}
```

### Stockage des avatars

- **Répertoire** : `avatars/`
- **Format** : `{username}_{uuid}.{ext}`
- **Taille max** : 2 MB
- **Types acceptés** : JPEG, PNG, GIF, WebP

---

## 🔒 Sécurité

### Hachage des mots de passe
- Algorithme : **bcrypt** avec salt automatique
- Coût : 12 rounds (par défaut de passlib)

### Tokens JWT
- **Algorithme** : HS256
- **Durée de vie** : 30 jours
- **Secret** : Configurable via `JWT_SECRET` (env var)
- **Contenu** :
  ```json
  {
    "sub": "username",
    "role": "admin",
    "exp": 1234567890
  }
  ```

### Protection des routes
- Routes `/api/auth/admin/*` : **Admin uniquement**
- Routes `/api/auth/me/*` : **Utilisateur connecté**
- Toutes les autres routes API : **Authentification requise**

---

## 🛠️ Configuration

### Variables d'environnement

```bash
# Secret pour JWT (IMPORTANT : changez en production !)
export JWT_SECRET="votre-secret-super-securise-ici"

# Port de l'application
export PORT=30172
```

### Recommandations production

1. **Changez le JWT_SECRET** par une clé aléatoire longue :
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

2. **Utilisez HTTPS** en production pour protéger les tokens

3. **Sauvegardez régulièrement** :
   - `data/users.json`
   - `avatars/`

4. **Politique de mots de passe** :
   - Minimum 6 caractères (configurable dans `auth.py`)
   - Recommandation : 12+ caractères avec majuscules, chiffres, symboles

---

## 📝 Cas d'usage

### Créer un nouveau membre

1. En tant qu'admin, accédez à `/admin`
2. Cliquez sur "➕ Créer un utilisateur"
3. Remplissez les informations :
   - Nom d'utilisateur (unique, requis)
   - Mot de passe (requis à la création)
   - Email (optionnel)
   - Nom d'affichage (optionnel)
   - Rôle : **Membre**
4. Cliquez sur "Créer"

### Promouvoir un membre en admin

1. Allez dans `/admin`
2. Trouvez l'utilisateur dans le tableau
3. Cliquez sur "✏️" (modifier)
4. Changez le rôle de "Membre" à "Admin"
5. Sauvegardez

### Réinitialiser un mot de passe oublié

**Méthode 1 (via admin panel)** :
1. Connectez-vous en tant qu'admin
2. `/admin` → Modifier l'utilisateur
3. Le mot de passe peut être changé sans connaître l'ancien

**Méthode 2 (via API)** :
```bash
curl -X POST http://localhost:30172/api/auth/admin/users/username/reset-password \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"new_password": "nouveaumdp123"}'
```

---

## 🐛 Dépannage

### Erreur : "Access denied. You must be admin"
**Problème** : Tentative d'accès à une route admin avec un compte membre.

**Solution** : Demandez à un admin de vous promouvoir.

### Erreur : "Invalid token" ou "Token expired"
**Problème** : Token JWT expiré ou invalide.

**Solution** : Reconnectez-vous.

### Avatar ne s'affiche pas
**Vérifiez** :
1. Le fichier existe dans `avatars/`
2. Les permissions de lecture sont correctes
3. Le chemin `/avatars/` est bien monté dans FastAPI

### Impossible de supprimer un utilisateur
**Cause** : Un admin ne peut pas se supprimer lui-même.

**Solution** : Demandez à un autre admin de le faire.

---

## 📚 Références

### Fichiers clés
- `auth.py` - Logique d'authentification et gestion utilisateurs
- `main.py` - Routes principales et intégration
- `static/admin.html` - Panel d'administration
- `static/profile.html` - Page de profil utilisateur
- `data/users.json` - Base de données utilisateurs
- `avatars/` - Stockage des photos de profil

### Technologies utilisées
- **FastAPI** - Framework web
- **Passlib** - Hachage des mots de passe (bcrypt)
- **PyJWT** - Génération et validation des tokens
- **Pydantic** - Validation des données

---

## ✨ Fonctionnalités futures

- [ ] Système de permissions granulaires
- [ ] Récupération de mot de passe par email
- [ ] Authentification 2FA
- [ ] Logs d'audit des actions admin
- [ ] Quotas de stockage par utilisateur
- [ ] Partage de vidéos entre utilisateurs
- [ ] API keys pour intégrations externes

---

🎉 **YTArchive v2.0** - Gestion multi-utilisateurs complète !
