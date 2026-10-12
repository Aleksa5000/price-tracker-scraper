import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

START_URL = "https://books.toscrape.com/index.html"
HEADERS = {"User-Agent": "price-tracker-scraper/1.0 (+https://github.com/Aleksa5000/price-tracker-scraper)"}
RATINGS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}


def parse_page(html, page_url):
    """Return (products, next_page_url or None) for one listing page."""
    soup = BeautifulSoup(html, "html.parser")
    products = []
    for card in soup.select("article.product_pod"):
        link = card.h3.a
        stars = card.select_one("p.star-rating")["class"][1]
        products.append({
            "title": link["title"],
            "price": float(re.search(r"[\d.]+", card.select_one(".price_color").text).group()),
            "availability": card.select_one(".availability").get_text(strip=True),
            "rating": RATINGS.get(stars, 0),
            "url": urljoin(page_url, link["href"]),
        })
    nxt = soup.select_one("li.next a")
    return products, urljoin(page_url, nxt["href"]) if nxt else None


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
    session = requests.Session()
    session.headers.update(HEADERS)
    url, products = START_URL, []
    for _ in range(pages):
        found, next_url = parse_page(fetch(session, url, delay=delay), url)
        products += found
        if not next_url:
            break
        url = next_url
        time.sleep(delay)  # be polite between pages
    return products
