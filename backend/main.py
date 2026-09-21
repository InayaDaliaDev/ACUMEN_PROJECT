from pathlib import Path
from io import BytesIO
import json
import os

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pypdf import PdfReader

from core.ai_engine import generate_text, classify_error
from core.utils import extract_json_block, extract_text
from backend.services.assessment import public_questions, calculate_profile

ROOT = Path(__file__).resolve().parent.parent
app = FastAPI(title="ACUMEN", version="3.0")

class Assessment(BaseModel):
    answers: dict

class AI(BaseModel):
    api_key: str = ""
    model: str = "gemini-2.5-flash"
    prompt: str = ""
    history: list[dict] = []
    profile: dict = {}

class Quiz(BaseModel):
    api_key: str = ""
    model: str = "gemini-2.5-flash"
    source_text: str
    num_questions: int = Field(8, ge=3, le=20)

class Plan(BaseModel):
    api_key: str = ""
    model: str = "gemini-2.5-flash"
    profile: dict
    chronotype: str
    daily_hours: int
    plan_length: int = Field(5, ge=1, le=7)
    preferred_slots: list[str]
    break_style: str
    energy_note: str
    tasks: str
    deadline: str = ""
    constraints: str = ""

class Sim(BaseModel):
    api_key: str = ""
    model: str = "gemini-2.5-flash"
    profile: dict
    scenario: str
    academic_tier: str = "University"
    environment: str = "Competitive academic environment"

class Feedback(BaseModel):
    message: str = ""
    rating: int = Field(ge=1, le=5)
    page: str = "general"

TECHNIQUE_LIBRARY = [
    {"name": "Retrieval practice", "description": "Recall from memory before checking notes."},
    {"name": "Spacing", "description": "Distribute learning across separate sessions."},
    {"name": "Interleaving", "description": "Mix related problem types to practise choosing a method."},
    {"name": "Implementation intentions", "description": "Specify when, where and how the next action begins."},
    {"name": "Worked examples", "description": "Study a solved example, then complete a similar problem yourself."},
    {"name": "Metacognitive monitoring", "description": "Predict what you know, test it, then compare prediction with performance."},
]

@app.get("/api/health")
def health():
    return {"status": "ok", "product": "ACUMEN", "version": "3.0"}

@app.get("/api/config")
def config():
    # FIX: The publishable Supabase key is safe for browser use. Never expose a secret/service_role key here.
    return {
        "supabase_url": os.getenv("SUPABASE_URL", "https://uqdxwzfvunftueqqofwi.supabase.co"),
        "supabase_publishable_key": os.getenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_Kk5ifh-1XIxP1IAknEWMoQ_f7xS0w7c"),
    }

@app.get("/api/questions")
def questions():
    return {"questions": public_questions(), "count": len(public_questions())}

@app.post("/api/assessment/score")
def score(x: Assessment):
    return calculate_profile(x.answers)

@app.post("/api/ai/chat")
def chat(x: AI):
    p = x.profile or {}
    axes = p.get("axes", [])
    advice = p.get("advice", [])
    system = f"""
You are ACUMEN's evidence-informed academic mentor for students.

ROLE
- Help a student reason about studying, motivation, planning, learning and academic habits.
- Be direct, calm and specific. Never diagnose ADHD, depression, anxiety, burnout or any other condition.
- Do not pretend the ACUMEN profile is a validated psychometric test. Treat it as self-report signals and hypotheses.
- Do not use brain myths, dopamine explanations, personality typing, fake neuroscience or invented citations.

EVIDENCE GUARDRAILS
Use established educational mechanisms when relevant: retrieval practice, spacing, interleaving, worked examples, metacognitive monitoring, implementation intentions, autonomy/competence/relatedness, and realistic task design.
Do not claim a technique is guaranteed to work. If evidence is mixed or the question needs professional help, say so plainly.

STUDENT PROFILE
{json.dumps(axes, ensure_ascii=False)}

PRIORITY GUIDANCE
{json.dumps(advice, ensure_ascii=False)}

RESPONSE FORMAT
1. Answer the student's actual question.
2. Connect it to one profile signal only if genuinely relevant.
3. Give one concrete experiment lasting 10-15 minutes.
4. End with: "Try this today: ..."
"""
    try:
        from core.ai_engine import invoke_llm_with_fallback
        r = invoke_llm_with_fallback(
            system,
            x.history + [{"role": "user", "content": x.prompt}],
            x.api_key,
            x.model,
            0.45,
            60,
        )
        return {"answer": extract_text(r.content)}
    except Exception as e:
        k, m = classify_error(e)
        raise HTTPException(503, detail={"kind": k, "message": m})

