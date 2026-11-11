"""Рекламный блок и обезличенные счётчики его показа/кликов."""

from __future__ import annotations

from datetime import date, timedelta

from . import config, db

KINDS = {"view", "click"}


def current() -> dict[str, str] | None:
    return config.AD


def record(kind: str) -> bool:
    """Агрегат по дням без идентификаторов пользователя."""
    if kind not in KINDS or config.AD is None:
        return False
    day = date.today().isoformat()
    with db.write_tx() as conn:
        conn.execute(
            "INSERT INTO ad_events(day, kind, count) VALUES(?, ?, 1) "
            "ON CONFLICT(day, kind) DO UPDATE SET count = count + 1",
            (day, kind),
        )
    return True


def stats(days: int = 14) -> dict:
    days = max(1, min(int(days), 90))
    cutoff = (date.today() - timedelta(days=days - 1)).isoformat()
    series: dict[str, dict[str, int]] = {}
    for row in db.rows(
        "SELECT day, kind, count FROM ad_events WHERE day >= ? ORDER BY day", (cutoff,)
    ):
        bucket = series.setdefault(row["day"], {"view": 0, "click": 0})
        if row["kind"] in bucket:
            bucket[row["kind"]] = int(row["count"])
    views = sum(item["view"] for item in series.values())
    clicks = sum(item["click"] for item in series.values())
    return {
        "views": views,
        "clicks": clicks,
        "ctr": round(clicks * 100.0 / views, 1) if views else 0.0,
        "days": [{"day": day, **counts} for day, counts in sorted(series.items())],
    }