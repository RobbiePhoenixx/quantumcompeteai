# Master Qualification Survey Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one source-aware qualification survey whose answers flow into the All-in-One CRM, get scored/segmented, and trigger an instant SMS to Jonathan for hot (team-of-2+) leads — without migrating the website.

**Architecture:** A static survey page on the SiteGround site POSTs answers to a new `/api/survey-intake` endpoint on the All-in-One Flask CRM. The endpoint upserts a Contact, stores a SurveyResponse, computes score+segment via a pure scoring module, fires a Twilio SMS on hot leads, and returns the correct per-source thank-you URL for redirect. Pixels/Kit on the form are preserved. CRM is built and locally verified before the form ships.

**Tech Stack:** Flask, SQLAlchemy, pytest (existing CRM patterns); Twilio REST via `requests` (already a dependency, no new package); vanilla JS/HTML survey page.

**Repos:**
- CRM: `/Users/jonathanacuna/Documents/VS Code Programs/All-in-One Business App - Saturday Workshop`
- Site: `/Users/jonathanacuna/Documents/VS Code Programs/Websites` (survey at `simpletechskills-site/survey/index.html`)

**Spec:** `docs/superpowers/specs/2026-05-17-master-qualification-survey-design.md`

---

## File Structure

CRM repo:
- Create `survey_scoring.py` — pure functions: `compute_score(answers)`, `compute_segment(answers)`. No Flask/db imports. Easiest to TDD.
- Create `survey_config.py` — `SURVEY_THANKYOU_MAP` (src → thank-you URL), scoring weight constants.
- Create `notifications.py` — `send_hot_lead_sms(lead)` using Twilio REST via `requests`; env-driven; never raises.
- Modify `models.py` — add `SurveyResponse` model + `to_dict()`.
- Create `blueprints/survey.py` — `survey_bp` with `POST /survey-intake`.
- Modify `app.py:80-98` — register `survey_bp` at `/api`.
- Create `tests/test_survey_scoring.py`, `tests/test_survey_intake.py`.

Site repo:
- Create `simpletechskills-site/survey/index.html` — adapted from `simpletechskills-site/quiz/index.html` (keep pixels/Kit/progress/auto-advance; add source-awareness, email/name prefill+hide, 9 questions, back button, `dvh` fix, slide transitions, keyboard nav, POST to CRM, per-source redirect).

---

## Pre-Flight Inputs (collect before Task 7/8; do not block Tasks 1-6)

