import streamlit as st
from data.question import ALL_QUESTIONS

# ==============================================================================
# 1. SESSION INTEGRITY CHECK
# ==============================================================================
# FIX: verifiait uniquement `answers`, ce qui bloquait le chemin cheat code
# (qui remplit core_vectors mais jamais answers). Meme logique que
# 01_Assessment.py maintenant.
if not st.session_state.get('answers') and not st.session_state.get('core_vectors'):
    st.error("🛑 No answers detected in session memory.")
    st.markdown("You need to complete the assessment before unlocking this report.")
    if st.button("🚀 Return to Assessment", type="primary", use_container_width=True):
        st.switch_page("pages/01_Assessment.py")
    st.stop()

if 'user_profile' not in st.session_state:
    st.session_state.user_profile = {"pseudo": "Anonymous Builder", "gender": "Unmapped", "initialized": True}

user_profile = st.session_state.user_profile
pseudo = (user_profile.get("pseudo", "Anonymous Builder") or "").strip() or "Operator"
classification = user_profile.get("gender", "Unmapped Human")
answers = st.session_state.get("answers", {}) or {}

VECTOR_KEYS = ["information_bandwidth", "execution_rigor", "chaos_tolerance", "cognitive_endurance"]

if not ALL_QUESTIONS:
    st.error("⚠️ CRITICAL: The global ALL_QUESTIONS database is empty or missing.")
    st.stop()


# ==============================================================================
# 2. DATA PARSING ENGINE — LIKERT SCALE (1-5 par affirmation)
# ==============================================================================
# UPGRADE : answers[qid] est maintenant {"A": 4, "B": 2, "C": 5, "D": 1} au
# lieu d'une seule lettre choisie — chaque affirmation est notee
# independamment. Meme formule ponderee que 01_Assessment.py :
#   poids = (note - 3) / 2   (-1.0 a +1.0, neutre a note=3)
sections_data = {}
all_ratings = []
vector_totals = {k: 0.0 for k in VECTOR_KEYS}

if answers:
    for q in ALL_QUESTIONS:
        q_id = q.get('id')
        ratings_for_q = answers.get(q_id, {}) or {}
        if not ratings_for_q:
            continue

        options = q.get("options", {}) or {}
        sec_name = q.get('section', 'General Mindset')
        if sec_name not in sections_data:
            sections_data[sec_name] = []

        question_items = []
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

            item = {
                "q_id": str(q_id),
                "question": q.get('question', 'Missing Question'),
                "choice_text": opt_data.get('text', ''),
                "label": opt_data.get('label', 'Standard Processing'),
                "advice": opt_data.get('advice', 'No direct advice available.'),
                "rating": rating,
            }
            question_items.append(item)
            all_ratings.append(item)

        sections_data[sec_name].extend(question_items)

    if not all_ratings:
        st.error("⚠️ We couldn't extract any behavioral patterns. The data matrix is empty.")
        if st.button("🔄 Try Assessment Again"):
            st.switch_page("pages/01_Assessment.py")
        st.stop()

    # UPGRADE : l'ancien "archetype le plus frequent" (Counter sur les
    # labels choisis) n'a plus de sens — chaque affirmation notee est
    # unique, donc chaque label n'apparait qu'une fois. L'archetype
    # dominant devient l'affirmation la mieux notee sur tout le quiz.
    top_matches = sorted(all_ratings, key=lambda r: r["rating"], reverse=True)[:3]
    dominant_archetype = top_matches[0]["label"] if top_matches else "Unclassified"

else:
    # Chemin cheat code : pas de notes individuelles, on lit directement
    # ce que 01_Assessment.py a deja stocke.
    vector_totals = st.session_state.get("core_vectors", {k: 0.0 for k in VECTOR_KEYS})
    top_matches = st.session_state.get("top_matches", [])
    dominant_archetype = top_matches[0]["label"] if top_matches else "Test Profile (developer shortcut)"


# ==============================================================================
# 3. THEORETICAL RANGE ENGINE
# ==============================================================================
# FIX / UPGRADE : avec l'ancien systeme a choix unique, le max/min
# theorique par question etait le meilleur/pire des 4 OPTIONS (on ne
# pouvait en choisir qu'une). Avec le Likert, les 4 options sont notees
# INDEPENDAMMENT — donc pour maximiser un axe sur une question, il faut
# mettre note=5 sur chaque option qui pousse cet axe positivement ET
# note=1 sur chaque option qui le pousse negativement (ce qui, une fois
# invertie par le poids negatif, pousse aussi POSITIVEMENT). Le vrai
# maximum atteignable par question et par axe est donc la somme des
# valeurs ABSOLUES des 4 vecteurs sur cet axe, pas juste le max/min d'un
# seul choix. Sans cette correction, la normalisation 0-100% aurait ete
# fausse (bornes trop etroites) pour le nouveau systeme de notation.
theoretical_max = {axis: 0.0 for axis in VECTOR_KEYS}
theoretical_min = {axis: 0.0 for axis in VECTOR_KEYS}

