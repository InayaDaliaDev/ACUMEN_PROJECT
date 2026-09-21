import html

import streamlit as st
from pypdf import PdfReader

from core.ai_engine import classify_error, invoke_llm_with_fallback
from core.utils import extract_json_block, extract_text, is_plausible_gemini_key
from langchain_core.messages import HumanMessage


# ==============================================================================
# ACUMEN — QUIZ FORGE
# HTML/CSS visual layer + Streamlit interaction layer.
# The HTML is intentionally kept in this page for now: it gives us a much more
# controlled interface without prematurely moving the whole application to React.
# ==============================================================================

st.markdown(
    """
<style>
/* -------------------------------------------------------------------------- */
/* PAGE SHELL                                                                 */
/* -------------------------------------------------------------------------- */

[data-testid="stAppViewContainer"] {
    background:
        radial-gradient(circle at 8% 8%, rgba(139, 92, 246, 0.10), transparent 30%),
        radial-gradient(circle at 92% 18%, rgba(6, 182, 212, 0.08), transparent 28%),
        #07080d;
}

[data-testid="stHeader"] {
    background: rgba(7, 8, 13, 0.78);
}

.block-container {
    max-width: 1180px;
    padding-top: 2.5rem;
    padding-bottom: 5rem;
}

/* -------------------------------------------------------------------------- */
/* HTML HERO                                                                  */
/* -------------------------------------------------------------------------- */

.acumen-hero {
    position: relative;
    overflow: hidden;
    padding: 2.2rem 2.3rem 2rem;
    border: 1px solid rgba(139, 92, 246, 0.24);
    border-radius: 24px;
    background:
        linear-gradient(135deg, rgba(139, 92, 246, 0.10), rgba(6, 182, 212, 0.04)),
        rgba(12, 13, 21, 0.88);
    box-shadow: 0 24px 80px rgba(0, 0, 0, 0.28);
}

.acumen-hero::before {
    content: "";
    position: absolute;
    inset: 0;
    pointer-events: none;
    background: linear-gradient(
        180deg,
        transparent 0%,
        rgba(139, 92, 246, 0.035) 49%,
        rgba(6, 182, 212, 0.08) 50%,
        transparent 51%
    );
    background-size: 100% 8px;
    opacity: 0.45;
}

.acumen-kicker {
    position: relative;
    margin: 0 0 0.45rem;
    color: #8d91a6;
    font-family: "IBM Plex Mono", monospace;
    font-size: 0.70rem;
    font-weight: 600;
    letter-spacing: 0.18em;
    text-transform: uppercase;
}

.acumen-title {
    position: relative;
    margin: 0;
    font-family: "Space Grotesk", sans-serif;
    font-size: clamp(2.3rem, 5vw, 4.2rem);
    line-height: 0.95;
    letter-spacing: -0.055em;
    font-weight: 800;
    background: linear-gradient(100deg, #f5f3ff 5%, #a78bfa 48%, #67e8f9 95%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

.acumen-subtitle {
    position: relative;
    max-width: 760px;
    margin: 1rem 0 0;
    color: #a9adbd;
    font-size: 1rem;
    line-height: 1.65;
}

.acumen-scanline {
    position: relative;
    width: 100%;
    height: 1px;
    margin-top: 1.55rem;
    background: linear-gradient(90deg, transparent, #8b5cf6 28%, #06b6d4 72%, transparent);
    opacity: 0.72;
}

/* -------------------------------------------------------------------------- */
/* HTML SECTION LABELS                                                        */
/* -------------------------------------------------------------------------- */

.acumen-section {
    margin: 2rem 0 0.85rem;
}

.acumen-section-label {
    margin: 0;
    color: #e6e7ef;
    font-family: "Space Grotesk", sans-serif;
    font-size: 1.05rem;
    font-weight: 700;
    letter-spacing: -0.02em;
}

.acumen-section-meta {
    margin: 0.22rem 0 0;
    color: #73788d;
    font-family: "IBM Plex Mono", monospace;
    font-size: 0.68rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}

/* -------------------------------------------------------------------------- */
/* STREAMLIT WIDGET POLISH                                                    */
/* -------------------------------------------------------------------------- */

[data-testid="stFileUploaderDropzone"] {
    min-height: 155px;
    border: 1px dashed rgba(139, 92, 246, 0.42);
    border-radius: 18px;
    background: rgba(14, 15, 24, 0.72);
}

[data-testid="stFileUploaderDropzone"]:hover {
    border-color: rgba(103, 232, 249, 0.65);
    background: rgba(17, 18, 29, 0.88);
}

textarea, input {
    border-radius: 12px !important;
}

[data-testid="stButton"] button {
    min-height: 48px;
    border-radius: 13px;
    border: 1px solid rgba(139, 92, 246, 0.34);
    font-family: "Space Grotesk", sans-serif;
    font-weight: 700;
    transition: transform 120ms ease, border-color 120ms ease;
}

[data-testid="stButton"] button:hover {
    transform: translateY(-1px);
    border-color: rgba(103, 232, 249, 0.60);
}

/* -------------------------------------------------------------------------- */
/* HTML QUIZ CARDS                                                            */
/* -------------------------------------------------------------------------- */

.quiz-card {
    margin: 0.85rem 0 1rem;
    padding: 1.45rem 1.5rem 1.25rem;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 18px;
    background: rgba(13, 14, 22, 0.88);
    box-shadow: 0 12px 38px rgba(0, 0, 0, 0.18);
}

.quiz-number {
    color: #67e8f9;
    font-family: "IBM Plex Mono", monospace;
    font-size: 0.66rem;
    font-weight: 700;
    letter-spacing: 0.16em;
    text-transform: uppercase;
}

.quiz-question {
    margin: 0.45rem 0 0;
    color: #f2f2f7;
    font-family: "Space Grotesk", sans-serif;
    font-size: 1.12rem;
    line-height: 1.5;
    font-weight: 650;
}

/* -------------------------------------------------------------------------- */
/* HTML SCORE CARD                                                            */
/* -------------------------------------------------------------------------- */

.score-card {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    margin: 1.2rem 0 1.5rem;
    padding: 1.3rem 1.5rem;
    border: 1px solid rgba(103, 232, 249, 0.22);
    border-radius: 18px;
    background: linear-gradient(135deg, rgba(6, 182, 212, 0.08), rgba(139, 92, 246, 0.08));
}

.score-label {
    color: #8d91a6;
    font-family: "IBM Plex Mono", monospace;
    font-size: 0.68rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
}

.score-value {
    color: #f8fafc;
    font-family: "IBM Plex Mono", monospace;
    font-size: 2rem;
    font-weight: 700;
}

/* -------------------------------------------------------------------------- */
/* SIDEBAR                                                                    */
/* -------------------------------------------------------------------------- */

[data-testid="stSidebar"] {
    background: #090a10;
    border-right: 1px solid rgba(255, 255, 255, 0.06);
}

.sidebar-title {
    color: #e9e7ff;
    font-family: "IBM Plex Mono", monospace;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.13em;
    text-transform: uppercase;
}

/* -------------------------------------------------------------------------- */
/* MOBILE                                                                     */
/* -------------------------------------------------------------------------- */

@media (max-width: 720px) {
    .block-container {
        padding-top: 1.2rem;
    }

    .acumen-hero {
        padding: 1.5rem;
        border-radius: 18px;
    }

    .acumen-title {
        font-size: 2.6rem;
    }
}
</style>
    """,
    unsafe_allow_html=True,
)


