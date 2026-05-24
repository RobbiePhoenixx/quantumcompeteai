# Avatar Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a simple "Avatar" page where a student uploads one photo + a scene description and gets back a still image of themselves in that scene plus an 8-second video of that same scene animated.

**Architecture:** Photo → R2 (presigned URL) → GPT Image-2 image-to-image → Veo 3.1 image-to-video. New page + two endpoints; the video step reuses a corrected Kie.ai Veo payload. The video animates the exact generated image, so the still and clip always match. Also fixes the existing reference-video function (same root-cause bug).

**Tech Stack:** Flask, SQLAlchemy, Kie.ai (GPT Image-2, Veo 3.1 `veo3_fast`), Cloudflare R2, SSE, pytest.

**Spec:** `docs/superpowers/specs/2026-05-23-avatar-generator-design.md`

---

## File Structure

- `services/kie_ai.py` (modify) — add `generate_video_from_image()`; fix `generate_video_with_reference()` payload.
- `tests/test_kie_video.py` (create) — payload + demo-mode tests for both functions.
- `blueprints/content_api.py` (modify) — add `/avatar/upload` and `/avatar/generate` (SSE).
- `blueprints/content.py` (modify) — add `GET /content/avatar` route.
- `templates/content/avatar.html` (create) — upload + prompt + live result + X-ray.
- `templates/base_admin.html` (modify) — add "Avatar" sidebar link.
- `tests/test_avatar_api.py` (create) — endpoint tests (auth, needs_r2, SSE).

---

### Task 1: Fix + add Veo payloads in `services/kie_ai.py`

**Files:**
- Modify: `services/kie_ai.py`
- Test: `tests/test_kie_video.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_kie_video.py
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

    # Stop polling immediately after task creation by making the status loop raise.
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_kie_video.py -v`
Expected: FAIL — `generate_video_from_image` does not exist; reference test fails on old `reference_images` payload.

- [ ] **Step 3: Implement**

In `services/kie_ai.py`:

(a) Fix the create payload inside `generate_video_with_reference()` (the `requests.post` to `VIDEO_CREATE_URL`):

```python
        create_response = requests.post(
            VIDEO_CREATE_URL,
            headers=headers,
            json={
                "prompt": prompt,
                "model": "veo3_fast",
                "aspect_ratio": "9:16",
                "generationType": "REFERENCE_2_VIDEO",  # Veo reference-to-video mode
                "generateAudio": False,                  # bypass Kie audio safety filter
                "imageUrls": [reference_image_url],       # correct key (was reference_images)
            },
            timeout=30
        )
```

(b) Add a new function. Put it after `generate_video_with_reference()`. It mirrors that function's two-phase polling and return shape — extract the shared polling into a private helper `_poll_veo_task(task_id, headers, emit, cost)` and call it from all three video functions to stay DRY:

```python
def generate_video_from_image(image_url, prompt, emit_event=None):
    """Animate a static image into an 8s clip via Veo 3.1 (image-to-video).

    Used by the Avatar page: the image already contains the student's face
    (placed there by GPT Image-2), so animating it keeps the still and the
    clip the same scene.
    """
    emit = emit_event or (lambda *a, **kw: None)
    prompt = _clean_prompt(prompt or "Subtle, natural movement. Camera slowly pushes in.")
    headers = _get_headers()

    if not headers:
        emit("video", "progress", "No Kie.ai API key set yet — showing a placeholder. Add your key in Settings > Kie.ai.")
        return {
            "video_url": "https://placehold.co/1080x1920/17181C/C7A35A?text=Add+Kie.ai+Key+in+Settings",
            "task_id": "demo_video_i2v_task",
            "duration": 0, "cost": 0.0, "demo": True,
        }

    emit("video", "progress", "Animating your photo into an 8-second clip with Veo 3.1 (image-to-video). This takes a few minutes.")
    try:
        create_response = requests.post(
            VIDEO_CREATE_URL,
            headers=headers,
            json={
                "prompt": prompt,
                "model": "veo3_fast",
                "aspect_ratio": "9:16",
                "generationType": "IMAGE_2_VIDEO",  # Veo image-to-video mode
                "generateAudio": False,             # bypass Kie audio safety filter
                "images": [image_url],              # i2v uses "images" (ref uses "imageUrls")
            },
            timeout=30
        )
        create_response.raise_for_status()
        create_data = create_response.json()
        data = create_data.get("data") or create_data
        task_id = data.get("taskId") or data.get("task_id") or create_data.get("taskId")
        if not task_id:
            raise Exception(f"No task_id in response: {create_data}")
        emit("video", "progress", f"Video task created! ID: {task_id}. Polling for the result...")
    except requests.exceptions.RequestException as e:
        emit("video", "error", f"Failed to create video task: {str(e)}")
        raise

    return _poll_veo_task(task_id, headers, emit, cost=0.30)
```

