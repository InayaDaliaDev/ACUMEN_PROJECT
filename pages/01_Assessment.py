import streamlit as st
import re
from data.question import ALL_QUESTIONS

# ==============================================================================
# PHASE 1: SESSION STATE INITIALIZATION
# ==============================================================================
if "current_q_idx" not in st.session_state:
    st.session_state.current_q_idx = 0

if "answers" not in st.session_state:
    st.session_state.answers = {}

if "flags" not in st.session_state:
    st.session_state.flags = {}

if "user_profile" not in st.session_state:
    st.session_state.user_profile = {"pseudo": "Builder"}

if not isinstance(ALL_QUESTIONS, list) or len(ALL_QUESTIONS) == 0:
    st.error("⚠️ CRITICAL: Question database is empty or missing. Cannot run the assessment.")
    st.stop()

TOTAL_QUESTIONS = len(ALL_QUESTIONS)
if st.session_state.current_q_idx > TOTAL_QUESTIONS:
    st.session_state.current_q_idx = TOTAL_QUESTIONS

VECTOR_KEYS = ["information_bandwidth", "execution_rigor", "chaos_tolerance", "cognitive_endurance"]


# ==============================================================================
# DEV SHORTCUT (test uniquement — a retirer ou cacher avant une vraie demo)
# ==============================================================================
with st.expander("🔧 Developer Shortcut (bypass le questionnaire pour tester)"):
    cheat_code = st.text_input("Code :", type="password", key="cheat_code_input")
    if st.button("Appliquer le profil de test"):
        if cheat_code == "XIN2":
            st.session_state.answers = {}
            st.session_state.dev_mode = True
            st.session_state.core_vectors = {
                "information_bandwidth": 2.5,
                "execution_rigor": 0.5,
                "chaos_tolerance": 1.0,
                "cognitive_endurance": 2.0,
            }
            st.session_state.flags["scan_completed"] = True
            st.session_state.flags["chatbot_unlocked"] = True
            st.session_state.current_q_idx = TOTAL_QUESTIONS
            st.success("Profil THE INTRINSICALLY DRIVEN appliqué !")
            st.rerun()
        elif cheat_code:
            st.error("Code incorrect.")


# ==============================================================================
# PHASE 2: QUESTIONNAIRE LOOP — LIKERT SCALE (1-5 par affirmation)
# ==============================================================================
# UPGRADE : chaque question proposait avant un choix unique (A/B/C/D).
# Maintenant, les 4 mêmes affirmations sont notées séparément de 1 à 5 —
# le contenu ne change pas, seule l'interaction change. Ça donne une
# donnée continue par affirmation au lieu d'un choix binaire forcé.
if st.session_state.current_q_idx < TOTAL_QUESTIONS:
    idx = st.session_state.current_q_idx
    q = ALL_QUESTIONS[idx]
    qid = q.get("id", idx)

    st.progress(idx / TOTAL_QUESTIONS)
    st.caption(f"Question {idx + 1} of {TOTAL_QUESTIONS}")

    st.subheader(q.get("question", "Untitled question"))
    st.caption("Rate how much each statement sounds like you — 1 (not at all) to 5 (completely).")

    options = q.get("options", {}) or {}
    option_keys = list(options.keys())
    existing_ratings = st.session_state.answers.get(qid, {})

    ratings = {}
    for key in option_keys:
        opt = options.get(key, {}) or {}
        text = opt.get("text", str(key))
        try:
            default_val = int(existing_ratings.get(key, 3))
        except (TypeError, ValueError):
            default_val = 3
        default_val = min(max(default_val, 1), 5)

        ratings[key] = st.slider(
            f"{key}) {text}",
            min_value=1, max_value=5, value=default_val, step=1,
            key=f"likert_{idx}_{key}"
        )

    nav_col1, nav_col2 = st.columns([1, 1])

    with nav_col1:
        if idx > 0:
            if st.button("← Previous", use_container_width=True):
                st.session_state.current_q_idx -= 1
                st.rerun()

    with nav_col2:
        if st.button("Confirm & continue →", type="primary", use_container_width=True):
            st.session_state.answers[qid] = ratings
            st.session_state.current_q_idx += 1

            if st.session_state.current_q_idx >= TOTAL_QUESTIONS:
                st.session_state.flags["scan_completed"] = True
                st.session_state.flags["chatbot_unlocked"] = True

            st.rerun()

    st.stop()


# ==============================================================================
# PHASE 3: ACCESS CONTROL
# ==============================================================================
if not st.session_state.flags.get("scan_completed"):
    st.error("🛑 Assessment incomplete or session expired.")
    st.markdown("You need to complete the full scan before viewing your Builder Profile.")
    if st.button("⬅️ Return to start"):
        st.switch_page("lumen_app.py")
    st.stop()

if not st.session_state.answers and not st.session_state.get("core_vectors"):
    st.error("⚠️ No answers found in memory. Please retake the assessment.")
    if st.button("🔄 Retake the assessment"):
        st.session_state.current_q_idx = 0
        st.session_state.answers = {}
        st.rerun()
    st.stop()


