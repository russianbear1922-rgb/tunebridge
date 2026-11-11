from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from unittest import mock

from fastapi.testclient import TestClient
from starlette.requests import Request

from app import accounts, ads, config, db, legal, main, stats
from app.ratelimit import RateLimiter


def _request(path: str = "/privacy", query: bytes = b"", headers: list | None = None) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "query_string": query,
            "headers": headers or [],
            "client": ("127.0.0.1", 1),
        }
    )


class DbIsolated(unittest.TestCase):
    """База во временном каталоге; поток TestClient видит тот же путь через env."""

    def setUp(self) -> None:
        self.old_path = os.environ.get("TUNEBRIDGE_DB_PATH")
        self.tempdir = tempfile.mkdtemp(prefix="tunebridge-surface-")
        db.use_path(os.path.join(self.tempdir, "test.db"))

    def tearDown(self) -> None:
        db.close_current()
        if self.old_path is None:
            os.environ.pop("TUNEBRIDGE_DB_PATH", None)
        else:
            os.environ["TUNEBRIDGE_DB_PATH"] = self.old_path
        shutil.rmtree(self.tempdir, ignore_errors=True)


class RateLimiterTest(unittest.TestCase):
    def test_blocks_after_limit_and_reports_retry(self) -> None:
        limiter = RateLimiter(3, 60)
        for _ in range(3):
            allowed, retry = limiter.check("ip")
            self.assertTrue(allowed)
            self.assertEqual(retry, 0.0)
        allowed, retry = limiter.check("ip")
        self.assertFalse(allowed)
        self.assertGreater(retry, 0.0)

    def test_keys_are_independent(self) -> None:
        limiter = RateLimiter(1, 60)
        self.assertTrue(limiter.check("a")[0])
        self.assertFalse(limiter.check("a")[0])
        self.assertTrue(limiter.check("b")[0])

    def test_reset_clears_hits(self) -> None:
        limiter = RateLimiter(1, 60)
        limiter.check("a")
        self.assertFalse(limiter.check("a")[0])
        limiter.reset()
        self.assertTrue(limiter.check("a")[0])

    def test_window_expiry(self) -> None:
        clock = [1000.0]
        with mock.patch("app.ratelimit.time.monotonic", lambda: clock[0]):
            limiter = RateLimiter(2, 10)
            self.assertTrue(limiter.check("k")[0])
            self.assertTrue(limiter.check("k")[0])
            self.assertFalse(limiter.check("k")[0])
            clock[0] += 11
            self.assertTrue(limiter.check("k")[0])


class AdCountersTest(DbIsolated):
    AD = {"label": "Реклама", "title": "T", "text": "", "cta": "", "url": "https://x.example", "image": ""}

    def test_record_aggregates_by_day_and_kind(self) -> None:
        with mock.patch.object(config, "AD", self.AD):
            self.assertTrue(ads.record("view"))
            self.assertTrue(ads.record("view"))
            self.assertTrue(ads.record("click"))
        result = ads.stats()
        self.assertEqual(result["views"], 2)
        self.assertEqual(result["clicks"], 1)
        self.assertEqual(result["ctr"], 50.0)
        self.assertEqual(len(result["days"]), 1)

    def test_invalid_kind_is_rejected(self) -> None:
        with mock.patch.object(config, "AD", self.AD):
            self.assertFalse(ads.record("bogus"))
        self.assertEqual(ads.stats()["views"], 0)

    def test_no_ad_slot_means_no_recording(self) -> None:
        with mock.patch.object(config, "AD", None):
            self.assertFalse(ads.record("view"))
        self.assertEqual(ads.stats()["views"], 0)

    def test_stats_days_are_clamped(self) -> None:
        with mock.patch.object(config, "AD", self.AD):
            ads.record("view")
        self.assertEqual(ads.stats(days=0)["views"], 1)
        self.assertEqual(ads.stats(days=1000)["views"], 1)