# ==============================================================================
# 1. SIDEBAR — ENGINE CONTROLS
# ==============================================================================
with st.sidebar:
    st.markdown('<p class="sidebar-title">Engine Control Matrix</p>', unsafe_allow_html=True)

    st.session_state.gemini_api_key = st.text_input(
        "Gemini API Key",
        value=st.session_state.get("gemini_api_key", ""),
        type="password",
        placeholder="AIzaSy...",
        help=(
            "Get a free key from Google AI Studio. Your key is kept only in "
            "the current Streamlit session."
        ),
    ).strip()

    selected_model = st.selectbox(
        "Inference Model",
        options=[
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
            "gemini-3.5-flash",
        ],
        index=0,
        help="Primary model. The shared Acumen engine automatically applies its fallback chain if needed.",
    )

    num_questions = st.slider(
        "Questions",
        min_value=3,
        max_value=15,
        value=5,
        step=1,
    )

    request_timeout = st.slider(
        "Request Timeout (s)",
        min_value=10,
        max_value=120,
        value=45,
        step=5,
    )

    st.caption("Fallback, retry and error classification are handled centrally by `core.ai_engine`.")


gemini_api_key = st.session_state.get("gemini_api_key", "")


# ==============================================================================
# 2. HTML HERO
# ==============================================================================
st.markdown(
    """
<div class="acumen-hero">
    <p class="acumen-kicker">Acumen // Knowledge Instrument</p>
    <h1 class="acumen-title">Quiz Forge</h1>
    <p class="acumen-subtitle">
        Feed the forge a course, notes, or a PDF. Acumen extracts the material,
        generates comprehension-focused questions, and turns the result into an
        interactive quiz.
    </p>
    <div class="acumen-scanline"></div>
</div>
    """,
    unsafe_allow_html=True,
)


