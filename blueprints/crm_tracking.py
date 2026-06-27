"""
CRM Email Tracking Blueprint — Quantum Compete AI
Handles open pixel + click redirect tracking for outbound campaigns.

Routes:
  GET /crm/track/open   → 1×1 GIF pixel, logs email open
  GET /crm/track/click  → logs click type, redirects to destination
"""

import urllib.parse
from flask import Blueprint, request, redirect, make_response, abort, current_app
from extensions import db
from models import EmailEvent

crm_tracking_bp = Blueprint("crm_tracking", __name__, url_prefix="/crm/track")

# Minimal transparent 1×1 GIF
_PIXEL = (
    b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00"
    b"\xff\xff\xff\x00\x00\x00\x21\xf9\x04\x00\x00\x00\x00"
    b"\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02"
    b"\x44\x01\x00\x3b"
)


def _log(event_type, destination=None):
    pid = request.args.get("pid", "").strip()
    cid = request.args.get("cid", "").strip()
    if not pid:
        return
    try:
        db.session.add(EmailEvent(
            prospect_id=pid,
            campaign_id=cid,
            event_type=event_type,
            destination=destination,
            ip_address=request.remote_addr,
            user_agent=request.headers.get("User-Agent", ""),
        ))
        db.session.commit()
    except Exception as e:
        current_app.logger.error(f"EmailEvent log failed: {e}")
        db.session.rollback()


@crm_tracking_bp.route("/open")
def track_open():
    _log("open")
    resp = make_response(_PIXEL)
    resp.headers["Content-Type"] = "image/gif"
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    return resp


@crm_tracking_bp.route("/click")
def track_click():
    event_type  = request.args.get("type", "click").strip()
    destination = urllib.parse.unquote(request.args.get("dest", "").strip())

    if destination and not destination.startswith(("http://", "https://")):
        abort(400)

    _log(event_type, destination=destination)
    return redirect(destination or "https://quantumcompete.ai", code=302)
