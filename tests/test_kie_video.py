"""Veo payload correctness — the root-cause fix for broken video generation.

Kie.ai's /veo/generate requires generationType + the right image key
(images for image-to-video, imageUrls for reference-to-video) + generateAudio:false.
The old code sent reference_images (ignored), so the photo never reached Veo.
"""
from unittest.mock import patch, MagicMock
import services.kie_ai as kie_ai


def _mock_post_returns_task():
    resp = MagicMock()
    resp.raise_for_status = lambda: None
    resp.json = lambda: {"data": {"taskId": "t-123"}}
    return resp


def test_image_to_video_sends_correct_veo_payload(monkeypatch):
    monkeypatch.setenv("KIE_AI_API_KEY", "k")
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return _mock_post_returns_task()

    with patch("services.kie_ai.requests.post", side_effect=fake_post), \
         patch("services.kie_ai.requests.get", side_effect=Exception("stop")), \
         patch("services.kie_ai.time.sleep", side_effect=KeyboardInterrupt):
        try:
            kie_ai.generate_video_from_image("https://img/x.png", "wave hello")
        except KeyboardInterrupt:
            pass

    assert captured["url"].endswith("/veo/generate")
    body = captured["json"]
    assert body["generationType"] == "IMAGE_2_VIDEO"
    assert body["images"] == ["https://img/x.png"]
    assert body["generateAudio"] is False
    assert body["model"] == "veo3_fast"
    assert body["aspect_ratio"] == "9:16"


def test_reference_video_sends_correct_veo_payload(monkeypatch):
    monkeypatch.setenv("KIE_AI_API_KEY", "k")
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["json"] = json
        return _mock_post_returns_task()

    with patch("services.kie_ai.requests.post", side_effect=fake_post), \
         patch("services.kie_ai.requests.get", side_effect=Exception("stop")), \
         patch("services.kie_ai.time.sleep", side_effect=KeyboardInterrupt):
        try:
            kie_ai.generate_video_with_reference("scene", "https://img/face.png")
        except KeyboardInterrupt:
            pass

    body = captured["json"]
    assert body["generationType"] == "REFERENCE_2_VIDEO"
    assert body["imageUrls"] == ["https://img/face.png"]
    assert "reference_images" not in body
    assert body["generateAudio"] is False


def test_image_to_video_demo_mode_without_key(monkeypatch):
    monkeypatch.delenv("KIE_AI_API_KEY", raising=False)
    monkeypatch.delenv("KIE_API_KEY", raising=False)
    result = kie_ai.generate_video_from_image("https://img/x.png", "wave")
    assert result["demo"] is True
    assert "placeholder" in result["video_url"] or "placehold" in result["video_url"]