# ==============================================================================
# 3. SOURCE INPUT
# ==============================================================================
st.markdown(
    """
<div class="acumen-section">
    <p class="acumen-section-label">01 / Load the source</p>
    <p class="acumen-section-meta">Text, markdown or PDF</p>
</div>
    """,
    unsafe_allow_html=True,
)

accepted_types = ["txt", "md", "pdf"]

uploaded_file = st.file_uploader(
    "Source file",
    type=accepted_types,
    label_visibility="collapsed",
)

raw_text = st.text_area(
    "Source text",
    height=210,
    placeholder=(
        "Or paste your course material here...\n\n"
        "The generator will only use the material you provide."
    ),
    label_visibility="collapsed",
)


def extract_pdf_text(file) -> str:
    """Extract text from an uploaded PDF without crashing the page."""
    try:
        reader = PdfReader(file)
        pages_text = []

        for page in reader.pages:
            page_text = page.extract_text() or ""
            if page_text.strip():
                pages_text.append(page_text)

        return "\n\n".join(pages_text)
    except Exception:
        return ""


content = ""

if uploaded_file is not None:
    file_name = uploaded_file.name.lower()

    if file_name.endswith(".pdf"):
        with st.spinner("Extracting source text..."):
            content = extract_pdf_text(uploaded_file)

        if not content.strip():
            st.error(
                "The PDF contains no extractable text. It may be scanned or image-based. "
                "Paste the text manually instead."
            )
    else:
        try:
            content = uploaded_file.read().decode("utf-8", errors="ignore")
        except Exception:
            st.error("The uploaded file could not be read.")

elif raw_text:
    content = raw_text.strip()


MAX_CHARS = 40000

if len(content) > MAX_CHARS:
    st.warning(
        f"Source exceeds {MAX_CHARS:,} characters. Only the beginning will be used."
    )
    content = content[:MAX_CHARS]

if content:
    word_count = len(content.split())
    st.caption(f"SOURCE READY // {word_count:,} words // {len(content):,} characters")


# ==============================================================================
# 4. GENERATION ENGINE
# ==============================================================================
def generate_quiz(
    source_text: str,
    api_key: str,
    model: str,
    timeout: int,
    n_questions: int,
):
    """Generate the quiz through the shared Acumen LLM engine."""

    # UPGRADE: Gemini client creation, fallback selection and retry behavior
    # no longer live in this page. This page owns only its domain-specific
    # prompt and output contract.
    system_prompt = f"""You are Acumen's Quiz Forge engine.

Generate exactly {n_questions} multiple-choice questions from the user's source material.
The questions must test genuine comprehension and reasoning, not merely superficial recall.

The source material is authoritative. Do not invent facts that are not supported by it.

Return STRICT valid JSON only, with no markdown and no text before or after it.
Use exactly this structure:
- top-level object: "questions"
- each question contains:
  - "question": string
  - "options": object with exactly A, B, C, D
  - "correct": exactly one of A, B, C, D
  - "explanation": concise explanation of why the correct answer is correct
"""

    try:
        # UPGRADE: the source is a HumanMessage rather than being interpolated
        # into the system prompt. This keeps instructions and user data
        # separated and avoids JSON braces being interpreted as prompt
        # template variables by ChatPromptTemplate.
        response = invoke_llm_with_fallback(
            system_prompt=system_prompt,
            history_messages=[HumanMessage(content=source_text)],
            api_key=api_key,
            model=model,
            temperature=0.4,
            timeout=timeout,
            max_history_tokens=24,
        )

        # FIX: Gemini content can be a list of blocks, not necessarily a str.
        # Normalize it before sending it to the JSON extractor.
        return extract_text(response.content), None

    except Exception as error:
        return None, error