for q in ALL_QUESTIONS:
    opts = (q.get("options", {}) or {}).values()
    for axis in VECTOR_KEYS:
        axis_abs_sum = 0.0
        for opt in opts:
            try:
                v = float((opt.get("vectors", {}) or {}).get(axis, 0.0))
            except (TypeError, ValueError):
                v = 0.0
            axis_abs_sum += abs(v)
        theoretical_max[axis] += axis_abs_sum
        theoretical_min[axis] -= axis_abs_sum


def normalize_axis(axis: str) -> int:
    lo, hi = theoretical_min[axis], theoretical_max[axis]
    if hi <= lo:
        return 50
    pct = (vector_totals[axis] - lo) / (hi - lo) * 100
    return max(0, min(100, round(pct)))


normalized_scores = {axis: normalize_axis(axis) for axis in VECTOR_KEYS}
strongest_key = max(vector_totals, key=vector_totals.get)
weakest_key = min(vector_totals, key=vector_totals.get)

AXIS_DISPLAY_NAMES = {
    "information_bandwidth": "Information Bandwidth",
    "execution_rigor": "Execution Rigor",
    "chaos_tolerance": "Chaos Tolerance",
    "cognitive_endurance": "Cognitive Endurance",
}


# ==============================================================================
# 4. THE BLUEPRINT GENERATOR (inchangé — construit sur strongest/weakest key,
# qui restent calculées de la même façon)
# ==============================================================================
AXIS_NARRATIVES = {
    "information_bandwidth": {
        "high": {
            "adj": "wide-scanning, pattern-hungry",
            "overreach": "you'll happily juggle five open threads at once, and sometimes lose the plot on which one actually matters right now",
        },
        "low": {
            "adj": "narrow-focus, detail-first",
            "blind_spot": "you do best with one clearly-defined piece of information at a time — throw six requirements at you simultaneously and details start quietly slipping through the cracks",
            "crisis": "under pressure, you'll re-read the same paragraph three times instead of asking someone to just summarize it for you",
            "synergy": "someone who scans the big picture fast and hands you one clean instruction at a time",
        },
    },
    "execution_rigor": {
        "high": {
            "adj": "structured, checklist-driven",
            "overreach": "you'll spend precious minutes perfecting a function nobody asked you to touch yet",
        },
        "low": {
            "adj": "fast-and-loose, ship-first",
            "blind_spot": "clean code and documentation feel like friction when the clock is running — you'll happily duct-tape a fix and move on without asking why it broke",
            "crisis": "when something breaks under deadline pressure, you patch the symptom, not the cause, and it usually resurfaces an hour later",
            "synergy": "someone who's genuinely energized by cleaning up after a sprint and closing the loose ends you left open",
        },
    },
    "chaos_tolerance": {
        "high": {
            "adj": "unshaken by pivots",
            "overreach": "you'll suggest ripping out the whole architecture mid-hackathon because you found a shinier framework at 2am",
        },
        "low": {
            "adj": "stability-seeking",
            "blind_spot": "a sudden scope change or a teammate improvising on the fly costs you real focus — you need the plan to hold still to do your best work",
            "crisis": "when the environment turns chaotic, you go quiet and disengage rather than push back or adapt out loud",
            "synergy": "someone who can absorb last-minute chaos and translate it into one calm, concrete next step for you",
        },
    },
    "cognitive_endurance": {
        "high": {
            "adj": "built for the long grind",
            "overreach": "you'll stay locked on one hard problem for hours, even past the point where a fresh pair of eyes would solve it faster",
        },
        "low": {
            "adj": "built for short, intense bursts",
            "blind_spot": "your best thinking comes in sharp 20-30 minute windows — push past that and your output quietly degrades while you keep typing anyway",
            "crisis": "in a long crunch, you'll keep working out of stubbornness long after your focus has actually left the building",
            "synergy": "someone who can take the wheel on the long, grinding stretches so you can show up fully for the sharp, high-leverage moments",
        },
    },
}


def build_blueprint(strong_key: str, weak_key: str) -> dict:
    strong = AXIS_NARRATIVES[strong_key]["high"]
    weak = AXIS_NARRATIVES[weak_key]["low"]

    tagline = f"{strong['adj'].capitalize()} — and {weak['adj']}."
    blind_spots = (
        f"{weak['blind_spot'].capitalize()}. "
        f"And because you're also {strong['adj']}, {strong['overreach']}."
    )
    crisis_mode = weak['crisis'].capitalize() + "."
    synergy = f"You need {weak['synergy']} — someone who covers exactly the ground where you run thin."

    return {
        "tagline": tagline,
        "blind_spots": blind_spots,
        "crisis_mode": crisis_mode,
        "synergy": synergy,
    }


strategy_block = build_blueprint(strongest_key, weakest_key)


# ==============================================================================
# 5. HIGH-IMPACT REPORT RENDERING
# ==============================================================================
st.markdown("<p style='color: #6366F1; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; margin-bottom: -10px;'>Diagnostic Unlocked</p>", unsafe_allow_html=True)
st.title("🧬 Your Builder Blueprint")
st.divider()