Extract `_poll_veo_task(task_id, headers, emit, cost)` from the existing two-phase
polling loop (PHASE_1_INTERVAL=30, PHASE_1_DURATION=300, PHASE_2_INTERVAL=60,
MAX_POLL_TIME=900; success_flag mapping; `resultUrls`/`videoUrl` extraction;
graceful `timed_out=True` return). Call it from `generate_video()`,
`generate_video_with_reference()`, and `generate_video_from_image()`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_kie_video.py tests/test_service_keys.py -v`
Expected: PASS (new tests green; existing key tests still green).

- [ ] **Step 5: Commit**

```bash
git add services/kie_ai.py tests/test_kie_video.py
git commit -m "fix: correct Kie Veo payload (generationType/imageUrls/generateAudio) + add image-to-video"
```

---

### Task 2: Avatar upload + generate endpoints in `blueprints/content_api.py`

**Files:**
- Modify: `blueprints/content_api.py`
- Test: `tests/test_avatar_api.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_avatar_api.py
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
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_avatar_api.py -v`
Expected: FAIL — routes/imports don't exist.

- [ ] **Step 3: Implement endpoints**

Add to `blueprints/content_api.py` imports (alias to keep tests patchable):

```python
from services.r2_storage import (
    is_configured as r2_is_configured,
    upload_headshot as r2_upload_headshot,
    get_presigned_url as r2_presigned_url,
)
from services.kie_ai import (
    generate_image as avatar_generate_image,
    generate_video_from_image as avatar_generate_video,
)
```

Upload route:

```python
@content_api_bp.route("/avatar/upload", methods=["POST"])
@login_required
def avatar_upload():
    """Upload the student's photo to R2 and return a presigned URL Kie can fetch."""
    if not r2_is_configured():
        return jsonify({"error": "R2 not configured", "needs_r2": True}), 400
    f = request.files.get("photo")
    if not f or not f.filename:
        return jsonify({"error": "No photo uploaded"}), 400
    if not (f.mimetype or "").startswith("image/"):
        return jsonify({"error": "Please upload an image file"}), 400
    result = r2_upload_headshot(f.read(), f.filename)
    key = result.get("key")
    # r2.dev public URLs 403 from Kie servers — hand Kie a presigned URL.
    photo_url = r2_presigned_url(key) if key else result.get("url")
    return jsonify({"photo_url": photo_url, "key": key})