# ==============================================================================
# PHASE 4: SCORE AGGREGATION
# ==============================================================================
st.markdown("<p style='color: #8B5CF6; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; margin-bottom: -10px;'>Step 02 / Decryption</p>", unsafe_allow_html=True)

pseudo_raw = st.session_state.user_profile.get("pseudo", "Unknown Builder")
pseudo = re.sub(r"[^\w\s\-']", "", str(pseudo_raw)).strip()[:60] or "Unknown Builder"

st.title(f"🧬 Profile Decrypted: {pseudo}")

top_matches = []

if st.session_state.answers:
    # UPGRADE : formule centree sur 3 (neutre).
    #   note 5 -> poids +1.0 (ajoute le vecteur complet)
    #   note 4 -> poids +0.5
    #   note 3 -> poids  0.0 (aucune contribution, vraiment neutre)
    #   note 2 -> poids -0.5
    #   note 1 -> poids -1.0 (contribue dans le sens OPPOSE du vecteur)
    # Un desaccord fort ("pas du tout moi") est un vrai signal, pas juste
    # une absence de signal — d'ou la soustraction plutot qu'un simple 0.
    st.write("Turning your ratings into an actual cognitive profile...")

    core_vectors = {k: 0.0 for k in VECTOR_KEYS}
    all_ratings = []

    for q in ALL_QUESTIONS:
        qid = q.get("id")
        ratings_for_q = st.session_state.answers.get(qid, {}) or {}
        options = q.get("options", {}) or {}

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

            weight = (rating - 3.0) / 2.0  # -1.0 .. +1.0

            vectors = opt_data.get("vectors", {}) or {}
            for v_key, v_val in vectors.items():
                if v_key in core_vectors:
                    try:
                        core_vectors[v_key] += weight * float(v_val)
                    except (TypeError, ValueError):
                        continue

            all_ratings.append({
                "qid": qid,
                "section": q.get("section", ""),
                "opt_key": opt_key,
                "rating": rating,
                "label": opt_data.get("label", "Unknown Pattern"),
                "advice": opt_data.get("advice", "Keep building."),
            })

    # UPGRADE : l'ancien systeme affichait "le label choisi le plus
    # souvent" — impossible maintenant puisque chaque affirmation est
    # notee independamment (96 labels tous uniques, aucune repetition
    # possible). A la place : les 3 affirmations qui t'ont recu la note
    # la plus haute sur l'ensemble du quiz — celles qui te decrivent le
    # plus fort, pas les plus frequentes.
    top_matches = sorted(all_ratings, key=lambda r: r["rating"], reverse=True)[:3]

    st.session_state["core_vectors"] = core_vectors
    st.session_state["top_matches"] = top_matches
    st.session_state["all_ratings"] = all_ratings

else:
    # Chemin cheat code : pas de notes individuelles, on garde les
    # vecteurs injectes tels quels.
    st.write("Test profile loaded via developer shortcut.")
    core_vectors = st.session_state.get("core_vectors", {k: 0.0 for k in VECTOR_KEYS})
    top_matches = st.session_state.get("top_matches", [])


# ==============================================================================
# PHASE 5: DASHBOARD
# ==============================================================================
st.subheader("📊 Cognitive Loadout Matrix")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Information Bandwidth", f"{int(core_vectors['information_bandwidth'])} pts")
col2.metric("Execution Rigor", f"{int(core_vectors['execution_rigor'])} pts")
col3.metric("Chaos Tolerance", f"{int(core_vectors['chaos_tolerance'])} pts")
col4.metric("Cognitive Endurance", f"{int(core_vectors['cognitive_endurance'])} pts")

st.divider()


# ==============================================================================
# PHASE 6: TACTICAL BRIEFING
# ==============================================================================
st.subheader("💡 Your Strongest Signals")

if top_matches:
    st.markdown("The 3 statements you rated most strongly — the patterns that describe you best:")
    for i, item in enumerate(top_matches, start=1):
        with st.expander(f"#{i} — {item['label']} (rated {int(item['rating'])}/5)", expanded=(i == 1)):
            st.info(f"**Directive:** {item['advice']}")
else:
    st.info(
        "No per-question detail available — this profile was loaded via the "
        "developer shortcut, not a real assessment run. The 4 scores above are "
        "still real and usable across the app (Mr. Brown, the Roadmap, etc.)."
    )

all_ratings = st.session_state.get("all_ratings", [])
if all_ratings:
    with st.expander("📋 See all 24 signals (full detail)"):
        for item in sorted(all_ratings, key=lambda r: r["rating"], reverse=True):
            st.markdown(f"**{item['label']}** — rated {int(item['rating'])}/5 (*{item['section']}*)")
            st.caption(item["advice"])
            st.write("")

st.write("")
st.write("")

nav_col1, nav_col2 = st.columns(2)
with nav_col1:
    if st.session_state.flags.get("chatbot_unlocked"):
        st.success("🔓 AI Mentor unlocked.")
        if st.button("Talk to Mr. Brown 🤖", use_container_width=True):
            st.switch_page("pages/03_Mr.Brown.py")
with nav_col2:
    if st.button("See the full Builder Blueprint 🧬", type="primary", use_container_width=True):
        st.switch_page("pages/02_Advices.py")