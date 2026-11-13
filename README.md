# Appli GAP — Météo des marchés

Indice de contexte (0 à 100) pour le **S&P 500**, le **CAC 40** et le **MSCI World**, calculé à partir de 6 piliers : croissance, inflation et banques centrales, conditions financières, valorisation, sentiment, incertitude.

Ce n'est pas un conseil d'investissement : l'indice décrit le contexte, il ne prévoit pas les marchés.

## Fonctionnement automatique

Le robot GitHub (`.github/workflows/mise-a-jour.yml`) tourne le 3 et le 18 de chaque mois :
1. `scripts/telecharger.py` télécharge les données (FRED, MSCI, Yahoo Finance, multpl.com, github.com/datasets) dans `data/`. Si une source ne répond pas, l'ancien fichier est gardé et l'erreur est affichée sur le site.
2. `scripts/export_site.py` recalcule l'indice (`backtest_v3.py` pour le S&P 500, `backtest_v4_indices.py` pour le CAC 40 et le MSCI World) et écrit `site/data/*.json`.
3. Le site `site/` est publié sur GitHub Pages.

Pour lancer une mise à jour à la main : onglet **Actions** → « Mise à jour mensuelle de l'indice GAP » → **Run workflow**.

## Méthode

- Chaque indicateur est converti en score sur 10 ans glissants (données passées uniquement), borné entre −2 et +2.
- Score d'un pilier = moyenne de ses indicateurs ; CAC 40 : zone euro 65 %, US 20 %, Chine 15 % ; MSCI World : US 70 %, zone euro 20 %, Chine 10 %.
- Indice = moyenne pondérée des piliers (25/15/20/15/15/10) ramenée sur 0-100, mélangée à moitié avec sa tendance sur 3 mois.
- Zones : prudence sous le 20e percentile de l'historique de l'indice, favorable au-dessus du 80e.
