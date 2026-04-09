import sqlite3
import json
from pathlib import Path

import pandas as pd
import streamlit as st

DB_PATH = Path(__file__).parent / "db" / "fitle.db"

st.set_page_config(page_title="Fitle Dashboard", layout="wide")


@st.cache_data
def run_query(query: str, params: tuple = ()) -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query(query, conn, params=params)
        return df
    finally:
        conn.close()


def safe_json_load(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    try:
        return json.loads(value)
    except Exception:
        return []


st.title("Fitle — Dashboard SQLite")
st.caption(f"Base utilisée : {DB_PATH}")

if not DB_PATH.exists():
    st.error("Base SQLite introuvable. Lance d'abord le scraper pour créer db/fitle.db")
    st.stop()


col1, col2, col3, col4 = st.columns(4)

sites_count = run_query("SELECT COUNT(*) AS n FROM sites")["n"].iloc[0]
products_count = run_query("SELECT COUNT(*) AS n FROM products")["n"].iloc[0]
variants_count = run_query("SELECT COUNT(*) AS n FROM variants")["n"].iloc[0]
guides_count = run_query("SELECT COUNT(*) AS n FROM size_guides")["n"].iloc[0]

col1.metric("Sites scrapés", int(sites_count))
col2.metric("Produits", int(products_count))
col3.metric("Variantes", int(variants_count))
col4.metric("Guides de taille", int(guides_count))

st.divider()


# Produits par site

st.subheader("Produits par site")

df_products_by_site = run_query("""
    SELECT
        s.url AS site,
        COUNT(p.id) AS nb_products
    FROM sites s
    LEFT JOIN products p ON p.site_id = s.id
    GROUP BY s.id, s.url
    ORDER BY nb_products DESC, s.url
""")

if not df_products_by_site.empty:
    st.dataframe(df_products_by_site, use_container_width=True)
    st.bar_chart(df_products_by_site.set_index("site"))
else:
    st.info("Aucune donnée de produits.")

st.divider()

# Variantes par site

st.subheader("Variantes par site")

df_variants_by_site = run_query("""
    SELECT
        s.url AS site,
        COUNT(v.id) AS nb_variants
    FROM sites s
    LEFT JOIN products p ON p.site_id = s.id
    LEFT JOIN variants v ON v.product_id = p.id
    GROUP BY s.id, s.url
    ORDER BY nb_variants DESC, s.url
""")

if not df_variants_by_site.empty:
    st.dataframe(df_variants_by_site, use_container_width=True)
else:
    st.info("Aucune donnée de variantes.")

st.divider()


# Vendors

st.subheader("Top vendors")

df_vendors = run_query("""
    SELECT
        COALESCE(NULLIF(TRIM(vendor), ''), 'Inconnu') AS vendor,
        COUNT(*) AS nb_products
    FROM products
    GROUP BY vendor
    ORDER BY nb_products DESC, vendor
    LIMIT 20
""")

if not df_vendors.empty:
    st.dataframe(df_vendors, use_container_width=True)
else:
    st.info("Aucun vendor trouvé.")

st.divider()


# Types de produits

st.subheader("Types de produits")

df_product_types = run_query("""
    SELECT
        COALESCE(NULLIF(TRIM(product_type), ''), 'Inconnu') AS product_type,
        COUNT(*) AS nb_products
    FROM products
    GROUP BY product_type
    ORDER BY nb_products DESC, product_type
    LIMIT 20
""")

if not df_product_types.empty:
    st.dataframe(df_product_types, use_container_width=True)
else:
    st.info("Aucun type de produit trouvé.")

st.divider()


# Guides de taille

st.subheader("Guides de taille détectés")

df_guides = run_query("""
    SELECT
        s.url AS site,
        g.title,
        g.url AS guide_url,
        LENGTH(COALESCE(g.raw_text, '')) AS raw_text_length,
        (
            SELECT COUNT(*)
            FROM size_tables t
            WHERE t.size_guide_id = g.id
        ) AS nb_tables
    FROM size_guides g
    JOIN sites s ON s.id = g.site_id
    ORDER BY s.url, g.title
""")

if not df_guides.empty:
    st.dataframe(df_guides, use_container_width=True)
else:
    st.info("Aucun guide de taille enregistré.")

st.divider()


# Explorer produits

st.subheader("Explorer les produits")

site_options = run_query("SELECT url FROM sites ORDER BY url")["url"].tolist()
selected_site = st.selectbox("Filtrer par site", ["Tous"] + site_options)

if selected_site == "Tous":
    df_products = run_query("""
        SELECT
            s.url AS site,
            p.id,
            p.title,
            p.vendor,
            p.product_type,
            p.url,
            p.tags,
            (
                SELECT COUNT(*)
                FROM variants v
                WHERE v.product_id = p.id
            ) AS nb_variants
        FROM products p
        JOIN sites s ON s.id = p.site_id
        ORDER BY s.url, p.title
    """)
else:
    df_products = run_query("""
        SELECT
            s.url AS site,
            p.id,
            p.title,
            p.vendor,
            p.product_type,
            p.url,
            p.tags,
            (
                SELECT COUNT(*)
                FROM variants v
                WHERE v.product_id = p.id
            ) AS nb_variants
        FROM products p
        JOIN sites s ON s.id = p.site_id
        WHERE s.url = ?
        ORDER BY p.title
    """, (selected_site,))

search_term = st.text_input("Recherche produit (titre)")
if search_term:
    df_products = df_products[
        df_products["title"].fillna("").str.contains(search_term, case=False, na=False)
    ]

st.dataframe(df_products, use_container_width=True)

st.divider()


# Détail d'un produit

st.subheader("Détail d'un produit")

if not df_products.empty:
    product_options = [
        f"{row['title']} | {row['site']} | #{row['id']}"
        for _, row in df_products.iterrows()
    ]
    selected_label = st.selectbox("Choisir un produit", product_options)

    selected_product_id = int(selected_label.split("#")[-1])

    df_product_detail = run_query("""
        SELECT
            p.id,
            s.url AS site,
            p.title,
            p.handle,
            p.vendor,
            p.product_type,
            p.url,
            p.tags,
            p.options,
            p.images,
            p.body_html,
            p.published_at,
            p.created_at,
            p.updated_at
        FROM products p
        JOIN sites s ON s.id = p.site_id
        WHERE p.id = ?
    """, (selected_product_id,))

    df_variants = run_query("""
        SELECT
            id,
            title,
            sku,
            price,
            available,
            inventory_quantity,
            option1,
            option2,
            option3,
            weight_grams
        FROM variants
        WHERE product_id = ?
        ORDER BY id
    """, (selected_product_id,))

    if not df_product_detail.empty:
        product = df_product_detail.iloc[0]

        left, right = st.columns([2, 1])

        with left:
            st.markdown(f"### {product['title']}")
            st.write(f"**Site :** {product['site']}")
            st.write(f"**Vendor :** {product['vendor']}")
            st.write(f"**Type :** {product['product_type']}")
            st.write(f"**URL :** {product['url']}")

            tags = safe_json_load(product["tags"])
            options = safe_json_load(product["options"])
            images = safe_json_load(product["images"])

            st.write("**Tags :**", tags if tags else "Aucun")
            st.write("**Options :**", options if options else "Aucune")

        with right:
            st.write("**Dates**")
            st.write(f"Publié : {product['published_at']}")
            st.write(f"Créé : {product['created_at']}")
            st.write(f"Mis à jour : {product['updated_at']}")

        st.markdown("#### Variantes")
        st.dataframe(df_variants, use_container_width=True)

        st.markdown("#### Images")
        if images:
            for img in images[:5]:
                st.image(img, width=180)
        else:
            st.info("Aucune image.")

        st.markdown("#### Description HTML brute")
        st.code(product["body_html"] or "", language="html")
else:
    st.info("Aucun produit à afficher.")

st.divider()


# Requêtes SQL utiles

st.subheader("Requêtes SQL utiles")

preset = st.selectbox(
    "Choisir une requête",
    [
        "Produits sans variantes",
        "Produits par vendor",
        "Guides avec tableaux",
        "Top 20 produits avec le plus de variantes",
        "Variantes en stock",
    ]
)

query_map = {
    "Produits sans variantes": """
        SELECT p.id, p.title, s.url AS site
        FROM products p
        JOIN sites s ON s.id = p.site_id
        LEFT JOIN variants v ON v.product_id = p.id
        WHERE v.id IS NULL
        ORDER BY s.url, p.title
    """,
    "Produits par vendor": """
        SELECT
            COALESCE(NULLIF(TRIM(vendor), ''), 'Inconnu') AS vendor,
            COUNT(*) AS nb_products
        FROM products
        GROUP BY vendor
        ORDER BY nb_products DESC, vendor
    """,
    "Guides avec tableaux": """
        SELECT
            s.url AS site,
            g.title,
            g.url,
            COUNT(t.id) AS nb_tables
        FROM size_guides g
        JOIN sites s ON s.id = g.site_id
        LEFT JOIN size_tables t ON t.size_guide_id = g.id
        GROUP BY g.id, s.url, g.title, g.url
        ORDER BY nb_tables DESC, s.url
    """,
    "Top 20 produits avec le plus de variantes": """
        SELECT
            p.id,
            p.title,
            s.url AS site,
            COUNT(v.id) AS nb_variants
        FROM products p
        JOIN sites s ON s.id = p.site_id
        LEFT JOIN variants v ON v.product_id = p.id
        GROUP BY p.id, p.title, s.url
        ORDER BY nb_variants DESC, p.title
        LIMIT 20
    """,
    "Variantes en stock": """
        SELECT
            p.title AS product,
            s.url AS site,
            v.title AS variant,
            v.sku,
            v.price,
            v.inventory_quantity
        FROM variants v
        JOIN products p ON p.id = v.product_id
        JOIN sites s ON s.id = p.site_id
        WHERE COALESCE(v.available, 0) = 1
        ORDER BY s.url, p.title, v.title
    """,
}

df_preset = run_query(query_map[preset])
st.dataframe(df_preset, use_container_width=True)