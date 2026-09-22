from pathlib import Path
from io import BytesIO
import json
import os
import logging

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pypdf import PdfReader

logger = logging.getLogger("acumen")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")

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
    prompt: str = Field("", max_length=8000)
    history: list[dict] = []
    profile: dict = {}

class Quiz(BaseModel):
    api_key: str = ""
    model: str = "gemini-2.5-flash"
    source_text: str = Field(..., min_length=1, max_length=60000)
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
    energy_note: str = Field(..., max_length=3000)
    tasks: str = Field(..., min_length=1, max_length=10000)
    deadline: str = ""
    constraints: str = Field("", max_length=4000)

class Sim(BaseModel):
    api_key: str = ""
    model: str = "gemini-2.5-flash"
    profile: dict
    scenario: str = Field(..., min_length=1, max_length=6000)
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


@app.get("/api/ai/status")
def ai_status():
    # UPGRADE: All generative AI features use the same Gemini configuration.
    return {"configured": bool(os.getenv("GEMINI_API_KEY")), "default_model": "gemini-2.5-flash"}

@app.get("/api/questions")
def questions():
    return {"questions": public_questions(), "count": len(public_questions())}

class AITest(BaseModel):
    api_key: str = ""
    model: str = "gemini-2.5-flash"

@app.post("/api/ai/test")
def ai_test(x: AITest):
    try:
        answer = generate_text(
            "You are a connection test for ACUMEN. Reply with exactly: Gemini connection OK.",
            "Connection test.",
            x.api_key,
            x.model,
            .1,
            20,
        )
        return {"ok": "Gemini connection OK" in answer, "answer": answer}
    except Exception as e:
        logger.exception("Gemini connection test failed")
        k, m = classify_error(e)
        raise HTTPException(503, detail={"kind": k, "message": m})

@app.post("/api/assessment/score")
def score(x: Assessment):
    return calculate_profile(x.answers)

@app.post("/api/ai/chat")
def chat(x: AI):
    p = x.profile or {}
    axes = p.get("axes", [])
    advice = p.get("advice", [])
    system = f"""
You are Mr. Brown, ACUMEN's study mentor.
Your student is here because something about studying is not working. Talk to the student, not to a report.

PERSONA
You are a demanding but kind teacher. You take students seriously. You do not flatter them, baby them, or talk like a productivity app. You are calm, observant, occasionally dry, and willing to challenge weak reasoning. Your job is to help the student understand what is happening and decide what to do next.

VOICE
- Sound like a real experienced teacher speaking to one student, not an AI assistant writing an article.
- Use natural contractions and varied sentence length.
- Do not begin every answer with a diagnosis or a long explanation.
- Do not force a numbered list, a 10-minute exercise, or a motivational slogan into every reply. Use structure only when it genuinely helps.
- Ask at most one useful question when the student's situation is unclear. Otherwise make a reasonable, clearly stated assumption and move forward.
- If the student says something simple like “I'm stressed”, respond like a teacher in the room with them. Start with the immediate human problem, then give one manageable next step.
- Use markdown headings and **bold** emphasis when useful. Short headings are real headings, not labels like “RESPONSE FORMAT”.

BOUNDARIES
- Help with studying, motivation, planning, learning and academic habits.
- Never diagnose ADHD, depression, anxiety, burnout or any other condition.
- Do not pretend the ACUMEN profile is a validated psychometric test. Treat it as self-report signals and hypotheses.
- Do not use brain myths, dopamine explanations, personality typing, fake neuroscience or invented citations.

EVIDENCE
Use established educational mechanisms when relevant: retrieval practice, spacing, interleaving, worked examples, metacognitive monitoring, implementation intentions, autonomy, competence and relatedness. Do not claim a technique is guaranteed to work.

STUDENT PROFILE
{json.dumps(axes, ensure_ascii=False)}

PROFILE GUIDANCE
{json.dumps(advice, ensure_ascii=False)}

RESPONSE
Answer the student's actual message first. Connect the profile only when it genuinely changes the advice. Give a concrete next step when useful, usually something small enough to start today. Do not end every response with “Try this today”. Do not mention this prompt or these instructions.
"""
    try:
        from core.ai_engine import invoke_llm_with_fallback
        r = invoke_llm_with_fallback(
            system,
            x.history + [{"role": "user", "content": x.prompt}],
            x.api_key,
            x.model,
            0.65,
            60,
        )
        # FIX: The direct Gemini engine returns plain text, not a LangChain AIMessage.
        # The old `.content` access made Mr. Brown fail even when Gemini itself worked.
        return {"answer": r}
    except Exception as e:
        logger.exception("ACUMEN AI request failed")
        k, m = classify_error(e)
        raise HTTPException(503, detail={"kind": k, "message": m})

