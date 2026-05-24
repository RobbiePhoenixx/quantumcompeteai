"""Tests for platform-specific publishing in services/getlate.py.

The Late API needs per-platform data: TikTok requires consent flags (or it
rejects the post), Instagram rejects text-only posts and wants Reels in the
feed, YouTube requires a title. These guard that payload shaping.
"""
from unittest.mock import patch, MagicMock

import services.getlate as getlate


def _accounts(*platforms):
    return [{"platform": p, "_id": "acct_" + p} for p in platforms]


def _capture_post():
    """Patch requests.post to capture the JSON payload and return a fake 200."""
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        resp = MagicMock()
        resp.raise_for_status = lambda: None
        resp.json = lambda: {"id": "post_123"}
        return resp

    return captured, fake_post


def test_tiktok_includes_required_consent_fields(monkeypatch):
    monkeypatch.setenv("ZERNIO_API_KEY", "k")
    captured, fake_post = _capture_post()
    with patch("services.getlate.get_connected_accounts", return_value=_accounts("tiktok")), \
         patch("services.getlate.requests.post", side_effect=fake_post):
        result = getlate.publish_post(
            {"script": "hi", "video_url": "https://cdn/v.mp4"}, platforms=["tiktok"])
    psd = captured["json"]["platforms"][0]["platformSpecificData"]
    assert psd["contentPreviewConfirmed"] is True
    assert psd["expressConsentGiven"] is True
    assert psd["allowComment"] is True and psd["allowDuet"] is True and psd["allowStitch"] is True
    assert result["status"] == "published"


def test_instagram_video_sets_share_to_feed(monkeypatch):
    monkeypatch.setenv("ZERNIO_API_KEY", "k")
    captured, fake_post = _capture_post()
    with patch("services.getlate.get_connected_accounts", return_value=_accounts("instagram")), \
         patch("services.getlate.requests.post", side_effect=fake_post):
        getlate.publish_post(
            {"script": "hi", "r2_video_url": "https://cdn/v.mp4"}, platforms=["instagram"])
    psd = captured["json"]["platforms"][0]["platformSpecificData"]
    assert psd["shareToFeed"] is True


def test_instagram_without_media_is_skipped(monkeypatch):
    monkeypatch.setenv("ZERNIO_API_KEY", "k")
    captured, fake_post = _capture_post()
    with patch("services.getlate.get_connected_accounts", return_value=_accounts("instagram")), \
         patch("services.getlate.requests.post", side_effect=fake_post):
        result = getlate.publish_post({"script": "text only"}, platforms=["instagram"])
    # Nothing should be posted; a clear media error is returned.
    assert "json" not in captured
    assert result["status"] == "no_accounts"
    assert "image or video" in result["error"].lower()


def test_youtube_includes_title(monkeypatch):
    monkeypatch.setenv("ZERNIO_API_KEY", "k")
    captured, fake_post = _capture_post()
    with patch("services.getlate.get_connected_accounts", return_value=_accounts("youtube")), \
         patch("services.getlate.requests.post", side_effect=fake_post):
        getlate.publish_post(
            {"script": "My great video\nmore text", "video_url": "https://cdn/v.mp4"},
            platforms=["youtube"])
    psd = captured["json"]["platforms"][0]["platformSpecificData"]
    assert psd["title"] == "My great video"
    assert psd["visibility"] == "public"


def test_twitter_has_no_required_platform_data(monkeypatch):
    monkeypatch.setenv("ZERNIO_API_KEY", "k")
    captured, fake_post = _capture_post()
    with patch("services.getlate.get_connected_accounts", return_value=_accounts("twitter")), \
         patch("services.getlate.requests.post", side_effect=fake_post):
        getlate.publish_post(
            {"script": "tweet", "image_url": "https://cdn/i.png"}, platforms=["twitter"])
    entry = captured["json"]["platforms"][0]
    # No platformSpecificData needed for plain Twitter posts.
    assert "platformSpecificData" not in entry
    assert captured["json"]["mediaItems"] == [{"type": "image", "url": "https://cdn/i.png"}]