class StatsOverviewTest(DbIsolated):
    def test_empty_overview_shape(self) -> None:
        result = stats.overview()
        for key in ("users", "new_users", "transfers", "transfers_week", "tracks", "sources", "targets", "recent", "ads"):
            self.assertIn(key, result)
        self.assertEqual(result["users"], 0)
        self.assertEqual(result["transfers"], 0)
        self.assertEqual(result["tracks"], 0)

    def test_counts_users_and_transfers(self) -> None:
        user = accounts.upsert_telegram_user({"id": 9001, "first_name": "Слушатель"})
        with db.write_tx() as conn:
            conn.execute(
                "INSERT INTO transfers(user_id, source_service, source_title, target, playlist_url, added, total, created_at) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                (int(user["id"]), "yandex", "Плейлист", "spotify", "https://open.spotify.com/playlist/x", 7, 10, 1_700_000_000.0),
            )
        result = stats.overview()
        self.assertEqual(result["users"], 1)
        self.assertEqual(result["transfers"], 1)
        self.assertEqual(result["tracks"], 7)
        self.assertEqual(result["sources"][0]["id"], "yandex")
        self.assertEqual(result["targets"][0]["id"], "spotify")
        self.assertEqual(result["recent"][0]["added"], 7)


class LegalRenderTest(unittest.TestCase):
    def test_titles_and_updated_date(self) -> None:
        cases = {
            ("privacy", "ru"): "Политика конфиденциальности",
            ("privacy", "en"): "Privacy Policy",
            ("terms", "ru"): "Условия использования",
            ("terms", "en"): "Terms of Service",
        }
        for (kind, lang), title in cases.items():
            html = legal.render(kind, lang)
            self.assertIn(title, html)
            self.assertIn(legal.UPDATED, html)
            self.assertIn("/static/css/legal.css", html)

    def test_contact_email_preferred(self) -> None:
        with mock.patch.object(config, "CONTACT_EMAIL", "help@example.com"), mock.patch.object(
            config, "CONTACT_TELEGRAM", "someone"
        ):
            label, href = legal._contact()
            html = legal.render("privacy", "ru")
        self.assertEqual(label, "help@example.com")
        self.assertEqual(href, "mailto:help@example.com")
        self.assertIn("help@example.com", html)
        self.assertIn("mailto:help@example.com", html)

    def test_contact_telegram_fallback(self) -> None:
        with mock.patch.object(config, "CONTACT_EMAIL", ""), mock.patch.object(
            config, "CONTACT_TELEGRAM", "tunebridge_help"
        ):
            label, href = legal._contact()
        self.assertEqual(label, "@tunebridge_help")
        self.assertEqual(href, "https://t.me/tunebridge_help")

    def test_no_contact_when_unset(self) -> None:
        with mock.patch.object(config, "CONTACT_EMAIL", ""), mock.patch.object(
            config, "CONTACT_TELEGRAM", ""
        ), mock.patch.object(config, "HOSTED", False):
            label, href = legal._contact()
        self.assertEqual((label, href), ("", ""))


class PageLangTest(unittest.TestCase):
    def test_query_param_wins(self) -> None:
        self.assertEqual(main._page_lang(_request(query=b"lang=en")), "en")
        self.assertEqual(main._page_lang(_request(query=b"lang=ru")), "ru")

    def test_accept_language(self) -> None:
        en = _request(headers=[(b"accept-language", b"en-US,en;q=0.9")])
        ru = _request(headers=[(b"accept-language", b"ru-RU,ru;q=0.9")])
        self.assertEqual(main._page_lang(en), "en")
        self.assertEqual(main._page_lang(ru), "ru")

    def test_default_is_ru(self) -> None:
        self.assertEqual(main._page_lang(_request()), "ru")

    def test_invalid_query_falls_back_to_header(self) -> None:
        req = _request(query=b"lang=fr", headers=[(b"accept-language", b"en")])
        self.assertEqual(main._page_lang(req), "en")