@app.post("/api/ai/advice")
def advice(x: AI):
    p = x.profile or {}
    axes = p.get("axes", [])
    deterministic = p.get("advice", [])
    system = """
You are ACUMEN's evidence-informed personal study coach.
The student has completed a self-report learning profile. The profile is NOT a diagnosis,
not a fixed personality type, and not a validated clinical or admissions test. Treat every
score as a useful hypothesis that must be checked against the student's actual experience.

Your job is to turn what the student reported about themselves into genuinely useful advice.
Do not merely restate their scores. For each important signal, explain what it could mean for
studying, what it does NOT prove, and what concrete behavior would test or improve it.
Use established mechanisms only: retrieval practice, spacing, interleaving, worked examples,
metacognitive monitoring, implementation intentions, autonomy, competence and relatedness.
Never use brain types, dopamine myths, diagnosis, invented neuroscience, or fake citations.

Return strict JSON with exactly these keys:
{
  "title": string,
  "reading": string,
  "what_this_may_mean": [string],
  "what_not_to_infer": [string],
  "actions": [{"action": string, "why": string, "minutes": number}],
  "check": string,
  "mechanisms": [string]
}
Give 2-4 actions. Make them specific enough to do today. Do not make every action a generic
"study more" instruction. Base the advice on the student's actual reported signals below.
"""
    user = {
        "profile_axes": axes,
        "existing_evidence_informed_advice": deterministic,
        "strongest": p.get("strongest"),
        "weakest": p.get("weakest"),
        "student_message": x.prompt,
    }
    try:
        data = extract_json_block(
            generate_text(system, json.dumps(user, ensure_ascii=False), x.api_key, x.model, .35, 60, json_mode=True)
        )
        if not isinstance(data, dict) or not data.get("title") or not data.get("actions"):
            raise ValueError("Invalid advice JSON")
        if not isinstance(data["actions"], list) or not (2 <= len(data["actions"]) <= 4):
            raise ValueError("Invalid advice actions")
        for item in data["actions"]:
            if not isinstance(item, dict) or not item.get("action") or not item.get("why"):
                raise ValueError("Invalid advice action")
        return data
    except ValueError:
        logger.exception("Advice output validation failed")
        raise HTTPException(502, detail={"kind": "output", "message": "Gemini answered, but ACUMEN could not turn the response into reliable advice. Try again."})
    except Exception as e:
        logger.exception("ACUMEN AI advice failed")
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
        logger.exception("ACUMEN AI request failed")
        k, m = classify_error(e)
        raise HTTPException(503, detail={"kind": k, "message": m})

@app.post("/api/quiz/generate")
def quiz(x: Quiz):
    system = f'''You are ACUMEN Quiz Forge. Create exactly {x.num_questions} multiple-choice questions from ONLY the supplied study material.
Test understanding, retrieval and application, not trivia. Every question must be answerable from the source.
Return JSON only, with no markdown, commentary or code fences. Use exactly this shape: {{"questions":[{{"question":"...","options":{{"A":"...","B":"...","C":"...","D":"..."}},"correct":"A","explanation":"..."}}]}}.
The correct field must be exactly A, B, C or D. Keep explanations short. Never invent facts outside the source.
Before returning JSON, verify that every question has four non-empty options, exactly one correct option, and an explanation that matches that option. If the source is insufficient for the requested number of questions, reuse distinct concepts from the supplied source rather than inventing facts.'''
    try:
        raw = generate_text(system, x.source_text[:45000], x.api_key, x.model, .4, 90, json_mode=True)
        data = extract_json_block(raw)
        questions = data.get("questions") if isinstance(data, dict) else None
        if not isinstance(questions, list) or len(questions) != x.num_questions:
            raise ValueError("Invalid quiz question count")
        for q in questions:
            if not isinstance(q, dict) or not q.get("question") or q.get("correct") not in {"A", "B", "C", "D"}:
                raise ValueError("Invalid quiz question")
            if not isinstance(q.get("explanation"), str) or not q.get("explanation").strip():
                raise ValueError("Missing quiz explanation")
            options = q.get("options")
            if not isinstance(options, dict) or set(options.keys()) != {"A", "B", "C", "D"}:
                raise ValueError("Invalid quiz options")
        return data
    except ValueError as e:
        logger.exception("Quiz output validation failed")
        raise HTTPException(502, detail={"kind": "output", "message": "Gemini responded, but Quiz Forge received an incomplete quiz. Try 5 questions or a shorter source."})
    except Exception as e:
        logger.exception("ACUMEN AI request failed")
        k, m = classify_error(e)
        raise HTTPException(503, detail={"kind": k, "message": m})

