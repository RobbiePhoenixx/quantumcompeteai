"""Regression tests for FireCrawl scraping.

Guards the "scrape() got an unexpected keyword argument 'params'" bug: the
modern firecrawl-py SDK (v2+, incl. 4.x) takes `formats=[...]` and has no
`params=` kwarg. The scrape call must use the modern signature.
"""
from unittest.mock import patch

import services.firecrawl as firecrawl_service


class _FakeDoc:
    markdown = "# Hello\n\nworld text here"
    metadata = {"title": "Test Title"}


def test_scrape_uses_modern_formats_not_params(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-key")
    calls = {}

    class FakeApp:
        def __init__(self, api_key=None):
            pass

        def scrape(self, url, **kwargs):
            calls["url"] = url
            calls["kwargs"] = kwargs
            return _FakeDoc()

    with patch("firecrawl.FirecrawlApp", FakeApp):
        result = firecrawl_service.scrape_url("https://example.com/article")

    # The crux of the fix: never send the legacy `params` kwarg to modern scrape().
    assert "params" not in calls["kwargs"]
    assert calls["kwargs"].get("formats") == ["markdown"]
    assert result["markdown"].startswith("# Hello")
    assert result["title"] == "Test Title"
    assert result["word_count"] > 0
    assert result["demo"] is False


def test_scrape_falls_back_to_legacy_scrape_url(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-key")
    calls = {}

    class LegacyApp:
        def __init__(self, api_key=None):
            pass

        # No modern scrape(); only legacy scrape_url(url, params=...).
        # It rejects `formats` so the service must fall back to `params`.
        def scrape_url(self, url, params=None):
            calls["params"] = params
            return {"markdown": "# Legacy\n\nbody", "metadata": {"title": "Old"}}

    with patch("firecrawl.FirecrawlApp", LegacyApp):
        result = firecrawl_service.scrape_url("https://example.com/old")

    assert calls["params"] == {"formats": ["markdown"]}
    assert result["title"] == "Old"


def test_scrape_demo_mode_without_key(monkeypatch):
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    result = firecrawl_service.scrape_url("https://example.com")
    assert result["demo"] is True
