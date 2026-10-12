import csv
from pathlib import Path

from tracker import alerts, storage
from tracker.scraper import parse_page

FIX = Path(__file__).parent / "fixtures"
URL = "https://books.toscrape.com/index.html"


def load():
    return parse_page((FIX / "page1.html").read_text(encoding="utf-8"), URL)


def test_parse_page():
    products, nxt = load()
    assert len(products) == 20
    first = products[0]
    assert first["title"] == "A Light in the Attic"
    assert first["price"] == 51.77
    assert first["rating"] == 3
    assert first["availability"] == "In stock"
    assert first["url"] == "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"
    assert nxt == "https://books.toscrape.com/catalogue/page-2.html"


def test_next_link_on_second_page():
    html = (FIX / "page2.html").read_text(encoding="utf-8")
    _, nxt = parse_page(html, "https://books.toscrape.com/catalogue/page-2.html")
    assert nxt == "https://books.toscrape.com/catalogue/page-3.html"


def test_price_changes_and_csv(tmp_path):
    conn = storage.connect(tmp_path / "t.db")
    products, _ = load()
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
