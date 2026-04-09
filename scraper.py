import json
import logging
import re
import time
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; FitleBot/1.0; +https://fitle.com)"
}

SIZE_GUIDE_SLUGS = [
    "guide-des-tailles",
    "guide-de-tailles",
    "guide-taille",
    "guide-tailles",
    "guide-des-pointures",
    "guide-pointures",
    "guide-des-pointure",
    "size-guide",
    "size-chart",
    "sizechart",
    "tableau-des-tailles",
    "mesures",
    "sizing",
    "sizing-guide",
]

FAQ_SLUGS = [
    "faq",
    "questions-frequentes",
    "foire-aux-questions",
    "aide",
    "help",
]

SIZE_KEYWORDS = [
    "taille", "tailles", "pointure", "pointures",
    "size", "sizes", "guide des tailles", "guide taille",
    "guide des pointures", "guide pointure",
    "size guide", "size chart",
    "eu", "uk", "us", "cm", "inch", "inches",
    "poitrine", "tour de poitrine", "waist", "hips", "bust",
    "équivalence", "equivalence", "measurement", "measurements"
]


def normalize_tags(raw_tags) -> list[str]:
    if not raw_tags:
        return []
    if isinstance(raw_tags, list):
        return [str(tag).strip() for tag in raw_tags if str(tag).strip()]
    if isinstance(raw_tags, str):
        return [tag.strip() for tag in raw_tags.split(",") if tag.strip()]
    return []


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def fetch_products(base_url: str, limit: int = 250) -> list[dict]:
    session = build_session()
    products = []
    page = 1
    base_url = base_url.rstrip("/")

    while True:
        url = f"{base_url}/products.json"
        params = {"limit": limit, "page": page}

        try:
            response = session.get(url, params=params, timeout=20)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            logger.error(f"Erreur produits (page {page}) : {e}")
            break
        except ValueError as e:
            logger.error(f"JSON invalide sur {url} page {page} : {e}")
            break

        batch = data.get("products", [])
        if not batch:
            break

        for raw in batch:
            products.append(parse_product(raw, base_url))

        logger.info(f"  Page {page} — {len(batch)} produits récupérés (total: {len(products)})")

        if len(batch) < limit:
            break

        page += 1
        time.sleep(0.4)

    return products


def parse_product(raw: dict, base_url: str) -> dict:
    variants = [
        {
            "id": v.get("id"),
            "title": v.get("title"),
            "sku": v.get("sku"),
            "price": v.get("price"),
            "available": v.get("available"),
            "inventory_quantity": v.get("inventory_quantity"),
            "option1": v.get("option1"),
            "option2": v.get("option2"),
            "option3": v.get("option3"),
            "weight": v.get("grams"),
        }
        for v in raw.get("variants", [])
    ]

    images = []
    for img in raw.get("images", []):
        src = img.get("src")
        if src:
            images.append(src)

    return {
        "id": raw.get("id"),
        "title": raw.get("title"),
        "handle": raw.get("handle"),
        "url": f"{base_url}/products/{raw.get('handle')}",
        "product_type": raw.get("product_type"),
        "vendor": raw.get("vendor"),
        "tags": normalize_tags(raw.get("tags")),
        "published_at": raw.get("published_at"),
        "created_at": raw.get("created_at"),
        "updated_at": raw.get("updated_at"),
        "options": raw.get("options", []),
        "variants": variants,
        "images": images,
        "body_html": raw.get("body_html", ""),
    }


def fetch_size_guide(base_url: str, products: Optional[list[dict]] = None) -> Optional[dict]:
    session = build_session()
    base_url = base_url.rstrip("/")

    logger.info("  Stratégie 1/4 : pages dédiées")
    result = _try_known_size_pages(session, base_url)
    if result:
        return result

    logger.info("  Stratégie 2/4 : liens du menu / footer / homepage")
    result = _find_size_guide_from_homepage(session, base_url)
    if result:
        return result

    logger.info("  Stratégie 3/4 : FAQ / aide")
    result = _try_faq_pages(session, base_url)
    if result:
        return result

    logger.info("  Stratégie 4/4 : fiches produit")
    if products:
        result = _extract_from_product_pages(session, products)
        if result:
            return result

    logger.warning(f"  Aucun guide de taille trouvé pour {base_url}")
    return None


def _try_known_size_pages(session: requests.Session, base_url: str) -> Optional[dict]:
    for slug in SIZE_GUIDE_SLUGS:
        url = f"{base_url}/pages/{slug}"
        result = _try_fetch_page(session, url, strategy="page dédiée")
        if result:
            return result
    return None


def _try_faq_pages(session: requests.Session, base_url: str) -> Optional[dict]:
    for slug in FAQ_SLUGS:
        url = f"{base_url}/pages/{slug}"
        try:
            response = session.get(url, timeout=20)
            if response.status_code != 200:
                continue

            if page_contains_size_info(response.text):
                logger.info(f"  Infos taille trouvées dans FAQ/aide : {url}")
                parsed = parse_size_guide_page(response.text, url)
                if parsed and (parsed["tables"] or parsed["raw_text"]):
                    return parsed
        except requests.RequestException:
            continue
    return None


def _find_size_guide_from_homepage(session: requests.Session, base_url: str) -> Optional[dict]:
    try:
        response = session.get(base_url, timeout=20)
        response.raise_for_status()
    except requests.RequestException:
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    candidates = []

    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        text = a.get_text(" ", strip=True).lower()
        href_lower = href.lower()

        if _looks_like_size_guide_link(text, href_lower):
            absolute_url = urljoin(base_url + "/", href)
            if _is_same_domain(base_url, absolute_url):
                candidates.append(absolute_url)

    seen = set()
    unique_candidates = []
    for url in candidates:
        if url not in seen:
            seen.add(url)
            unique_candidates.append(url)

    for url in unique_candidates[:15]:
        result = _try_fetch_page(session, url, strategy="lien homepage/menu/footer")
        if result:
            return result

    return None


