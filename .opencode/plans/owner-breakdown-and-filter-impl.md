# Implémentation : Breakdowns Orientation + Chaîne/Candidat + Filtrage

## Résumé
Deux breakdowns côte à côte : répartition par orientation et répartition par chaîne/candidat. Filtres selectbox et chips pour supprimer les filtres actifs. 1 chaîne = 1 candidat (pas many-to-many).

## Décisions de design

| Décision | Choix |
|----------|-------|
| Nombre de breakdowns | 2 : orientation + chaîne/candidat |
| Couleurs barres chaîne/candidat | Couleur de l'orientation du canal (ORIENTATION_COLORS) |
| NULL titles/owners | Regrouper sous "non classé" / "inconnu" |
| Selectbox | "Toutes" en premier, valeur None = pas de filtre |
| Chips HTML | Chips HTML pour affichage + st.button() Streamlit pour l'action |
| Schema DB | Inchange - ne pas toucher a _seed() ni au schema |
| Count | Reflete les filtres actifs |
| Filtrage combine | AND (intersection) quand les deux filtres sont actifs |

## Layout cote a cote

```
+---------------------------+---------------------------+
|  Repartition par          |  Repartition par          |
|  orientation              |  chaine/candidat          |
|                           |                           |
|  Gauche     12/20  60%   |  Melanchon    8/15  53%   |
|  Droite      5/12  42%   |  Macron       6/18  33%   |
|  Centre      3/8   38%   |  Le Pen       4/10  40%   |
|                           |                           |
|  [Selectbox: Toutes v]    |  [Selectbox: Toutes v]    |
+---------------------------+---------------------------+
 [Chaine: Melanchon x]        <- chips filtres actifs
```

## Fichiers a modifier

### 1. src/lucas_v2/ui/db_search.py

**Ajouts :**

- Dataclass ChannelStats :
  - channel_title: str | None
  - orientation: str | None  (pour la couleur)
  - matched: int
  - total: int

- search_chunks_by_channel(conn, match_query) :
  - Meme logique que search_chunks_by_orientation mais groupe par c.title
  - Selectionne aussi c.orientation pour la couleur
  - Retourne list[ChannelStats] triee par matched/total ratio descendant
  - NULL title → regroupe sous "non classe"

**Modifications :**

- search_videos(conn, match_query, limit, offset, channel_filter=None, owner_filter=None) :
  - Construire la clause WHERE dynamiquement
  - channel_filter → AND c.title = ?
  - owner_filter → AND c.owner = ?
  - Construire le tuple params dynamiquement

- count_videos(conn, match_query, channel_filter=None, owner_filter=None) :
  - Meme logique dynamique que search_videos

### 2. src/lucas_v2/ui/app.py

**Ajouts :**

- Session state dans _sync_search_state :
  - st.session_state["channel_filter"] = None
  - st.session_state["owner_filter"] = None

- _render_channel_breakdown(conn, match_query) :
  - Appelle search_chunks_by_channel()
  - Barres horizontales avec couleur = ORIENTATION_COLORS[channel.orientation]
  - Label = channel_title (ou "non classe" si NULL)
  - Texte : matched/total XX.X%
  - st.selectbox en dessous avec options : ["Toutes"] + tous les titres de chaines
  - Selection → met a jour session_state["channel_filter"]

- _render_active_filters() :
  - Verifie channel_filter et owner_filter dans session state
  - Si actifs, affiche des chips HTML : Chaine: X x / Candidat: Y x
  - Bouton st.button("x") a cote de chaque chip pour clear
  - Bouton "Effacer tous" si au moins un filtre actif

**Modifications :**

- _render_video_list() :
  - Garder _render_orientation_breakdown dans la colonne 1
  - Ajouter _render_channel_breakdown dans la colonne 2
  - Layout : col_orient, col_channel = st.columns(2)
  - Passer channel_filter et owner_filter a search_videos() et count_videos()
  - Afficher _render_active_filters() entre les breakdowns et la liste

- Imports : ajouter ChannelStats, search_chunks_by_channel

### 3. tests/test_search_db.py

**Note :** Pas de OwnerStats separe. 1 chaine = 1 candidat. La fonction search_chunks_by_owner() n'est pas necessaire : on utilise search_chunks_by_channel() pour le breakdown, et le filtre owner_filter sur search_videos() pour filtrer par owner.

**Ajouts :**

- Imports des nouvelles fonctions/dataclasses
- Donnees de test : creer 2 channels avec owners et orientations differents directement dans les tests (pas de modification de _seed())

**Tests :**

- test_search_chunks_by_channel_single : 1 channel, verify matched/total
- test_search_chunks_by_channel_multi : 2 channels, verify both appear sorted by ratio
- test_search_chunks_by_channel_empty : non-existent query → []
- test_search_chunks_by_channel_null_title : channel avec title=NULL → "non classe"
- test_search_videos_with_channel_filter : filtre par title → seules les videos matching retournees
- test_search_videos_with_owner_filter : filtre par owner → filtering
- test_search_videos_with_both_filters : AND combine
- test_count_videos_with_filters : count reflete les filtres

## Etapes d'implementation

1. Ajouter ChannelStats dans db_search.py (avec champ orientation)
2. Implementer search_chunks_by_channel()
3. Modifier search_videos() et count_videos() pour accepter les filtres
4. Ajouter session state filters dans _sync_search_state (app.py)
5. Implementer _render_channel_breakdown() (app.py)
6. Implementer _render_active_filters() (app.py)
7. Modifier _render_video_list() avec layout 2 colonnes + filtres
8. Ajouter les tests dans test_search_db.py
9. Verifier : uv run pytest tests/ -v + uv run pyright

## Validation fonctionnelle

1. uv run streamlit run streamlit_app.py
2. Rechercher un terme → verification des deux breakdowns cote a cote
3. Selectionner une chaine → filtre appliqué + chip affiche
4. Selectionner un candidat → filtre AND combine
5. Cliquer "x Effacer" → filtre supprime
6. Changer la requete → filtres reset automatiquement