# ==============================================================================
# 5. GENERATE ACTION
# ==============================================================================
st.markdown(
    """
<div class="acumen-section">
    <p class="acumen-section-label">02 / Forge the assessment</p>
    <p class="acumen-section-meta">The selected model is only the primary route</p>
</div>
    """,
    unsafe_allow_html=True,
)

if st.button(
    "Forge Quiz",
    type="primary",
    use_container_width=True,
):
    if not is_plausible_gemini_key(gemini_api_key):
        st.error("Enter a valid Gemini API key in the sidebar before continuing.")

    elif not content:
        st.warning("Load a source file or paste some material first.")

    else:
        with st.spinner("Analyzing material and forging questions..."):
            raw_response, error = generate_quiz(
                source_text=content,
                api_key=gemini_api_key,
                model=selected_model,
                timeout=request_timeout,
                n_questions=num_questions,
            )

        if error is not None:
            # UPGRADE: all AI pages now share the same error classification.
            _, user_facing_error = classify_error(error)
            st.error(user_facing_error)

        else:
            quiz_data = extract_json_block(raw_response)

            if (
                quiz_data
                and isinstance(quiz_data, dict)
                and isinstance(quiz_data.get("questions"), list)
                and quiz_data.get("questions")
            ):
                st.session_state["generated_quiz_data"] = quiz_data
                st.session_state["quiz_answers"] = {}
                st.session_state["quiz_graded"] = False
                st.session_state["generated_quiz_raw"] = None
                st.success("Quiz forged successfully.")

            else:
                st.session_state["generated_quiz_data"] = None
                st.session_state["generated_quiz_raw"] = raw_response
                st.warning(
                    "The model responded, but the expected JSON structure could not be parsed."
                )


# ==============================================================================
# 6. QUIZ DISPLAY
# ==============================================================================quiz_data = st.session_state.get("generated_quiz_data")

if quiz_data:
    questions = quiz_data.get("questions", [])

    st.markdown(
        f"""
<div class="acumen-section">
    <p class="acumen-section-label">03 / Assessment interface</p>
    <p class="acumen-section-meta">{len(questions)} generated questions</p>
</div>
        """,
        unsafe_allow_html=True,
    )

    quiz_answers = st.session_state.setdefault("quiz_answers", {})

    for i, question_data in enumerate(questions):
        question_text = html.escape(str(question_data.get("question", "")).strip())
        options = question_data.get("options", {}) or {}
        option_keys = [key for key in ["A", "B", "C", "D"] if key in options]

        st.markdown(
            f"""
<div class="quiz-card">
    <div class="quiz-number">Question {i + 1:02d}</div>
    <div class="quiz-question">{question_text}</div>
</div>
            """,
            unsafe_allow_html=True,
        )

        selected = st.radio(
            f"Answer question {i + 1}",
            options=option_keys,
            format_func=lambda key, opts=options: f"{key}  ·  {opts.get(key, '')}",
            index=None,
            key=f"quiz_radio_{i}",
            label_visibility="collapsed",
        )

        quiz_answers[i] = selected

    if st.button("Evaluate Answers", use_container_width=True):
        st.session_state["quiz_graded"] = True

    if st.session_state.get("quiz_graded"):
        score = 0

        for i, question_data in enumerate(questions):
            correct = question_data.get("correct")
            user_answer = quiz_answers.get(i)
            explanation = question_data.get("explanation", "")

            if user_answer == correct:
                score += 1
                st.success(
                    f"Question {i + 1}: Correct. {explanation}"
                )
            else:
                correct_text = question_data.get("options", {}).get(correct, "")
                st.error(
                    f"Question {i + 1}: Incorrect. "
                    f"Correct answer: {correct}) {correct_text}. {explanation}"
                )

        st.markdown(
            f"""
<div class="score-card">
    <div>
        <div class="score-label">Assessment result</div>
        <div class="score-value">{score} / {len(questions)}</div>
    </div>
    <div class="score-label">ACUMEN // EVALUATED</div>
</div>
            """,
            unsafe_allow_html=True,
        )


elif st.session_state.get("generated_quiz_raw"):
    st.markdown(
        """
<div class="acumen-section">
    <p class="acumen-section-label">03 / Raw engine output</p>
    <p class="acumen-section-meta">The response did not match the expected schema</p>
</div>
        """,
        unsafe_allow_html=True,
    )
    st.code(st.session_state["generated_quiz_raw"], language="text")
