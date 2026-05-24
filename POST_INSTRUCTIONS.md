# All-in-One Business App — Setup Instructions

## What You Got

A complete business operating system — CRM, content automation, calendar booking, AI assistant, email marketing, digital products store, and analytics — all in one Flask app.

---

## Step 1: Unzip the File

Unzip `all-in-one-app.zip` into a folder on your computer:

```bash
unzip all-in-one-app.zip -d All-in-One-Business-App
cd All-in-One-Business-App
```

Or just double-click the zip file on Mac — it will create a folder automatically.

---

## Step 2: Set Up Python Environment

Make sure you have Python 3.10+ installed. Then run:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Step 3: Configure Your Environment

```bash
cp .env.example .env
```

Open `.env` in any text editor and fill in your keys. **The app works without any API keys** — everything runs in demo mode with placeholder data, so you can explore immediately.

### Key Settings to Customize

| Variable | What It Does | Required? |
|----------|-------------|-----------|
| `ADMIN_USER` | Your login username | Has a default |
| `ADMIN_PASS` | Your login password | Has a default |
| `BUSINESS_NAME` | Shown in the header/sidebar | Has a default |
| `OPENAI_API_KEY` | Powers Jackie AI assistant | Optional |
| `OPENROUTER_API_KEY` | Powers content automation | Optional |
| `STRIPE_SECRET_KEY` | Enables payments | Optional |
| `RESEND_API_KEY` | Enables email sending | Optional |

All other keys (FireCrawl, Kie.ai, Zernio, R2, Umami) are optional and only needed when you want to use those specific features.

---

## Step 4: Start the App

```bash
python app.py
```

**Or** double-click `launch.command` (Mac only) — it handles everything automatically.

Open your browser to **http://localhost:8000**

---

## Step 5: Log In

Default credentials (change these in `.env`):

- **Username:** `instructor`
- **Password:** `SaturdayWorkshop2026!`

The app auto-seeds demo data on first run — you'll see sample contacts, deals, products, and bookings already loaded.

---

## What's Inside

### CRM Section
- **Dashboard** — revenue chart, KPI cards, recent transactions
- **Contacts** — full contact database with status tracking
- **Deals** — sales pipeline with stage filtering
- **Pages** — website page manager with funnel visualization
- **Products** — digital product catalog with Stripe checkout
- **Analytics** — visitor tracking and pageview stats

### Marketing Section
- **Content** — AI-powered content creation with a 6-stage pipeline (Scrape, Script, Image, Video, Caption, Publish)
- **Email** — templates, automation triggers, and send tracking

### Tools Section
- **Bookings** — calendar scheduling with a public booking page at `/bookings/book`
- **Jackie AI** — business advisor chatbot (needs OpenAI or OpenRouter key)
- **Manual & Help** — usage guide + reseller sales playbook with pricing packages

### Settings
- Configure all API keys from the UI (no restart needed)
- Toggle features on/off with `FEATURE_*` env vars

---

## Feature Toggles

Turn features on or off in your `.env` file:

```
FEATURE_PRODUCTS=true
FEATURE_CLIENTS=true
FEATURE_TASKS=true
FEATURE_EMAIL=true
FEATURE_ANALYTICS=true
FEATURE_BOOKINGS=true
```

Set any to `false` to hide that section from the sidebar.

---

## Public Pages (No Login Required)

These pages are visible to your customers:

| URL | What It Is |
|-----|-----------|
| `/` | Landing page |
| `/sales` | Sales page |
| `/products/store` | Digital products store |
| `/bookings/book` | Public booking form |
| `/onboarding/` | Client onboarding survey |

---

## Deploy to Production (Railway)

```bash
brew install railway
railway login
railway init -n "all-in-one-business-app"
railway add --database postgres
railway variables set DATABASE_URL='${{Postgres.DATABASE_URL}}'
railway variables set SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
railway variables set ADMIN_USER="yourusername"
railway variables set ADMIN_PASS="YourStrongPassword!"
railway up
railway domain
```

Set the rest of your env vars in the Railway dashboard.

---

## Running Tests

```bash
python -m pytest tests/ -v
```

---

## Need Help?

- **Coaching:** simpletechskills.com/coaching
- **Community:** simpletechskills.com/academy
- **Workshop:** Join the next Saturday Workshop for live walkthroughs
