# Plan : Affichage synthétique en mode --dry-run

## Objectif

Remplacer l'affichage verbose actuel du `--dry-run` (qui liste chaque vidéo individuellement) par un tableau récapitulatif par chaîne :

- **Déjà scrapées** : vidéos retournées par l'API qui existent déjà dans la table `video`
- **À scraper** : vidéos retournées par l'API mais absentes de la table `video` (+ vidéos qui matchent `force_id` si `--url` est utilisé)

Ces deux compteurs sont indépendants de `--force-all` — ils reflètent l'état de la base par rapport à ce que l'API retourne avec les paramètres de `channels.yaml`.

## Fichiers à modifier

1. **`src/lucas_v2/__init__.py`** — Refactorer `_process_videos`, `_resolve_channel` et `ingest`

## Approche

### Étape 1 : Modifier `_resolve_channel` pour retourner `channel_title`

Actuellement retourne `tuple[int, str] | None` = `(row_id, yt_channel_id)`. Modifier pour retourner `tuple[int, str, str] | None` = `(row_id, yt_channel_id, channel_title)`. Le `channel_title` est déjà résolu (ligne 47), juste pas retourné.

Mettre à jour les 2 sites d'appel :
- `ingest` ligne 199-204 : `(channel_row_id, yt_channel_id, channel_title)`
- `_ingest_single_video` ligne 240-245 : `(channel_row_id_c, yt_channel_id_c, _channel_title_c)`

### Étape 2 : Modifier `_process_videos` pour retourner des stats

Changer la signature (ligne 120) pour qu'elle retourne `tuple[int, int]` = `(nb_new, nb_already_scraped)` au lieu de `None`.

Dans la boucle `for` (ligne 128), en mode `dry_run` :
- Ne plus logger les détails de chaque vidéo (supprimer la ligne 130 et le bloc 137-139)
- Incrémenter `existing_count` si la vidéo existe déjà et `vid_yt_id != force_id`, `new_count` sinon
- Retourner `(new_count, existing_count)` à la fin

Le try/except `RateLimitedError` (lignes 144-152) reste dans le path non-dry-run.

### Étape 3 : Modifier `ingest` pour afficher le tableau synthétique

Dans la boucle `for spec in channels` (ligne 197), en mode `dry_run` :
1. Récupérer `channel_title` depuis `_resolve_channel` (3-tuple)
2. Appeler `_process_videos` et collecter le résultat `(new_count, existing_count)`
3. Stocker `(spec.url, channel_title, new_count, existing_count)` dans `dry_run_results`

Après la boucle, si `dry_run`, logger le tableau via `_print_dry_run_summary`.

### Étape 4 : Cas --url

Le flow `--url` (`_ingest_single_video`, ligne 213) est séparé. En mode dry-run, le comportement actuel (message simple) est suffisant — pas de tableau récapitulatif.

### Détails d'implémentation

**`_resolve_channel` (ligne 40) :**
```python
def _resolve_channel(spec: ChannelSpec, conn: Any) -> tuple[int, str, str] | None:
    from lucas_v2.db import upsert_channel
    from lucas_v2.youtube_api import resolve_channel_id

    try:
        yt_channel_id: str
        channel_title: str
        yt_channel_id, channel_title = resolve_channel_id(spec.url)
        logger.info("  channelId: %s (%s)", yt_channel_id, channel_title)
        row_id: int = upsert_channel(conn, spec.url, yt_channel_id, channel_title)
        return row_id, yt_channel_id, channel_title  # ← ajout channel_title
    except Exception as e:
        logger.error("  ERREUR résolution chaîne : %s", e)
        return None
```

