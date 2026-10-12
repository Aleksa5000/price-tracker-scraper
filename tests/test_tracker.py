import csv
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from tracker import alerts, scraper, storage
from tracker.__main__ import main
from tracker.scraper import parse_page

FIX = Path(__file__).parent / "fixtures"
URL = "https://books.toscrape.com/index.html"
PAGE2 = "https://books.toscrape.com/catalogue/page-2.html"
BLOCKED = "<html><body><h1>Access denied</h1></body></html>"  # no product list at all


def load():
    return parse_page((FIX / "page1.html").read_text(encoding="utf-8"), URL)


def test_parse_page():
    products, nxt, skipped = load()
    assert len(products) == 20 and skipped == 0
    first = products[0]
    assert first["title"] == "A Light in the Attic"
    assert first["price"] == 51.77
    assert first["rating"] == 3
    assert first["availability"] == "In stock"
    assert first["url"] == "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"
    assert nxt == "https://books.toscrape.com/catalogue/page-2.html"


def test_next_link_on_second_page():
    html = (FIX / "page2.html").read_text(encoding="utf-8")
    _, nxt, _ = parse_page(html, PAGE2)
    assert nxt == "https://books.toscrape.com/catalogue/page-3.html"


def test_price_changes_and_csv(tmp_path):
    conn = storage.connect(tmp_path / "t.db")
    products, _, _ = load()
    storage.save_run(conn, products)
    assert storage.price_changes(conn) == []  # first run: nothing to compare

    products[0]["price"] = 40.00   # drop
    products[1]["price"] = 100.00  # increase
    storage.save_run(conn, products)
    changes = {c["title"]: c for c in storage.price_changes(conn)}
    assert len(changes) == 2
    assert changes[products[0]["title"]]["pct"] < 0
    assert changes[products[1]["title"]]["pct"] > 0

    out = tmp_path / "out.csv"
    assert storage.export_csv(conn, out) == 20
    with open(out, encoding="utf-8") as f:
        rows = {r["title"]: r["price"] for r in csv.DictReader(f)}
    assert rows[products[0]["title"]] == "40.0"


class FakeResponse:
    def raise_for_status(self):
        pass


def test_alerts(monkeypatch):
    posted = []
    monkeypatch.setattr(alerts.requests, "post",
                        lambda url, json, timeout: posted.append(json) or FakeResponse())
    changes = [{"title": "Book", "old_price": 50.0, "price": 40.0, "pct": -20.0}]

    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)
    assert alerts.send_alerts(changes, threshold=45) == 0 and not posted  # unset: silent

    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://example.test/hook")
    assert alerts.send_alerts(changes, threshold=45) == 1
    assert "Book" in posted[0]["text"] and posted[0]["text"] == posted[0]["content"]
    assert alerts.send_alerts(changes, min_drop_pct=30) == 0  # drop too small


def page1_without(pattern):
    """Page 1 with the first match of a regex cut out, which breaks the first card."""
    return re.sub(pattern, "", (FIX / "page1.html").read_text(encoding="utf-8"), count=1, flags=re.S)


def serve(monkeypatch, pages):
    """Answer scraper.fetch from {url: html}, so scrape() never touches the network."""
    monkeypatch.setattr(scraper, "fetch", lambda session, url, delay: pages[url])


def run_cli(tmp_path):
    return main(["--db", str(tmp_path / "t.db"), "scrape", "--delay", "0"])


def stored_rows(tmp_path):
    return storage.connect(tmp_path / "t.db").execute("SELECT COUNT(*) FROM price_history").fetchone()[0]


@pytest.mark.parametrize("pattern, field", [
    (r'<p class="price_color">.*?</p>', "price"),
    (r'<p class="star-rating.*?</p>', "rating"),
    (r'<p class="instock availability">.*?</p>', "availability"),
    (r'title="A Light in the Attic"', "title"),
])
def test_broken_card_is_skipped(pattern, field, capsys):
    products, _, skipped = parse_page(page1_without(pattern), URL)
    assert skipped == 1 and len(products) == 19  # the other cards still parse
    assert products[0]["title"] != "A Light in the Attic"
    err = capsys.readouterr().err
    assert URL in err and f"missing {field}" in err


def test_scrape_counts_skipped_cards(monkeypatch):
    serve(monkeypatch, {URL: page1_without(r'<p class="price_color">.*?</p>'),
                        PAGE2: (FIX / "page2.html").read_text(encoding="utf-8")})
    products, skipped = scraper.scrape(pages=2, delay=0)
    assert (len(products), skipped) == (39, 1)


def test_scrape_without_products_fails(monkeypatch, capsys):
    serve(monkeypatch, {URL: BLOCKED})
    with pytest.raises(scraper.ScrapeError, match="layout"):
        scraper.scrape(pages=1, delay=0)
    assert f"{URL}: no valid products" in capsys.readouterr().err


def test_empty_page_in_the_middle_only_warns(monkeypatch, capsys):
    nxt = '<li class="next"><a href="catalogue/page-2.html">next</a></li>'
    serve(monkeypatch, {URL: nxt, PAGE2: (FIX / "page2.html").read_text(encoding="utf-8")})
    products, _ = scraper.scrape(pages=2, delay=0)
    assert len(products) == 20
    assert f"{URL}: no valid products" in capsys.readouterr().err


def test_cli_reports_skipped_cards(tmp_path, monkeypatch, capsys):
    serve(monkeypatch, {URL: page1_without(r'<p class="price_color">.*?</p>')})
    assert run_cli(tmp_path) is None
    out, err = capsys.readouterr()
    assert "stored 19 products" in out and "skipped 1 malformed" in err
    assert stored_rows(tmp_path) == 19


def test_cli_without_products_fails_and_alerts(tmp_path, monkeypatch, capsys):
    serve(monkeypatch, {URL: BLOCKED})
    posted = []
    monkeypatch.setattr(alerts.requests, "post",
                        lambda url, json, timeout: posted.append(json) or FakeResponse())

    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)
    assert run_cli(tmp_path) == 1
    err = capsys.readouterr().err
    assert "layout" in err and "blocked" in err and not posted  # unset: no alert

    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://example.test/hook")
    assert run_cli(tmp_path) == 1
    assert "scrape failed" in posted[0]["text"]
    assert stored_rows(tmp_path) == 0  # no run was written


def test_failure_alert_survives_dead_webhook(monkeypatch, capsys):
    def down(url, json, timeout):
        raise alerts.requests.ConnectionError("down")
    monkeypatch.setattr(alerts.requests, "post", down)
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://example.test/hook")
    assert alerts.send_failure_alert("x") is False
    assert "could not send" in capsys.readouterr().err


def test_python_m_tracker_exits_non_zero(tmp_path):
    # runs tracker/__main__.py for real, with the network call swapped for a blocked page
    code = ("import runpy, tracker.scraper as s; s.fetch = lambda *a, **k: '<html></html>';"
            "runpy.run_module('tracker', run_name='__main__')")
    r = subprocess.run([sys.executable, "-c", code, "--db", str(tmp_path / "t.db"), "scrape"],
                       cwd=Path(__file__).parent.parent, capture_output=True, text=True,
                       env={**os.environ, "ALERT_WEBHOOK_URL": ""})  # never hit a real webhook
    assert r.returncode == 1 and "layout" in r.stderr
