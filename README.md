# ACUMEN 3.0

Student-built metacognitive learning lab.

## Stack
- FastAPI backend
- Vanilla HTML/CSS/JavaScript frontend
- Supabase Auth + Postgres + RLS
- Gemini through the existing Python AI engine

## Run
```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8001
```
Then open `http://127.0.0.1:8001`.

## Supabase
The app uses the `Small Projects` Supabase project. The browser uses the publishable key only. Anonymous Auth must be enabled in Supabase Auth for history/profile persistence to work without email registration.

## AI
Assessment, history and the blueprint do not require a Gemini key. The mentor, quiz forge, simulations and roadmap do.

## Research layer
Advice is deliberately built around evidence-informed mechanisms including retrieval practice, spacing, interleaving, metacognitive monitoring, implementation intentions and Self-Determination Theory. ACUMEN does not present its profile as a validated clinical or diagnostic instrument.
