import argparse
import json
import logging
from datetime import datetime
from pathlib import Path

from scraper import fetch_products, fetch_size_guide
from database import get_connection, init_db, save_products, save_size_guide, upsert_site

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DEFAULT_SITES = [
    "https://www.kleman-france.com",
    "https://www.andre.fr",
    "https://minuitsurterre.com",
]

OUTPUT_DIR = Path(__file__).parent / "output"


def scrape_site(base_url: str, fetch_guide: bool = True) -> dict:
    logger.info(f"━━━ Scraping : {base_url}")

    logger.info("→ Récupération des produits...")
    products = fetch_products(base_url)
    logger.info(f"✓ {len(products)} produits trouvés.")

    guide = None
    if fetch_guide:
        logger.info("→ Recherche du guide de taille...")
        guide = fetch_size_guide(base_url, products=products)
        if guide:
            table_count = len(guide.get("tables", []))
            logger.info(f"✓ Guide trouvé : {guide['title']} ({table_count} tableau(x))")
        else:
            logger.info("✗ Pas de guide de taille détecté.")

    return {
        "site": base_url,
        "products": products,
        "size_guide": guide,
    }


def save_as_json(result: dict) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    domain = result["site"].replace("https://", "").replace("http://", "").replace("/", "_").strip("_")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = OUTPUT_DIR / f"{domain}_{timestamp}.json"

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    logger.info(f"✓ JSON exporté → {filepath}")


def save_as_sqlite(result: dict, conn) -> None:
    site_id = upsert_site(conn, result["site"])
    save_products(conn, result["products"], site_id)
    if result["size_guide"]:
        save_size_guide(conn, result["size_guide"], site_id)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scraper Shopify — produits & guides de taille")
    parser.add_argument(
        "--sites",
        nargs="+",
        default=DEFAULT_SITES,
        metavar="URL",
        help="URL(s) des sites Shopify à scraper",
    )
    parser.add_argument(
        "--output",
        choices=["json", "sqlite", "both"],
        default="both",
        help="Format de sortie (défaut: both)",
    )
    parser.add_argument(
        "--no-size-guide",
        action="store_true",
        help="Ne pas chercher les guides de taille",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    conn = None
    if args.output in ("sqlite", "both"):
        conn = get_connection()
        init_db(conn)

    all_results = []

    for site_url in args.sites:
        try:
            result = scrape_site(site_url, fetch_guide=not args.no_size_guide)
            all_results.append(result)

            if args.output in ("json", "both"):
                save_as_json(result)

            if args.output in ("sqlite", "both") and conn:
                save_as_sqlite(result, conn)

        except Exception as e:
            logger.error(f"Erreur inattendue pour {site_url} : {e}", exc_info=True)
            continue

    if conn:
        conn.close()

    total_products = sum(len(r["products"]) for r in all_results)
    guides_found = sum(1 for r in all_results if r["size_guide"])

    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logger.info(f"TERMINÉ — {len(all_results)} site(s) scrapé(s)")
    logger.info(f"          {total_products} produits au total")
    logger.info(f"          {guides_found}/{len(all_results)} guide(s) de taille trouvé(s)")


if __name__ == "__main__":
    main()