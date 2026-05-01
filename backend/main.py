from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Any
from datetime import datetime
import os
import time
from dotenv import load_dotenv

# Load environment variables from backend/.env (works even when run from repo root)
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

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

# ── App ────────────────────────────────────────────────────────
app = FastAPI(title="HPAlytics Backend", version="3.0.0")

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
    age:  Optional[str] = None
    gender: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    role:  Optional[str] = None

class SubmitPayload(BaseModel):
    answers: List[int]
    user: Optional[UserInfo] = None

# ── Scoring logic ─────────────────────────────────────────────
REPORTS = {
    "High":     "Elevated stress indicators detected across multiple psychometric dimensions. "
                "Patterns suggest heightened cortisol response and sympathetic nervous system activation. "
                "Immediate clinical consultation and structured intervention strongly recommended.",
    "Moderate": "Moderate stress levels identified with notable patterns. Lifestyle adjustments, "
                "mindfulness-based stress reduction, and relaxation techniques are advised.",
    "Low":      "Low stress levels detected. Indicates stable mental wellness and effective coping mechanisms.",
}

def compute_breakdown(answers: List[int]) -> dict:
    a = answers
    return {
        "cognitive": (a[0] if len(a)>0 else 0) + (a[4] if len(a)>4 else 0) +
                     (a[8] if len(a)>8 else 0) + (a[10] if len(a)>10 else 0),
        "anxiety":   (a[1] if len(a)>1 else 0) + (a[5] if len(a)>5 else 0),
        "emotional": (a[6] if len(a)>6 else 0) + (a[7] if len(a)>7 else 0) +
                     (a[9] if len(a)>9 else 0) + (a[11] if len(a)>11 else 0) +
                     (a[12] if len(a)>12 else 0),
        "sleep":     (a[2] if len(a)>2 else 0) + (a[3] if len(a)>3 else 0) +
                     (a[13] if len(a)>13 else 0),
    }

def compute_level(breakdown: dict) -> str:
    w = (breakdown["sleep"]     * 1.2 +
         breakdown["anxiety"]   * 1.5 +
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

# ── Routes ────────────────────────────────────────────────────
@app.get("/")
def root():
    return {"message": "🚀 HPAlytics Python Backend Running Successfully"}

@app.get("/health")
def health():
    return {"status": "ok", "uptime": time.process_time()}

@app.post("/submit")
async def submit(payload: SubmitPayload):
    if not payload.answers:
        raise HTTPException(status_code=400, detail="No answers provided")
    if any((not isinstance(v, int)) or v < 1 or v > 5 for v in payload.answers):
        raise HTTPException(status_code=422, detail="All answer values must be integers between 1 and 5")

    answers   = payload.answers
    user      = payload.user or UserInfo()

    score     = sum(answers)
    breakdown = compute_breakdown(answers)
    level     = compute_level(breakdown)
    report    = REPORTS[level]
    remedies  = build_remedies(breakdown)

    # ── Persist to MongoDB (if configured) ────────────────────
    if users_col is not None:
        doc = {
            **(user.model_dump()),
            "answers":   answers,
            "score":     score,
            "level":     level,
            "breakdown": breakdown,
            "report":    report,
            "remedies":  remedies,
            "createdAt": datetime.utcnow(),
        }
        await users_col.insert_one(doc)

    # ── In-memory session log ──────────────────────────────────
    sessions.append({
        "ts":        datetime.utcnow().isoformat(),
        "user":      user.model_dump(),
        "score":     score,
        "level":     level,
        "breakdown": breakdown,
    })

    return {
        "score":     score,
        "level":     level,
        "report":    report,
        "breakdown": breakdown,
        "remedies":  remedies,
    }

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
