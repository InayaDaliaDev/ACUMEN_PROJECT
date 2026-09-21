from __future__ import annotations

from collections import defaultdict
from data.question import ALL_QUESTIONS

# FIX: Keep the four dimensions interpretable for students. They are app constructs,
# not clinical or validated psychometric scores.
AXES = [
    "information_bandwidth",
    "execution_rigor",
    "chaos_tolerance",
    "cognitive_endurance",
]

AXIS_META = {
    "information_bandwidth": {
        "name": "Active Processing",
        "short": "How effectively you turn information into something you can manipulate.",
        "color": "cyan",
    },
    "execution_rigor": {
        "name": "Execution Reliability",
        "short": "How consistently intentions become concrete study behavior.",
        "color": "purple",
    },
    "chaos_tolerance": {
        "name": "Uncertainty Flexibility",
        "short": "How comfortably you adapt when the task, plan or environment changes.",
        "color": "amber",
    },
    "cognitive_endurance": {
        "name": "Cognitive Endurance",
        "short": "How well you sustain useful effort across demanding study periods.",
        "color": "blue",
    },
}

# UPGRADE: Advice is grounded in established learning/motivation mechanisms rather than
# claims about dopamine, brain types, or diagnoses. The frontend labels this as evidence-
# informed guidance, not personalized clinical advice.
EVIDENCE_ADVICE = {
    "information_bandwidth": {
        "low": {
            "title": "Make learning active",
            "why": "Passive rereading can create familiarity without proving that you can retrieve or use the idea.",
            "actions": [
                "Close the notes and write what you remember for 3 minutes.",
                "Turn one heading into two questions, then answer them from memory.",
                "For a problem, explain why each step works before checking the solution.",
            ],
            "minutes": 10,
        },
        "mid": {
            "title": "Add a retrieval check",
            "why": "Your profile does not suggest a major processing bottleneck, but retrieval makes weak spots visible.",
            "actions": [
                "After a short study block, do 5 minutes of closed-book recall.",
                "Mark every answer you were uncertain about and revisit only those.",
            ],
            "minutes": 10,
        },
        "high": {
            "title": "Use your processing strength deliberately",
            "why": "Strong active processing is most useful when it produces explanations, predictions or solved problems, not just more notes.",
            "actions": [
                "Explain one difficult concept without looking at your material.",
                "Create one novel example that the original lesson did not give you.",
            ],
            "minutes": 10,
        },
    },
    "execution_rigor": {
        "low": {
            "title": "Shrink the start",
            "why": "When starting is unreliable, adding a larger plan can increase friction. A visible first action is easier to execute and evaluate.",
            "actions": [
                "Write one task in verb + object form: 'solve 3 exercises', not 'study maths'.",
                "Set a 10-minute start window and begin before reorganizing your system.",
                "Prepare the exact document, exercise or chapter before the timer starts.",
            ],
            "minutes": 10,
        },
        "mid": {
            "title": "Convert intentions into cues",
            "why": "A plan becomes more actionable when it specifies when and where the behavior starts.",
            "actions": [
                "Choose one fixed cue: after breakfast, after class, or at your desk.",
                "Attach one concrete action to it and remove the first setup step.",
            ],
            "minutes": 10,
        },
        "high": {
            "title": "Protect execution from over-optimization",
            "why": "Strong organization helps only while it remains connected to actual work.",
            "actions": [
                "Cap planning at 10 minutes, then execute the smallest meaningful block.",
                "Keep one visible metric: problems solved, pages retrieved, or concepts explained.",
            ],
            "minutes": 10,
        },
    },
    "chaos_tolerance": {
        "low": {
            "title": "Train flexibility in small doses",
            "why": "A rigid environment can make an unexpected change feel disproportionately disruptive. Small planned variations are a low-cost way to practice adaptation.",
            "actions": [
                "Change one harmless study variable today: location, order, or problem type.",
                "If interrupted, write the next exact step before switching tasks so re-entry is easier.",
            ],
            "minutes": 10,
        },
        "mid": {
            "title": "Build a fallback plan",
            "why": "Flexibility is easier when you already know what the second-best option is.",
            "actions": [
                "For your next study block, define Plan A and a 10-minute Plan B.",
                "When something changes, switch deliberately rather than abandoning the session.",
            ],
            "minutes": 10,
        },
        "high": {
            "title": "Use flexibility without losing structure",
            "why": "Adaptability is useful when it serves the goal rather than constantly replacing it.",
            "actions": [
                "Keep the outcome fixed while allowing the method to change.",
                "End every flexible session by recording what was actually completed.",
            ],
            "minutes": 10,
        },
    },
    "cognitive_endurance": {
        "low": {
            "title": "Design shorter productive cycles",
            "why": "Long sessions are not automatically better. Productive study depends on sustained useful effort and recovery.",
            "actions": [
                "Run one 15-minute active study block, then take a short break.",
                "Use retrieval, practice questions or explanation instead of passive reading during the block.",
                "Repeat only if the first block stayed productive.",
            ],
            "minutes": 15,
        },
        "mid": {
            "title": "Alternate effort and recovery",
            "why": "Spacing learning over time is supported by evidence and reduces the temptation to rely on one giant session.",
            "actions": [
                "Split today's work into two shorter sessions separated by several hours.",
                "Start the second session with 3 minutes of retrieval from the first.",
            ],
            "minutes": 12,
        },
        "high": {
            "title": "Protect endurance with deliberate breaks",
            "why": "High persistence is valuable, but it can hide fatigue or turn into diminishing-return hours.",
            "actions": [
                "Insert a real break before performance drops instead of waiting until you crash.",
                "Use the later part of a long session for retrieval or problem solving, not endless rereading.",
            ],
            "minutes": 12,
        },
    },
}


