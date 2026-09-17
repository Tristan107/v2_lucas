# Plan — IHM Streamlit recherche FTS `transcript_chunk_fts`

## 1. Goal

Ajouter une IHM Streamlit permettant de rechercher un ou plusieurs mots dans les vidéos ingérées, via l'index FTS5 existant.

Exigences validées :
- Champ libre acceptant `travail*`, `immigr* travail*`. `MATCH` + `AND` explicite entre expressions séparées par espaces.
- Écran unique : liste de vidéos dont ≥1 chunk matche. Chaque vidéo = **panneau collapsible fermé par défaut, lazy-loadé** (requête chunks seulement à l'ouverture, sous la vidéo).
- Label vidéo : `channel.owner, channel.orientation, video.upload_date, video.title` + suffixe **` (X mentions)`** à droite du titre. Tri : **plus récent d'abord** (`upload_date DESC`). Miniature : hors scope (pas scrappée).
- Panneau ouvert : chunks matchés avec `snippet(transcript_chunk_fts, 0, '**', '**', '…', 12)`, **gras** natif Streamlit. Au début de chaque chunk : timestamp `start_s` format `hh:mm:ss` (`02:34:20`) **cliquable → lien externe nouvel onglet** `https://www.youtube.com/watch?v=<id>&t=<start_s>`.
- Chunks : **ordre chronologique (`seq_no`), 10 premiers + bouton "Voir plus" (+10)**.
- Séparation stricte : logique UI dans **`src/lucas_v2/ui/`**, ingestion inchangée. **Déployable Streamlit Cloud facilement**.

## 2. Findings (analyse codebase)

- `src/lucas_v2/schema.sql` : `video(id, fk_channel_id, youtube_str_id UNIQUE, title, upload_date, duration_s, ...)`, `channel(channel_url UNIQUE, channel_id, title, orientation, owner)`, `transcript_chunk(id, fk_video_id, seq_no, start_s INTEGER, end_s, text, tokens)`, `transcript_chunk_fts(text, tokenize="unicode61 remove_diacritics 2")` + 3 triggers sync. Aucune migration nécessaire.
- `src/lucas_v2/db.py:70-92` : `search_chunks(conn, query, limit)` fait déjà `MATCH ? ORDER BY bm25` + `snippet(..., '<b>','</b>','…',12)` + `JOIN video`. Pattern à réutiliser pour 2 nouvelles requêtes groupées/filtrées.
- `README.md § Exemple` : lien profond = `watch?v=<id>&t=<start_s>`.
- `pyproject.toml` : pas de `streamlit`. `python>=3.11`, `typeCheckingMode=strict`, `extraPaths=["src"]`.

## 3. Spec technique

### 3.1 Fichiers

| Fichier | Action |
|---|---|
| `src/lucas_v2/ui/__init__.py` | Créer (vide typé). |
| `src/lucas_v2/ui/query.py` | Créer : helpers purs, 0 import Streamlit/DB. |
| `src/lucas_v2/ui/db_search.py` | Créer : 2 requêtes + count, typage strict. |
| `src/lucas_v2/ui/app.py` | Créer : seul fichier Streamlit, fonction `render_app()`. |
| `streamlit_app.py` (racine) | Créer : 5 lignes max, `from lucas_v2.ui.app import render_app; render_app()`. |
| `pyproject.toml` | Modifier : ajouter `streamlit>=1.35`. |
| `tests/test_search_query.py` | Créer : tests purs. |
| `tests/test_search_db.py` | Créer : tests SQLite `:memory:` + `init_schema`. |

### 3.2 `ui/query.py`

```python
def build_match_query(raw: str) -> str:
    """'immigr*  travail*' -> 'immigr* AND travail*'. ValueError si vide."""
def format_hhmmss(total_s: int) -> str:
    """9260 -> '02:34:20'."""
def youtube_url(youtube_str_id: str, start_s: int) -> str:
    """'https://www.youtube.com/watch?v=<id>&t=<start_s>'."""
```

### 3.3 `ui/db_search.py`

Types :
```python
@dataclass(frozen=True, slots=True)
class VideoHit: youtube_str_id: str; title: str | None; upload_date: str | None; owner: str | None; orientation: str | None; mentions: int
@dataclass(frozen=True, slots=True)
class ChunkHit: seq_no: int; start_s: int; end_s: int; snippet: str; youtube_str_id: str
```

SQL 1 — vidéos (tri récent) :
```sql
SELECT v.youtube_str_id, v.title, v.upload_date, c.owner, c.orientation, COUNT(*) AS mentions
FROM transcript_chunk_fts f
JOIN transcript_chunk tc ON tc.id = f.rowid
JOIN video v ON v.id = tc.fk_video_id
LEFT JOIN channel c ON c.id = v.fk_channel_id
WHERE transcript_chunk_fts MATCH ?
GROUP BY v.id
ORDER BY v.upload_date DESC, v.id DESC
LIMIT 100
```

SQL 2 — chunks d'une vidéo (chrono + pagination) :
```sql
SELECT tc.seq_no, tc.start_s, tc.end_s,
       snippet(transcript_chunk_fts, 0, '**', '**', '…', 12) AS snippet,
       v.youtube_str_id
FROM transcript_chunk_fts f
JOIN transcript_chunk tc ON tc.id = f.rowid
JOIN video v ON v.id = tc.fk_video_id
WHERE transcript_chunk_fts MATCH ? AND v.youtube_str_id = ?
ORDER BY tc.seq_no ASC
LIMIT ? OFFSET ?
```

SQL 3 — count total : même WHERE avec `COUNT(*)`.

### 3.4 `ui/app.py`

- `_get_conn()` : `@st.cache_resource`, load_dotenv + fallback `st.secrets`.
- `render_app()` : `st.title`, `st.text_input`, `st.button("Rechercher")`.
- Pour chaque vidéo : `st.expander(label, expanded=False)` avec label `date • owner [orientation] • title (X mentions)`.
- Dans l'expander : requête chunks lazy, 10 premiers, `st.columns([1,5])` pour timestamp + snippet.
- `st.link_button(hh:mm:ss, url)` pour chaque chunk.
- "Voir plus (+10)" avec `st.session_state` pour pagination.

### 3.5 Contraintes

- Typage strict, `pyright` zéro warning/erreur.
- Complexité cognitive ≤15 par fonction.
- Pas de changement schéma.

## 4. Tests

- `build_match_query` : 1 terme, 2 termes → AND, espaces multiples, vide → ValueError.
- `format_hhmmss` : 0, 95, 9260.
- `youtube_url` : vérifie format.
- `search_videos` : tri date DESC + mentions correct.
- `search_video_chunks` : ordre seq_no, LIMIT/OFFSET, snippet contient `**`.

## 5. Critères d'acceptation

- AND entre espaces.
- Liste tri récent avec `(X mentions)`.
- Expander lazy sous la vidéo.
- Snippet `**` en gras (native Streamlit).
- Timestamp `hh:mm:ss` → nouvel onglet au bon `start_s`.
- Voir plus +10.
- `src/lucas_v2/ui/` isolé.
- Cloud OK via `streamlit_app.py` + secrets.

## 6. Étapes build

1. Ajouter `streamlit` à `pyproject`, `uv sync`.
2. Créer `ui/query.py` + tests purs, `pyright`.
3. Créer `ui/db_search.py` + tests `:memory:`, `pyright`.
4. Créer `ui/app.py` + `streamlit_app.py` + `secrets example`.
5. Recette manuelle complète + `uv run pytest -v` + `pyright`.
