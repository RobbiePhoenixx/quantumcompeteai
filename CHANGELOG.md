# Changelog

All notable changes to the All-in-One Business App, newest first.
The version shown in the sidebar footer (`templates/base_admin.html`) should match
the latest released version here.

Format: each weekly release gets a `## vX.Y — YYYY-MM-DD` section grouped into
**Added / Fixed / Changed**. Keep entries short and student-readable.

---

## v5.1 — 2026-05-23

### Added
- **Avatar generator** (`/content/avatar`): upload a photo + describe a scene →
  get a still image of yourself in it, then an 8-second video of that same scene.
  Built on GPT Image-2 (image-to-image) + Veo 3.1 (image-to-video).
- **Live "Processing" library**: submitting on the Create screen now sends you
  straight to the Content Library, where the new item shows a non-clickable
  Processing card that auto-refreshes to Ready (with confetti) when it finishes —
  so you can batch-create instead of waiting on one screen.
- **Real-time publish feedback**: the detail page shows Processing → Posted /
  Not-posted, with the actual reason on failure.
- **More publish platforms** in the Create dropdown: Facebook, Threads, Pinterest
  (alongside TikTok, Instagram, YouTube, LinkedIn, X/Twitter).
- **Jackie live voice** (OpenAI Realtime API) + robust API-key detection so a
  valid key never silently drops to demo mode.
- `POST_INSTRUCTIONS.md` student setup guide.
- `CHANGELOG.md` (this file).

### Fixed
- **Video polling hit the wrong endpoint** — it polled `/veo/get-1080p-video`
  (an HD-fetch endpoint that returns `data:null` for 720p jobs), so it read
  "processing" forever and never noticed a success OR failure (looked like a
  15-minute hang). Now polls `/veo/record-info`, which returns the real
  `successFlag` + result URLs + error message. Avatar also retries the video once
  on a transient Kie error and feeds Veo the permanent R2 image URL.
- **Kie API key pasted as "Bearer <key>"** is now tolerated (stripped) instead of
  producing "Bearer Bearer <key>" and failing every image/video request — a
  common student paste mistake.
- **Jackie live voice was silent (just text)**: the browser used the retired
  Beta WebSocket + `openai-insecure-api-key` method with an ephemeral key, which
  the GA Realtime API rejects. Rewrote the browser transport to **WebRTC** (the
  supported GA path: ephemeral key + SDP exchange to `/v1/realtime/calls`), with
  native mic capture, audio playback, mute, and a data channel for transcripts.
  (Still requires a real OpenAI key with Realtime access — not an OpenRouter key.)
- **Kie image/video "broken/expiring" bug** (the big one): Kie serves generated
  media from a temporary host that (a) deletes files after 14 days and (b)
  occasionally fails TLS with `[SSL: BAD_SIGNATURE]`. The R2 re-host download now
  retries once with verification disabled so the bytes always come through and
  get copied to your permanent Cloudflare R2 bucket. The pipeline also stops
  falsely claiming "permanent URLs" when an upload actually failed.
- **Avatar media now re-hosted to R2** too (was keeping raw 14-day Kie URLs).
- **Veo video generation**: corrected the Kie payload — `imageUrls` /
  `generationType` / `generateAudio:false` (the old `reference_images` key was
  ignored, so the photo never reached the video).
- **Publish "button not working"**: it was a dead stub that never called the API;
  now it actually publishes via the publish endpoint.
- **X/Twitter never matched**: the dropdown used `x` but Late identifies the
  platform as `twitter`.
- **Platform-specific publishing**: TikTok now sends the required consent flags
  (was getting rejected), Instagram videos post as Reels in the feed and
  text-only IG posts are skipped with a clear message, YouTube includes a title.
- **FireCrawl scraping crashed** with `scrape() got an unexpected keyword
  argument 'params'` on firecrawl-py v4 — now uses the modern `scrape(formats=…)`
  signature.
- **Delete on the detail page** hit a 404 URL (`/content/api/item/<id>`); fixed
  to `/content/api/<id>`.
- **Publish endpoint** only marks an item "published" on real success and always
  returns clean JSON (no 500/HTML pages) so the UI can show a real reason.
- `generate_image` guards the image-to-image branch so a blank reference can't
  trigger a 422 (falls back to text-to-image).

### Changed
- New content items are created as `queued` (not `draft`) so they read as
  Processing immediately on the library.
- `generate_image` docstring/comments corrected (GPT Image-2, not Nano Banana Pro).

---

## v5.0 — baseline

- Initial workshop release: CRM + content automation pipeline, bookings, digital
  products store, Jackie AI assistant, email, R2 storage, GetLate/Zernio
  publishing, feature-toggle blueprints.