def public_questions():
    return [
        {
            "id": q["id"],
            "section": q["section"],
            "question": q["question"],
            "statements": [
                {"key": k, "label": v["label"], "text": v["text"]}
                for k, v in q["options"].items()
            ],
        }
        for q in ALL_QUESTIONS
    ]


def _band(value: float) -> str:
    if value < 43:
        return "low"
    if value > 68:
        return "high"
    return "mid"


def _normalise(raw: float, minimum: float, maximum: float) -> float:
    if maximum == minimum:
        return 50.0
    return round(max(0.0, min(100.0, (raw - minimum) / (maximum - minimum) * 100)), 1)


def calculate_profile(answers):
    raw = defaultdict(float)
    ratings = []
    mins = defaultdict(float)
    maxs = defaultdict(float)

    # FIX: Missing responses are no longer silently treated as neutral. The API still
    # returns a profile for debugging, but the browser prevents incomplete submissions.
    for q in ALL_QUESTIONS:
        for opt in q["options"].values():
            for axis, value in opt.get("vectors", {}).items():
                mins[axis] -= abs(value)
                maxs[axis] += abs(value)

        rs = answers.get(q["id"], {}) or {}
        for key, opt in q["options"].items():
            try:
                rating = max(1.0, min(5.0, float(rs.get(key, 3))))
            except (TypeError, ValueError):
                rating = 3.0
            weight = (rating - 3.0) / 2.0
            for axis, value in opt.get("vectors", {}).items():
                raw[axis] += value * weight
            ratings.append(
                {
                    "question_id": q["id"],
                    "section": q["section"],
                    "label": opt["label"],
                    "choice_text": opt["text"],
                    "advice": opt.get("advice", ""),
                    "rating": rating,
                }
            )

    vectors = {
        axis: _normalise(raw[axis], mins[axis], maxs[axis]) for axis in AXES
    }
    strongest = max(AXES, key=vectors.get)
    weakest = min(AXES, key=vectors.get)

    axis_cards = []
    for axis in AXES:
        band = _band(vectors[axis])
        axis_cards.append(
            {
                "key": axis,
                "name": AXIS_META[axis]["name"],
                "description": AXIS_META[axis]["short"],
                "score": vectors[axis],
                "band": band,
                "advice": EVIDENCE_ADVICE[axis][band],
            }
        )

    # UPGRADE: Advice is generated from the lowest actionable dimensions instead of
    # treating the most extreme answer as a personality identity.
    priority = sorted(axis_cards, key=lambda x: x["score"])[:2]
    advice = [
        {
            "axis": card["key"],
            "axis_name": card["name"],
            **card["advice"],
        }
        for card in priority
    ]

    return {
        "raw": {k: round(v, 3) for k, v in raw.items()},
        "vectors": vectors,
        "axes": axis_cards,
        "top_matches": sorted(ratings, key=lambda x: x["rating"], reverse=True)[:3],
        "strongest": strongest,
        "weakest": weakest,
        "all_ratings": ratings,
        "advice": advice,
        "method_note": "Scores are directional self-report signals created by ACUMEN. They are not diagnostic and have not been validated as a clinical or admissions instrument.",
    }