- [ ] Twilio Account SID, Auth Token, From number → CRM env vars `TWILIO_SID`, `TWILIO_TOKEN`, `TWILIO_FROM`.
- [ ] Jonathan's destination mobile number → env var `HOT_LEAD_TO`.
- [ ] Exact thank-you page URLs for each `src` (stsk, tiktok, ig, fb, yt) + workshop confirm URL → fill `SURVEY_THANKYOU_MAP`.
- [ ] CRM public base URL on Railway (for the form's POST target) → set as `CRM_INTAKE_URL` in the form.

---

### Task 1: SurveyResponse model

**Files:**
- Modify: `models.py` (append after `Contact`, near line 41)
- Test: `tests/test_survey_intake.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_survey_intake.py
import json
def test_surveyresponse_model_roundtrip(app):
    from extensions import db
    from models import Contact, SurveyResponse
    with app.app_context():
        c = Contact(name="A B", email="a@b.com", phone="+15551112222")
        db.session.add(c); db.session.commit()
        sr = SurveyResponse(contact_id=c.id, src="tiktok", role="owner",
            revenue="100k_500k", team_size="2_10", problem="manual_hours",
            spend="500_1000", computer="mac", urgency="asap",
            lead_score=55, segment="hot_call", raw_json=json.dumps({"src":"tiktok"}))
        db.session.add(sr); db.session.commit()
        assert sr.id is not None
        d = sr.to_dict()
        assert d["segment"] == "hot_call" and d["contact_id"] == c.id
```

- [ ] **Step 2: Run, expect fail**

Run: `cd "/Users/jonathanacuna/Documents/VS Code Programs/All-in-One Business App - Saturday Workshop" && python -m pytest tests/test_survey_intake.py::test_surveyresponse_model_roundtrip -v`
Expected: FAIL `ImportError: cannot import name 'SurveyResponse'`

- [ ] **Step 3: Implement model** (append in `models.py` after line 41)

```python
class SurveyResponse(db.Model):
    __tablename__ = "survey_responses"
    id         = db.Column(db.Integer, primary_key=True)
    contact_id = db.Column(db.Integer, db.ForeignKey("contacts.id"), nullable=False)
    src        = db.Column(db.String(30))
    role       = db.Column(db.String(30))
    revenue    = db.Column(db.String(30))
    team_size  = db.Column(db.String(30))
    problem    = db.Column(db.String(40))
    spend      = db.Column(db.String(30))
    computer   = db.Column(db.String(20))
    urgency    = db.Column(db.String(20))
    lead_score = db.Column(db.Integer, default=0)
    segment    = db.Column(db.String(30))
    raw_json   = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id, "contact_id": self.contact_id, "src": self.src,
            "role": self.role, "revenue": self.revenue, "team_size": self.team_size,
            "problem": self.problem, "spend": self.spend, "computer": self.computer,
            "urgency": self.urgency, "lead_score": self.lead_score,
            "segment": self.segment,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
```

Add relationship on `Contact` (after line 27): `survey_responses = db.relationship("SurveyResponse", backref="contact", lazy=True, cascade="all, delete-orphan")`

(`db.create_all()` at `app.py:139` auto-creates the table — no migration framework in this repo.)

- [ ] **Step 4: Run, expect pass**

Run: same pytest command. Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add models.py tests/test_survey_intake.py
git commit -m "feat: SurveyResponse model"
```

---

### Task 2: Scoring + segmentation (pure, TDD)

**Files:**
- Create: `survey_config.py`
- Create: `survey_scoring.py`
- Test: `tests/test_survey_scoring.py`

- [ ] **Step 1: Write failing tests** (cover the spec's precedence rules)

```python
# tests/test_survey_scoring.py
from survey_scoring import compute_score, compute_segment

BASE = dict(role="owner", revenue="lt_100k", team_size="just_me",
            problem="manual_hours", spend="nothing", computer="mac", urgency="researching")

def test_solo_is_not_hot():
    assert compute_segment({**BASE}) != "hot_call"

def test_team_2plus_is_hot_even_on_windows():
    a = {**BASE, "team_size": "2_10", "computer": "windows"}
    assert compute_segment(a) == "hot_call"   # hot trigger beats Mac filter

def test_windows_solo_is_waitlist():
    a = {**BASE, "computer": "windows"}
    assert compute_segment(a) == "windows_waitlist"

def test_exploring_low_revenue_is_nurture():
    a = {**BASE, "role": "exploring"}
    assert compute_segment(a) == "nurture"

def test_score_orders_team_then_revenue_then_urgency():
    big = compute_score({**BASE, "team_size": "50_plus", "revenue": "1m_plus", "urgency": "asap"})
    small = compute_score({**BASE, "team_size": "2_10", "revenue": "lt_100k", "urgency": "researching"})
    assert big > small
```

- [ ] **Step 2: Run, expect fail**

Run: `python -m pytest tests/test_survey_scoring.py -v`
Expected: FAIL `ModuleNotFoundError: survey_scoring`

- [ ] **Step 3: Implement**

```python
# survey_config.py
SCORE_TEAM    = {"just_me": 0, "2_10": 20, "11_50": 35, "50_plus": 50}
SCORE_REVENUE = {"lt_100k": 0, "100k_500k": 15, "500k_1m": 25, "1m_plus": 35}
SCORE_URGENCY = {"researching": 0, "30_days": 10, "asap": 20}

# src -> thank-you URL. FILL real URLs in Pre-Flight before Task 7.
SURVEY_THANKYOU_MAP = {
    "stsk":     "https://simpletechskills.com/thank-you",
    "tiktok":   "https://simpletechskills.com/thank-you",
    "ig":       "https://simpletechskills.com/thank-you",
    "fb":       "https://simpletechskills.com/thank-you",
    "yt":       "https://simpletechskills.com/thank-you",
    "workshop": "https://simpletechskills.com/workshop-confirmed",
}
DEFAULT_THANKYOU = "https://simpletechskills.com/thank-you"
```

```python
# survey_scoring.py
from survey_config import SCORE_TEAM, SCORE_REVENUE, SCORE_URGENCY

HOT_TEAMS = {"2_10", "11_50", "50_plus"}

def compute_score(a):
    return (SCORE_TEAM.get(a.get("team_size"), 0)
            + SCORE_REVENUE.get(a.get("revenue"), 0)
            + SCORE_URGENCY.get(a.get("urgency"), 0))

def compute_segment(a):
    # Evaluation order per spec: hot_call -> windows_waitlist -> workshop -> course -> nurture
    if a.get("team_size") in HOT_TEAMS:
        return "hot_call"
    # "both" => has a Mac, NOT waitlisted. Only pure windows/unsure waitlist (spec line 61).
    if a.get("computer") in ("windows", "unsure"):
        return "windows_waitlist"
    if a.get("role") == "exploring":
        return "nurture"
    if a.get("revenue") == "lt_100k" or a.get("role") in ("9_to_5", "freelancer"):
        return "course"
    return "workshop"
```

- [ ] **Step 4: Run, expect pass**

Run: `python -m pytest tests/test_survey_scoring.py -v`. Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add survey_config.py survey_scoring.py tests/test_survey_scoring.py
git commit -m "feat: survey scoring + segmentation with hot-call precedence"
```

---

### Task 3: Twilio SMS notifier (TDD, mocked)

**Files:**
- Create: `notifications.py`
- Test: `tests/test_notifications.py`

- [ ] **Step 1: Failing test** (mock `requests.post`; never raises; skips when unconfigured)

```python
# tests/test_notifications.py
import notifications

def test_skips_when_unconfigured(monkeypatch):
    monkeypatch.delenv("TWILIO_SID", raising=False)
    assert notifications.send_hot_lead_sms({"name":"X"}) is False  # no creds -> no send

def test_sends_when_configured(monkeypatch):
    calls = {}
    def fake_post(url, **kw): calls["url"]=url; calls["data"]=kw.get("data");  \
        return type("R",(),{"status_code":201,"text":"ok"})()
    monkeypatch.setenv("TWILIO_SID","AC1"); monkeypatch.setenv("TWILIO_TOKEN","t")
    monkeypatch.setenv("TWILIO_FROM","+1999"); monkeypatch.setenv("HOT_LEAD_TO","+1888")
    monkeypatch.setattr(notifications.requests, "post", fake_post)
    ok = notifications.send_hot_lead_sms({"name":"Jane","phone":"+15551234567",
        "revenue":"1m_plus","team_size":"11_50","problem":"manual_hours",
        "urgency":"asap","src":"tiktok","lead_score":90})
    assert ok is True and "AC1" in calls["url"] and calls["data"]["To"]=="+1888"

def test_never_raises_on_error(monkeypatch):
    monkeypatch.setenv("TWILIO_SID","AC1"); monkeypatch.setenv("TWILIO_TOKEN","t")
    monkeypatch.setenv("TWILIO_FROM","+1999"); monkeypatch.setenv("HOT_LEAD_TO","+1888")
    def boom(*a, **k): raise RuntimeError("network")
    monkeypatch.setattr(notifications.requests, "post", boom)
    assert notifications.send_hot_lead_sms({"name":"Z"}) is False
```

- [ ] **Step 2: Run, expect fail** — `python -m pytest tests/test_notifications.py -v` → ModuleNotFoundError

- [ ] **Step 3: Implement**

```python
# notifications.py
import os, requests

def send_hot_lead_sms(lead: dict) -> bool:
    sid = os.environ.get("TWILIO_SID"); tok = os.environ.get("TWILIO_TOKEN")
    frm = os.environ.get("TWILIO_FROM"); to = os.environ.get("HOT_LEAD_TO")
    if not all([sid, tok, frm, to]):
        return False
    body = (f"HOT LEAD ({lead.get('lead_score','?')}) {lead.get('name','')}\n"
            f"Tap to call: {lead.get('phone','')}\n"
            f"Team {lead.get('team_size','?')} | Rev {lead.get('revenue','?')} | "
            f"{lead.get('urgency','?')} | src {lead.get('src','?')}\n"
            f"Problem: {lead.get('problem','?')}")
    try:
        r = requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
            data={"From": frm, "To": to, "Body": body},
            auth=(sid, tok), timeout=8)
        return r.status_code in (200, 201)
    except Exception:
        return False
```

- [ ] **Step 4: Run, expect pass** — 3 passed

- [ ] **Step 5: Commit**

```bash
git add notifications.py tests/test_notifications.py
git commit -m "feat: Twilio hot-lead SMS notifier (safe, env-driven)"
```

---

### Task 4: `/api/survey-intake` endpoint

**Files:**
- Create: `blueprints/survey.py`
- Modify: `app.py:80-98` (register blueprint)
- Test: `tests/test_survey_intake.py` (append)

- [ ] **Step 1: Failing tests** (upsert by email, store response, segment, conditional SMS, return thankyou_url)

```python
# append to tests/test_survey_intake.py
import notifications

def _payload(**o):
    base = dict(name="Jane Doe", email="jane@x.com", phone="+15551234567",
        src="tiktok", role="owner", revenue="1m_plus", team_size="11_50",
        problem="manual_hours", spend="1000_3000", computer="mac", urgency="asap")
    base.update(o); return base

def test_intake_creates_contact_and_response_and_returns_thankyou(client, monkeypatch):
    sent = {}
    monkeypatch.setattr(notifications, "send_hot_lead_sms", lambda l: sent.setdefault("v", l) or True)
    r = client.post("/api/survey-intake", json=_payload())
    assert r.status_code == 200
    j = r.get_json()
    assert j["ok"] is True and j["segment"] == "hot_call"
    assert j["thankyou_url"].startswith("http")
    assert sent.get("v", {}).get("name") == "Jane Doe"   # hot -> SMS fired

def test_intake_upserts_same_email(client, monkeypatch):
    monkeypatch.setattr(notifications, "send_hot_lead_sms", lambda l: True)
    client.post("/api/survey-intake", json=_payload())
    client.post("/api/survey-intake", json=_payload(team_size="just_me"))
    from models import Contact
    from extensions import db
    assert Contact.query.filter_by(email="jane@x.com").count() == 1

def test_intake_solo_no_sms(client, monkeypatch):
    calls = []
    monkeypatch.setattr(notifications, "send_hot_lead_sms", lambda l: calls.append(l))
    r = client.post("/api/survey-intake", json=_payload(team_size="just_me", role="9_to_5", revenue="lt_100k"))
    assert r.get_json()["segment"] in ("course","nurture","workshop")
    assert calls == []   # not hot -> no SMS

def test_intake_missing_required_400(client):
    r = client.post("/api/survey-intake", json={"src":"tiktok"})
    assert r.status_code == 400
```

- [ ] **Step 2: Run, expect fail** — 404/ImportError on `/api/survey-intake`

- [ ] **Step 3: Implement blueprint**

```python
# blueprints/survey.py
import json
from flask import Blueprint, request, jsonify
from extensions import db
from models import Contact, SurveyResponse, log_activity
from survey_scoring import compute_score, compute_segment
from survey_config import SURVEY_THANKYOU_MAP, DEFAULT_THANKYOU
import notifications

survey_bp = Blueprint("survey", __name__)

REQUIRED = ("name", "email", "phone", "role", "revenue", "team_size",
            "problem", "spend", "computer", "urgency")

@survey_bp.route("/survey-intake", methods=["POST"])
def survey_intake():
    data = request.get_json(silent=True) or {}
    missing = [k for k in REQUIRED if not str(data.get(k, "")).strip()]
    if missing:
        return jsonify({"ok": False, "error": "missing", "fields": missing}), 400

    email = data["email"].strip().lower()
    contact = Contact.query.filter(db.func.lower(Contact.email) == email).first()
    if not contact:
        contact = Contact(name=data["name"].strip(), email=email)
        db.session.add(contact)
    contact.phone = data["phone"].strip()
    contact.name = data["name"].strip()
    src = (data.get("src") or "stsk").strip()
    contact.lead_source = src

    score = compute_score(data)
    segment = compute_segment(data)
    # NOTE during build: confirm "Hot Lead" status doesn't break existing
    # status filters/badges (existing default is "Lead"). Adjust vocabulary if so.
    contact.status = "Hot Lead" if segment == "hot_call" else "Lead"
    db.session.flush()  # contact.id

    sr = SurveyResponse(contact_id=contact.id, src=src, role=data["role"],
        revenue=data["revenue"], team_size=data["team_size"], problem=data["problem"],
        spend=data["spend"], computer=data["computer"], urgency=data["urgency"],
        lead_score=score, segment=segment, raw_json=json.dumps(data))
    db.session.add(sr)
    log_activity("survey", f"Survey: {segment} (score {score}, src {src})", contact_id=contact.id)
    db.session.commit()

    if segment == "hot_call":
        notifications.send_hot_lead_sms({
            "name": contact.name, "phone": contact.phone, "revenue": data["revenue"],
            "team_size": data["team_size"], "problem": data["problem"],
            "urgency": data["urgency"], "src": src, "lead_score": score})

    return jsonify({"ok": True, "contact_id": contact.id, "segment": segment,
                    "lead_score": score,
                    "thankyou_url": SURVEY_THANKYOU_MAP.get(src, DEFAULT_THANKYOU)})
```

Register in `app.py` (with the other blueprint registrations, ~line 92):

```python
    from blueprints.survey import survey_bp
    app.register_blueprint(survey_bp, url_prefix="/api")
```

- [ ] **Step 4: Run, expect pass** — `python -m pytest tests/test_survey_intake.py -v` → all pass

- [ ] **Step 5: Commit**

```bash
git add blueprints/survey.py app.py tests/test_survey_intake.py
git commit -m "feat: /api/survey-intake — upsert, score, segment, hot-lead SMS"
```

---

### Task 5: CORS for the survey POST

**Files:** Modify `blueprints/survey.py`

The form is served from `simpletechskills.com` (SiteGround) but POSTs to the Railway CRM — cross-origin. Add a scoped CORS header + OPTIONS handler on the survey blueprint only (do not globally open CORS).

- [ ] **Step 1: Failing test** (append to `tests/test_survey_intake.py`)

```python
def test_intake_options_preflight(client):
    r = client.open("/api/survey-intake", method="OPTIONS")
    assert r.status_code == 200
    assert r.headers.get("Access-Control-Allow-Origin") == "https://simpletechskills.com"
```

- [ ] **Step 2: Run, expect fail** (no ACAO header / 405)

- [ ] **Step 3: Implement** — add to `blueprints/survey.py`:

```python
ALLOWED_ORIGIN = "https://simpletechskills.com"

@survey_bp.after_request
def _cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = ALLOWED_ORIGIN
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    return resp

@survey_bp.route("/survey-intake", methods=["OPTIONS"])
def survey_intake_preflight():
    return ("", 200)
```

- [ ] **Step 4: Run, expect pass** — full file: `python -m pytest tests/test_survey_intake.py -v`

- [ ] **Step 5: Commit**

```bash
git add blueprints/survey.py tests/test_survey_intake.py
git commit -m "feat: scoped CORS for cross-origin survey intake"
```

---

### Task 6: Full CRM suite green

- [ ] **Step 1:** Run `python -m pytest -q` in the CRM repo.
- [ ] **Step 2:** Expected: all prior tests still pass + new survey tests pass. Fix regressions before proceeding.
- [ ] **Step 3:** Commit only if fixes were needed: `git commit -am "test: keep suite green with survey feature"`

---

### Task 7: Survey form page (site repo)

**Files:**
- Create: `/Users/jonathanacuna/Documents/VS Code Programs/Websites/simpletechskills-site/survey/index.html`

Base it on the existing `simpletechskills-site/quiz/index.html` (copy it, then modify). **Preserve verbatim:** all `<head>` pixel/analytics blocks (Meta, TikTok, Google, Metricool), fonts, the dark theme CSS, progress bar, `showScreen()`, `selectOption()`, auto-advance pattern, and the Kit subscribe/tag/sequence `fetch` logic in `submitEmail`.

**Changes (each its own commit):**

- [ ] **7a — Source + prefill bootstrap.** Add near top of `<script>`:

```javascript
var QS = new URLSearchParams(location.search);
var SRC = (QS.get('src') || 'stsk').toLowerCase();
var PREFILL_EMAIL = QS.get('email') || '';
var PREFILL_NAME  = QS.get('name')  || '';
var CRM_INTAKE_URL = 'https://<RAILWAY-CRM-HOST>/api/survey-intake'; // set from Pre-Flight
```
If `PREFILL_EMAIL` is present: set name/email inputs, and skip the name/email screen (start the quiz at Q1 role; keep a small "not you? change email" link that reveals the email field). If absent: show name/email as the first screen, required.
Commit: `feat(survey): source-aware + email/name prefill`

- [ ] **7b — Replace question set with the 9 spec questions** (role, revenue, team_size, problem [AI or content], spend, computer, urgency) using the existing `.option-btn`/`answerQX` pattern; store into an `answers` object with the exact value keys used in `survey_scoring.py` (`just_me`,`2_10`,`11_50`,`50_plus`; `lt_100k`,`100k_500k`,`500k_1m`,`1m_plus`; `researching`,`30_days`,`asap`; etc.). Keep progress bar (update "of 9"). Commit: `feat(survey): 9 qualification questions`

- [ ] **7c — Back button.** Fixed top-left arrow; maintains a screen history stack; hidden on first screen and on terminal screens. Commit: `feat(survey): back navigation`

- [ ] **7d — Mobile viewport fix.** Replace `min-height: 100vh` / container `100vh` with `100dvh` and a `@supports` fallback to `-webkit-fill-available`; add `touch-action: manipulation` and `-webkit-tap-highlight-color: transparent` on `.option-btn`/`.cta-btn` (kills double-tap zoom). Commit: `fix(survey): mobile viewport + tap behavior`

- [ ] **7e — Slide transitions + keyboard nav.** Swap fade for directional slide on `.screen.active`; on question screens, keys `1-4`/`A-D` select an option, `Enter` advances, `Backspace` goes back. Commit: `feat(survey): slide transitions + keyboard nav`

- [ ] **7f — Submit to CRM + per-source redirect.** In `submitEmail` (final step), keep all pixel + Kit logic, and add: POST the full `answers` + `name,email,phone,src` to `CRM_INTAKE_URL` (`fetch`, `keepalive:true`). On success use returned `thankyou_url`; on failure fall back to a hardcoded per-source map mirroring `SURVEY_THANKYOU_MAP`. Retry the POST once on network error (store payload in `sessionStorage`, replay on next load if still unsent). Always redirect after ≤3s so UX never blocks. Commit: `feat(survey): post to CRM + source-correct redirect`

---

### Task 8: Local integration gate (HARD GATE — form does not ship until this passes)

- [ ] **Step 1:** In CRM repo, create `.env` with real Twilio creds + `HOT_LEAD_TO` (Jonathan's number) + fill `SURVEY_THANKYOU_MAP` real URLs. Run CRM locally: `python app.py` (note local URL, e.g. `http://127.0.0.1:5000`).
- [ ] **Step 2:** In the local `survey/index.html`, temporarily set `CRM_INTAKE_URL` to the local CRM URL and open the file/serve it locally.
- [ ] **Step 3:** Submit one test lead per segment:
  - Hot: team `11_50`, owner, `1m_plus`, `asap`, Mac
  - Hot-on-Windows: team `2_10`, computer `windows` (must still be hot)
  - Course: `9_to_5`, `lt_100k`, solo
  - Nurture: role `exploring`
  - Windows-waitlist: solo + `windows`
- [ ] **Step 4:** Verify for each: Contact created/updated (no dupes on repeat email), SurveyResponse row stored with correct `segment`+`lead_score`, `thankyou_url` correct for `src`, browser redirected there.
- [ ] **Step 5:** Verify the **hot** submissions delivered an SMS to Jonathan's phone with name/phone/score.
- [ ] **Step 6:** Jonathan explicitly confirms: "local gate passed." Revert `CRM_INTAKE_URL` in the form to the Railway host. Do not proceed without this confirmation.

---

### Task 9: Deploy (only after Task 8 confirmed)

- [ ] **Step 1:** Deploy CRM to Railway (its own push; set Twilio + thank-you env vars in Railway). Verify `GET /api/health` returns ok on the Railway URL; smoke one `POST /api/survey-intake`.
- [ ] **Step 2:** Confirm the form's `CRM_INTAKE_URL` points at the Railway host.
- [ ] **Step 3:** Deploy `survey/index.html` to SiteGround using the **siteground-deploy** skill (preserve `.htaccess`/permissions per that skill).
- [ ] **Step 4:** Production smoke: load `https://simpletechskills.com/survey?src=tiktok&email=test%2Bsmoke@x.com&name=Smoke`, complete it, confirm CRM contact + correct thank-you redirect; delete the smoke contact.
- [ ] **Step 5:** Repoint each lead-magnet opt-in (stsk, tiktok, ig, fb, yt) and the workshop confirmation to `/survey?src=<source>&email=<email>&name=<name>`. Commit site repo.

---

## Notes
- TDD throughout: Tasks 1-5 are red→green→commit. Tasks 7-9 are integration/deploy.
- DRY: the src→thank-you mapping lives in `survey_config.py`; the form's fallback map must mirror it (documented in 7f).
- YAGNI: no WhatsApp, no site migration, no new analytics — per spec Non-Goals.
- Hard gate (Task 8) is non-negotiable per Jonathan's instruction.
