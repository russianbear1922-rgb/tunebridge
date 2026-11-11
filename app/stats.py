"""Сводка для оператора: пользователи, переносы и реклама."""

from __future__ import annotations

import time

from . import accounts, ads, db


def overview(days: int = 14) -> dict:
    now = time.time()
    week = now - 7 * 86400
    real_users = "telegram_id IS NOT NULL AND telegram_id != 0"
    users = int(db.scalar(f"SELECT COUNT(*) FROM users WHERE {real_users}", default=0) or 0)
    new_users = int(
        db.scalar(f"SELECT COUNT(*) FROM users WHERE {real_users} AND created_at >= ?", (week,), default=0) or 0
    )
    transfers = int(db.scalar("SELECT COUNT(*) FROM transfers", default=0) or 0)
    transfers_week = int(
        db.scalar("SELECT COUNT(*) FROM transfers WHERE created_at >= ?", (week,), default=0) or 0
    )
    tracks = int(db.scalar("SELECT COALESCE(SUM(added), 0) FROM transfers", default=0) or 0)
    sources = [
        {"id": row["source_service"], "count": int(row["total"])}
        for row in db.rows(
            "SELECT source_service, COUNT(*) AS total FROM transfers "
            "WHERE source_service IS NOT NULL GROUP BY source_service ORDER BY total DESC LIMIT 6"
        )
    ]
    targets = [
        {"id": row["target"], "count": int(row["total"])}
        for row in db.rows(
            "SELECT target, COUNT(*) AS total FROM transfers "
            "WHERE target IS NOT NULL GROUP BY target ORDER BY total DESC LIMIT 6"
        )
    ]
    recent = [
        {
            "source_title": row["source_title"],
            "source": row["source_service"],
            "target": row["target"],
            "target_name": row["target"],
            "url": row["playlist_url"],
            "added": int(row["added"]),
            "total": int(row["total"]),
            "created_at": accounts.iso(row["created_at"]),
            "user": row["first_name"] or row["username"] or "Гость",
        }
        for row in db.rows(
            "SELECT t.source_title, t.source_service, t.target, t.playlist_url, t.added, t.total, t.created_at, "
            "u.first_name, u.username FROM transfers t LEFT JOIN users u ON u.id = t.user_id "
            "ORDER BY t.id DESC LIMIT 10"
        )
    ]
    return {
        "users": users,
        "new_users": new_users,
        "transfers": transfers,
        "transfers_week": transfers_week,
        "tracks": tracks,
        "sources": sources,
        "targets": targets,
        "recent": recent,
        "ads": ads.stats(days),
    }