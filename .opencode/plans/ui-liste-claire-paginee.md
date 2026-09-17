# Plan — Liste claire paginée + vue détail chunks

## 1. Goal
- Thème clair + header LUCAS identique à `../lucas` (palette d'origine).
- Écran liste : vidéos à plat, sans expander, paginées par 10 en lazy (LIMIT/OFFSET), date `jj/mm/aaaa`.
- Écran détail plein écran : rappel vidéo + chunks paginés 10/page, snippet FTS 15 tokens (au lieu de 12).

## 2. Findings
- `src/lucas_v2/ui/app.py` : `search_videos(limit=100)` + `st.expander` + chunks inline 10 + `Voir plus`.
- `src/lucas_v2/ui/db_search.py` : `search_videos`, `search_video_chunks` (snippet 12), `count_video_chunks`.
- `../lucas/app.py:21-27` : header HTML coloré + caption. `.streamlit/config.toml` : thème clair.
- `upload_date` : texte `YYYYMMDD` (ex `20250615`).

## 3. Spec technique

### 3.1 `.streamlit/config.toml` (créer)
```toml
[server]
headless = true
port = 8501
address = "0.0.0.0"
[theme]
primaryColor = "#E63946"
backgroundColor = "#FFFFFF"
secondaryBackgroundColor = "#F8F9FA"
textColor = "#264653"
font = "sans serif"
```

### 3.2 `ui/query.py` (+ tests)
```python
def format_date_fr(upload_date: str | None) -> str:
    """'20250615' -> '15/06/2025'. None/invalide -> ''."""
```
Règles : `None`/`""` → `""` ; 8 chiffres → `dd/mm/aaaa` via slicing ; sinon retour brut. Complexité ≤5.

### 3.3 `ui/db_search.py`
- `SNIPPET_TOKENS: Final = 15`
- `search_videos(conn, match_query, limit=10, offset=0)` : même SELECT/GROUP/ORDER + `LIMIT ? OFFSET ?`.
- `count_videos(conn, match_query) -> int` :
```sql
SELECT COUNT(*) FROM (
  SELECT v.id FROM transcript_chunk_fts f
  JOIN transcript_chunk tc ON tc.id = f.rowid
  JOIN video v ON v.id = tc.fk_video_id
  WHERE transcript_chunk_fts MATCH ? GROUP BY v.id)
```
- `search_video_chunks` : `snippet(..., '**','**','…', 15)`, signature inchangée (limit=10, offset=0).
- `count_video_chunks` : inchangé.

### 3.4 `ui/app.py` (rewrite, complexité ≤15/fonction)
- Constantes `VIDEOS_PER_PAGE=10`, `CHUNKS_PER_PAGE=10`.
- Header : markdown HTML LUCAS + caption (copie `../lucas`).
- Session : `last_match_query`, `video_page`, `selected_video_id: str|None`, `chunk_page`.
- `render_app()` : routeur liste/détail + reset d'état si `match_query` change (purge `chunk_page`, `video_page=0`, `selected_video_id=None`).
- `_render_video_list` : `count_videos` → pages → `search_videos(page)` → carte `### titre (X)` + meta `date FR • owner • [orientation]` + `st.button("Voir les extraits (X)")` → set detail + rerun ; `divider` ; pagination `Précédent/Suivant` disabled aux bornes.
- `_render_video_detail` : `← Retour`, fiche (titre, meta, lien YouTube search), `count_video_chunks` + `search_video_chunks(page)`, `columns([1,5])` timestamp `link_button` + snippet, pagination chunks.
- Zéro `st.expander`, zéro `Voir plus`.

## 4. Tests
- `format_date_fr` : valide, None, vide, invalide.
- `count_videos` : 2 vidéos pour "travail", 0 pour inexistant.
- `search_videos` pagination : limit=1 offset=0 → vid récente ; offset=1 → ancienne ; total cohérent avec count.
- `search_video_chunks` : snippet contient `**`, ordre seq_no.
- `pytest` + `pyright` strict verts.

## 5. Critères d'acceptation
Fond clair, header identique v1, dates FR, pas d'expander, liste 10/page lazy, détail plein écran avec rappel + chunks 10/page, snippet 15, Prev/Next + Retour fonctionnels.

## 6. Étapes build
1. Tests DB/query d'abord (RED).
2. `query.py`, `db_search.py` (GREEN).
3. `.streamlit/config.toml` + `app.py`.
4. `pytest -v` + `pyright`, recette manuelle.
