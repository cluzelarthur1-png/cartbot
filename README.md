# 🎫 Cart Claim Bot

Bot Discord qui relaie les carts de KalysBot avec un système de tickets.

---

## ⚙️ Configuration rapide

### 1. Crée ton bot Discord

1. Va sur https://discord.com/developers/applications
2. **New Application** → donne un nom
3. Onglet **Bot** → clique **Add Bot**
4. Copie le **Token** (tu en auras besoin)
5. Active ces **Privileged Intents** :
   - ✅ Server Members Intent
   - ✅ Message Content Intent
6. Onglet **OAuth2 > URL Generator** :
   - Scopes : `bot` + `applications.commands`
   - Bot Permissions : `Manage Channels`, `Send Messages`, `Read Messages`, `View Channels`, `Manage Roles`
   - Copie le lien et invite le bot sur ton serveur

---

### 2. Prépare ton serveur Discord

Crée ces salons/catégories si pas déjà existants :
- Salon texte : `#carts` (où KalysBot poste)
- Salon texte : `#claims` (où le bot repostera)
- Catégorie : `tickets` (pour les tickets créés)
- Rôle : `Admin` (pour les permissions)

---

### 3. Lance le bot

#### Option A — En local / VPS

```bash
# Installe les dépendances
pip install -r requirements.txt

# Lance avec ton token
DISCORD_TOKEN=ton_token_ici python bot.py
```

#### Option B — Railway (hébergement gratuit recommandé)

1. Va sur https://railway.app et connecte ton GitHub
2. Upload les fichiers `bot.py` et `requirements.txt`
3. Dans **Variables**, ajoute :
   ```
   DISCORD_TOKEN = ton_token_ici
   ```
4. Deploy !

#### Option C — Fichier .env en local

Crée un fichier `.env` :
```
DISCORD_TOKEN=ton_token_ici
```

Et installe python-dotenv :
```bash
pip install python-dotenv
```

Ajoute en haut de `bot.py` :
```python
from dotenv import load_dotenv
load_dotenv()
```

---

## 🔧 Personnaliser

Dans `bot.py`, modifie les constantes en haut du fichier :

```python
CART_CHANNEL_NAME    = "carts"      # salon KalysBot
CLAIM_CHANNEL_NAME   = "claims"     # salon de claim
TICKET_CATEGORY_NAME = "tickets"    # catégorie tickets
KALYSBOT_NAME        = "KalysBot"   # nom exact du bot
ADMIN_ROLE_NAME      = "Admin"      # nom du rôle admin
```

---

## 🎮 Commandes disponibles

| Commande | Description | Permission |
|---|---|---|
| `/setmessage <texte>` | Change le message custom sur les carts | Admin |
| `/viewmessage` | Affiche le message actuel | Tout le monde |

---

## 📋 Fonctionnement

```
KalysBot poste dans #carts
        ↓
Ton bot détecte l'embed "Cart Ready!"
        ↓
Parse : site, event, catégorie, places, rangée, prix, date
        ↓
Poste dans #claims avec bouton "🎫 Claim Cart"
        ↓
Quelqu'un clique → ticket privé créé
(user + admins seulement)
        ↓
Bouton "🔒 Fermer le ticket" dans le ticket
```