col1, col2, col3 = st.columns(3)
col1.metric(label="BUILDER ALIAS", value=pseudo.upper())
col2.metric(label="OPERATIONAL PROFILE", value=classification.upper())
col3.metric(label="DOMINANT ARCHETYPE", value=dominant_archetype.upper())

st.write("")
st.write("")

left_layout, right_layout = st.columns([5, 4], gap="large")

with left_layout:
    st.markdown("### 🛠️ Hackathon Survival Guide")
    st.caption("Generated from your two most defining traits — not a generic lookup.")

    st.markdown(f"""
    <div style="background-color: #1E1E2E; border-left: 4px solid #6366F1; padding: 18px; border-radius: 6px; margin-bottom: 20px;">
        <div style="font-weight: 700; color: #F3F4F6; font-size: 16px; margin-bottom: 4px;">STRONGEST: {AXIS_DISPLAY_NAMES[strongest_key].upper()} · WEAKEST: {AXIS_DISPLAY_NAMES[weakest_key].upper()}</div>
        <div style="font-style: italic; color: #9CA3AF; font-size: 14px;">"{strategy_block['tagline']}"</div>
    </div>
    """, unsafe_allow_html=True)

    with st.container(border=True):
        st.markdown("🚨 **YOUR BIGGEST BLIND SPOT**")
        st.markdown(strategy_block["blind_spots"])

    with st.container(border=True):
        st.markdown("🔥 **WHAT HAPPENS IN CRISIS MODE**")
        st.markdown(strategy_block["crisis_mode"])

    with st.container(border=True):
        st.markdown("🤝 **YOUR DREAM TEAMMATE**")
        st.markdown(strategy_block["synergy"])

with right_layout:
    st.markdown("### 📊 Your 4-Axis Signature")
    st.caption("Where you land on each core dimension — this is the raw data the blueprint above is built from.")
    st.write("")

    for axis, display_name in AXIS_DISPLAY_NAMES.items():
        pct = normalized_scores[axis]
        tag = ""
        if axis == strongest_key:
            tag = " · strongest"
        elif axis == weakest_key:
            tag = " · weakest"
        st.markdown(f"**{display_name}{tag}**")
        st.progress(pct / 100, text=f"{pct}%")
        st.write("")

    # UPGRADE : l'ancien "Raw signal frequency" comptait combien de fois
    # chaque label apparaissait — sens perdu puisque chaque label est
    # maintenant unique. Remplace par le classement des affirmations les
    # mieux notees, qui porte la meme idee ("quels signaux dominent
    # vraiment ton profil") sous la nouvelle logique.
    if top_matches:
        with st.expander("🔬 Your top-rated statements (advanced)"):
            st.caption("The statements you rated highest across the whole assessment.")
            for item in top_matches:
                st.markdown(f"**{item['label']}** — rated {int(item['rating'])}/5")


# ==============================================================================
# 6. TACTICAL ADVICE ARCHIVE (adapte au Likert — affiche les 4 notes par
# question, triees, au lieu du seul choix qu'on aurait fait avant)
# ==============================================================================
st.write("")
st.divider()
st.markdown("### 🔍 Tactical Advice Archive")
st.caption("Every statement you rated, organized by section — highest-rated first within each question.")
st.write("")

if sections_data:
    tab_names = [name.split(":")[1].strip() if ":" in name else name for name in sections_data.keys()]
    valid_tabs = [name for name in tab_names if name]

    if valid_tabs:
        tabs = st.tabs(valid_tabs)
        for tab, (sec_full_name, items) in zip(tabs, sections_data.items()):
            with tab:
                st.write("")
                # Regrouper par question pour afficher les 4 notes ensemble
                by_question = {}
                for item in items:
                    by_question.setdefault(item["q_id"], {"question": item["question"], "items": []})
                    by_question[item["q_id"]]["items"].append(item)

                for q_id, q_data in by_question.items():
                    st.markdown(f"**Q{q_id}: {q_data['question']}**")
                    ranked = sorted(q_data["items"], key=lambda r: r["rating"], reverse=True)
                    for item in ranked:
                        with st.expander(f"{int(item['rating'])}/5 — {item['label']}"):
                            st.markdown(f"*{item['choice_text']}*")
                            st.divider()
                            st.info(f"💡 **Tactical Remediation:** {item['advice']}")
                    st.write("")
else:
    st.info("No detailed signals logged yet — this profile was loaded via the developer shortcut.")


# ==============================================================================
# 7. FOOTER
# ==============================================================================
st.write("")
st.divider()
col_foot1, col_foot2 = st.columns([3, 1])

with col_foot1:
    st.caption("ACUMEN Metacognitive Profiler • Runs entirely on your own answers, no external API needed for this page.")

with col_foot2:
    if st.button("Start Over 🔄", use_container_width=True, type="secondary"):
        st.session_state.answers = {}
        if "current_q_idx" in st.session_state:
            st.session_state.current_q_idx = 0
        if "flags" in st.session_state:
            st.session_state.flags["scan_completed"] = False
            st.session_state.flags["chatbot_unlocked"] = False
        st.switch_page("pages/01_Assessment.py")