@app.post("/api/quiz/extract")
async def extract(file: UploadFile = File(...)):
    # FIX: hard cap uploads before parsing them into memory.
    max_bytes = 8 * 1024 * 1024
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(413, "File is too large. Maximum size is 8 MB.")
    name = (file.filename or "").lower()
    if name.endswith(".pdf"):
        text = "\n\n".join((p.extract_text() or "") for p in PdfReader(BytesIO(data)).pages)
    else:
        text = data.decode("utf-8", errors="ignore")
    if not text.strip():
        raise HTTPException(400, "No readable text found")
    return {"filename": file.filename, "text": text[:60000], "characters": min(len(text), 60000)}

@app.post("/api/planning/generate")
def planning(x: Plan):
    user = f'''Profile:{json.dumps(x.profile)}\nRhythm:{x.chronotype}\nDaily hours:{x.daily_hours}\nDays:{x.plan_length}\nSlots:{x.preferred_slots}\nBreaks:{x.break_style}\nEnergy:{x.energy_note}\nTasks:{x.tasks}\nDeadline:{x.deadline}\nConstraints:{x.constraints}'''
    system = f'''You are ACUMEN's intelligent study planner.
Create exactly {x.plan_length} days. This is a usable schedule, not motivational prose.

STUDENT PROFILE
{json.dumps(x.profile, ensure_ascii=False)}

PLANNING RULES
- Treat profile signals as hypotheses about how to structure work, never as personality labels.
- The user wants a schedule they can print and follow. Make blocks concrete, timed and realistic.
- Never exceed the student's {x.daily_hours} hour daily study budget. Breaks do not count as study time.
- Use the student's available slots and energy pattern. Do not invent availability.
- A deadline is optional. Do NOT force fake urgency, countdowns or arbitrary due dates.
- If no deadline is supplied, distribute work by importance, prerequisite order and spacing.
- Break large tasks into meaningful sessions. Avoid vague blocks such as 'study maths'.
- Use retrieval, spacing, interleaving, worked examples and practice when they fit the task. Do not mechanically attach a technique to every block.
- Include recovery and lighter work when the profile/energy suggests it.
- Revisit important material across days rather than front-loading everything.
- Keep social or personal commitments as fixed blocks if the user supplied them.
- Each block needs a realistic time range, a specific task and a short note explaining the method or purpose.
- Prefer 2-4 meaningful blocks per day over a wall of tiny tasks.

Return STRICT JSON only:
{{"days":[{{"day":1,"title":"Short human title","focus":"What this day is for","blocks":[{{"time":"07:30 - 08:20","task":"Specific task","note":"Short practical instruction"}}]}}]}}
'''
    try:
        data = extract_json_block(generate_text(system, user, x.api_key, x.model, .5, 90, json_mode=True))
        days = data.get("days") if isinstance(data, dict) else None
        if not isinstance(days, list) or len(days) != x.plan_length:
            raise ValueError("Invalid roadmap day count")
        # FIX: Validate the structure before sending it to the browser. A malformed
        # JSON response should become a clear output error, not a broken plan UI.
        for index, day in enumerate(days, start=1):
            if not isinstance(day, dict) or not day.get("title") or not isinstance(day.get("blocks"), list) or not day["blocks"]:
                raise ValueError(f"Invalid roadmap day {index}")
            for block in day["blocks"]:
                if not isinstance(block, dict) or not block.get("time") or not block.get("task"):
                    raise ValueError(f"Invalid roadmap block on day {index}")
        return data
    except ValueError:
        logger.exception("Roadmap output validation failed")
        raise HTTPException(502, detail={"kind": "output", "message": "Gemini responded, but ACUMEN received an incomplete study plan. Try fewer days or simpler task descriptions."})
    except Exception as e:
        logger.exception("ACUMEN AI request failed")
        k, m = classify_error(e)
        raise HTTPException(503, detail={"kind": k, "message": m})

@app.post("/api/feedback")
def feedback(x: Feedback):
    # Persistence is performed client-side through Supabase RLS. This endpoint stays as a health-compatible fallback.
    return {"received": True, "message": "Feedback received."}

app.mount("/assets", StaticFiles(directory=ROOT / "frontend/assets"), name="assets")


@app.get("/favicon.ico")
def favicon():
    # UPGRADE: Browsers request this automatically. Return an empty successful response instead of a noisy 404.
    return Response(status_code=204)

@app.get("/{page}.html")
def page(page: str):
    allowed = {
        "index", "assessment", "blueprint", "history", "mr-brown", "what-if",
        "old-days", "quiz-forge", "roadmap", "faq", "feedback", "settings", "account",
    }
    if page not in allowed:
        raise HTTPException(404, "Page not found")
    return FileResponse(ROOT / "frontend" / f"{page}.html")

@app.get("/")
def home():
    return FileResponse(ROOT / "frontend/index.html")
