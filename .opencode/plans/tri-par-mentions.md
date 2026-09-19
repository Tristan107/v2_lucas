# Plan : Trier les vidéos par nombre de mentions décroissant

## Objectif

Changer l'ordre de tri des résultats de recherche : **nombre de mentions (chunks matchés) en premier**, puis date de publication, puis ID comme tiebreaker.

**Avant** : `ORDER BY v.upload_date DESC, COUNT(*) DESC, v.id DESC`
**Après** : `ORDER BY COUNT(*) DESC, v.upload_date DESC, v.id DESC`

---

## Fichiers à modifier

### 1. `src/lucas_v2/ui/db_search.py` — Ligne 89

**Changement** : Inverser les deux premiers critères du `ORDER BY`.

```python
# Avant
"ORDER BY v.upload_date DESC, COUNT(*) DESC, v.id DESC "

# Après
"ORDER BY COUNT(*) DESC, v.upload_date DESC, v.id DESC "
```

Aussi mettre à jour la docstring de `search_videos()` (lignes 66-69) :

```python
# Avant
"""Return distinct videos whose chunks match *match_query*.

Ordered by upload date descending, then mention count descending,
then video id descending as a stable tiebreaker.
"""

# Après
"""Return distinct videos whose chunks match *match_query*.

Ordered by mention count descending, then upload date descending,
then video id descending as a stable tiebreaker.
"""
```

### 2. `src/lucas_v2/ui/app.py` — Ligne 357

**Changement** : Ajouter un caption indicateur de tri sous le compteur de résultats.

```python
# Avant (ligne 357)
st.caption(f"{total} vidéos trouvées — Page {page + 1} sur {total_pages}")

# Après
st.caption(f"{total} vidéos trouvées — Triées par nombre de mentions — Page {page + 1} sur {total_pages}")
```

### 3. `tests/test_search_db.py` — Tests à adapter

Le seed data a `vid1` (20240101, 2 chunks "travail") et `vid2` (20250615, 2 chunks "travail"). Avec le nouveau tri, les deux ont le même nombre de mentions (2), donc le tiebreaker est la date → vid2 reste en premier. **Aucun changement nécessaire pour `test_search_videos_order_desc` et `test_search_videos_pagination`.**

**Test existant à vérifier** :
- `test_search_videos_same_date_order_by_mentions_desc` (ligne 141) — déjà cohérent avec le nouveau tri (mentions d'abord, même date).

**Nouveau test à ajouter** : `test_search_videos_mentions_primary_order` — vérifier que quand une vidéo a plus de mentions mais est plus ancienne, elle passe quand même en premier.

```python
def test_search_videos_mentions_primary_order() -> None:
    """Les vidéos avec le plus de mentions passent en premier, même si plus anciennes."""
    conn = _conn()
    ch_id = upsert_channel(conn, "https://yt.com/ch1", "UC1", "Chaîne", "gauche", "Alice")
    vid_old_many = upsert_video(conn, ch_id, "vid_old_many", "Ancienne mais citée", "20240101", 300, "fr", "manual", "ok", None)
    vid_new_few = upsert_video(conn, ch_id, "vid_new_few", "Récente mais peu citée", "20250615", 120, "fr", "manual", "ok", None)
    replace_chunks(conn, vid_old_many, [
        Chunk(seq_no=0, start_s=0, end_s=5, text="le travail est important", tokens=4),
        Chunk(seq_no=1, start_s=6, end_s=10, text="encore du travail ici", tokens=4),
        Chunk(seq_no=2, start_s=11, end_s=15, "toujours du travail partout", tokens=4),
    ])
    replace_chunks(conn, vid_new_few, [
        Chunk(seq_no=0, start_s=0, end_s=5, text="le travail c'est bien", tokens=4),
    ])
    conn.commit()
    results = search_videos(conn, "travail")
    assert len(results) == 2
    # vid_old_many (3 mentions) avant vid_new_few (1 mention), malgré la date
    assert results[0].youtube_str_id == "vid_old_many"
    assert results[1].youtube_str_id == "vid_new_few"
    assert results[0].mentions == 3
    assert results[1].mentions == 1
```

---

## Résumé des modifications

| Fichier | Ligne(s) | Changement |
|---------|----------|------------|
| `src/lucas_v2/ui/db_search.py` | 89 | `ORDER BY COUNT(*) DESC, v.upload_date DESC, v.id DESC` |
| `src/lucas_v2/ui/db_search.py` | 66-69 | Docstring mise à jour |
| `src/lucas_v2/ui/app.py` | 357 | Caption avec indicateur de tri |
| `tests/test_search_db.py` | après 156 | Nouveau test `test_search_videos_mentions_primary_order` |

---

## Vérification

1. `uv run pytest tests/test_search_db.py -v` — tous les tests passent
2. `uv run pyright` — zéro erreur
3. `uv run streamlit run streamlit_app.py` — tester manuellement avec une recherche et vérifier que les vidéos les plus citées apparaissent en premier