class PublicHttpTest(DbIsolated):
    def setUp(self) -> None:
        super().setUp()
        self.client = TestClient(main.app, raise_server_exceptions=False)
        self.client.__enter__()

    def tearDown(self) -> None:
        self.client.__exit__(None, None, None)
        super().tearDown()

    def test_health_reports_mode_and_free(self) -> None:
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertIn("mode", payload)
        self.assertIn("free", payload)

    def test_index_injects_absolute_seo_urls(self) -> None:
        with mock.patch.object(main, "BASE_URL", "https://tune.example"):
            response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn('href="https://tune.example/"', response.text)
        self.assertIn('content="https://tune.example/static/img/og-image.png"', response.text)
        self.assertIn('content="https://tune.example/"', response.text)

    def test_robots_and_sitemap(self) -> None:
        with mock.patch.object(main, "BASE_URL", "https://tune.example"):
            robots = self.client.get("/robots.txt")
            sitemap = self.client.get("/sitemap.xml")
        self.assertIn("Sitemap: https://tune.example/sitemap.xml", robots.text)
        self.assertIn("Disallow: /api/", robots.text)
        self.assertEqual(sitemap.text.count("<loc>"), 3)
        self.assertIn("/privacy", sitemap.text)
        self.assertIn("/terms", sitemap.text)

    def test_legal_pages_ru_and_en(self) -> None:
        self.assertIn("Политика конфиденциальности", self.client.get("/privacy?lang=ru").text)
        self.assertIn("Privacy Policy", self.client.get("/privacy?lang=en").text)
        self.assertIn("Условия использования", self.client.get("/terms?lang=ru").text)
        self.assertIn("Terms of Service", self.client.get("/terms?lang=en").text)

    def test_manifest_served(self) -> None:
        response = self.client.get("/manifest.webmanifest")
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/manifest+json", response.headers["content-type"])
        self.assertTrue(response.json()["icons"])

    def test_unknown_page_is_html_404(self) -> None:
        response = self.client.get("/no-such-page")
        self.assertEqual(response.status_code, 404)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("Страница не найдена", response.text)

    def test_unknown_api_is_json_404(self) -> None:
        response = self.client.get("/api/no-such-endpoint")
        self.assertEqual(response.status_code, 404)
        self.assertIn("application/json", response.headers["content-type"])

    def test_unhandled_page_error_is_html_500(self) -> None:
        @main.app.get("/__boom_html")
        def _boom() -> dict:
            raise RuntimeError("boom")

        try:
            with mock.patch.object(main, "logger"):
                response = self.client.get("/__boom_html")
            self.assertEqual(response.status_code, 500)
            self.assertIn("text/html", response.headers["content-type"])
            self.assertIn("Что-то сломалось", response.text)
        finally:
            main.app.router.routes[:] = [
                route for route in main.app.router.routes if getattr(route, "path", None) != "/__boom_html"
            ]

    def test_unhandled_api_error_is_json_500(self) -> None:
        @main.app.get("/api/__boom")
        def _boom() -> dict:
            raise RuntimeError("boom")

        try:
            with mock.patch.object(main, "logger"):
                response = self.client.get("/api/__boom")
            self.assertEqual(response.status_code, 500)
            self.assertEqual(response.json()["message"], "Внутренняя ошибка сервера")
        finally:
            main.app.router.routes[:] = [
                route for route in main.app.router.routes if getattr(route, "path", None) != "/api/__boom"
            ]

    def test_oversized_body_is_413(self) -> None:
        with mock.patch.object(main, "RATE_LIMIT_ENABLED", True), mock.patch.object(main, "MAX_BODY_BYTES", 5):
            response = self.client.post("/api/ads/event", json={"kind": "view"})
        self.assertEqual(response.status_code, 413)

    def test_rate_limit_returns_429_with_retry_after(self) -> None:
        fresh = RateLimiter(2, 60)
        with mock.patch.object(main, "RATE_LIMIT_ENABLED", True), mock.patch.object(main, "_limiter_global", fresh):
            self.assertEqual(self.client.get("/api/health").status_code, 200)
            self.assertEqual(self.client.get("/api/health").status_code, 200)
            blocked = self.client.get("/api/health")
        self.assertEqual(blocked.status_code, 429)
        self.assertIn("Retry-After", blocked.headers)

    def test_ad_event_endpoint_records_and_rejects(self) -> None:
        ad = {"label": "Реклама", "title": "T", "text": "", "cta": "", "url": "https://x.example", "image": ""}
        with mock.patch.object(config, "AD", ad):
            ok = self.client.post("/api/ads/event", json={"kind": "view"})
            bad = self.client.post("/api/ads/event", json={"kind": "nope"})
        self.assertEqual(ok.json(), {"ok": True})
        self.assertEqual(bad.json(), {"ok": False})

    def test_admin_stats_available_to_local_admin(self) -> None:
        response = self.client.get("/api/admin/stats")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        for key in ("users", "transfers", "tracks", "ads", "recent", "sources", "targets"):
            self.assertIn(key, payload)


if __name__ == "__main__":
    unittest.main()