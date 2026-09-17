# Plan : Page d'accueil LUCAS avec navigation Multi-page

## Objectif

Créer une page d'accueil pour LUCAS avec deux boutons de navigation ("YouTube" et "Sondages") en utilisant la structure **Multi-page Streamlit** (fichiers dans `pages/`).

## Contexte technique

- **Framework** : Streamlit (Python)
- **Navigation actuelle** : Aucune page d'accueil, l'UI va directement à la recherche YouTube via `st.session_state`
- **Structure cible** : Multi-page Streamlit avec fichiers dans `pages/`

## Architecture Multi-page Streamlit

```
streamlit_app.py          → Page d'accueil (racine)
pages/
  1_YouTube.py            → Écran de recherche YouTube
  2_Sondages.py           → Écran Sondages (placeholder)
```

Chaque fichier dans `pages/` devient une page accessible via l'URL `/#/page_name`.

---

## Fichiers à modifier/créer

### 1. Modifier `streamlit_app.py` (page d'accueil)

**Objectif** : Transformer l'entrée en page d'accueil avec titre centré et boutons de navigation.

**Contenu** :
- Titre centré : "LUCAS — L'Usine de Collecte d'informations et d'Analyse Synthétique"
- Sous-titre : "🏛️ Veille politique automatisée — Échéance présidentielle 2027"
- Deux boutons côte à côte :
  - **YouTube** : avec image `Youtube_logo.png` (depuis `src/lucas_v2/ui/img/`), navigue vers `pages/1_YouTube.py`
  - **Sondages** : avec emoji 📋, navigue vers `pages/2_Sondages.py`

**Technique** :
- Utiliser `st.image()` pour le logo YouTube
- Utiliser `st.page_link()` pour la navigation multi-page
- Centrer le titre et les boutons avec `st.columns()` ou CSS inline

### 2. Créer `pages/1_YouTube.py` (écran de recherche)

**Objectif** : Déplacer la fonctionnalité de recherche YouTube existante dans cette page.

**Contenu** :
- Header : "LUCAS - Recherche YouTube"
- Barre de recherche + bouton "Rechercher"
- Liste de vidéos paginée (fonctionnalité existante)
- Détail de vidéo avec chunks (fonctionnalité existante)

**Technique** :
- Importer et réutiliser les fonctions existantes de `app.py` (`_inject_compact_style`, `_render_video_list`, `_render_video_detail`, etc.)
- Adapter `render_app()` → `render_youtube_page()` dans `app.py`
- Le header change : "LUCAS - Recherche YouTube" au lieu du header actuel

### 3. Créer `pages/2_Sondages.py` (placeholder)

**Objectif** : Page placeholder pour la fonctionnalité Sondages à venir.

**Contenu** :
- Header : "LUCAS - Sondages"
- Message : "📋 Bientôt disponible"
- Description contextuelle (optionnel)

### 4. Refactorer `src/lucas_v2/ui/app.py`

**Objectif** : Extraire la logique de recherche YouTube pour la rendre réutilisable depuis `pages/1_YouTube.py`.

**Modifications** :
- Renommer `render_app()` → `render_youtube_page()` (ou garder `render_app` et créer une fonction séparée)
- Créer `render_homepage()` pour la page d'accueil (dans `streamlit_app.py` directement)
- Garder toutes les fonctions helpers existantes (`_inject_compact_style`, `_render_header`, etc.)

---

## Détails d'implémentation

### `streamlit_app.py` (page d'accueil)

```python
import streamlit as st
from pathlib import Path

IMG_DIR = Path(__file__).parent / "src" / "lucas_v2" / "ui" / "img"

def render_homepage() -> None:
    # Titre centré
    st.markdown(
        "<h1 style='text-align:center;'>"
        "LUCAS — L'Usine de Collecte d'informations<br>et d'Analyse Synthétique"
        "</h1>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<p style='text-align:center;font-size:1.2em;'>"
        "🏛️ Veille politique automatisée — Échéance présidentielle 2027"
        "</p>",
        unsafe_allow_html=True,
    )

    # Deux colonnes pour les boutons
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        # Bouton YouTube avec logo
        col_yt, col_label = st.columns([1, 3])
        with col_yt:
            st.image(str(IMG_DIR / "Youtube_logo.png"), width=40)
        with col_label:
            st.page_link("pages/1_YouTube.py", label="YouTube", use_container_width=True)

        # Bouton Sondages avec emoji
        st.page_link("pages/2_Sondages.py", label="📋 Sondages", use_container_width=True)

render_homepage()
```

### `pages/1_YouTube.py`

```python
from lucas_v2.ui.app import render_youtube_page
render_youtube_page()
```

### `pages/2_Sondages.py`

```python
import streamlit as st

st.markdown(
    "<h1 style='text-align:center;'>LUCAS - Sondages</h1>",
    unsafe_allow_html=True,
)
st.info("📋 Bientôt disponible")
```

### Modifications dans `app.py`

- Ajouter une fonction `render_youtube_page()` qui effectue :
  1. Injection des styles compacts
  2. Affichage du header "LUCAS - Recherche YouTube"
  3. Barre de recherche
  4. Logique de navigation liste/détail

---

## Tests fonctionnels

1. **Page d'accueil** :
   - Vérifier que le titre est centré et affiché correctement
   - Vérifier que le sous-titre est affiché
   - Vérifier que les deux boutons sont visibles

2. **Navigation YouTube** :
   - Cliquer sur "YouTube" → accès à la page de recherche
   - Le header affiche "LUCAS - Recherche YouTube"
   - La recherche fonctionne (entrer un terme, voir les résultats)
   - La pagination fonctionne
   - Le clic sur une vidéo affiche le détail
   - Le bouton "← Retour à la liste" fonctionne

3. **Navigation Sondages** :
   - Cliquer sur "Sondages" → accès à la page placeholder
   - Le message "Bientôt disponible" s'affiche

4. **Navigation latérale Streamlit** :
   - Le sidebar affiche les pages disponibles
   - La navigation entre pages fonctionne

5. **Vérification pyright** :
   - Aucune erreur de type
   - Toutes les fonctions correctement typées

---

## Contraintes respectées

- ✅ Strong typing (pyright)
- ✅ Cognitive complexity ≤ 15
- ✅ Pas de modification de structure de BDD
- ✅ Utilisation de `uv`
- ✅ Logo YouTube depuis le dossier `img/` existant
- ✅ Emoji 📋 pour Sondages (pas de fichier image nécessaire)

---

## Ordre d'implémentation

1. Refactorer `app.py` : extraire `render_youtube_page()` depuis `render_app()`
2. Créer `pages/` directory
3. Créer `pages/1_YouTube.py`
4. Créer `pages/2_Sondages.py`
5. Modifier `streamlit_app.py` pour devenir la page d'accueil
6. Exécuter pyright et corriger les erreurs de type
7. Tester manuellement dans le navigateur
