# Master Qualification Survey → CRM → Hot-Lead Alert — Design

**Date:** 2026-05-17
**Status:** Approved (design), pending spec review
**Owner:** Jonathan Acuna (Doctor AI / Simple Tech Skills)

## Problem

Leads enter from many sources (lead magnets on simpletechskills, TikTok, Instagram,
Facebook, YouTube) and from workshop signups, but there is no single point that
**assesses, segments, and qualifies** them. High-value leads (small teams /
businesses) are not contacted fast. The goal — modeled on the "fill form →
immediate qualifying callback" sales process — is:

> Every lead fills ONE survey. The CRM scores them instantly. A team-of-2+ lead
> triggers an immediate SMS to Jonathan so he can call within minutes. Everyone
> else is auto-segmented to the right offer (course / workshop / Academy) and
> nurtured via Kit.

## Goals

- One master survey used by all lead-magnet sources AND workshop students.
- Answers land in the existing **All-in-One Business App CRM** (Flask/SQLAlchemy,
  Railway-ready) as the system of record.
- Automatic lead scoring + segmentation.
- Instant **SMS** (Twilio) to Jonathan on a hot lead (team size 2+).
- After submit, route the lead to the correct lead-magnet thank-you page
  (per source) so they still receive the free gift; workshop students route to
  a workshop confirmation.
- Existing Meta/TikTok/Google pixels and Kit integration on the form remain
  intact.

## Non-Goals (YAGNI)

- **No website migration.** The marketing site stays on SiteGround. Only the
  CRM (the brain) runs on Railway.
- No WhatsApp (Business API approval delay — out of scope this week; revisit later).
- No replacement of Kit; Kit tagging/sequence logic is preserved.
- No new analytics dashboards beyond what the CRM already has.

## The Survey — 9 Questions

| # | Question | Options | Purpose |
|---|----------|---------|---------|
| 1 | First name + email | text | Identity → CRM contact |
| 2 | Phone (required) | text | Required for callback / SMS context |
| 3 | What best describes you? | owner / manager / freelancer / 9-to-5 / exploring | ICP split |
| 4 | Revenue or income | <$100k / $100k–$500k / $500k–$1M / $1M+ | Score / offer fork |
| 5 | Team size | just me / 2–10 / 11–50 / 50+ | **Primary hot-lead trigger** |
| 6 | Biggest AI or content problem right now | 4 options | Pain → messaging |
| 7 | Monthly spend on content/help | 4 bands | Budget signal |
| 8 | What computer do you use? | Mac / Windows / both / unsure | Mac-only workshop filter |
| 9 | How soon do you want this solved? | ASAP / 30 days / researching | Urgency / priority order |

## Segmentation & Routing Rules

- **🔥 Hot — call list (instant SMS):** team size in {2–10, 11–50, 50+}.
  Revenue and urgency only set priority order within the call list.
- **Solo / 9-to-5 / exploring:** no call. Auto-route to workshop / Academy /
  course offer + Kit sequence based on role + revenue.
- **Windows / unsure:** existing Windows-waitlist behavior preserved.
- **Exploring + low revenue:** free-training nurture.

**Precedence:** the hot-call trigger (team size 2+) takes priority over the
Mac-only filter. A team-of-2+ lead on Windows is still `hot_call` (Jonathan
calls regardless of OS); the Windows-waitlist outcome only applies to
solo/non-hot leads. Segment evaluation order: hot_call → windows_waitlist →
workshop → course → nurture.

Computed fields stored on the lead: `lead_score` (int), `segment`
(hot_call | workshop | course | nurture | windows_waitlist).

**`lead_score` formula** (drives call-list priority ordering only; does not
change segment): team size (just me 0 / 2–10 20 / 11–50 35 / 50+ 50) +
revenue (<100k 0 / 100k–500k 15 / 500k–1M 25 / 1M+ 35) + urgency (researching
0 / 30 days 10 / ASAP 20). Higher score = called first within the hot list.
Exact weights are tunable during planning; the structure (team > revenue >
urgency) is fixed.

