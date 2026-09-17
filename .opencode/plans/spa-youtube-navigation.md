# Plan : Convertir en application monopage — Fix bouton YouTube

## Problème

Le bouton YouTube sur la page d'accueil (`streamlit_app.py`) utilise `<a href="/#/1_YouTube">` dans `st.html()`. Ce routeur HTML ne s'intègre pas à Streamlit → le clic ne fait rien.

## Solution : Application monopage (SPA)

Supprimer la structure multi-pages (`pages/`) et gérer la navigation via `st.session_state`.

## Étapes d'implémentation

### Étape 1 — Modifier `streamlit_app.py`

Ajouter la logique SPA au fichier d'entrée :

1. **Initialiser l'état de navigation** en haut du fichier :
   ```python
   if "current_page" not in st.session_state:
       st.session_state["current_page"] = "home"
   ```

2. **Créer des boutons de navigation fonctionnels** qui remplacent les `<a href>` cassés :
   - La carte YouTube → `st.session_state["current_page"] = "youtube"` + `st.rerun()`
   - La carte Sondages → `st.session_state["current_page"] = "sondages"` + `st.rerun()`

3. **Afficher conditionnellement la bonne vue** :
   ```python
   page = st.session_state["current_page"]
   if page == "home":
       render_homepage()
   elif page == "youtube":
       render_youtube_page()
   elif page == "sondages":
       render_sondages_page()
   ```

4. **Créer `render_homepage()`** — le contenu actuel de la fonction (title + cartes), sans le `@st.dialog` sondages. Ajouter un bouton "← Accueil" sur les pages secondaires.

5. **Créer `render_sondages_page()`** — le contenu de `pages/2_Sondages.py` déplacé ici.

6. **Gérer le `@st.dialog` sondages** — garder le decorator pour le mode dialogue, mais aussi supporter l'affichage inline via SPA.

### Étape 2 — Supprimer `pages/1_YouTube.py`

Ce fichier n'est plus nécessaire. Le code est dans `src/lucas_v2/ui/app.py` et sera appelé directement par `streamlit_app.py`.

### Étape 3 — Supprimer `pages/2_Sondages.py`

Le contenu sera intégré dans `streamlit_app.py`.

### Étape 4 — Vérifier `src/lucas_v2/ui/app.py`

Aucune modification nécessaire. `render_youtube_page()` fonctionne déjà de manière autonome. Vérifier juste qu'il n'y a pas de dépendance implicite au répertoire `pages/`.

## Fichiers modifiés

| Fichier | Action |
|---|---|
| `streamlit_app.py` | Réécriture partielle (ajout SPA) |
| `pages/1_YouTube.py` | Suppression |
| `pages/2_Sondages.py` | Suppression |
| `src/lucas_v2/ui/app.py` | Aucun changement |

## Test fonctionnel

1. `uv run streamlit run streamlit_app.py`
2. Page d'accueil affiche les cartes YouTube et Sondages
3. Clic sur carte YouTube → page de recherche YouTube s'affiche
4. Recherche fonctionne, pagination fonctionne
5. Bouton "← Accueil" retourne à l'accueil
6. Clic sur carte Sondages → message "Coming soon" s'affiche
7. Retour à l'accueil fonctionne depuis Sondages
