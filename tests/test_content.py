def test_content_index_requires_auth(client):
    resp = client.get("/content/")
    assert resp.status_code == 302

def test_content_index_loads(auth_client):
    resp = auth_client.get("/content/")
    assert resp.status_code == 200

def test_content_create_page_loads(auth_client):
    resp = auth_client.get("/content/create")
    assert resp.status_code == 200

def test_content_detail_404(auth_client):
    resp = auth_client.get("/content/9999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Content Library: a piece that's still processing must NOT be clickable.
# (After submitting on the Create screen the user is bounced here while the
# pipeline runs in the background — they shouldn't be able to open a half-baked
# item, and the page should auto-refresh it via the .is-processing hook.)
# ---------------------------------------------------------------------------
def test_processing_item_is_not_clickable(auth_client, app):
    from models import ContentItem
    from extensions import db
    with app.app_context():
        item = ContentItem(input_text="batch idea", input_type="idea",
                           platform="tiktok", status="scripting")
        db.session.add(item)
        db.session.commit()
        item_id = item.id

    resp = auth_client.get("/content/")
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    # No link to the detail page for a processing item...
    assert 'href="/content/{}"'.format(item_id) not in html
    # ...and it's flagged for the live-refresh poll + shows the processing state.
    assert "is-processing" in html
    assert "Processing" in html


def test_ready_item_is_clickable(auth_client, app):
    from models import ContentItem
    from extensions import db
    with app.app_context():
        item = ContentItem(input_text="finished idea", input_type="idea",
                           platform="tiktok", status="ready")
        db.session.add(item)
        db.session.commit()
        item_id = item.id

    resp = auth_client.get("/content/")
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert 'href="/content/{}"'.format(item_id) in html
