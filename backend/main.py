from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Any, Dict
from datetime import datetime
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


def parse_followup_questions(raw_text: str) -> List[dict]:
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
            valid_questions.append({"q": q, "cat": cat})
    if len(valid_questions) < 5:
        return []
    return valid_questions[:8]


def generate_questions_with_gemini(payload: GenerateQuestionsPayload) -> List[dict]:
    if not GEMINI_API_KEY or genai is None:
        return FALLBACK_FOLLOWUP_QUESTIONS
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-1.5-flash")
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
