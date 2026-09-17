# Plan : chunks ≈128 tokens (≤128 strict) vectorisables MiniLM-L12-v2

## 1. Objectif
Passer de chunks phrase (~10-20 mots, `128` = plafond rarement atteint) à des chunks **greedy-pack les plus proches de 128 sans jamais dépasser**, pour vectorisation future via `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (WordPiece, `max_seq_length=128`).
Contraintes actées utilisateur : compteur = **tokenizer MiniLM réel**, compromis **remplissage > phrase propre**, **cues SRT atomiques** (jamais coupées sauf exception oversize), overlap à trancher (cf §2).

## 2. Overlap : sans vs avec — explication demandée
Contexte : `chunking.py` actuel fait overlap (rejoue `k+1..end` quand coupe mid-sentence).

**Sans overlap (disjoint, recommandé défaut pour embeddings) :**
- Chaque cue indexée 1x → pas de doublons de vecteurs, DB plus petite, `top-k` vectoriel/FTS diversifié (pas 2 voisins quasi-identiques qui écrasent le rappel).
- Scores propres : un contenu dupliqué pèse 2x en BM25/cosinus et fausse le ranking + `seq_no` continu simple.
- Coût : une requête à cheval sur une frontière perd du contexte (phrase coupée). Atténué par le compromis §4 (frontière phrase préférée quand proche du max) + recherche `seq_no±1` au moment RAG au lieu de dupliquer au stockage.

**Avec overlap (ex. 1 phrase / 1 cue quand coupe mid-sentence) :**
- +Rappel sur requêtes trans-frontière, contexte préservé — standard RAG 10-20%.
- −Stockage gonflé, voisins near-dup, dedup nécessaire au rerank, `sum(tokens)` > total réel, backfill plus lourd.
- Recommandation plan : implémenter **`overlap=0` par défaut**, paramètre `overlap_cues: int = 0` prêt pour V-RAG si le rappel trans-frontière s'avère faible (mesurer d'abord, activer ensuite avec 1). Ne pas mélanger les deux régimes dans la même table sans colonne `overlap`.

## 3. État actuel (fichiers lus)
- `src/lucas_v2/chunking.py` : `count_tokens=len(split())`, `chunk_cues(max_tokens=128)` pack-then-backtrack + overlap + `oversize` émis tel quel (viole ≤128). `_ends_sentence` = `.`/`;` uniquement (rate `? ! : …` FR).
- `src/lucas_v2/srt.py` : `Cue(start_s,end_s,text)`, atomique par construction.
- `src/lucas_v2/__init__.py:103` : `chunk_cues(cues)` défaut 128 ; `db.py:replace_chunks` stocke `tokens` (sémantique va changer mot→WordPiece → backfill requis).
- `tests/test_srt_chunk.py` : 12 tests sur l'ancien régime (dont `test_overlap_on_truncation`, `test_single_cue_oversize` qui assert `tokens==200` → à réécrire).
- `pyproject.toml` : pas de `transformers`/`sentence-transformers` → à ajouter.

## 4. Décisions / paramètres cibles
| Paramètre | Valeur | Motif |
|---|---|---|
| Tokenizer | `AutoTokenizer.from_pretrained("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")`, `add_special_tokens=False` | Compte WordPiece réel = garantie vectorisable |
| `MAX_TOKENS` | `126` contenu (+2 `[CLS]/[SEP]` = 128 modèle) — nommer `MAX_CONTENT_TOKENS=126`, garder alias `max_tokens` | Évite toute troncation silencieuse côté `sentence-transformers` |
| `SOFT_MIN` | `110` | Plage cible 110-126 : remplit proche du max tout en laissant une fenêtre pour finir sur phrase propre |
| Ponctuation FR | `. ; ? ! : …` (+ `...`) sur `rstrip()` | Auto-subs FR ponctuent avec `? !`, l'ancien `.`/`;` seul sous-détecte |
| Cues | atomiques ; seule exception §5.4 | Choix utilisateur |
| Overlap défaut | `0`, param `overlap_cues=0` | §2 |
| Queue restante | si dernier chunk `< MIN_TAIL=30` et `len(chunks)≥1` → fusionner avec précédent **si** total fusionné ≤126, sinon garder tel quel (jamais dépasser) | Évite micro-chunks de fin sans violer le plafond |
| `tokens` DB | redéfini = compte WordPiece contenu | Backfill obligatoire (`--force`) |

## 5. Algorithme proposé (remplace `chunk_cues`)
```
i=0
tant que i<n :
  j=i, text=""
  tant que j<n et tok(text + cues[j]) <= MAX (126) : text+=cues[j]; j++
  end=j-1
  si end<i :  # cue oversize isolée → §5.4
  si end==n-1 : flush(i..end) [queue, règle fusion §4]; fin
  si tok(text) >= SOFT_MIN :
     # cherche première frontière de phrase entre SOFT_MIN et MAX
     k = premier idx>=i avec tok(i..idx)>=SOFT_MIN et _ends_sentence(i..idx)
     si k trouvé et k<end : flush(i..k); i=k+1 (+overlap si activé); continuer
  flush(i..end)  # coupe mid-sentence assumée = plus proche de 128
  i=end+1 (+overlap si activé et frontière interne trouvée)
