import streamlit as st
import re
import uuid
from typing import Annotated, TypedDict
from core.utils import extract_text, is_plausible_gemini_key
from core.ai_engine import invoke_llm_with_fallback, stream_graph_response

try:
    from langchain_core.messages import HumanMessage, AIMessage
except ImportError:
    st.error("⚠️ CRITICAL FAULT: Missing core dependencies. Execute: pip install langchain langchain-google-genai google-generativeai")
    st.stop()

try:
    from langgraph.graph import StateGraph, START, END
    from langgraph.graph.message import add_messages
    from langgraph.checkpoint.memory import MemorySaver
except ImportError:
    st.error("⚠️ CRITICAL FAULT: Missing LangGraph. Execute: pip install langgraph")
    st.stop()


if not st.session_state.get("flags", {}).get("scan_completed"):
    st.error("🛑 ACCESS DENIED: Neural baseline not established. Complete the diagnostic scan first.")
    if st.button("🚀 Initiate Assessment", type="primary", use_container_width=True):
        st.switch_page("lumen_app.py")
    st.stop()

user_profile = st.session_state.get("user_profile", {}) or {}
pseudo_raw = user_profile.get("pseudo", "Operator")
pseudo = re.sub(r"[^\w\s\-']", "", str(pseudo_raw)).strip()[:60] or "Operator"

answers = st.session_state.get("answers", {}) or {}
core_vectors_from_state = st.session_state.get("core_vectors", {}) or {}

vector_labels = {
    "information_bandwidth": "Information Bandwidth",
    "execution_rigor": "Execution Rigor",
    "chaos_tolerance": "Chaos Tolerance",
    "cognitive_endurance": "Cognitive Endurance"
}

if answers:
    try:
        from data.question import ALL_QUESTIONS
    except ImportError:
        st.error("⚠️ Missing database connection to data.question.ALL_QUESTIONS")
        st.stop()

    if not isinstance(ALL_QUESTIONS, list) or len(ALL_QUESTIONS) == 0:
        st.error("⚠️ Question database is empty or malformed. Cannot compute cognitive profile.")
        st.stop()

    vector_totals = {k: 0.0 for k in vector_labels}
    all_ratings = []

    for q in ALL_QUESTIONS:
        q_id = q.get('id')
        ratings_for_q = answers.get(q_id, {}) or {}
        if not ratings_for_q:
            continue

        options = q.get("options", {}) or {}
        q_section = q.get('section', f"Query {q_id}")

        for opt_key, opt_data in options.items():
            if not isinstance(opt_data, dict):
                continue
            rating = ratings_for_q.get(opt_key)
            if rating is None:
                continue
            try:
                rating = float(rating)
            except (TypeError, ValueError):
                continue

            weight = (rating - 3.0) / 2.0
            vectors = opt_data.get("vectors", {}) or {}
            for v_key, v_val in vectors.items():
                if v_key in vector_totals:
                    try:
                        vector_totals[v_key] += weight * float(v_val)
                    except (TypeError, ValueError):
                        continue

            all_ratings.append({
                "section": q_section,
                "text": opt_data.get("text", opt_key),
                "label": opt_data.get("label", "Unmapped"),
                "rating": rating,
            })

    ranked = sorted(all_ratings, key=lambda r: r["rating"], reverse=True)
    dominant_archetype = ranked[0]["label"] if ranked else "Unclassified"

    detailed_choices = [
        f"- {m['section']}: {m['text']} (Signaling {m['label']}, rated {int(m['rating'])}/5)"
        for m in ranked[:8]
    ]
    detailed_choices_block = "\n".join(detailed_choices) if detailed_choices else "- (No detailed signals on file.)"

else:
    vector_totals = {k: float(core_vectors_from_state.get(k, 0.0)) for k in vector_labels}
    strongest_preview = max(vector_totals, key=vector_totals.get) if vector_totals else "information_bandwidth"
    dominant_archetype = f"{vector_labels.get(strongest_preview, strongest_preview)}-Dominant Profile (test profile)"
    detailed_choices_block = (
        "- (Profile injected via developer shortcut - no individual question responses on file. "
        "Calibrate purely from the cognitive vectors below.)"
    )

strongest_key = max(vector_totals, key=vector_totals.get) if vector_totals else "information_bandwidth"
weakest_key = min(vector_totals, key=vector_totals.get) if vector_totals else "cognitive_endurance"


