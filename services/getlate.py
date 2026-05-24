"""
services/getlate.py — Publishing via GetLate.dev
==================================================
Multi-platform social media publishing in one API call.
Students learn: this is the "output" stage — where content goes live.
"""

import os
import requests
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# API endpoint
# ---------------------------------------------------------------------------
GETLATE_BASE_URL = "https://getlate.dev/api/v1"


def _parse_scheduled_time(scheduled_at_str):
    """Parse a scheduled_at string into UTC ISO 8601 format."""
    formats = [
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(scheduled_at_str, fmt)
            dt_utc = dt.replace(tzinfo=timezone.utc)
            return dt_utc.isoformat()
        except (ValueError, TypeError):
            continue
    # Can't parse — return as-is
    return scheduled_at_str


def _get_headers():
    """Build auth headers for GetLate API."""
    # .env.example / the Settings page call this ZERNIO_API_KEY (the rebrand).
    # GETLATE_API_KEY is kept as a fallback for older .env files.
    api_key = os.getenv("ZERNIO_API_KEY") or os.getenv("GETLATE_API_KEY")
    if not api_key:
        return None
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }


# ---------------------------------------------------------------------------
# _platform_specific_data() — per-platform options the Late API needs
# ---------------------------------------------------------------------------
def _platform_specific_data(platform, has_image, has_video, content_item):
    """Build the `platformSpecificData` block Late expects for each platform.

    These aren't cosmetic — some are required or the post silently fails:
      - TikTok rejects a post without the consent/interaction flags.
      - Instagram videos should be Reels surfaced in the feed.
      - YouTube needs a title.
    Verified against the Late API platform docs.
    """
    if platform == "instagram":
        # A video auto-publishes as a Reel; shareToFeed also puts it in the
        # main feed. (Instagram requires media — that's enforced by the caller.)
        return {"shareToFeed": True} if has_video else {}

    if platform == "tiktok":
        # Required: contentPreviewConfirmed + expressConsentGiven; allowComment
        # for all, allowDuet/allowStitch for videos. videoMadeWithAi is honest
        # disclosure since this app generates the content with AI.
        return {
            "privacyLevel": "PUBLIC_TO_EVERYONE",
            "contentPreviewConfirmed": True,
            "expressConsentGiven": True,
            "allowComment": True,
            "allowDuet": True,
            "allowStitch": True,
            "videoMadeWithAi": True,
        }

    if platform == "youtube":
        # YouTube requires a title. Use the article title, else the first line
        # of the script, else a sane default.
        title = (content_item.get("article_title")
                 or (content_item.get("script") or "").strip().split("\n")[0]
                 or "New video")
        return {
            "title": title[:100],
            "visibility": "public",
            "containsSyntheticMedia": True,  # AI-content disclosure
        }

    if platform == "facebook":
        page_id = content_item.get("facebook_page_id")
        return {"pageId": page_id} if page_id else {}

    return {}


