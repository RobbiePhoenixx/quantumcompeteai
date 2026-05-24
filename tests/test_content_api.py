import json
from unittest.mock import patch


def test_create_content_requires_auth(client):
    resp = client.post("/content/api/create",
                       data=json.dumps({"input_text": "test"}),
                       content_type="application/json")
    assert resp.status_code == 401

def test_list_items(auth_client):
    resp = auth_client.get("/content/api/items")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert isinstance(data, list)

def test_delete_nonexistent(auth_client):
    resp = auth_client.delete("/content/api/9999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Publish: the "Publish Now" button must actually send, and the item should
# only flip to "published" when the post genuinely went out.
# ---------------------------------------------------------------------------
def _make_item(app, status="ready", platform="tiktok"):
    from models import ContentItem
    from extensions import db
    with app.app_context():
        item = ContentItem(input_text="x", input_type="idea",
                           platform=platform, status=status, script="hello")
        db.session.add(item)
        db.session.commit()
        return item.id


def test_publish_marks_published_on_success(auth_client, app):
    from models import ContentItem
    from extensions import db
    item_id = _make_item(app)
    with patch("services.getlate.publish_post",
               return_value={"post_id": "p1", "platforms_published": ["tiktok"], "demo": False}):
        resp = auth_client.post("/content/api/{}/publish".format(item_id))
    assert resp.status_code == 200
    with app.app_context():
        assert db.session.get(ContentItem, item_id).status == "published"


def test_publish_does_not_mark_published_on_error(auth_client, app):
    from models import ContentItem
    from extensions import db
    item_id = _make_item(app)
    with patch("services.getlate.publish_post",
               return_value={"error": "No connected account for: tiktok"}):
        resp = auth_client.post("/content/api/{}/publish".format(item_id))
    assert resp.status_code == 200
    body = json.loads(resp.data)
    assert "error" in body
    with app.app_context():
        # Status must be left alone so the user can connect an account and retry.
        assert db.session.get(ContentItem, item_id).status == "ready"


def test_publish_returns_clean_json_on_exception(auth_client, app):
    from models import ContentItem
    from extensions import db
    item_id = _make_item(app)
    # publish_post raising must NOT surface as a 500/HTML page — the button needs
    # JSON with a real reason for its feedback banner.
    with patch("services.getlate.publish_post",
               side_effect=RuntimeError("GetLate 503 Service Unavailable")):
        resp = auth_client.post("/content/api/{}/publish".format(item_id))
    assert resp.status_code == 200
    body = json.loads(resp.data)
    assert "503" in body["error"]
    with app.app_context():
        assert db.session.get(ContentItem, item_id).status == "ready"
