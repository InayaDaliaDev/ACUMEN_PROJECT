# ACUMEN — Student Lab

ACUMEN is a student-built metacognitive study lab. It combines a Likert self-reflection scan, a practical blueprint, longitudinal history, an AI mentor, scenario simulations, a quiz generator and a study roadmap.

## Run locally

From the project root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8001
```

Open `http://127.0.0.1:8001`.

FastAPI docs: `http://127.0.0.1:8001/docs`

## AI configuration

Put `GEMINI_API_KEY` in the backend environment if you want ACUMEN to use one server-side key. The Settings page also supports a browser-local BYOK key. Never commit real keys.

## Persistence

ACUMEN works without Supabase Auth by using localStorage. When an authenticated Supabase session exists, scans, profiles, conversations and feedback are synchronized to Supabase under RLS policies.

Anonymous sign-in is intentionally **not** called automatically. If Anonymous Sign-Ins are enabled later in Supabase, an auth flow can be added without changing the assessment UI.

## Architecture

- `frontend/` — HTML + CSS + vanilla JavaScript
- `backend/` — FastAPI API and assessment service
- `core/` — AI engine and shared utilities
- `data/` — question bank
- `pages/` + `acumen_app.py` — legacy Streamlit implementation kept during migration

## Safety / limits

ACUMEN is an educational self-reflection tool, not a clinical diagnosis or validated intelligence test. AI outputs can be wrong and should be treated as hypotheses and experiments, not authority.


## Product principle
An account is optional. The scan, blueprint and local history work without one. Account creation exists only for cross-device history.
