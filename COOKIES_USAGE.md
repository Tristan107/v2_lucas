# Cookies YouTube — mode d'emploi (anti-429 yt-dlp)

## Principe

L'ingestion yt-dlp peut être freinée par des HTTP 429. Pour réduire ce risque,
on s'authentifie avec un **compte YouTube secondaire** (jamais le principal)
via un fichier `cookies.txt` passé à yt-dlp (`cookiefile`).

Le fichier est un **instantané statique** : une fois exporté, il ne dépend
plus du navigateur. yt-dlp le relit à chaque vidéo.

## Installation

1. Installer l'extension « Get cookies.txt LOCALLY ».
2. Se connecter à YouTube avec le **compte secondaire**.
3. Exporter les cookies de `youtube.com` (format Netscape).
4. Sauvegarder hors repo : `~/.config/lucas/cookies.txt`.
5. Protéger : `chmod 600 ~/.config/lucas/cookies.txt`.
6. Déclarer dans `.env` (chemin absolu, pas de `~`) :

```
YOUTUBE_COOKIES_FILE=/home/tristan/.config/lucas/cookies.txt
```

Sans cette variable (ou chemin invalide), l'ingest tourne en **mode anonyme**
avec un warning — pas d'échec dur.

## Vérifier que c'est pris en compte

```bash
uv run python -c "
from dotenv import load_dotenv
load_dotenv()
from lucas_v2.ingest.subs import get_cookie_file, base_opts
print('cookie file:', get_cookie_file())
print('cookiefile' in base_opts('/tmp/x'))
"
```

Test réel (passe par la CLI, qui charge `.env`) :

```bash
uv run lucas-v2 ingest -c channels.yaml --url "https://www.youtube.com/watch?v=VIDEO_ID" 2>&1 | grep -i -E "cookie|anonyme|429"
```

`Cookies YouTube chargés depuis ...` → actif. `mode anonyme` → inactif.

## Après l'export : ce qu'on peut / ne peut pas faire

| Action | Risque |
|---|---|
| Fermer l'onglet / le navigateur | ✅ Aucun |
| Changer de compte (sélecteur, sans déconnexion) | ✅ Aucun |
| Cliquer **« Se déconnecter »** | ⚠️ À éviter : peut invalider la session côté Google et tuer les cookies exportés |
| Changer le mot de passe du compte secondaire | ❌ Révoque la session → ré-exporter |
| « Se déconnecter de tous les appareils » | ❌ Révoque la session → ré-exporter |

Recommandé : laisser le compte secondaire connecté (profil navigateur
séparé idéalement, rouvert uniquement pour les ré-exports).

## Durée de vie et renouvellement

Les cookies expirent naturellement (typiquement quelques mois) sans prévenir.
Symptôme : retour des **429 persistants**, avec le message
« Si cookies configurés, vérifier leur validité (ré-exporter) ».

Renouvellement : se reconnecter avec le compte secondaire → ré-exporter →
écraser `~/.config/lucas/cookies.txt` → `chmod 600`. `.env` inchangé.
Noter la date d'export pour anticiper (rappel ~3–6 mois).
