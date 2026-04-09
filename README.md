# Fitle — Shopify Scraper (Produits & Guides de Taille)

Dans le cadre du test technique Fitle, l’objectif est de développer un outil capable de :

- récupérer automatiquement les produits depuis des sites Shopify
- détecter et extraire les guides de taille
- structurer ces données dans un format exploitable

# 1. Extraction des produits

Utilisation de l’endpoint Shopify :

```
/products.json
```

Récupération des informations suivantes :

- titre
- URL
- vendor (marque)
- type produit
- tags
- options (ex : tailles)
- variantes (prix, stock, SKU…)
- images
- description HTML

# 2. Extraction des guides de taille

Stratégie progressive (du plus fiable au plus heuristique) :

1. Pages dédiées :

   - `/pages/guide-des-tailles`
   - `/pages/size-guide`
   - `/pages/guide-des-pointures`

2. Liens présents dans la homepage (menu / footer)

3. Pages FAQ ou aide

4. Fiches produit (tables HTML ou texte)

Le scraper détecte :

- les tableaux HTML (`<table>`)
- ou, à défaut, du texte contenant des informations de taille (ex : conseils de fit)


# 3. Stockage des données

Deux formats disponibles :

# JSON

- 1 fichier par site
- format lisible et portable

# SQLite (`db/fitle.db`)

Tables principales :

| Table         | Description       |
| ------------- | ----------------- |
| `sites`       | sites scrapés     |
| `products`    | produits          |
| `variants`    | variantes         |
| `size_guides` | guides de taille  |
| `size_tables` | tableaux extraits |


# 4. Dashboard interactif

Un dashboard Streamlit permet :

- visualisation des KPIs :

  - nombre de produits
  - nombre de variantes
  - nombre de guides de taille
- analyse par site
- exploration des produits
- inspection détaillée (options, variantes, HTML…)
- exécution de requêtes SQL prédéfinies


# Installation

```bash
git clone <repo>
cd fitle-scraper
pip install -r requirements.txt
```

# Utilisation

# Scraper les sites

```bash
python main.py
```

# Scraper des sites spécifiques

```bash
python main.py --sites https://www.andre.fr
```

# Désactiver les guides de taille

L’option `--no-size-guide` permet de désactiver la recherche des guides de taille afin d’accélérer le scraping ou de tester uniquement l’extraction des produits.

```bash
python main.py --no-size-guide
```


# Dashboard

```bash
python -m streamlit run dashboard.py
```

Puis ouvrir :

```
http://localhost:8501
```

# Choix techniques

- Python : simplicité d’utilisation et excellent écosystème pour le scraping (requests, BeautifulSoup…)
- API Shopify `/products.json` : méthode fiable, rapide et évite le parsing HTML fragile
- BeautifulSoup : parsing HTML robuste et standard en Python
- SQLite : base de données légère, portable et sans configuration
- JSON : format lisible et facilement exploitable
- Streamlit : permet de créer rapidement un dashboard interactif

# Conclusion

Ce projet met en place une solution robuste pour :

- extraire des données produits depuis des sites Shopify
- détecter des guides de taille malgré leur hétérogénéité
- structurer et explorer ces données via une base SQLite et un dashboard