TECHNIQUE_LIBRARY = [
    {"name": "Spaced Repetition", "description": "Reviewing material at increasing intervals timed just before you'd naturally forget it (the spacing effect), instead of cramming everything into one session.", "addresses": ["cognitive_endurance", "execution_rigor"], "leverages": []},
    {"name": "Interleaving", "description": "Mixing different topics or problem types within a single session instead of blocking one subject at a time, which forces the brain to actively discriminate which method applies.", "addresses": ["information_bandwidth"], "leverages": ["chaos_tolerance"]},
    {"name": "The Feynman Technique", "description": "Explaining a concept in the simplest possible language as if teaching a beginner, then using the exact points where you stumble to find and patch real gaps in understanding.", "addresses": ["information_bandwidth"], "leverages": ["execution_rigor"]},
    {"name": "Chunking (Cognitive Load Management)", "description": "Breaking dense material into small, tightly-scoped units small enough to fit in working memory, mastering each before combining them into the bigger structure.", "addresses": ["cognitive_endurance", "information_bandwidth"], "leverages": ["execution_rigor"]},
    {"name": "Timeboxing / Pomodoro-style sprints", "description": "Working in short, strictly bounded focus intervals with enforced breaks, using the external time limit as structure instead of relying on willpower alone.", "addresses": ["execution_rigor", "cognitive_endurance"], "leverages": []},
    {"name": "Dual Coding", "description": "Pairing verbal explanations with diagrams, sketches, or spatial layouts of the same idea, since encoding information two different ways measurably improves recall.", "addresses": ["information_bandwidth"], "leverages": ["chaos_tolerance"]},
    {"name": "Active Recall / Retrieval Practice", "description": "Closing the book and forcing yourself to reconstruct the material from memory (self-testing) instead of re-reading it - proven to build far stronger long-term retention.", "addresses": ["cognitive_endurance"], "leverages": ["execution_rigor"]},
    {"name": "Elaborative Interrogation", "description": "Continuously asking yourself 'why is this true?' and 'how does this connect to what I already know?' while studying, turning passive reading into active reasoning.", "addresses": ["execution_rigor"], "leverages": ["information_bandwidth"]},
    {"name": "Method of Loci (Memory Palace)", "description": "Mentally placing pieces of information along a vivid, familiar spatial route (a house, a walk to school), then 'walking through' it to retrieve them in order.", "addresses": ["cognitive_endurance"], "leverages": ["chaos_tolerance", "information_bandwidth"]},
    {"name": "Desirable Difficulties", "description": "Deliberately making practice harder in the short term - testing before you feel ready, varying conditions, spacing things out - because the extra short-term struggle produces much stronger long-term learning.", "addresses": ["execution_rigor"], "leverages": ["chaos_tolerance"]},
]


def select_priority_techniques(weakest_key: str, strongest_key: str) -> list:
    addresses_weak = [t["name"] for t in TECHNIQUE_LIBRARY if weakest_key in t.get("addresses", [])]
    leverages_strong = [t["name"] for t in TECHNIQUE_LIBRARY if strongest_key in t.get("leverages", [])]
    picks = []
    for name in addresses_weak[:2] + leverages_strong[:1]:
        if name not in picks:
            picks.append(name)
    if not picks:
        picks = [TECHNIQUE_LIBRARY[0]["name"]]
    return picks


st.markdown("""
<style>
    .chat-header { background: linear-gradient(90deg, #6366F1 0%, #A855F7 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-weight: 800; font-size: 2.5rem; letter-spacing: -1px; }
    .metric-pill { background-color: #1E1E2E; border: 1px solid #333; border-radius: 20px; padding: 5px 15px; font-size: 0.85rem; color: #A1A1AA; display: inline-block; margin-right: 10px; margin-bottom: 20px; }
</style>
""", unsafe_allow_html=True)

st.markdown("<h1 class='chat-header'>MR. BROWN</h1>", unsafe_allow_html=True)
st.markdown(f"""
<div class='metric-pill'>👤 Operator: <b>{pseudo}</b></div>
<div class='metric-pill'>🧬 Archetype: <b>{dominant_archetype}</b></div>
<div class='metric-pill'>⚡ Core Advantage: <b>{vector_labels.get(strongest_key, strongest_key)}</b></div>
""", unsafe_allow_html=True)
st.divider()

if "brown_thread_id" not in st.session_state:
    st.session_state.brown_thread_id = str(uuid.uuid4())