**`_process_videos` (lignes 120-152) :**
```python
def _process_videos(
    videos: list[dict[str, Any]], channel_row_id: int,
    spec: ChannelSpec, conn: Any, force: bool, dry_run: bool, tok: Any,
    force_id: str | None = None,
) -> tuple[int, int]:  # ← changement de retour
    from lucas_v2.db import video_exists
    from lucas_v2.subs import RateLimitedError

    new_count: int = 0
    existing_count: int = 0
    for i, vid in enumerate(videos):
        vid_yt_id: str = str(vid["youtube_str_id"])

        is_new: bool = not video_exists(conn, vid_yt_id)

        if dry_run:
            if is_new or vid_yt_id == force_id:
                new_count += 1
            else:
                existing_count += 1
            continue  # ← plus de log individuel

        logger.info("  >> %s (%s)", vid["title"], vid_yt_id)
        if not force and not is_new and vid_yt_id != force_id:
            logger.info("     Déjà scrapée, skip (utiliser --force-all ou --url pour re-scraper).")
            continue

        if i > 0:
            time.sleep(INTER_VIDEO_DELAY_S)

        try:
            _download_and_store(vid, channel_row_id, spec, conn, is_new, tok)
        except RateLimitedError:
            logger.warning(
                "Rate-limit persistant : ingestion arrêtée. "
                "%d vidéo(s) restante(s) reprises au prochain lancement.",
                len(videos) - i - 1,
            )
            break

    return new_count, existing_count
```

**`ingest` (ligne 197+) :**
```python
    dry_run_results: list[tuple[str, str, int, int]] = []

    for spec in channels:
        logger.info("--- %s ---", spec.url)
        result = _resolve_channel(spec, conn)
        if result is None:
            continue
        channel_row_id, yt_channel_id, channel_title = result

        videos = _fetch_videos(yt_channel_id, spec)
        logger.info("  %d vidéo(s) trouvée(s).", len(videos))
        new_count, existing_count = _process_videos(
            videos, channel_row_id, spec, conn, force_all, dry_run, tok,
        )
        if dry_run:
            dry_run_results.append((spec.url, channel_title, new_count, existing_count))

    if dry_run and dry_run_results:
        _print_dry_run_summary(dry_run_results)

    logger.info("Terminé.")
```

**Sites d'appel `_resolve_channel` à mettre à jour :**
- `ingest` ligne 199-204 : déstructurer en `(channel_row_id, yt_channel_id, channel_title)`
- `_ingest_single_video` ligne 240-245 : déstructurer en `(channel_row_id_c, yt_channel_id_c, _channel_title_c)`

**Nouvelle fonction `_print_dry_run_summary` :**
```python
def _print_dry_run_summary(results: list[tuple[str, str, int, int]]) -> None:
    """Affiche un tableau récapitulatif en mode dry-run."""
    logger.info("\n--- dry-run summary ---")
    total_existing: int = 0
    total_new: int = 0
    for url, title, new_c, exist_c in results:
        label: str = f"{url} ({title})" if title else url
        logger.info("  %-50s %5d          %5d", label, exist_c, new_c)
        total_existing += exist_c
        total_new += new_c
    logger.info("  %-50s %5d          %5d", "Total", total_existing, total_new)
    logger.info("  %d vidéo(s) à scraper.", total_new)
```

**Aucune modification dans `db.py`** — les compteurs sont dérivés de `video_exists()` appelé dans la boucle existante.

## Complexité

- `_resolve_channel` : ajout d'une valeur au tuple retour → complexité identique
- `_process_videos` : ajout de 2 compteurs + return + suppression de 3 lignes → complexité ≤ 10
- `ingest` : ajout d'une liste + déstructuration 3-tuple + affichage → complexité ≤ 12
- `_print_dry_run_summary` : simple boucle d'affichage → complexité ≤ 5

## Vérification

1. `lucas-v2 ingest --dry-run` → affiche le tableau récapitulatif avec les bons comptes
2. `lucas-v2 ingest` (sans --dry-run) → comportement identique à aujourd'hui
3. `lucas-v2 ingest --dry-run --force-all` → les comptes sont les mêmes
4. `lucas-v2 ingest --dry-run --url <url>` → affiche le message dry-run simple
5. Pyright passe sans erreurs
