# Avatar Generator — Design Spec

**Date:** 2026-05-23
**Status:** Approved (design), pending implementation
**Author:** Jonathan + Claude

## Summary

A new, self-contained "Avatar" page for students: upload one photo, type a short
scene description, and get back **one still image of yourself in that scene** plus
**one 8-second video of that same scene animated**. It is a deliberately stripped-down
("baby") version of the proprietary Content Automation Machine — no scraping,
scripting, captions, multi-platform, or publishing. Just photo in → image + clip out.

It also fixes the root-cause bug that currently breaks video generation across the app.

## Goals

- A simple, reliable one-off generator a beginner can use in one screen.
- The still image and the video are always the **same scene** (no reconciliation).
- Fix the real reason Veo video generation doesn't work today.
- Reuse what the app already has (GPT Image-2 image-to-image, R2 upload, SSE X-ray,
  two-phase polling). Add as little new surface as possible.

## Non-Goals (keep it "baby")

- No FireCrawl scraping, no LLM scripting, no captions, no multi-platform fan-out,
  no GetLate publishing, no character sheets / B-roll engine.
- Not a replacement for the proprietary CAM. No proprietary tooling is exposed.

## Root-Cause Fix

Veo on Kie.ai is currently called with the wrong request shape. The working
proprietary CAM code (`Content-Automation-Machine 2.0/app/services/kie_ai.py`)
shows the correct payload for `/veo/generate`:

- Reference-to-video needs: `generationType: "REFERENCE_2_VIDEO"`, `imageUrls: [...]`,
  `generateAudio: false`.
- Image-to-video needs: `generationType: "IMAGE_2_VIDEO"`, `images: [imageUrl]`,
  `generateAudio: false`.

The app's current `generate_video_with_reference()` sends `reference_images: [...]`
(an unrecognized key) and omits `generationType` and `generateAudio`. Kie therefore
ignores the photo (falls back to plain text-to-video) or the request fails the audio
safety filter. `generateAudio: false` bypasses that filter — a reliability default
carried over from CAM.

### Changes to `services/kie_ai.py`

1. **New** `generate_video_from_image(image_url, prompt, emit_event=None)` — Veo
   image-to-video. Payload:
   ```json
   {
     "prompt": "<motion prompt>",
     "model": "veo3_fast",
     "aspect_ratio": "9:16",
     "generationType": "IMAGE_2_VIDEO",
     "generateAudio": false,
     "images": ["<image_url>"]
   }
   ```
   Reuses the existing two-phase patient polling and graceful-timeout return shape
   (`timed_out=True`).

2. **Fix** existing `generate_video_with_reference()` so the main pipeline's headshot
   video also works: `reference_images` → `imageUrls`, add
   `generationType: "REFERENCE_2_VIDEO"` and `generateAudio: false`. Same root cause,
   minimal edit.

## User Flow

```
Upload photo ─▶ R2 (presigned URL) ─▶ GPT Image-2 image-to-image ─▶ IMAGE (you in scene)
                                                                          │
                                                       Veo 3.1 IMAGE_2_VIDEO (animate image)
                                                                          ▼
                                                                   8-second VIDEO
```

Two AI calls. Because the video animates the exact image just produced, the still and
the clip are guaranteed to be the same scene.

## Components

| Piece | Responsibility | Location |
|---|---|---|
| Avatar page | Upload field + scene prompt + live result (image, then video) with the SSE X-ray log | `templates/content/avatar.html`; route `GET /content/avatar` in `blueprints/content.py` |
| Upload endpoint | Receive multipart photo → R2 → return a **presigned** URL Kie can fetch | `POST /content/api/avatar/upload` in `blueprints/content_api.py` |
| Generate endpoint | SSE stream: image stage (GPT Image-2 i2i) → video stage (Veo i2v); persist result | `POST /content/api/avatar/generate` in `blueprints/content_api.py` |
| i2v service | Correct Veo image-to-video payload + polling | `services/kie_ai.py` |
| Storage | `upload_headshot(bytes, filename)` → `get_presigned_url(key)` | reuse `services/r2_storage.py` |
| Persistence | Save as a `ContentItem` (reuse `image_url`, `video_url`, `image_prompt`) so it lists in the Content Library and reuses the detail view | `models.py` (existing) |

## Data Flow / Contracts

1. **Upload** — `POST /content/api/avatar/upload` (multipart, field `photo`).
   - Validates an image file is present and is an image content-type.
   - Uploads raw bytes via `r2_storage.upload_headshot`.
   - Returns `{ "photo_url": "<presigned r2 url>", "key": "<r2 key>" }`.
   - If R2 not configured → `400 { "error": "R2 not configured", "needs_r2": true }`.

2. **Generate** — `POST /content/api/avatar/generate` (JSON
   `{ "photo_url": "...", "prompt": "..." }`) → `text/event-stream`.
   - Creates a `ContentItem` (`input_type="avatar"`, `platform="tiktok"`,
     `include_video=True`, status `draft`).
   - **Image stage:** `generate_image(prompt, reference_image_url=photo_url)` →
     save `image_url`, emit SSE `image complete` with the URL (UI shows it immediately).
   - **Video stage:** `generate_video_from_image(image_url, prompt)` → save `video_url`,
     emit SSE `video complete`; on timeout emit `video warning` and finish with the
     image only.
   - Marks item `ready`, emits `done`.
   - SSE event shape matches the existing pipeline:
     `{ stage, status, message, detail }`.

## Error Handling

- **No R2:** page renders a clear "Add your R2 keys in Settings to use Avatar"
  notice; upload endpoint returns `needs_r2`. No silent failure.
- **No Kie key:** `generate_image` / `generate_video_from_image` already return demo
  placeholders — surfaced in the X-ray as a "add your Kie.ai key" message.
- **Video timeout:** graceful — the still image is still delivered; the X-ray explains
  the clip may still be processing (existing `timed_out` behavior).
- **Bad upload (no file / not an image):** `400` with a friendly message.

## Testing

- `services/kie_ai.py`:
  - `generate_video_from_image` posts the correct payload
    (`generationType=IMAGE_2_VIDEO`, `images=[url]`, `generateAudio=False`,
    `model=veo3_fast`) — assert via mocked `requests.post`.
  - `generate_video_with_reference` now posts `imageUrls` +
    `generationType=REFERENCE_2_VIDEO` + `generateAudio=False` (regression guard for
    the fix).
  - Both return demo placeholder when no API key.
- Endpoints (mock services + R2):
  - upload returns presigned URL; returns `needs_r2` when R2 unset.
  - generate streams image-then-video SSE events and persists a `ContentItem`.

## Open Questions

None blocking. Aspect ratio fixed at 9:16 (portrait) for the baby version.