with st.sidebar:
    st.markdown("### 🎛️ Engine Matrix (Gemini API)")
    st.session_state.gemini_api_key = st.text_input(
        "Gemini Authentication Key:",
        value=st.session_state.get("gemini_api_key", ""),
        type="password",
        help=(
            "**How to get your key (free):**\n\n"
            "1. Go to [aistudio.google.com/apikey](https://aistudio.google.com/apikey)\n"
            "2. Sign in with a Google account\n"
            "3. Click **'Create API key'**\n"
            "4. Paste it here (it starts with `AIza...`)\n\n"
            "It's never stored anywhere except in your browser session for this app."
        )
    ).strip()

    selected_model = st.selectbox(
        "Language Model Topology:",
        options=["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-3.5-flash", "gemini-flash-latest"],
        index=0,
        help="gemini-2.5-flash offers the best balance of quality and reliability. Try gemini-3.5-flash if you want noticeably better instruction-following on complex prompts."
    )

    temperature = st.slider("Cognitive Drift (Temperature):", 0.0, 1.0, 0.55, 0.05,
                            help="Lower values yield sharper, more literal answers. Higher values sound more natural but less predictable.")
    request_timeout = st.slider("Request Timeout (s)", 10, 120, 45, 5)

    st.divider()
    if st.button("Purge Session Memory 🧹", use_container_width=True, type="secondary"):
        st.session_state.brown_thread_id = str(uuid.uuid4())
        st.rerun()

gemini_api_key = st.session_state.get("gemini_api_key", "")


class MentorState(TypedDict):
    messages: Annotated[list, add_messages]
    pseudo: str
    dominant_archetype: str
    strongest_key: str
    weakest_key: str
    strongest_label: str
    weakest_label: str
    detailed_choices: str
    selected_techniques: list


def build_system_prompt(state: MentorState) -> str:
    library_block = "\n".join(f"- {t['name']}: {t['description']}" for t in TECHNIQUE_LIBRARY)
    priority = state.get("selected_techniques") or []
    priority_block = ", ".join(priority) if priority else "(none flagged - pick freely from the library)"

    return f"""
[ROLE]
You are Mr. Brown, an elite, uncompromising, yet deeply invested intellectual mentor and strategist. You work with self-directed students who take ownership of their own learning, whatever subject or field they're actually in - you never assume a specific major, career track, or academic background beyond what's given to you in the CONTEXT below.

[CORE BEHAVIORAL GUIDELINES]
1. Intellectual Rigor over Comfort: Never hand out cheap validation or surface-level summaries. Demand deep, rigorous first-principles thinking. Treat the user like an equal peer in a high-level seminar.
2. Precision Over Vagueness: Favor precise explanations, clear logical structure, and systematic problem-solving over rote memorization or mundane descriptions - regardless of the subject matter at hand.
3. Tone: Sharp, articulate, pragmatic, slightly cynical about standard institutional paths, but fiercely supportive of intellectual autonomy, mastery, and precision. Speak with quiet authority - like a real mentor talking to someone they respect, not a customer-support script.
4. Contextual Adaptation: Seamlessly integrate the user's actual dominant archetype and cognitive profile vectors (information bandwidth, execution rigor, chaos tolerance, cognitive endurance) - given below in CONTEXT - when calibrating the complexity, pacing, and tone of your answers. Push them precisely where their metrics indicate room for growth. These vectors, not any assumption about their field of study, are what should drive personalization.
5. Real Listening Before Advice: If the user's request is ambiguous, underspecified, or could go multiple directions, ask ONE sharp clarifying question before dumping a full answer - don't guess and pad the response with hedges to cover every interpretation at once. If the request is already clear and specific, just answer it directly.
6. Ground Advice in Named Mechanisms: When you give a piece of advice, name the actual psychological or learning-science mechanism behind it (spacing effect, cognitive load, ego-involvement, desirable difficulty, etc.) before the action step - never a generic productivity tip with no explanation of why it works for this specific person.
7. Vary Your Structure: Do not default to the same bullet-point or numbered-list scaffold in every response. Write in natural prose when the answer is a single coherent idea; use structure only when the content genuinely has multiple distinct parts. Avoid stock openers like "Great question!" or "Let's break this down:".
8. No Fluff: Eliminate generic AI filler phrases ("Sure, I can help with that!", "As an AI..."). Start straight with substance.
9. Never Invent Terminology: You do not have a private vocabulary of made-up frameworks ("operational triage protocol", "cognitive load constraints", or similar impressive-sounding but fabricated terms). If you reference a technique, it MUST be one of the named techniques in THE VERIFIED TECHNIQUE LIBRARY below, referenced explicitly by its actual name, using its actual description as grounding. If none of the library techniques genuinely fit the situation, say so plainly and reason from first principles in plain, ordinary language instead of inventing jargon to sound sophisticated.
10. Always Land on One Concrete Action: Never end a response on an abstract diagnosis alone, however well-articulated. Every substantive answer must close with ONE specific, concrete next step the person can realistically do in the next 10-15 minutes - tied to their actual situation as they described it, not a generic instruction that could apply to anyone. If they gave you a vague situation with no real specifics to act on, ask what you need before prescribing anything, rather than filling the gap with abstraction.

[TASK]
Recommend and adapt techniques FROM THE VERIFIED LIBRARY below to the operator's specific dominant archetype and cognitive metrics whenever relevant - never substitute generic advice for a named, explained technique from this library when one applies.

[VERIFIED TECHNIQUE LIBRARY]
{library_block}

[PRIORITY PICKS FOR THIS OPERATOR]
{priority_block}

[FORMAT]
Format responses using Markdown, but only where structure genuinely helps - not by default. Write in English with flawless, economical eloquence. Match your response length to the actual weight of the question: a quick check-in deserves a short answer, a real roadblock deserves real depth - depth means more concrete specifics and a fuller explanation of the mechanism, not more abstract restatement of the same idea in different words.

[CONTEXT]
- Operator Name: {state.get('pseudo', 'Operator')}
- Dominant Cognitive Archetype: {state.get('dominant_archetype', 'Unclassified')}
- Primary Strength: {state.get('strongest_label', '')}
- Critical Growth Axis: {state.get('weakest_label', '')}

Operator's Specific Neural Footprint:
{state.get('detailed_choices', '')}
"""


