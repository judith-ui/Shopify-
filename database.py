import sqlite3
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "db" / "fitle.db"


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sites (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            url         TEXT NOT NULL UNIQUE,
            scraped_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS products (
            id           INTEGER PRIMARY KEY,
            site_id      INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
            title        TEXT,
            handle       TEXT,
            url          TEXT,
            product_type TEXT,
            vendor       TEXT,
            tags         TEXT,
            published_at TEXT,
            created_at   TEXT,
            updated_at   TEXT,
            options      TEXT,
            images       TEXT,
            body_html    TEXT
        );

        CREATE TABLE IF NOT EXISTS variants (
            id                 INTEGER PRIMARY KEY,
            product_id         INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
            title              TEXT,
            sku                TEXT,
            price              TEXT,
            available          INTEGER,
            inventory_quantity INTEGER,
            option1            TEXT,
            option2            TEXT,
            option3            TEXT,
            weight_grams       INTEGER
        );

        CREATE TABLE IF NOT EXISTS size_guides (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            site_id  INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
            url      TEXT,
            title    TEXT,
            raw_text TEXT,
            UNIQUE(site_id, url)
        );

        CREATE TABLE IF NOT EXISTS size_tables (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            size_guide_id INTEGER NOT NULL REFERENCES size_guides(id) ON DELETE CASCADE,
            headers       TEXT,
            rows          TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_products_site_id ON products(site_id);
        CREATE INDEX IF NOT EXISTS idx_variants_product_id ON variants(product_id);
        CREATE INDEX IF NOT EXISTS idx_size_guides_site_id ON size_guides(site_id);
    """)
    conn.commit()
    logger.info("Base de données initialisée.")


def upsert_site(conn: sqlite3.Connection, url: str) -> int:
    conn.execute("""
        INSERT INTO sites (url, scraped_at)
        VALUES (?, datetime('now'))
        ON CONFLICT(url) DO UPDATE SET scraped_at = datetime('now')
    """, (url,))
    conn.commit()

    row = conn.execute("SELECT id FROM sites WHERE url = ?", (url,)).fetchone()
    return row["id"]


def save_products(conn: sqlite3.Connection, products: list[dict], site_id: int) -> None:
    for p in products:
        conn.execute("""
            INSERT OR REPLACE INTO products
              (id, site_id, title, handle, url, product_type, vendor,
               tags, published_at, created_at, updated_at, options, images, body_html)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            p.get("id"),
            site_id,
            p.get("title"),
            p.get("handle"),
            p.get("url"),
            p.get("product_type"),
            p.get("vendor"),
            json.dumps(p.get("tags", []), ensure_ascii=False),
            p.get("published_at"),
            p.get("created_at"),
            p.get("updated_at"),
            json.dumps(p.get("options", []), ensure_ascii=False),
            json.dumps(p.get("images", []), ensure_ascii=False),
            p.get("body_html", ""),
        ))

        conn.execute("DELETE FROM variants WHERE product_id = ?", (p.get("id"),))

        for v in p.get("variants", []):
            conn.execute("""
                INSERT INTO variants
                  (id, product_id, title, sku, price, available,
                   inventory_quantity, option1, option2, option3, weight_grams)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (
                v.get("id"),
                p.get("id"),
                v.get("title"),
                v.get("sku"),
                v.get("price"),
                int(bool(v.get("available"))),
                v.get("inventory_quantity"),
                v.get("option1"),
                v.get("option2"),
                v.get("option3"),
                v.get("weight"),
            ))

    conn.commit()
    logger.info(f"{len(products)} produits sauvegardés.")


def save_size_guide(conn: sqlite3.Connection, guide: dict, site_id: int) -> None:
    conn.execute("""
        INSERT INTO size_guides (site_id, url, title, raw_text)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(site_id, url) DO UPDATE SET
            title = excluded.title,
            raw_text = excluded.raw_text
    """, (site_id, guide["url"], guide["title"], guide.get("raw_text", "")))

    row = conn.execute("""
        SELECT id FROM size_guides WHERE site_id = ? AND url = ?
    """, (site_id, guide["url"])).fetchone()
    guide_id = row["id"]

    conn.execute("DELETE FROM size_tables WHERE size_guide_id = ?", (guide_id,))

    for table in guide.get("tables", []):
        conn.execute("""
            INSERT INTO size_tables (size_guide_id, headers, rows)
            VALUES (?, ?, ?)
        """, (
            guide_id,
            json.dumps(table["headers"], ensure_ascii=False),
            json.dumps(table["rows"], ensure_ascii=False),
        ))

    conn.commit()
    logger.info("Guide de taille sauvegardé.")