@app.post("/api/ai/advice")
def advice(x: AI):
    p = x.profile or {}
    system = """
You are ACUMEN's evidence-informed student coach. Create a short, practical intervention.
Use only established learning/motivation mechanisms: retrieval practice, spacing, interleaving,
worked examples, implementation intentions, metacognitive monitoring, autonomy, competence and relatedness.
Do not diagnose. Do not use fake neuroscience. Treat the profile as a hypothesis, not a fact.
Return strict JSON with keys: title, explanation, action, action_minutes, mechanism, caveat.
"""
    try:
        data = extract_json_block(
            generate_text(system, json.dumps(p, ensure_ascii=False), x.api_key, x.model, .35, 60)
        )
        if not isinstance(data, dict) or not data.get("action"):
            raise ValueError("Invalid advice JSON")
        return data
    except Exception as e:
        k, m = classify_error(e)
        raise HTTPException(503, detail={"kind": k, "message": m})

@app.post("/api/simulations/what-if")
def whatif(x: Sim):
    return _simulation(x, "You are CHRONOS. Simulate plausible academic mechanisms, not destiny. Separate assumptions, tradeoffs, uncertainty and interventions.")

@app.post("/api/simulations/old-days")
def olddays(x: Sim):
    return _simulation(x, "You are ACUMEN's alternate-timeline engine. Explore a plausible counterfactual academic path with tradeoffs and second-order effects. Never present fiction as prediction.")

def _simulation(x: Sim, system: str):
    try:
        return {"answer": generate_text(system, f"Profile:{json.dumps(x.profile)}\nTier:{x.academic_tier}\nEnvironment:{x.environment}\nScenario:{x.scenario}", x.api_key, x.model, .7, 60)}
    except Exception as e:
        k, m = classify_error(e)
        raise HTTPException(503, detail={"kind": k, "message": m})

@app.post("/api/quiz/generate")
def quiz(x: Quiz):
    system = f'''You are ACUMEN Quiz Forge. Generate exactly {x.num_questions} MCQs from the supplied study material. Test comprehension and application. Return STRICT JSON only: {{"questions":[{{"question":"...","options":{{"A":"...","B":"...","C":"...","D":"..."}},"correct":"A","explanation":"..."}}]}}. Never use facts outside the source.'''
    try:
        data = extract_json_block(generate_text(system, x.source_text[:40000], x.api_key, x.model, .4, 90))
        if not isinstance(data, dict) or not data.get("questions"):
            raise ValueError("Invalid quiz JSON")
        return data
    except Exception as e:
        k, m = classify_error(e)
        raise HTTPException(503, detail={"kind": k, "message": m})

@app.post("/api/quiz/extract")
async def extract(file: UploadFile = File(...)):
    data = await file.read()
    name = (file.filename or "").lower()
    if name.endswith(".pdf"):
        text = "\n\n".join((p.extract_text() or "") for p in PdfReader(BytesIO(data)).pages)
    else:
        text = data.decode("utf-8", errors="ignore")
    if not text.strip():
        raise HTTPException(400, "No readable text found")
    return {"filename": file.filename, "text": text[:40000], "characters": min(len(text), 40000)}

@app.post("/api/planning/generate")
def planning(x: Plan):
    user = f'''Profile:{json.dumps(x.profile)}\nRhythm:{x.chronotype}\nDaily hours:{x.daily_hours}\nDays:{x.plan_length}\nSlots:{x.preferred_slots}\nBreaks:{x.break_style}\nEnergy:{x.energy_note}\nTasks:{x.tasks}\nDeadline:{x.deadline}\nConstraints:{x.constraints}'''
    system = f'''You are ACUMEN Neural Roadmap. Build exactly {x.plan_length} realistic days. Never exceed the daily hour budget. Respect slots, deadlines and constraints. Use retrieval practice and spacing where appropriate. Return STRICT JSON: {{"days":[{{"day":1,"title":"...","blocks":[{{"time":"...","task":"...","note":"..."}}]}}]}}.'''
    try:
        data = extract_json_block(generate_text(system, user, x.api_key, x.model, .5, 90))
        if not isinstance(data, dict) or len(data.get("days", [])) != x.plan_length:
            raise ValueError("Invalid roadmap JSON")
        return data
    except Exception as e:
        k, m = classify_error(e)
        raise HTTPException(503, detail={"kind": k, "message": m})

@app.post("/api/feedback")
def feedback(x: Feedback):
    # Persistence is performed client-side through Supabase RLS. This endpoint stays as a health-compatible fallback.
    return {"received": True, "message": "Feedback received."}

app.mount("/assets", StaticFiles(directory=ROOT / "frontend/assets"), name="assets")

@app.get("/{page}.html")
def page(page: str):
    allowed = {
        "index", "assessment", "blueprint", "history", "mr-brown", "what-if",
        "old-days", "quiz-forge", "roadmap", "faq", "feedback", "settings",
    }
    if page not in allowed:
        raise HTTPException(404, "Page not found")
    return FileResponse(ROOT / "frontend" / f"{page}.html")

@app.get("/")
def home():
    return FileResponse(ROOT / "frontend/index.html")
