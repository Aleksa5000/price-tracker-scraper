import argparse
import sys

from . import storage
from .alerts import send_alerts, send_failure_alert
from .scraper import ScrapeError, scrape


def print_report(changes):
    if not changes:
        print("No price changes since the previous run.")
        return
    for label, subset in (("DROPS", [c for c in changes if c["pct"] < 0]),
                          ("INCREASES", [c for c in changes if c["pct"] > 0])):
        if subset:
            print(f"{label} ({len(subset)})")
            for c in sorted(subset, key=lambda c: c["pct"]):
                print(f"  {c['title'][:45]:<45} £{c['old_price']:>6.2f} -> £{c['price']:>6.2f}  {c['pct']:+.1f}%")


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # the £ sign on Windows consoles
    p = argparse.ArgumentParser(prog="tracker", description="Track product prices over time.")
    p.add_argument("--db", default="prices.db", help="SQLite file (default: prices.db)")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scrape", help="scrape books.toscrape.com and store a new run")
    s.add_argument("--pages", type=int, default=1, help="number of listing pages (default: 1)")
    s.add_argument("--delay", type=float, default=1.0, help="seconds between requests (default: 1)")
    s.add_argument("--threshold", type=float, help="alert if a price drops below this value")
    s.add_argument("--drop-pct", type=float, help="alert if a price drops by at least this percent")
    sub.add_parser("report", help="show price changes in the latest run")
    e = sub.add_parser("export", help="export the latest snapshot to CSV")
    e.add_argument("path")
    args = p.parse_args(argv)

    conn = storage.connect(args.db)
    if args.cmd == "scrape":
        try:
            products, skipped = scrape(args.pages, args.delay)
        except ScrapeError as e:  # layout change or block page: store nothing, fail loudly
            print(f"error: {e} No run was stored.", file=sys.stderr)
            send_failure_alert(str(e))
            return 1
        run_id = storage.save_run(conn, products)
        print(f"Run #{run_id}: stored {len(products)} products from {args.pages} page(s).")
        changes = storage.price_changes(conn)
        print_report(changes)
        sent = send_alerts(changes, args.threshold, args.drop_pct)
        if sent:
            print(f"Sent webhook alert for {sent} price drop(s).")
        if skipped:
            print(f"warning: skipped {skipped} malformed product card(s) in this run.", file=sys.stderr)
    elif args.cmd == "report":
        print_report(storage.price_changes(conn))
    else:
        print(f"Exported {storage.export_csv(conn, args.path)} rows to {args.path}")


if __name__ == "__main__":
    sys.exit(main())
