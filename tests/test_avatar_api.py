import io
import json
from unittest.mock import patch


def test_avatar_upload_requires_auth(client):
    resp = client.post("/content/api/avatar/upload")
    assert resp.status_code == 401


def test_avatar_upload_needs_r2(auth_client):
    with patch("blueprints.content_api.r2_is_configured", return_value=False):
        resp = auth_client.post(
            "/content/api/avatar/upload",
            data={"photo": (io.BytesIO(b"fakejpgbytes"), "me.jpg")},
            content_type="multipart/form-data",
        )
    assert resp.status_code == 400
    assert json.loads(resp.data).get("needs_r2") is True


def test_avatar_upload_returns_presigned_url(auth_client):
    with patch("blueprints.content_api.r2_is_configured", return_value=True), \
         patch("blueprints.content_api.r2_upload_headshot", return_value={"url": "https://pub/x.jpg", "key": "headshots/x.jpg", "demo": False}), \
         patch("blueprints.content_api.r2_presigned_url", return_value="https://presigned/x.jpg"):
        resp = auth_client.post(
            "/content/api/avatar/upload",
            data={"photo": (io.BytesIO(b"fakejpgbytes"), "me.jpg")},
            content_type="multipart/form-data",
        )
    assert resp.status_code == 200
    body = json.loads(resp.data)
    assert body["photo_url"] == "https://presigned/x.jpg"
    assert body["key"] == "headshots/x.jpg"


def test_avatar_generate_requires_auth(client):
    resp = client.post("/content/api/avatar/generate",
                       data=json.dumps({"photo_url": "u", "prompt": "p"}),
                       content_type="application/json")
    assert resp.status_code == 401


def test_avatar_generate_streams_image_then_video(auth_client):
    with patch("blueprints.content_api.avatar_generate_image", return_value={"image_url": "https://img/a.png", "task_id": "i1", "cost": 0.09, "demo": False}), \
         patch("blueprints.content_api.avatar_generate_video", return_value={"video_url": "https://vid/a.mp4", "task_id": "v1", "cost": 0.30, "demo": False}):
        resp = auth_client.post(
            "/content/api/avatar/generate",
            data=json.dumps({"photo_url": "https://presigned/x.jpg", "prompt": "on a beach"}),
            content_type="application/json",
        )
        body = resp.get_data(as_text=True)
    assert "https://img/a.png" in body
    assert "https://vid/a.mp4" in body
    assert "image" in body and "video" in body
    assert '"done"' in body


def test_avatar_generate_requires_photo_url(auth_client):
    resp = auth_client.post("/content/api/avatar/generate",
                            data=json.dumps({"photo_url": "", "prompt": "on a beach"}),
                            content_type="application/json")
    assert resp.status_code == 400


def test_avatar_page_renders(auth_client):
    resp = auth_client.get("/content/avatar")
    assert resp.status_code == 200
    assert b"Avatar" in resp.data


def test_avatar_page_warns_when_r2_missing(auth_client):
    from unittest.mock import patch
    with patch("services.r2_storage.is_configured", return_value=False):
        resp = auth_client.get("/content/avatar")
    assert resp.status_code == 200
    # When R2 is not configured the page must tell the student to add R2 keys.
    assert b"R2" in resp.data


# ---------------------------------------------------------------------------
# Avatar media must be re-hosted to R2 so it survives Kie's 14-day deletion.
# ---------------------------------------------------------------------------
def test_rehost_to_r2_returns_r2_url_and_saves(app):
    from blueprints.content_api import _rehost_to_r2
    from models import ContentItem
    from extensions import db
    with app.app_context():
        item = ContentItem(input_text="x", input_type="avatar",
                           platform="tiktok", status="ready")
        db.session.add(item)
        db.session.commit()
        cid = item.id
        with patch("blueprints.content_api.r2_is_configured", return_value=True), \
             patch("blueprints.content_api.r2_upload_image",
                   return_value={"url": "https://r2.dev/x.png"}):
            url = _rehost_to_r2(cid, "image", "https://kie/temp.png", False, lambda *a, **k: None)
        assert url == "https://r2.dev/x.png"
        assert db.session.get(ContentItem, cid).r2_image_url == "https://r2.dev/x.png"


def test_rehost_to_r2_passthrough_when_not_configured(app):
    from blueprints.content_api import _rehost_to_r2
    with app.app_context():
        with patch("blueprints.content_api.r2_is_configured", return_value=False):
            url = _rehost_to_r2(1, "image", "https://kie/temp.png", False, lambda *a, **k: None)
        assert url == "https://kie/temp.png"


def test_generate_image_blank_reference_uses_text_to_image(monkeypatch):
    import services.kie_ai as kie
    from unittest.mock import MagicMock
    monkeypatch.setenv("KIE_AI_API_KEY", "k")
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["json"] = json
        r = MagicMock()
        r.raise_for_status = lambda: None
        r.json = lambda: {"data": {"taskId": "t"}}
        return r

    with patch("services.kie_ai.requests.post", side_effect=fake_post), \
         patch("services.kie_ai.requests.get", side_effect=Exception("stop")), \
         patch("services.kie_ai.time.sleep", side_effect=KeyboardInterrupt):
        try:
            kie.generate_image("a cat", reference_image_url="   ")
        except KeyboardInterrupt:
            pass

    # Blank reference must NOT trigger image-to-image (which would 422).
    assert captured["json"]["model"] == "gpt-image-2-text-to-image"
    assert "input_urls" not in captured["json"]["input"]
