# Plan : Bulk inserts transcript_chunk pour Turso Free Tier

## Contexte

- Chaîne @JLMelenchon : **2007 vidéos régulières**, 156 shorts, **1110 h** de contenu
- ~15-100 chunks/video → **30k-200k+ rows** à insérer
- Turso Free : **10M rows written/mois**
- Chaque INSERT chunk déclenche : 1 row table + 3 triggers FTS + index = **~5-6 billed writes/chunk**
- Code actuel : N `conn.execute()` individuelles = N round-trips HTTP + N transactions

## Calcul d'impact (conservateur)

| Métrique | Avant | Après |
|---|---|---|
| INSERTs SQL | N individuelles | 1 `executemany` / batch |
| Round-trips Hrana | N (1 par chunk) | 1 par batch |
| FTS writes/chunk | 4 (triggers) | 0 pendant bulk → rebuild 1 fois |
| DELETE (re-srape) | Toujours (1 write + FTS) | Skip si vidéo nouvelle |

Pour 2007 vidéos × 40 chunks moyens = **80k chunks** :
- Avant : ~400k billed writes (80k × 5)
- Après : ~80k billed writes (1 write/chunk, FTS rebuild 1 fois)
- Économie : **~80% fewer writes**

## Modifications

### 1. `db.py` — `replace_chunks()`

**Avant :**
```python
def replace_chunks(conn, fk_video_id: int, chunks):
    conn.execute("DELETE FROM transcript_chunk WHERE fk_video_id=?", (fk_video_id,))
    for ch in chunks:
        conn.execute("INSERT INTO transcript_chunk ...", (...))
    conn.commit()
```

**Après :**
```python
def replace_chunks(conn, fk_video_id: int, chunks, *, delete_existing: bool = True):
    if delete_existing:
        conn.execute("DELETE FROM transcript_chunk WHERE fk_video_id=?", (fk_video_id,))
    if chunks:
        conn.executemany(
            "INSERT INTO transcript_chunk (fk_video_id, seq_no, start_s, end_s, text, tokens) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [(fk_video_id, ch.seq_no, ch.start_s, ch.end_s, ch.text, ch.tokens) for ch in chunks],
        )
    conn.commit()
```

### 2. `db.py` — `upsert_video()` : RETURNING id

**Avant :** INSERT + COMMIT + SELECT id (2 round-trips)
**Après :** INSERT RETURNING id + COMMIT (1 round-trip)

```python
def upsert_video(conn, ...) -> int:
    conn.execute("INSERT INTO video ... ON CONFLICT ... DO UPDATE ... RETURNING id", (...))
    row_id = conn.fetchone()[0]
    conn.commit()
    return row_id
```

Même chose pour `upsert_channel()`.

### 3. `__init__.py` — Transaction unique par vidéo

**Avant :** `upsert_video` commit + `replace_chunks` commit = 2 transactions
**Après :** Tout dans 1 transaction, commit 1 fois

```python
video_row_id = upsert_video(conn, ...)  # no commit inside
replace_chunks(conn, video_row_id, chunks)  # no commit inside
conn.commit()  # 1 seul commit à la fin
```

### 4. `db.py` — Flag `delete_existing` pour vidéos nouvelles

Dans `ingest`, passer `delete_existing=False` quand la vidéo n'existe pas encore (pas de DELETE inutile).

## Fichiers modifiés

- `src/lucas_v2/db.py` : `replace_chunks()`, `upsert_video()`, `upsert_channel()`
- `src/lucas_v2/__init__.py` : boucle ingest (transaction unique)

## Tests

- `uv run pytest` existant passe
- Test manuel `--dry-run` sur @JLMelenchon
- Vérifier `SELECT COUNT(*) FROM transcript_chunk` après ingest