```

Generate route (SSE — mirror the existing `create()` threading/queue pattern):

```python
@content_api_bp.route("/avatar/generate", methods=["POST"])
@login_required
def avatar_generate():
    """Stream: GPT Image-2 (you in the scene) then Veo image-to-video (8s clip)."""
    data = request.get_json() or {}
    photo_url = data.get("photo_url", "")
    prompt = data.get("prompt", "").strip()

    item = ContentItem(
        input_text=prompt, input_type="avatar", platform="tiktok",
        include_video=True, status="draft",
    )
    db.session.add(item)
    db.session.commit()
    content_id = item.id

    q = queue.Queue()
    app = current_app._get_current_object()

    def emit(stage, status, message, detail=""):
        q.put(json.dumps({"content_id": content_id, "stage": stage,
                          "status": status, "message": message, "detail": detail}))

    def run():
        with app.app_context():
            try:
                emit("image", "started", "Placing you into your scene with GPT Image-2...")
                img = avatar_generate_image(prompt, emit_event=emit, reference_image_url=photo_url)
                row = db.session.get(ContentItem, content_id)
                row.image_prompt = prompt
                row.image_url = img.get("image_url", "")
                row.image_task_id = img.get("task_id", "")
                db.session.commit()
                emit("image", "complete", "Here's you in the scene! Now animating it into an 8-second clip.",
                     {"image_url": img.get("image_url", "")})

                vid = avatar_generate_video(img.get("image_url", ""), prompt, emit_event=emit)
                row = db.session.get(ContentItem, content_id)
                row.video_url = vid.get("video_url") or ""
                row.video_task_id = vid.get("task_id", "")
                row.status = "ready"
                db.session.commit()
                if vid.get("timed_out"):
                    emit("video", "warning", "The clip is still rendering — your image is ready now; check back for the video.",
                         {"image_url": img.get("image_url", "")})
                else:
                    emit("video", "complete", "Your 8-second avatar clip is ready!",
                         {"video_url": vid.get("video_url", ""), "image_url": img.get("image_url", "")})
            except Exception as e:
                row = db.session.get(ContentItem, content_id)
                if row:
                    row.status = "failed"
                    db.session.commit()
                emit("pipeline", "error", f"Something went wrong: {e}. Check your Kie.ai key in Settings.")
        q.put("DONE")

    threading.Thread(target=run, daemon=True).start()

    def stream():
        while True:
            try:
                msg = q.get(timeout=960)
                if msg == "DONE":
                    yield f"data: {json.dumps({'stage': 'done', 'status': 'complete', 'content_id': content_id})}\n\n"
                    break
                yield f"data: {msg}\n\n"
            except queue.Empty:
                yield f"data: {json.dumps({'stage': 'done', 'status': 'timeout'})}\n\n"
                break

    return Response(stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_avatar_api.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add blueprints/content_api.py tests/test_avatar_api.py
git commit -m "feat: avatar upload + generate (image-then-video SSE) endpoints"
```

---

### Task 3: Avatar page (route + template + nav link)

**Files:**
- Modify: `blueprints/content.py` (add `GET /content/avatar`)
- Create: `templates/content/avatar.html`
- Modify: `templates/base_admin.html` (sidebar link after Create)
- Test: `tests/test_avatar_api.py` (add page route test)

- [ ] **Step 1: Write the failing test**

```python
def test_avatar_page_renders(auth_client):
    resp = auth_client.get("/content/avatar")
    assert resp.status_code == 200
    assert b"Avatar" in resp.data
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_avatar_api.py::test_avatar_page_renders -v`
Expected: FAIL — 404.

- [ ] **Step 3: Implement**

In `blueprints/content.py` add:

```python
@content_bp.route("/avatar")
@login_required
def avatar():
    """Baby one-off: upload a photo -> image + 8s video of you in the scene."""
    from services.r2_storage import is_configured as r2_is_configured
    return render_template("content/avatar.html", r2_ready=r2_is_configured())
```

Create `templates/content/avatar.html` (extends `base_admin.html`, Alpine.js):
- If `not r2_ready`: show a notice "Add your R2 keys in Settings to use Avatar" and disable the form.
- Form: file input (`photo`, accept `image/*`) with preview, a textarea (scene prompt), a Generate button.
- On submit: `POST /content/api/avatar/upload` (FormData) → get `photo_url`; then open the SSE `POST /content/api/avatar/generate` via `fetch` + `ReadableStream` reader (the existing create.html already streams SSE this way — copy that reader pattern).
- Render the X-ray log (each SSE `message`), show the image when `image complete` arrives, then the `<video controls>` when `video complete` arrives.

Add sidebar link in `templates/base_admin.html` after the Create link (line ~71):

```html
            <a href="/content/avatar" class="sidebar-link {% if request.path == '/content/avatar' %}active{% endif %}">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="8" r="4"/><path d="M4 21v-1a8 8 0 0 1 16 0v1"/></svg>
                <span x-show="sidebarOpen">Avatar</span>
            </a>
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_avatar_api.py -v`
Expected: PASS.

- [ ] **Step 5: Manual smoke (optional, needs real keys)**

`python app.py` → log in → `/content/avatar` → upload a photo + "standing in a sunny park" → confirm image appears, then 8s video.

- [ ] **Step 6: Commit**

```bash
git add blueprints/content.py templates/content/avatar.html templates/base_admin.html tests/test_avatar_api.py
git commit -m "feat: Avatar page (upload photo -> image + 8s video)"
```

---

## Final Verification

- [ ] Run full suite: `python -m pytest tests/ -v` (or at least `tests/test_kie_video.py tests/test_avatar_api.py tests/test_service_keys.py tests/test_content_api.py`).
- [ ] Confirm no regression in existing content pipeline tests.
