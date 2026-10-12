import os

import requests


def send_alerts(changes, threshold=None, min_drop_pct=None):
    """Post price drops to ALERT_WEBHOOK_URL (Slack/Discord-compatible). No-op if unset."""
    url = os.environ.get("ALERT_WEBHOOK_URL")
    if not url:
        return 0
    hits = [
        c for c in changes
        if c["pct"] < 0
        and ((threshold is not None and c["price"] < threshold)
             or (min_drop_pct is not None and -c["pct"] >= min_drop_pct))
    ]
    if not hits:
        return 0
    lines = [f"{c['title']}: £{c['old_price']:.2f} -> £{c['price']:.2f} ({c['pct']:+.1f}%)" for c in hits]
    text = "Price drops detected:\n" + "\n".join(lines)
    # "text" is read by Slack, "content" by Discord
    requests.post(url, json={"text": text, "content": text}, timeout=10).raise_for_status()
    return len(hits)
