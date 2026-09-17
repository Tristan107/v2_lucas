# Plan : Restaurer les couleurs des capitales dans le sous-titre de la page d'accueil

## Objectif
Remettre les couleurs LUCAS sur les lettres du sous-titre « L'Usine de Collecte d'informations et d'Analyse Synthétique » de la page d'accueil. Les lettres identiques doivent garder la même couleur.

## Fichier à modifier
`streamlit_app.py` — ligne 33

## Modification
Remplacer le texte plain du sous-titre par des `<span>` colorés :

```diff
-                — L'Usine de Collecte d'informations<br>et d'Analyse Synthétique
+                — <span style="color:#E63946">L</span>'<span style="color:#457B9D">U</span>sine de <span style="color:#2A9D8F">C</span>ollecte d'informations<br>et d'<span style="color:#E9C46A">A</span>nalyse <span style="color:#457B9D">S</span>ynthétique
```

## Correspondance des couleurs
| Lettre | Couleur | Utilisation |
|--------|---------|-------------|
| L | #E63946 (rouge) | **L**'Usine |
| U | #457B9D (bleu) | **U**sine |
| C | #2A9D8F (vert/turquoise) | **C**ollecte |
| A | #E9C46A (or) | **A**nalyse |
| S | #457B9D (bleu) | **S**ynthétique |

## Vérification
1. Lancer l'app Streamlit
2. Vérifier que les lettres du sous-titre sont colorées comme le titre LUCAS
3. Vérifier qu'aucun autre élément n'a changé
