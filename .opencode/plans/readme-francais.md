# Plan : Adaptation README.md en français

## Objectif
Rendre le README.md accessible en le rédigeant entièrement en français, en centrant sur l'objectif du projet (veille politique pour Lucas et ses amis), et en retirant les détails d'implémentation. L'exemple SQL sera déplacé dans AGENTS.md.

---

## Fichier 1 : `README.md`

### 1. Titre et description d'accroche

Remplacer l'ancien titre et la description technique par :

```markdown
# Lucas v2 — Veille politique YouTube

Outil de veille politique pour Lucas et ses amis : collecte automatique
des transcripts de vidéos YouTube de chaînes politiques françaises,
rendus interrogeables via une interface web.

Créé en vue de l'élection présidentielle de 2027, Lucas v2 permet de
suivre et chercher dans le discours politique diffusé sur YouTube.
```

### 2. Retirer la section « Fonctionnement »

La section actuelle décrit les modules internes (`youtube_api.py`, `subs.py`, `srt.py`, `chunking.py`, `db.py`). Remplacer par une description simple du flux :

```markdown
## Fonctionnement

1. **Chaînes** : un fichier YAML définit les chaînes YouTube à suivre
2. **Collecte** : les vidéos et sous-titres français sont récupérés automatiquement
3. **Indexation** : les transcripts sont découpés en segments et stockés dans une base de données
4. **Recherche** : une interface web permet de chercher dans tous les transcripts avec liens YouTube
```

### 3. Retirer les sections techniques

Sections à supprimer complètement :
- « Structure » (arborescence interne du code)
- « Exemple de recherche SQL » (→ déplacé dans AGENTS.md)
- Le bloc « Biggest channel (Mélenchon)... Turso limits » en fin de fichier

### 4. Sections à conserver (adaptées en français)

#### Prérequis
```markdown
## Prérequis

- Python ≥ 3.11, [uv](https://docs.astral.sh/uv/)
- Clé **YouTube Data API v3** (Google Cloud Console → activer l'API → clé)
- Base **Turso** + token (`TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`)
```

#### Installation
Conserver telle quelle.

#### Configuration
Conserver telle quelle (déjà en français).

#### Lancement
Conserver les commandes, traduire les commentaires en français plus fluide si nécessaire.

#### Recherche Streamlit (IHM)
Conserver, simplifier la description. Retirer la note Streamlit Cloud (détail de déploiement).

#### Tests
Conserver telle quelle.

### 5. Résultat final attendu

Le README contiendra ces sections dans l'ordre :
1. Titre + description contextuelle
2. Prérequis
3. Installation
4. Configuration
5. Lancement (ingestion)
6. Recherche Streamlit (IHM)
7. Tests

---

## Fichier 2 : `AGENTS.md`

### Ajouter l'exemple SQL

Dans la **section 7 (Database Schema)**, après le bloc DDL et la sous-section « Status Values », ajouter :

```markdown
### Exemple de requête FTS5

```sql
SELECT tc.seq_no, tc.start_s, tc.end_s,
       snippet(transcript_chunk_fts, 0, '<b>', '</b>', '…', 12) AS extrait,
       tc."text",
       bm25(transcript_chunk_fts) AS rank,
       'https://www.youtube.com/watch?v=' || v.youtube_str_id || '&t=' || tc.start_s AS video_link,
       v.title
FROM transcript_chunk_fts
JOIN transcript_chunk tc ON tc.id = transcript_chunk_fts.rowid
JOIN video v ON v.id = tc.fk_video_id
WHERE transcript_chunk_fts MATCH 'boulot*'
ORDER BY rank
LIMIT 20;
```

Le lien `video_link` produit une URL directe vers le début du chunk
(ex. `https://www.youtube.com/watch?v=abc123&t=95`).
```

---

## Vérification

- [ ] README.md est entièrement en français (hors noms propres techniques)
- [ ] README.md mentionne « pour Lucas et ses amis »
- [ ] README.md explique l'objectif (veille politique, élection 2027)
- [ ] README.md ne contient plus de détails d'implémentation internes
- [ ] L'exemple SQL est présent dans AGENTS.md section 7
- [ ] Aucune information utile n'est perdue
