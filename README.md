# Thermoplan

A small PWA that plans next week's Cookidoo menu.

It pulls what you cooked around the same week in previous years, the recipes in a
saved collection, and anything already pinned to next week's calendar, then asks
Gemini to fill the remaining lunch/dinner slots in that style. You review the
result as a gallery, drop anything you don't want, and (soon) push it back to the
Cookidoo calendar.

Built for one household — access is limited to a hand-picked set of Google
accounts.

## How it works

```
PWA (Firebase Hosting)
  │  Google sign-in (Firebase Auth)  →  ID token with the `access` custom claim
  │
  ├─ POST /api/prepare   → Cloud Function `prepare`  → Cookidoo (cookidoo-api)
  │     fetches history / collection / already-planned, builds the prompt
  │
  └─ POST /api/generate  → Cloud Function `generate` → Gemini (google-genai)
        prompt + datasets → structured menu (JSON, schema-constrained)
```

Both functions are 2nd-gen Python, `europe-west1`, `max_instances=1`. They are
public at the Cloud Run level (Hosting's rewrite proxy can't authenticate to a
private 2nd-gen function) but every request is checked in code: a valid Firebase
ID token carrying `access: true`. `/api/*` reaches the functions through Hosting
rewrites (`firebase.json`), so the browser calls are same-origin.

## Layout

```
index.html, vite.config.js, web/     frontend (Vite + vite-plugin-pwa)
public/                               PWA icons, favicon
functions/
  main.py                            HTTP entry points + the auth gate
  prepare.py                         Cookidoo fetches + prompt builder
  generate.py                        Gemini call + response schema
  set_access.py                      grant/revoke the `access` claim (not deployed)
  requirements.txt                   function runtime deps (pip, not uv)
firebase.json, .firebaserc           Hosting + functions config
.github/workflows/                    deploy on push to main
```

The frontend is a single view with a small state machine: **idle → ready → done**
(fetch inputs → edit prompt → generate → gallery).

## Local development

```bash
# frontend
npm install
npm run dev                 # http://localhost:5173

# functions (uses functions/venv; firebase-tools discovers them by importing)
cd functions
python -m venv venv && venv/bin/pip install -r requirements.txt
```

## Deploy

Push to `main`. `.github/workflows/firebase-hosting-merge.yml` builds the
frontend, sets up Python 3.14, builds `functions/venv`, and runs
`firebase deploy --only hosting,functions` with the `FIREBASE_SERVICE_ACCOUNT_*`
repo secret. PRs get a build check plus a preview channel (skipped for Dependabot
and forks, which don't get the secret).

Manual deploy: `firebase deploy --only functions` (or `--only hosting`).

## Secrets and access

Function secrets (Google Secret Manager, set once):

```bash
firebase functions:secrets:set COOKIDOO_EMAIL
firebase functions:secrets:set COOKIDOO_PASSWORD
firebase functions:secrets:set GEMINI_API_KEY      # https://aistudio.google.com/apikey
```

Grant a person access (they must have signed in once so the account exists):

```bash
gcloud auth application-default login
cd functions
venv/bin/python set_access.py you@example.com her@example.com   # grant
venv/bin/python set_access.py --revoke someone@example.com      # revoke
venv/bin/python set_access.py --list                            # who has it
```

After granting, that user signs out and back in (or the app force-refreshes their
token on the first 403).

## Planning knobs

Set per run in the UI (**Settings**), passed to `/api/prepare`:

| Knob | Default | Meaning |
|---|---|---|
| Week | Next week | Which week to plan (1–6 weeks out) |
| Years back | 3 | How many previous years of history to look at |
| Window ± weeks | 3 | Weeks either side of the target week to include |
| Max minutes | 90 | Time cap for suggestions |
| Collection | `Lunchbox` | Saved Cookidoo collection to draw from (blank to skip) |

The module constants in `prepare.py` are the fallback defaults.

## Known limitations

- **"For You" suggestions are disabled.** The old script scraped a Cookidoo
  website endpoint that needs a browser session cookie; the headless OAuth login
  only yields a mobile-API token, and that endpoint now 502s regardless. The
  `fantasy` input and its prompt rule are omitted when there's no data.
- Cost is effectively $0 at ~1–2 runs/week (Cloud Run free tier, Gemini free
  tier, Artifact Registry cleanup policy set to 1 day). Blaze is required for
  Cloud Functions but nothing here bills at this volume.
