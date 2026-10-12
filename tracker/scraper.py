import re
import sys
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

START_URL = "https://books.toscrape.com/index.html"
HEADERS = {"User-Agent": "price-tracker-scraper/1.0 (+https://github.com/Aleksa5000/price-tracker-scraper)"}
RATINGS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}


class ScrapeError(Exception):
    """The scrape produced no usable products."""


def _need(value, field):
    """Return value, or raise ValueError naming the card field that is missing."""
    if value is None:
        raise ValueError(field)
    return value


def parse_page(html, page_url):
    """Return (products, next_page_url or None, skipped_card_count) for one listing page."""
    soup = BeautifulSoup(html, "html.parser")
    products, skipped = [], 0
    for n, card in enumerate(soup.select("article.product_pod"), 1):
        try:
            link = _need(card.select_one("h3 a"), "title")
            price_tag = _need(card.select_one(".price_color"), "price")
            price = _need(re.search(r"\d+(?:\.\d+)?", price_tag.text), "price")
            availability = _need(card.select_one(".availability"), "availability")
            stars = _need(card.select_one("p.star-rating"), "rating")["class"][-1]
            products.append({
                "title": _need(link.get("title"), "title"),
                "price": float(price.group()),
                "availability": availability.get_text(strip=True),
                "rating": RATINGS.get(stars, 0),
                "url": urljoin(page_url, _need(link.get("href"), "url")),
            })
        except ValueError as e:  # a broken card must not kill the page
            skipped += 1
            print(f"warning: {page_url}: skipped product card {n}, missing {e}", file=sys.stderr)
    nxt = soup.select_one("li.next a")
    return products, urljoin(page_url, nxt["href"]) if nxt else None, skipped


def fetch(session, url, retries=3, delay=1.0):
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, timeout=15)
            resp.raise_for_status()
            resp.encoding = "utf-8"
            return resp.text
        except requests.RequestException:
            if attempt == retries:
                raise
            time.sleep(delay * attempt)  # simple linear backoff


def scrape(pages=1, delay=1.0):
    """Return (products, skipped_card_count); raise ScrapeError if no valid product was found."""
    session = requests.Session()
    session.headers.update(HEADERS)
    url, products, skipped = START_URL, [], 0
    for _ in range(pages):
        found, next_url, bad = parse_page(fetch(session, url, delay=delay), url)
        if not found:
            print(f"warning: {url}: no valid products on this page", file=sys.stderr)
        products += found
        skipped += bad
        if not next_url:
            break
        url = next_url
        time.sleep(delay)  # be polite between pages
    if not products:
        raise ScrapeError(f"No valid products found ({skipped} malformed card(s) skipped). "
                          "The site layout has probably changed or the request was blocked.")
    return products, skipped