def _extract_from_product_pages(session: requests.Session, products: list[dict]) -> Optional[dict]:
    checked = 0

    for product in products[:15]:
        url = product.get("url", "")
        if not url:
            continue

        try:
            response = session.get(url, timeout=20)
            if response.status_code != 200:
                continue

            parsed = parse_size_guide_page(response.text, url, fallback_title="Guide des tailles (fiche produit)")
            if parsed and (parsed["tables"] or parsed["raw_text"]):
                logger.info(f"  Guide extrait depuis fiche produit : {url}")
                return parsed

            checked += 1
            time.sleep(0.2)
        except requests.RequestException:
            continue

    logger.info(f"  {checked} fiches produit inspectées sans guide exploitable.")
    return None


def _try_fetch_page(session: requests.Session, url: str, strategy: str = "") -> Optional[dict]:
    try:
        response = session.get(url, timeout=20)
        if response.status_code != 200:
            return None

        parsed = parse_size_guide_page(response.text, url)
        if parsed and (parsed["tables"] or parsed["raw_text"]):
            logger.info(f"  Guide trouvé ({strategy}) : {url}")
            return parsed
    except requests.RequestException:
        return None

    return None


def parse_size_guide_page(html: str, url: str, fallback_title: str = "Guide des tailles") -> dict:
    soup = BeautifulSoup(html, "html.parser")

    title = soup.find("h1") or soup.find("h2") or soup.find("title")
    title_text = title.get_text(" ", strip=True) if title else fallback_title

    tables = []
    for table in soup.find_all("table"):
        if not is_probable_size_table(table):
            continue

        headers = [th.get_text(" ", strip=True) for th in table.find_all("th")]

        rows = []
        for tr in table.find_all("tr"):
            cells = [cell.get_text(" ", strip=True) for cell in tr.find_all(["td", "th"])]
            if cells:
                rows.append(cells)

        if rows:
            final_headers = headers
            final_rows = rows

            if not final_headers and len(rows) >= 2:
                first_row = rows[0]
                if any(_contains_size_signal(cell) for cell in first_row):
                    final_headers = first_row
                    final_rows = rows[1:]

            if final_rows:
                tables.append({
                    "headers": final_headers,
                    "rows": final_rows,
                })

    raw_text = ""
    if not tables:
        raw_text = extract_relevant_size_text(soup)

    return {
        "url": url,
        "title": title_text or fallback_title,
        "tables": tables,
        "raw_text": raw_text,
    }


def is_probable_size_table(table) -> bool:
    text = normalize_space(table.get_text(" ", strip=True)).lower()
    if not text:
        return False

    keywords = [
        "taille", "pointure", "size", "eu", "uk", "us",
        "cm", "inch", "bust", "waist", "hips", "poitrine"
    ]
    score = sum(1 for kw in keywords if kw in text)
    rows = table.find_all("tr")

    return len(rows) >= 2 and score >= 2


def page_contains_size_info(html: str) -> bool:
    lowered = normalize_space(BeautifulSoup(html, "html.parser").get_text(" ", strip=True)).lower()
    hits = sum(1 for kw in SIZE_KEYWORDS if kw in lowered)
    return hits >= 2


def extract_relevant_size_text(soup: BeautifulSoup) -> str:
    blocks = []

    selectors = [
        "main",
        "article",
        "[class*='size']",
        "[id*='size']",
        "[class*='taille']",
        "[id*='taille']",
        "[class*='guide']",
        "[id*='guide']",
        "[class*='faq']",
        "[id*='faq']",
        "[class*='accordion']",
        "[class*='tabs']",
        "[class*='drawer']",
        "[class*='modal']",
    ]

    for selector in selectors:
        try:
            for node in soup.select(selector):
                text = normalize_space(node.get_text(" ", strip=True))
                if _text_looks_relevant(text):
                    blocks.append(text)
        except Exception:
            continue

    if not blocks:
        full_text = normalize_space(soup.get_text(" ", strip=True))
        if _text_looks_relevant(full_text):
            blocks.append(full_text[:4000])

    deduped = []
    seen = set()
    for block in blocks:
        key = block[:500]
        if key not in seen:
            seen.add(key)
            deduped.append(block)

    return "\n\n".join(deduped)[:4000]


def _text_looks_relevant(text: str) -> bool:
    lowered = text.lower()
    hits = sum(1 for kw in SIZE_KEYWORDS if kw in lowered)
    return hits >= 2 and len(text) >= 80


def _contains_size_signal(cell: str) -> bool:
    lowered = cell.lower()
    return any(kw in lowered for kw in ["taille", "size", "pointure", "eu", "uk", "us", "cm"])


def _looks_like_size_guide_link(text: str, href: str) -> bool:
    haystack = f"{text} {href}".lower()
    patterns = [
        "guide des tailles",
        "guide taille",
        "guide pointure",
        "guide des pointures",
        "size guide",
        "size chart",
        "sizing guide",
        "tailles",
        "pointures",
        "mesures",
    ]
    return any(p in haystack for p in patterns)


def _is_same_domain(base_url: str, candidate_url: str) -> bool:
    base_netloc = urlparse(base_url).netloc.replace("www.", "")
    cand_netloc = urlparse(candidate_url).netloc.replace("www.", "")
    return base_netloc == cand_netloc


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()