from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict
from datetime import datetime, timedelta
import json
import os
import time
import uuid
from dotenv import load_dotenv

# Load environment variables from backend/.env (works even when run from repo root)
BASE_DIR = os.path.dirname(__file__)
load_dotenv(os.path.join(BASE_DIR, ".env"))

DATA_DIR = os.path.join(BASE_DIR, "data")
USERS_JSON_PATH = os.path.join(DATA_DIR, "users.json")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# ── MongoDB via motor (async) ──────────────────────────────────
try:
    from motor.motor_asyncio import AsyncIOMotorClient
    MONGO_URI = os.getenv("MONGO_URI", "")
    mongo_client = AsyncIOMotorClient(MONGO_URI) if MONGO_URI else None
    db = mongo_client["hpalytics"] if mongo_client else None
    users_col = db["users"] if db else None
except Exception:
    mongo_client = None
    users_col = None

# ── Gemini client (optional) ───────────────────────────────────
try:
    import google.generativeai as genai
except Exception:
    genai = None

# ── App ────────────────────────────────────────────────────────
app = FastAPI(title="HPAlytics Backend", version="4.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory session store (debug) ───────────────────────────
sessions: list = []

# ── Pydantic models ───────────────────────────────────────────
class UserInfo(BaseModel):
    name: Optional[str] = None
    age: Optional[str] = None
    gender: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None


class SubmitPayload(BaseModel):
    answers: List[int]
    answers_r2: Optional[List[int]] = None
    user: Optional[UserInfo] = None


class GenerateQuestionsPayload(BaseModel):
    role: str
    answers: List[int]
    breakdown: Dict[str, int]
    level: str


class WeeklyCheckinPayload(BaseModel):
    email: str
    role: str
    session_history: List[Dict[str, Any]] = Field(default_factory=list)


class WeeklySubmitPayload(BaseModel):
    email: str
    answers: List[int]
    questions: List[Dict[str, str]]
    user: Optional[UserInfo] = None


class AnalyticsInsightPayload(BaseModel):
    email: str
    session_history: List[Dict[str, Any]] = Field(default_factory=list)


class SignupPayload(BaseModel):
    name: str
    email: str
    password: str
    age: str
    gender: str
    phone: str
    role: str


class LoginPayload(BaseModel):
    email: str
    password: str


# ── Scoring logic ─────────────────────────────────────────────
REPORTS = {
    "High": "Elevated stress indicators detected across multiple psychometric dimensions. "
            "Patterns suggest heightened cortisol response and sympathetic nervous system activation. "
            "Immediate clinical consultation and structured intervention strongly recommended.",
    "Moderate": "Moderate stress levels identified with notable patterns. Lifestyle adjustments, "
                "mindfulness-based stress reduction, and relaxation techniques are advised.",
    "Low": "Low stress levels detected. Indicates stable mental wellness and effective coping mechanisms.",
}


FALLBACK_FOLLOWUP_QUESTIONS = [
    {"q": "Which daily situations most consistently trigger your stress response?", "cat": "anxiety"},
    {"q": "How often do unfinished tasks keep occupying your thoughts at night?", "cat": "cognitive"},
    {"q": "How frequently do you feel emotionally drained even after routine activities?", "cat": "emotional"},
    {"q": "How often do stress-related thoughts make it harder for you to fall asleep?", "cat": "sleep"},
    {"q": "How often do you feel you have enough support to handle your current stressors?", "cat": "emotional"},
]


FALLBACK_WEEKLY_QUESTIONS = [
    {"q": "Compared with your last assessment, how often have racing thoughts interrupted your day this week?", "cat": "cognitive", "focus": True},
    {"q": "How often did unfinished tasks stay on your mind after you tried to rest?", "cat": "cognitive", "focus": True},
    {"q": "How often did upcoming responsibilities create noticeable worry this week?", "cat": "anxiety", "focus": True},
    {"q": "How often did you feel physical tension, restlessness, or a fast heartbeat during stressful moments?", "cat": "anxiety", "focus": True},
    {"q": "How often did you feel emotionally drained by the end of the day?", "cat": "emotional", "focus": False},
    {"q": "How often did your mood recover after taking a short break or talking to someone supportive?", "cat": "emotional", "focus": False},
    {"q": "How often did stress make it harder to fall asleep or stay asleep?", "cat": "sleep", "focus": False},
    {"q": "How often did you wake up feeling rested enough to handle the day?", "cat": "sleep", "focus": False},
    {"q": "How often did this week's stress feel more manageable than your previous assessment?", "cat": "emotional", "focus": False},
    {"q": "How often were you able to pause and reset before stress built up?", "cat": "cognitive", "focus": False},
]


VALID_CATS = {"cognitive", "anxiety", "emotional", "sleep"}


def ensure_users_store() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(USERS_JSON_PATH):
        with open(USERS_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump({}, f, indent=2)


def load_users() -> dict:
    ensure_users_store()
    with open(USERS_JSON_PATH, "r", encoding="utf-8") as f:
        raw = f.read().strip()
    if not raw:
        return {}
    data = json.loads(raw)
    return data if isinstance(data, dict) else {}


def save_users(users_data: dict) -> None:
    ensure_users_store()
    with open(USERS_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(users_data, f, indent=2)


def compute_breakdown(answers: List[int]) -> dict:
    a = answers
    return {
        "cognitive": (a[0] if len(a) > 0 else 0) + (a[4] if len(a) > 4 else 0) +
                     (a[8] if len(a) > 8 else 0) + (a[10] if len(a) > 10 else 0),
        "anxiety": (a[1] if len(a) > 1 else 0) + (a[5] if len(a) > 5 else 0),
        "emotional": (a[6] if len(a) > 6 else 0) + (a[7] if len(a) > 7 else 0) +
                     (a[9] if len(a) > 9 else 0) + (a[11] if len(a) > 11 else 0) +
                     (a[12] if len(a) > 12 else 0),
        "sleep": (a[2] if len(a) > 2 else 0) + (a[3] if len(a) > 3 else 0) +
                 (a[13] if len(a) > 13 else 0),
    }


def apply_round2_to_breakdown(breakdown: dict, answers_r2: List[int]) -> dict:
    merged = {
        "cognitive": int(breakdown.get("cognitive", 0)),
        "anxiety": int(breakdown.get("anxiety", 0)),
        "emotional": int(breakdown.get("emotional", 0)),
        "sleep": int(breakdown.get("sleep", 0)),
    }
    order = ["cognitive", "anxiety", "emotional", "sleep"]
    for i, val in enumerate(answers_r2):
        merged[order[i % len(order)]] += val
    return merged


def compute_level(breakdown: dict) -> str:
    w = (breakdown["sleep"] * 1.2 +
         breakdown["anxiety"] * 1.5 +
         breakdown["emotional"] * 1.4 +
         breakdown["cognitive"] * 1.3)
    if w > 60 or breakdown["anxiety"] >= 8:
        return "High"
    if w > 35:
        return "Moderate"
    return "Low"


def build_remedies(breakdown: dict) -> list:
    remedies = []

    if breakdown["sleep"] > 5:
        remedies.append({
            "title": "Sleep Regulation Protocol", "icon": "💤",
            "details": [
                "Maintain consistent 7–8 hour sleep schedule",
                "Avoid screens before bedtime",
                "Limit caffeine intake after 2 PM",
                "Practice guided relaxation before sleep",
            ],
        })

    if breakdown["anxiety"] > 5:
        remedies.append({
            "title": "Anxiety Management Plan", "icon": "🧘",
            "details": [
                "Practice deep breathing (4-7-8)",
                "Reduce overthinking triggers",
                "Daily mindfulness (10 mins)",
                "Break tasks into smaller goals",
            ],
        })

    if breakdown["emotional"] > 8:
        remedies.append({
            "title": "Emotional Stability Strategy", "icon": "💛",
            "details": [
                "Daily journaling",
                "Talk to trusted person",
                "Music therapy",
                "Spend time in nature",
            ],
        })

    if breakdown["cognitive"] > 8:
        remedies.append({
            "title": "Cognitive Focus Plan", "icon": "🧩",
            "details": [
                "Use Pomodoro technique",
                "Avoid multitasking",
                "Prioritize tasks",
                "Take regular breaks",
            ],
        })

    if not remedies:
        remedies.append({
            "title": "Wellness Maintenance", "icon": "🌿",
            "details": [
                "Maintain physical activity",
                "Social interaction",
                "Digital detox",
                "Routine check-ups",
            ],
        })

    return remedies


def build_gemini_prompt(role: str, answers: List[int], breakdown: dict, level: str) -> str:
    return f"""
You are a clinical psychologist conducting a personalised stress assessment.

The user is a {role} who completed a 15-question base stress screening.

Their responses indicate:
- Cognitive Load Score: {breakdown.get("cognitive", 0)} / 20
- Anxiety Index: {breakdown.get("anxiety", 0)} / 10
- Emotional State Score: {breakdown.get("emotional", 0)} / 25
- Sleep Disruption Score: {breakdown.get("sleep", 0)} / 15
- Overall Stress Level: {level}

Their per-question answers (1=Never, 5=Always): {answers}

Generate [5 to 8] personalised follow-up questions that:
1. Probe the dimensions where scores are highest
2. Are phrased naturally and clinically
3. Are specific to their role ({role})
4. Help identify root causes of their stress pattern
5. Are answerable on the same 1–5 frequency scale

Return ONLY valid JSON, no extra text:
{{
  "questions": [
    {{ "q": "Question text here?", "cat": "cognitive|anxiety|emotional|sleep" }}
  ]
}}
""".strip()


def safe_extract_json_block(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("```")
        for part in parts:
            candidate = part.strip()
            if candidate.startswith("json"):
                candidate = candidate[4:].strip()
            if candidate.startswith("{") and candidate.endswith("}"):
                return candidate
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        return cleaned[start:end + 1]
    return cleaned


def parse_followup_questions(raw_text: str, min_count: int = 5, max_count: int = 8, keep_focus: bool = False) -> List[dict]:
    json_text = safe_extract_json_block(raw_text)
    parsed = json.loads(json_text)
    questions = parsed.get("questions", []) if isinstance(parsed, dict) else []
    if not isinstance(questions, list):
        return []
    valid_questions = []
    for item in questions:
        if not isinstance(item, dict):
            continue
        q = str(item.get("q", "")).strip()
        cat = str(item.get("cat", "")).strip().lower()
        if q and cat in VALID_CATS:
            parsed_item = {"q": q, "cat": cat}
            if keep_focus:
                parsed_item["focus"] = bool(item.get("focus", False))
            valid_questions.append(parsed_item)
    if len(valid_questions) < min_count:
        return []
    return valid_questions[:max_count]


def generate_questions_with_gemini(payload: GenerateQuestionsPayload) -> List[dict]:
    if not GEMINI_API_KEY or genai is None:
        return FALLBACK_FOLLOWUP_QUESTIONS
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.5-flash")
        prompt = build_gemini_prompt(
            role=payload.role,
            answers=payload.answers,
            breakdown=payload.breakdown,
            level=payload.level,
        )
        result = model.generate_content(prompt)
        text = getattr(result, "text", "") or ""
        parsed_questions = parse_followup_questions(text)
        return parsed_questions if parsed_questions else FALLBACK_FOLLOWUP_QUESTIONS
    except Exception:
        return FALLBACK_FOLLOWUP_QUESTIONS


def normalize_breakdown(raw: Any) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    return {key: int(raw.get(key, 0) or 0) for key in VALID_CATS}


def parse_session_date(value: Any) -> datetime:
    text = str(value or "").strip()
    if not text:
        return datetime.min
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return datetime.min


def sorted_sessions_desc(session_history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    safe_history = session_history if isinstance(session_history, list) else []
    return sorted(
        [s for s in safe_history if isinstance(s, dict)],
        key=lambda s: parse_session_date(s.get("date")),
        reverse=True,
    )


def get_user_sessions(email: str) -> List[dict]:
    users_data = load_users()
    user = users_data.get(email.strip().lower())
    if not user:
        return []
    user_sessions = user.get("sessions", [])
    return user_sessions if isinstance(user_sessions, list) else []


def compute_avg_breakdown(recent_sessions: List[Dict[str, Any]]) -> dict:
    if not recent_sessions:
        return {key: 0.0 for key in VALID_CATS}
    totals = {key: 0.0 for key in VALID_CATS}
    for session in recent_sessions:
        breakdown = normalize_breakdown(session.get("breakdown", {}))
        for key in totals:
            totals[key] += breakdown[key]
    return {key: round(totals[key] / len(recent_sessions), 2) for key in totals}


def build_weekly_checkin_prompt(role: str, avg_breakdown: dict, top_2_dims: List[str], last_session: dict, session_count: int) -> str:
    last_breakdown_str = json.dumps(last_session.get("breakdown", {}))
    last_level = last_session.get("level", "Moderate")
    last_date = str(last_session.get("date", ""))[:10]

    return f"""
You are a clinical psychologist conducting a weekly stress monitoring follow-up.

USER PROFILE:
- Role: {role}
- Assessment number: {session_count + 1} (returning user)
- Last assessed: {last_date}
- Last stress level: {last_level}
- Last breakdown: {last_breakdown_str}
- Historical averages: Cognitive {avg_breakdown['cognitive']:.1f}, Anxiety {avg_breakdown['anxiety']:.1f}, Emotional {avg_breakdown['emotional']:.1f}, Sleep {avg_breakdown['sleep']:.1f}
- Primary concern dimensions this week: {', '.join(top_2_dims)}

Generate exactly 10 personalized weekly check-in questions that:
1. Reference the user's previous experience indirectly.
2. Focus 4-5 questions on the top concern dimensions: {', '.join(top_2_dims)}
3. Include 2-3 questions tracking improvement or regression from last assessment
4. Are answerable on a 1-5 frequency scale (1=Never, 5=Always)
5. Feel conversational and supportive, not clinical and cold
6. Are specific to a {role}'s context

Return ONLY valid JSON, no preamble, no markdown fences:
{{
  "questions": [
    {{ "q": "Question text?", "cat": "cognitive|anxiety|emotional|sleep", "focus": true|false }}
  ]
}}

"focus" is true if the question targets one of the top_2_dims.
""".strip()


def build_insight_prompt(role: str, session_history: List[Dict[str, Any]]) -> str:
    sessions_str = json.dumps([
        {
            "date": str(s.get("date", ""))[:10],
            "score": s.get("score", 0),
            "level": s.get("level", "Low"),
            "breakdown": s.get("breakdown", {}),
        }
        for s in session_history[-5:]
    ], indent=2)

    return f"""
You are a clinical psychologist analyzing a {role}'s stress trend data.

ASSESSMENT HISTORY (chronological):
{sessions_str}

Write a 2-3 sentence personalized insight that:
1. Acknowledges the trend honestly (improving/stable/worsening)
2. Highlights the most significant dimension change
3. Gives one concrete, actionable micro-recommendation for this week
4. Uses warm, empathetic language, not cold clinical language

Return ONLY the insight as plain text. No headers, no bullets, no JSON.
Maximum 80 words.
""".strip()


def generate_weekly_questions_with_gemini(role: str, avg_breakdown: dict, top_2_dims: List[str], last_session: dict, session_count: int) -> List[dict]:
    if not GEMINI_API_KEY or genai is None:
        return FALLBACK_WEEKLY_QUESTIONS
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.5-flash")
        prompt = build_weekly_checkin_prompt(role, avg_breakdown, top_2_dims, last_session, session_count)
        result = model.generate_content(prompt)
        text = getattr(result, "text", "") or ""
        parsed_questions = parse_followup_questions(text, min_count=10, max_count=12, keep_focus=True)
        return parsed_questions if parsed_questions else FALLBACK_WEEKLY_QUESTIONS
    except Exception:
        return FALLBACK_WEEKLY_QUESTIONS


def compute_weekly_breakdown(answers: List[int], questions: List[dict]) -> dict:
    breakdown = {"cognitive": 0, "anxiety": 0, "emotional": 0, "sleep": 0}
    for i, val in enumerate(answers):
        if i < len(questions):
            cat = str(questions[i].get("cat", "cognitive")).lower()
            if cat in breakdown:
                breakdown[cat] += val
    return breakdown


def fallback_insight(session_history: List[Dict[str, Any]]) -> str:
    if len(session_history) < 2:
        return "Your latest check-in gives us a useful new baseline. This week, choose one small routine you can repeat daily, such as a short wind-down before sleep."
    previous = session_history[-2]
    latest = session_history[-1]
    delta = int(latest.get("score", 0) or 0) - int(previous.get("score", 0) or 0)
    trend = "improved" if delta < 0 else "increased" if delta > 0 else "stayed steady"
    latest_bd = normalize_breakdown(latest.get("breakdown", {}))
    prev_bd = normalize_breakdown(previous.get("breakdown", {}))
    changed_dim = max(VALID_CATS, key=lambda key: abs(latest_bd[key] - prev_bd[key]))
    return f"Your stress score has {trend} compared with your previous assessment. The biggest shift is in {changed_dim}, so keep this week simple: schedule one brief reset before that pressure usually peaks."


# ── Routes ────────────────────────────────────────────────────
@app.get("/")
def root():
    return {"message": "🚀 HPAlytics Python Backend Running Successfully"}


@app.get("/health")
def health():
    return {"status": "ok", "uptime": time.process_time()}


@app.post("/auth/signup")
def auth_signup(payload: SignupPayload):
    users_data = load_users()
    email = payload.email.strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
    if email in users_data:
        raise HTTPException(status_code=400, detail="Email already exists")

    users_data[email] = {
        "name": payload.name.strip(),
        "email": email,
        "password": payload.password,
        "age": payload.age.strip(),
        "gender": payload.gender.strip(),
        "phone": payload.phone.strip(),
        "role": payload.role.strip(),
        "sessions": [],
    }
    save_users(users_data)
    return {"ok": True, "email": email}


@app.post("/auth/login")
def auth_login(payload: LoginPayload):
    users_data = load_users()
    email = payload.email.strip().lower()
    user = users_data.get(email)
    if not user or user.get("password") != payload.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return {
        "ok": True,
        "user": {
            "name": user.get("name", ""),
            "email": user.get("email", email),
            "role": user.get("role", ""),
            "age": user.get("age", ""),
            "gender": user.get("gender", ""),
            "phone": user.get("phone", ""),
        },
    }


@app.post("/generate-questions")
def generate_questions(payload: GenerateQuestionsPayload):
    if not payload.answers:
        raise HTTPException(status_code=400, detail="No answers provided")
    if any((not isinstance(v, int)) or v < 1 or v > 5 for v in payload.answers):
        raise HTTPException(status_code=422, detail="All answer values must be integers between 1 and 5")

    questions = generate_questions_with_gemini(payload)
    return {"questions": questions}


@app.post("/submit")
async def submit(payload: SubmitPayload):
    if not payload.answers:
        raise HTTPException(status_code=400, detail="No answers provided")
    if any((not isinstance(v, int)) or v < 1 or v > 5 for v in payload.answers):
        raise HTTPException(status_code=422, detail="All answer values must be integers between 1 and 5")

    answers_r2 = payload.answers_r2 or []
    if any((not isinstance(v, int)) or v < 1 or v > 5 for v in answers_r2):
        raise HTTPException(status_code=422, detail="All round 2 answer values must be integers between 1 and 5")

    answers = payload.answers
    user = payload.user or UserInfo()
    all_answers = answers + answers_r2

    score = sum(all_answers)
    breakdown = compute_breakdown(answers)
    if answers_r2:
        breakdown = apply_round2_to_breakdown(breakdown, answers_r2)
    level = compute_level(breakdown)
    report = REPORTS[level]
    remedies = build_remedies(breakdown)

    session_doc = {
        "session_id": str(uuid.uuid4()),
        "date": datetime.utcnow().isoformat(),
        "role": user.role or "",
        "answers_r1": answers,
        "answers_r2": answers_r2,
        "score": score,
        "level": level,
        "breakdown": breakdown,
        "report": report,
        "remedies": remedies,
        "checkin_type": "full",
        "session_number": 1,
    }

    # ── Persist to MongoDB (if configured) ────────────────────
    if users_col is not None:
        doc = {
            **(user.model_dump()),
            "answers": answers,
            "answers_r2": answers_r2,
            "score": score,
            "level": level,
            "breakdown": breakdown,
            "report": report,
            "remedies": remedies,
            "createdAt": datetime.utcnow(),
        }
        await users_col.insert_one(doc)
    else:
        # ── JSON fallback persistence to backend/data/users.json ─
        email = (user.email or "").strip().lower()
        if email:
            users_data = load_users()
            if email in users_data:
                sessions_data = users_data[email].get("sessions", [])
                if not isinstance(sessions_data, list):
                    sessions_data = []
                session_doc["session_number"] = len(sessions_data) + 1
                sessions_data.append(session_doc)
                users_data[email]["sessions"] = sessions_data
                save_users(users_data)

    # ── In-memory session log ──────────────────────────────────
    sessions.append({
        "ts": datetime.utcnow().isoformat(),
        "user": user.model_dump(),
        "score": score,
        "level": level,
        "breakdown": breakdown,
    })

    return {
        "score": score,
        "level": level,
        "report": report,
        "breakdown": breakdown,
        "remedies": remedies,
    }


@app.get("/users/me/sessions")
def get_my_sessions(email: str = Query(...)):
    email_lc = email.strip().lower()
    users_data = load_users()
    user = users_data.get(email_lc)
    if not user:
        return {"sessions": []}
    user_sessions = user.get("sessions", [])
    return {"sessions": user_sessions if isinstance(user_sessions, list) else []}


@app.get("/users/me/weekly-status")
def get_weekly_status(email: str = Query(...)):
    session_history = sorted_sessions_desc(get_user_sessions(email))
    if not session_history:
        return {"eligible": False, "reason": "no_sessions"}

    last_session = session_history[0]
    last_date = parse_session_date(last_session.get("date"))
    if last_date == datetime.min:
        return {"eligible": False, "reason": "invalid_last_session", "session_count": len(session_history)}

    days_since = max(0, (datetime.utcnow() - last_date).days)
    if datetime.utcnow() - last_date >= timedelta(days=7):
        return {
            "eligible": True,
            "last_session": last_session,
            "days_since": days_since,
            "session_count": len(session_history),
        }

    return {
        "eligible": False,
        "reason": "too_soon",
        "days_until_eligible": max(1, 7 - days_since),
        "days_since": days_since,
        "session_count": len(session_history),
        "last_session": last_session,
    }


@app.post("/weekly-checkin/generate-questions")
def generate_weekly_checkin(payload: WeeklyCheckinPayload):
    session_history = payload.session_history or get_user_sessions(payload.email)
    sorted_history = sorted_sessions_desc(session_history)
    if not sorted_history:
        return {
            "questions": FALLBACK_WEEKLY_QUESTIONS,
            "focus_dimensions": ["cognitive", "anxiety"],
            "avg_breakdown": {key: 0.0 for key in VALID_CATS},
        }

    recent_sessions = sorted_history[:3]
    avg_breakdown = compute_avg_breakdown(recent_sessions)
    top_2_dimensions = sorted(avg_breakdown.keys(), key=lambda key: avg_breakdown[key], reverse=True)[:2]
    last_session = sorted_history[0]
    questions = generate_weekly_questions_with_gemini(
        role=payload.role,
        avg_breakdown=avg_breakdown,
        top_2_dims=top_2_dimensions,
        last_session=last_session,
        session_count=len(sorted_history),
    )
    return {
        "questions": questions,
        "focus_dimensions": top_2_dimensions,
        "avg_breakdown": avg_breakdown,
    }


@app.post("/weekly-checkin/submit")
def submit_weekly_checkin(payload: WeeklySubmitPayload):
    if not payload.answers:
        raise HTTPException(status_code=400, detail="No answers provided")
    if len(payload.answers) < 10 or len(payload.answers) > 12:
        raise HTTPException(status_code=422, detail="Weekly check-in requires 10 to 12 answers")
    if any((not isinstance(v, int)) or v < 1 or v > 5 for v in payload.answers):
        raise HTTPException(status_code=422, detail="All answer values must be integers between 1 and 5")

    email = payload.email.strip().lower()
    user = payload.user or UserInfo(email=email)
    if not user.email:
        user.email = email

    questions = payload.questions if isinstance(payload.questions, list) else []
    breakdown = compute_weekly_breakdown(payload.answers, questions)
    score = sum(payload.answers)
    level = compute_level(breakdown)
    report = REPORTS[level]
    remedies = build_remedies(breakdown)

    users_data = load_users()
    sessions_data = []
    if email not in users_data:
        users_data[email] = {
            "name": user.name or "",
            "email": email,
            "password": "",
            "age": user.age or "",
            "gender": user.gender or "",
            "phone": user.phone or "",
            "role": user.role or "",
            "sessions": [],
        }
    sessions_data = users_data[email].get("sessions", [])
    if not isinstance(sessions_data, list):
        sessions_data = []

    session_doc = {
        "session_id": str(uuid.uuid4()),
        "date": datetime.utcnow().isoformat(),
        "role": user.role or "",
        "answers": payload.answers,
        "questions": questions,
        "score": score,
        "level": level,
        "breakdown": breakdown,
        "report": report,
        "remedies": remedies,
        "checkin_type": "weekly",
        "session_number": len(sessions_data) + 1,
    }

    sessions_data.append(session_doc)
    users_data[email]["sessions"] = sessions_data
    save_users(users_data)

    sessions.append({
        "ts": datetime.utcnow().isoformat(),
        "user": user.model_dump(),
        "score": score,
        "level": level,
        "breakdown": breakdown,
        "checkin_type": "weekly",
    })

    return {
        "score": score,
        "level": level,
        "report": report,
        "breakdown": breakdown,
        "remedies": remedies,
    }


@app.post("/analytics/insight")
def analytics_insight(payload: AnalyticsInsightPayload):
    history = payload.session_history or get_user_sessions(payload.email)
    chronological = list(reversed(sorted_sessions_desc(history)))[-5:]
    if not chronological:
        return {"insight": fallback_insight([])}

    role = ""
    users_data = load_users()
    user = users_data.get(payload.email.strip().lower())
    if user:
        role = user.get("role", "")
    role = role or chronological[-1].get("role", "user")

    if not GEMINI_API_KEY or genai is None:
        return {"insight": fallback_insight(chronological)}

    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.5-flash")
        result = model.generate_content(build_insight_prompt(role, chronological))
        insight = (getattr(result, "text", "") or "").strip()
        if not insight:
            insight = fallback_insight(chronological)
        return {"insight": insight[:700]}
    except Exception:
        return {"insight": fallback_insight(chronological)}


@app.get("/sessions")
def get_sessions():
    return {"count": len(sessions), "sessions": sessions}


@app.get("/users")
async def get_users():
    if users_col is None:
        return {"error": "MongoDB not configured", "users": []}
    cursor = users_col.find().sort("createdAt", -1)
    data = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        data.append(doc)
    return data