## Architecture

Three units, each independently testable:

### 1. Survey form (static, on SiteGround)
- Source-aware: `/survey?src={stsk|tiktok|ig|fb|yt|workshop}`.
- **Email/name pre-fill:** the lead-magnet opt-in form already collects email
  (and name). It passes them to the survey via query string
  (`&email=<urlencoded>&name=<urlencoded>`). When present, the survey
  pre-fills and **hides** Q1 (name/email) so the lead doesn't re-enter it —
  one less field. If absent (e.g. direct/workshop link), Q1 is shown and
  required as normal. Pre-filled email is still used as the CRM upsert key.
  Email is editable via a small "not you? change email" link in case of typos.
- One-question-at-a-time UX (extends the existing quiz page: keeps pixels, Kit,
  progress bar, auto-advance; adds back button, mobile `dvh` fix, slide
  transitions, keyboard nav).
- On submit: POST all answers + `src` to the CRM intake endpoint, then redirect
  to the source's thank-you page (mapping table below). Submit is non-blocking
  for pixels (fire Lead pixel before navigation, same pattern as today).

### 2. CRM intake endpoint (All-in-One Business App, Flask)
- `POST /api/survey-intake` — validates payload, upserts a `Contact`
  (match by email; update if exists), creates a `SurveyResponse` row, computes
  `lead_score` + `segment`, sets `Contact.lead_source = src`,
  `Contact.status` accordingly.
- Returns `{ ok, contact_id, segment, thankyou_url }` so the form can redirect.
- Idempotent on email within a short window (avoid double-submit dupes).

### 3. Hot-lead alert (Twilio SMS)
- If `segment == hot_call`, send SMS to Jonathan's number with: name, phone
  (tap-to-call link), revenue, team size, top problem, urgency, source.
- Twilio creds via env vars. Failure is logged, never blocks the response.

### Data model (new)
`SurveyResponse`: id, contact_id (FK), src, role, revenue, team_size, problem,
spend, computer, urgency, lead_score, segment, created_at, raw_json.

### Source → thank-you page map
A single config dict (`SURVEY_THANKYOU_MAP`) keyed by `src`, returning the
existing lead-magnet thank-you URL (stsk/tiktok/ig/fb/yt) or workshop
confirmation URL. Workshop students (`src=workshop`) route to workshop confirm.

## Data Flow

```
Lead clicks lead-magnet CTA (any platform)
  → /survey?src=<source>
  → answers 9 questions (pixels fire as today)
  → POST /api/survey-intake (CRM)
       → upsert Contact, create SurveyResponse, score + segment
       → if hot_call: Twilio SMS to Jonathan
       → Kit: subscribe + tag + sequence (preserved logic)
       → return thankyou_url for src
  → browser redirects to correct thank-you / workshop page (gets free gift)
```

## Error Handling

- CRM unreachable: form still redirects to thank-you page (lead not lost to UX);
  failed POSTs are queued client-side (retry once) and logged. Pixels still fire.
- Twilio failure: logged, does not block intake response.
- Duplicate email: update existing Contact + append new SurveyResponse, do not
  create duplicate Contact.
- Missing/invalid phone: form-level required validation before submit.

## Testing & Rollout (hard gate)

1. Build CRM intake endpoint + scoring + Twilio SMS first.
2. Run CRM locally; point a LOCAL copy of the form at it. Submit test leads
   covering each segment. Verify: Contact created/updated, SurveyResponse
   stored, score/segment correct, hot-lead SMS received on Jonathan's phone,
   thank-you redirect correct per source.
3. **Only after Jonathan confirms the above works locally** → deploy the form
   live to SiteGround (siteground-deploy skill).
4. CRM deploys to Railway as its own push (separate from the site).

The form does NOT go live before the CRM is tested and confirmed receiving it.

## Open Questions

- Twilio account: confirm existing account/credentials vs. new signup.
- Exact thank-you page URLs per source (stsk/tiktok/ig/fb/yt) — to be collected
  during planning.
- Jonathan's destination mobile number for SMS alerts.