def select_techniques_node(state: MentorState, config) -> dict:
    picks = select_priority_techniques(state.get("weakest_key", ""), state.get("strongest_key", ""))
    return {"selected_techniques": picks}


def mentor_node(state: MentorState, config) -> dict:
    cfg = (config or {}).get("configurable", {})
    system_prompt = build_system_prompt(state)
    response = invoke_llm_with_fallback(
        system_prompt=system_prompt,
        history_messages=state.get("messages", []),
        api_key=cfg.get("api_key", ""),
        model=cfg.get("model", "gemini-2.5-flash"),
        temperature=cfg.get("temperature", 0.55),
        timeout=cfg.get("timeout", 45),
    )
    return {"messages": [response]}


@st.cache_resource
def get_mentor_app():
    graph = StateGraph(MentorState)
    graph.add_node("select_techniques", select_techniques_node)
    graph.add_node("mentor", mentor_node)
    graph.add_edge(START, "select_techniques")
    graph.add_edge("select_techniques", "mentor")
    graph.add_edge("mentor", END)
    return graph.compile(checkpointer=MemorySaver())


mentor_app = get_mentor_app()


def build_config():
    return {"configurable": {"thread_id": st.session_state.brown_thread_id, "api_key": gemini_api_key, "model": selected_model, "temperature": temperature, "timeout": request_timeout}}


def get_checkpointed_messages():
    try:
        snapshot = mentor_app.get_state(build_config())
        if not snapshot or not snapshot.values:
            return []
        return snapshot.values.get("messages", [])
    except Exception:
        return []


def seed_greeting_if_new():
    if get_checkpointed_messages():
        return
    greeting = f"Alright, {pseudo}. I've looked at your profile — what are you actually stuck on right now?"
    try:
        mentor_app.update_state(build_config(), {"messages": [AIMessage(content=greeting)]})
    except Exception:
        pass


seed_greeting_if_new()


for m in get_checkpointed_messages():
    if isinstance(m, HumanMessage):
        with st.chat_message("user", avatar="👤"):
            st.markdown(extract_text(m.content))
    elif isinstance(m, AIMessage):
        with st.chat_message("assistant", avatar="🎓"):
            st.markdown(extract_text(m.content))


if prompt := st.chat_input(f"Enter your academic roadblock, {pseudo}..."):
    if not is_plausible_gemini_key(gemini_api_key):
        st.error("⚠️ Mr. Brown offline. Please input a valid Gemini API Key in the Engine Matrix.")
        st.stop()

    prompt = prompt.strip()[:4000]

    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar="🎓"):
        message_placeholder = st.empty()
        input_state = {
            "messages": [HumanMessage(content=prompt)],
            "pseudo": pseudo,
            "dominant_archetype": dominant_archetype,
            "strongest_key": strongest_key,
            "weakest_key": weakest_key,
            "strongest_label": vector_labels.get(strongest_key, strongest_key),
            "weakest_label": vector_labels.get(weakest_key, weakest_key),
            "detailed_choices": detailed_choices_block,
        }
        full_response, error_message = stream_graph_response(
            app=mentor_app,
            input_state=input_state,
            config=build_config(),
            placeholder=message_placeholder,
            node_filter={"mentor"},
        )
        if error_message:
            st.error(error_message)