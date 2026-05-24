"""
blueprints/content_api.py — Content JSON API Blueprint
=======================================================
JSON API routes for content items and the SSE pipeline stream.
Registered at url_prefix="/content/api".

Teaching notes:
- SSE (Server-Sent Events): real-time pipeline updates without WebSockets
- Threading: pipeline runs in background thread, results queued to stream
- publish_post() in services/getlate.py takes a content_item dict — not
  individual caption/platform/media args. We build that dict here.
"""

import json
import queue
import threading
from datetime import datetime
from flask import Blueprint, request, jsonify, Response, current_app
from auth import login_required
from models import ContentItem, PipelineLog
from extensions import db
from services.r2_storage import (
    is_configured as r2_is_configured,
    upload_headshot as r2_upload_headshot,
    get_presigned_url as r2_presigned_url,
    upload_image as r2_upload_image,
    upload_video as r2_upload_video,
)
from services.kie_ai import (
    generate_image as avatar_generate_image,
    generate_video_from_image as avatar_generate_video,
)

content_api_bp = Blueprint("content_api", __name__)


@content_api_bp.route("/create", methods=["POST"])
@login_required
def create():
    """Create content item and run pipeline via SSE stream."""
    data = request.get_json() or {}

    item = ContentItem(
        input_text=data.get("input_text", ""),
        input_type=data.get("input_type", "idea"),
        platform=data.get("platform", "tiktok"),
        include_video=data.get("include_video", False),
        # "queued" (not "draft") so the moment the user lands back on the library
        # the new item already reads as Processing — no race where it flashes as a
        # clickable Draft before the background pipeline advances it.
        status="queued",
    )
    db.session.add(item)
    db.session.commit()

    content_id = item.id
    q = queue.Queue()
    app = current_app._get_current_object()

    def emit(stage, status, message, detail=""):
        q.put(json.dumps({
            "content_id": content_id,
            "stage": stage,
            "status": status,
            "message": message,
            "detail": detail,
        }))

    def run():
        with app.app_context():
            from pipeline import run_pipeline
            run_pipeline(content_id, emit)
        q.put("DONE")

    threading.Thread(target=run, daemon=True).start()

    def stream():
        while True:
            try:
                msg = q.get(timeout=960)  # 16 min max (longer than video timeout)
                if msg == "DONE":
                    yield f"data: {json.dumps({'stage': 'done', 'status': 'complete', 'content_id': content_id})}\n\n"
                    break
                yield f"data: {msg}\n\n"
            except queue.Empty:
                yield f"data: {json.dumps({'stage': 'done', 'status': 'timeout'})}\n\n"
                break

    return Response(stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@content_api_bp.route("/items", methods=["GET"])
@login_required
def list_items():
    """List all content items as JSON."""
    status_filter = request.args.get("status")
    query = ContentItem.query.order_by(ContentItem.created_at.desc())
    if status_filter:
        query = query.filter_by(status=status_filter)
    items = query.all()
    return jsonify([item.to_dict() for item in items])


@content_api_bp.route("/<int:item_id>", methods=["GET"])
@login_required
def get_item(item_id):
    """Get a single content item."""
    item = ContentItem.query.get_or_404(item_id)
    data = item.to_dict()
    data["logs"] = [log.to_dict() for log in item.pipeline_logs]
    return jsonify(data)


@content_api_bp.route("/<int:item_id>", methods=["DELETE"])
@login_required
def delete_item(item_id):
    """Delete a content item."""
    item = ContentItem.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    return jsonify({"success": True})


@content_api_bp.route("/<int:item_id>/publish", methods=["POST"])
@login_required
def publish(item_id):
    """
    Publish content item via GetLate.dev.

    publish_post() in services/getlate.py expects:
        content_item: dict (script, image_url, r2_image_url, video_url,
                            r2_video_url, platform, scheduled_at)
        platforms:    list of platform name strings (optional)
        emit_event:   SSE callback (optional)

    We build a content_item dict from the ORM object and pass it through.
    """
    item = ContentItem.query.get_or_404(item_id)
    from services.getlate import publish_post

    # Build the content_item dict that publish_post() expects
    content_item = {
        "script": item.script or "",
        "platform": item.platform or "tiktok",
        "image_url": item.image_url or "",
        "r2_image_url": item.r2_image_url or "",
        "video_url": item.video_url or "",
        "r2_video_url": item.r2_video_url or "",
        "scheduled_at": getattr(item, "scheduled_at", None),
    }

    # Resolve caption for the item's platform
    if item.captions:
        try:
            captions_dict = json.loads(item.captions)
            content_item["script"] = captions_dict.get(
                item.platform,
                captions_dict.get("default", item.script or "")
            )
        except (json.JSONDecodeError, AttributeError):
            pass  # fall back to item.script set above

    try:
        result = publish_post(
            content_item=content_item,
            platforms=[item.platform] if item.platform else None,
        )
    except Exception as e:
        # Never leak a 500/HTML page to the button — give it clean JSON so the
        # user sees a real reason instead of "check your connection".
        return jsonify({"error": str(e)}), 200

    # Only mark the item as published when the post actually went out (or ran in
    # demo mode). If publishing failed — e.g. no connected social account — leave
    # the status untouched so the user can fix it and retry, and surface the error.
    if result.get("error"):
        return jsonify(result), 200

    item.status = "published"
    item.published_at = datetime.utcnow()
    db.session.commit()

    return jsonify(result)


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
    MAX_PHOTO_BYTES = 15 * 1024 * 1024  # 15 MB — generous for a phone photo
    if request.content_length and request.content_length > MAX_PHOTO_BYTES:
        return jsonify({"error": "Photo is too large (max 15 MB)."}), 400
    result = r2_upload_headshot(f.read(), f.filename)
    key = result.get("key")
    # r2.dev public URLs 403 from Kie servers — hand Kie a presigned URL.
    photo_url = r2_presigned_url(key) if key else result.get("url")
    return jsonify({"photo_url": photo_url, "key": key})


def _rehost_to_r2(content_id, kind, url, is_demo, emit):
    """Copy a generated asset into R2 so it survives Kie's 14-day deletion.

    Returns the URL to display: the permanent R2 URL if the copy worked,
    otherwise the original (temporary) URL. Saves r2_image_url / r2_video_url.
    """
    if not url or is_demo or "placehold" in url or not r2_is_configured():
        return url
    try:
        res = (r2_upload_image if kind == "image" else r2_upload_video)(url, emit_event=emit)
        r2_url = res.get("url")
        if r2_url:
            row = db.session.get(ContentItem, content_id)
            if kind == "image":
                row.r2_image_url = r2_url
            else:
                row.r2_video_url = r2_url
            db.session.commit()
            return r2_url
    except Exception as e:
        emit("r2_upload", "warning",
             f"Could not save the {kind} to R2 ({e}); using the temporary URL for now.")
    return url


@content_api_bp.route("/avatar/generate", methods=["POST"])
@login_required
def avatar_generate():
    """Stream: GPT Image-2 (you in the scene) then Veo image-to-video (8s clip)."""
    data = request.get_json() or {}
    photo_url = data.get("photo_url", "")
    prompt = (data.get("prompt") or "").strip()

    if not photo_url:
        return jsonify({"error": "Upload a photo first."}), 400
    if not prompt:
        return jsonify({"error": "Describe the scene you want."}), 400

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
            img = None
            try:
                emit("image", "started", "Placing you into your scene with GPT Image-2...")
                img = avatar_generate_image(prompt, emit_event=emit, reference_image_url=photo_url)
                image_url = img.get("image_url", "")
                row = db.session.get(ContentItem, content_id)
                row.image_prompt = prompt
                row.image_url = image_url
                row.image_task_id = img.get("task_id", "")
                db.session.commit()

                # Re-host to R2 so the image doesn't vanish when Kie's temporary
                # URL expires (Kie deletes generated media after 14 days).
                display_image = _rehost_to_r2(content_id, "image", image_url, img.get("demo"), emit)

                emit("image", "complete", "Here's you in the scene! Now animating it into an 8-second clip.",
                     {"image_url": display_image})

                # Animate the generated image. Prefer the permanent R2 URL (valid
                # cert, won't expire) over Kie's temporary host as the source Veo
                # has to fetch. Veo occasionally returns a transient "Internal
                # Error, please try again" — retry once so a blip doesn't waste the
                # photo + image the user already generated.
                video_src = display_image or image_url
                vid = None
                for _attempt in range(2):
                    try:
                        vid = avatar_generate_video(video_src, prompt, emit_event=emit)
                        break
                    except Exception as ve:
                        if _attempt == 0:
                            emit("video", "warning",
                                 "Kie hit a transient error on the video — retrying once...")
                            continue
                        raise
                video_url = vid.get("video_url") or ""
                row = db.session.get(ContentItem, content_id)
                row.video_url = video_url
                row.video_task_id = vid.get("task_id", "")
                row.status = "ready"
                db.session.commit()

                if vid.get("timed_out"):
                    emit("video", "warning", "The clip is still rendering — your image is ready now; check back for the video.",
                         {"image_url": display_image})
                else:
                    display_video = _rehost_to_r2(content_id, "video", video_url, vid.get("demo"), emit)
                    emit("video", "complete", "Your 8-second avatar clip is ready!",
                         {"video_url": display_video, "image_url": display_image})
            except Exception as e:
                row = db.session.get(ContentItem, content_id)
                if row:
                    row.status = "failed"
                    db.session.commit()
                detail = {"image_url": img.get("image_url", "")} if img else ""
                emit("pipeline", "error", f"Something went wrong: {e}. Check your Kie.ai key in Settings.", detail)
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