# ---------------------------------------------------------------------------
# publish_post() — Send content to connected social accounts
# ---------------------------------------------------------------------------
def publish_post(content_item, platforms=None, emit_event=None):
    """
    Publish a content item to social media via GetLate.dev.

    Args:
        content_item: dict from the database (must have script, image_url, etc.)
        platforms: list of platform names to publish to (defaults to item's platform)
        emit_event: Callback for SSE logging

    Returns:
        dict with: post_id, platforms_published, status
    """
    emit = emit_event or (lambda *a, **kw: None)
    headers = _get_headers()

    if not platforms:
        platforms = [content_item.get("platform", "instagram")]

    if not headers:
        emit("publish", "progress", "No GetLate API key set yet — simulating publish. To publish for real, get your key from https://getlate.dev and paste it in Settings > GetLate > API Key.")
        return {
            "post_id": "demo_post_id",
            "platforms_published": platforms,
            "status": "demo",
            "demo": True,
            "message": "Get your key from https://getlate.dev and add it in Settings."
        }

    emit("publish", "progress", f"Publishing to {', '.join(platforms)} via GetLate.dev...")

    try:
        # The Late API targets a specific connected account per platform.
        # Without accountId it can't actually publish — the post silently
        # lands as a DRAFT (this was Paul's "it went out as a draft" bug).
        accounts = get_connected_accounts(emit_event)
        by_platform = {}
        for acct in accounts:
            plat = acct.get("platform")
            acct_id = acct.get("_id") or acct.get("id") or acct.get("accountId")
            if plat and acct_id and plat not in by_platform:
                by_platform[plat] = acct_id

        # Resolve media up front — per-platform rules depend on it. Prefer the
        # permanent R2 URLs (Instagram needs a public, direct CDN link — no
        # Google Drive/Dropbox).
        image_url = content_item.get("r2_image_url") or content_item.get("image_url")
        video_url = content_item.get("r2_video_url") or content_item.get("video_url")
        has_image, has_video = bool(image_url), bool(video_url)

        target_platforms = []
        missing = []
        skipped_no_media = []
        for p in platforms:
            if p not in by_platform:
                missing.append(p)
                continue
            # Instagram rejects text-only posts — it requires an image or video.
            if p == "instagram" and not (has_image or has_video):
                skipped_no_media.append(p)
                continue
            entry = {"platform": p, "accountId": by_platform[p]}
            psd = _platform_specific_data(p, has_image, has_video, content_item)
            if psd:
                entry["platformSpecificData"] = psd
            target_platforms.append(entry)

        if not target_platforms:
            reason = f"No connected account for: {', '.join(platforms)}"
            if skipped_no_media:
                reason = ("Instagram needs an image or video to post — generate "
                          "media first, then publish.")
            emit("publish", "error", reason)
            return {
                "post_id": None,
                "platforms_published": [],
                "status": "no_accounts",
                "demo": False,
                "error": reason,
            }
        if missing:
            emit("publish", "progress",
                 f"Skipping (not connected): {', '.join(missing)}")
        if skipped_no_media:
            emit("publish", "progress",
                 "Skipping Instagram — it needs an image or video (no text-only posts).")

        # Build the post payload in the shape the Late API expects.
        payload = {
            "content": content_item.get("script", ""),
            "platforms": target_platforms,
        }

        # Media is a top-level `mediaItems` array (the old `media` key was
        # ignored by the API, so images never attached — Paul's "no image" bug).
        media_items = []
        if image_url:
            media_items.append({"type": "image", "url": image_url})
        if video_url:
            media_items.append({"type": "video", "url": video_url})
        if media_items:
            payload["mediaItems"] = media_items

        # Publish now vs schedule. Without an explicit flag the API defaults
        # to saving a draft instead of posting.
        if content_item.get("scheduled_at"):
            parsed_time = _parse_scheduled_time(content_item["scheduled_at"])
            if parsed_time:
                payload["scheduledFor"] = parsed_time
                payload["timezone"] = "America/Los_Angeles"
            else:
                payload["publishNow"] = True
        else:
            payload["publishNow"] = True

        response = requests.post(
            f"{GETLATE_BASE_URL}/posts",
            headers=headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()

        post_id = data.get("id", data.get("post_id", "unknown"))

        emit("publish", "progress",
             f"Published! Post ID: {post_id}")

        return {
            "post_id": post_id,
            "platforms_published": [t["platform"] for t in target_platforms],
            "status": "published",
            "demo": False,
            "response": data
        }

    except requests.exceptions.RequestException as e:
        error_msg = str(e)
        emit("publish", "error", f"GetLate error: {error_msg}")
        raise


# ---------------------------------------------------------------------------
# get_connected_accounts() — List connected social accounts
# ---------------------------------------------------------------------------
def get_connected_accounts(emit_event=None):
    """
    Fetch the list of connected social media accounts from GetLate.dev.

    Returns:
        list of account dicts with: id, platform, username, status
    """
    emit = emit_event or (lambda *a, **kw: None)
    headers = _get_headers()

    if not headers:
        # Return demo accounts so the UI has something to show
        return [
            {"id": "demo_1", "platform": "instagram", "username": "@demo_user", "status": "demo"},
            {"id": "demo_2", "platform": "tiktok", "username": "@demo_user", "status": "demo"},
            {"id": "demo_3", "platform": "linkedin", "username": "Demo User", "status": "demo"},
        ]

    try:
        response = requests.get(
            f"{GETLATE_BASE_URL}/accounts",
            headers=headers,
            timeout=15
        )
        response.raise_for_status()
        data = response.json()
        # The endpoint may return a bare list or {"accounts": [...]}.
        if isinstance(data, list):
            return data
        return data.get("accounts", []) or data.get("data", [])

    except requests.exceptions.RequestException as e:
        emit("publish", "error", f"Failed to fetch connected accounts: {str(e)}")
        return []