```
- `_ends_sentence` étendue FR (regex `[.;?!:…]+$` + `...`).
- Comptage incrémental avec cache `tok(cue)` + `tok(joint)` pour rester O(n) (tokenizer Rust rapide, mais éviter `encode` du prefix complet à chaque pas sur longues vidéos : cacher par cue, sommer avec correction espace — valider que `sum != joint` WordPiece `##` reste exact : si écart, recompter joint avant flush).
- Timestamps : `start_s=cues[i].start_s`, `end_s=cues[end].end_s`, `text=" ".join`, `tokens=tok(text)`.

### 5.4 Exception oversize (cue seule >126, inévitable avec cues atomiques)
Seul cas où on coupe **intra-cue** (sinon garantie ≤128 impossible) :
1. split cue en mots, greedy-pack mots au tokenizer ≤126 en sous-chunks `a,b,…` ;
2. timestamps : `start_s`/`end_s` de la cue mère répliqués (ou interpolation proportionnelle au nb de mots — choisir réplication simple V1, noter l'approximation) ;
3. log `warning oversize split cue_idx`.
Alternative écartée : émettre oversize (statu quo) → **rejetée** car non-vectorisable.

## 6. Fichiers à modifier (build, pas ce plan)
1. `pyproject.toml` : ajouter `transformers>=4.40`, (optionnel `sentence-transformers>=2.7` en dep future — pour V1 seul `transformers+tokenizers+hf-hub` suffit pour compter). `uv sync`.
2. `src/lucas_v2/chunking.py` : nouveau `get_tokenizer()` (cache singleton + var d'env `LUCAS_TOKENIZER` + fallback whitespace avec `warnings.warn` offline), `count_tokens(text, tokenizer=None)`, constantes `MAX_CONTENT_TOKENS/SOFT_MIN/MIN_TAIL`, `_ends_sentence` FR, `chunk_cues(cues, max_tokens=126, soft_min=110, overlap_cues=0, tokenizer=None)`, helper `_split_oversize_cue`.
3. `src/lucas_v2/__init__.py` : passer le tokenizer partagé (chargé 1x, pas par vidéo), log `cues → chunks, avg/max tokens`.
4. `tests/test_srt_chunk.py` : adapter (mock tokenizer whitespace pour tests rapides + 1 test d'intégration tokenizer réel `pytest -m slow`) : `tokens<=126` strict, `110<=tokens` sur chunks non-finaux quand cues atomiques le permettent, pas d'overlap par défaut, queue fusionnée, oversize splitté, ponctuation `? ! :` reconnue, `sum(couverture)` sans perte hors overlap.
5. Docs : `README.md` §Chunking (126+2, 110-126, cues atomiques, backfill `--force`) + plan détaillé existant.

## 7. Tests / vérification (TDD)
- `uv run pytest tests/ -v` vert avant/après.
- Nouveaux asserts : `max(tok)<=126` sur corpus FR réel (auto+manuel), `mean>100`, `0` chunk `>126`, aucun texte perdu (re-join couvre toutes les cues sauf overlap paramétré), distribution `tokens` histogramme.
- Script lecture seule : `SELECT tokens, length(text) FROM transcript_chunk` avant/après `--force` sur 1 vidéo pour montrer 10→~115.
- Backfill : `ingest --force` (skip `video_exists` contourné) ; pas de migration SQL (même schéma, sémantique `tokens` changée — signaler dans README).

## 8. Risques
- DL tokenizer HF au premier run (offline/CI → fallback whitespace + warn ; pinner `revision` du tokenizer pour stabilité des comptes).
- `sum(tok cue)` ≠ `tok(joint)` (WordPiece contextuel `##`) → toujours valider au `encode` joint avant `flush`.
- FR auto sans ponctuation → coupes mid-sentence fréquentes (assumé par le compromis ; overlap=1 réactivable si RAG décevant).
- Perf : `encode` par candidat O(n²) sur longues vidéos → cache + comptage incrémental (§5).
- `tokens` historiques (mots) vs nouveaux (WordPiece) mélangés si backfill partiel → imposer `--force` complet + doc.

## 9. Hors scope
Embeddings/stockage pgvector, recherche vectorielle, rerank, overlap RAG dynamique (`seq_no±1` au read), multi-langues, changement schéma Turso.
