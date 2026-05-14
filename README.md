# HPAlytics — Clinical Stress Assessment Platform

A full-stack mental health stress assessment platform with a **Python FastAPI backend** and a **vanilla HTML/CSS/JS frontend**. Provides psychometric scoring, AI-generated personalised follow-up questions via Google Gemini, structured clinical reports, PDF export, and session history tracking.

---

## Architecture Overview

```
HPAlytics/
├── backend/
│   ├── main.py              # FastAPI app — all routes, scoring logic, Gemini integration
│   ├── data/
│   │   └── users.json       # JSON fallback user store (auto-created if no MongoDB)
│   └── .env                 # Local secrets (not committed)
├── frontend/
│   ├── auth.html            # Sign up / Sign in (Step 0)
│   ├── index.html           # Entry details (Step 1)
│   ├── profile.html         # User profile & role selection (Step 2)
│   ├── questions.html       # 2-round psychometric assessment (Step 3)
│   ├── result.html          # Clinical report, remedies, history chart (Step 4)
│   ├── script.js            # Legacy script (superseded by inline JS in HTML files)
│   └── style.css            # Global design system
├── requirements.txt
└── README.md
```

---

## User Flow

```
auth.html  →  index.html  →  profile.html  →  questions.html  →  result.html
 Sign In       Entry Info      Role Setup      2-Round Quiz        Report + PDF
```

1. **Auth** — Sign up or log in (credentials stored in `users.json` / MongoDB).
2. **Entry** — Confirm name, email, phone (pre-filled for returning users).
3. **Profile** — Set age, gender, role (Student / Professional / Homemaker).
4. **Assessment Round 1** — 15 role-specific psychometric questions (1–5 frequency scale).
5. **Assessment Round 2** — 5–8 AI-generated personalised follow-up questions (via Gemini, with fallback).
6. **Report** — Stress score, dimension breakdown, remedies, trend chart, PDF download.

---

## Quick Start

### 1. Python Environment

```bash
cd backend
python -m venv venv

# Activate
source venv/bin/activate        # macOS / Linux
venv\Scripts\activate           # Windows PowerShell
```

### 2. Install Dependencies

```bash
pip install -r ../requirements.txt
```

### 3. Configure Environment (Optional)

Create `backend/.env`:

```env
# MongoDB (optional — app runs in-memory/JSON without this)
MONGO_URI=mongodb+srv://<username>:<password>@cluster.mongodb.net/hpalytics

# Google Gemini (optional — fallback questions used if absent)
GEMINI_API_KEY=your_gemini_api_key_here
```

### 4. Run the Backend

```bash
# From backend/ directory:
uvicorn main:app --reload --port 5000

# Or from repo root:
uvicorn backend.main:app --reload --port 5000
```

Server runs at **`http://localhost:5000`**

### 5. Open the Frontend

```bash
# Option A — open directly in browser
open frontend/index.html

# Option B — serve with Python static server
cd frontend && python -m http.server 3000
# Then visit http://localhost:3000
```

> **Note:** The frontend hardcodes `http://localhost:5000` for API calls. If you change the backend port, update the `fetch()` URLs in `questions.html` and `result.html`.

---

## API Reference

### Base URL: `http://localhost:5000`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Welcome message & version |
| `GET` | `/health` | Server health & uptime |
| `POST` | `/auth/signup` | Register a new user |
| `POST` | `/auth/login` | Authenticate a user |
| `POST` | `/submit` | Submit assessment answers, get scored report |
| `POST` | `/generate-questions` | Generate Round 2 questions via Gemini |
| `GET` | `/users/me/sessions?email=` | Fetch a user's session history |
| `GET` | `/sessions` | In-memory session log (debug) |
| `GET` | `/users` | All users from MongoDB (requires Mongo) |

Interactive docs: **`http://localhost:5000/docs`** (Swagger UI) and **`http://localhost:5000/redoc`**

---

### POST `/auth/signup`

```json
{
  "name": "Jane Doe",
  "email": "jane@example.com",
  "password": "secret123",
  "age": "28",
  "gender": "Female",
  "phone": "9876543210",
  "role": "student"
}
```

**Response:** `{ "ok": true, "email": "jane@example.com" }`

---

### POST `/auth/login`

```json
{ "email": "jane@example.com", "password": "secret123" }
```

**Response:** `{ "ok": true, "user": { "name": "Jane Doe", "email": "...", "role": "student", ... } }`

---

### POST `/submit`

```json
{
  "answers": [1, 2, 3, 4, 5, 1, 2, 3, 4, 5, 1, 2, 3, 4, 5],
  "answers_r2": [2, 3, 1, 4, 2],
  "user": {
    "name": "Jane Doe",
    "age": "28",
    "gender": "Female",
    "phone": "9876543210",
    "email": "jane@example.com",
    "role": "student"
  }
}
```

**Response:**

```json
{
  "score": 52,
  "level": "Moderate",
  "report": "Moderate stress levels identified…",
  "breakdown": {
    "cognitive": 14,
    "anxiety": 8,
    "emotional": 18,
    "sleep": 12
  },
  "remedies": [
    {
      "title": "Sleep Regulation Protocol",
      "icon": "💤",
      "details": ["Maintain 7–8 hour sleep schedule", "Avoid screens before bed"]
    }
  ]
}
```

**Validation:** All values in `answers` and `answers_r2` must be integers between 1–5. Returns HTTP 422 otherwise.

---

### POST `/generate-questions`

```json
{
  "role": "student",
  "answers": [1, 2, 3, 4, 5, 1, 2, 3, 4, 5, 1, 2, 3, 4, 5],
  "breakdown": { "cognitive": 12, "anxiety": 6, "emotional": 14, "sleep": 9 },
  "level": "Moderate"
}
```

**Response:** `{ "questions": [ { "q": "...", "cat": "anxiety" }, ... ] }`

Returns 5–8 Gemini-generated questions, falling back to 5 hardcoded questions if Gemini is unavailable or returns an invalid response.

---

## Scoring & Classification

### Dimension Breakdown (Round 1, 15 questions)

| Dimension | Question Indices | Max Score |
|-----------|-----------------|-----------|
| Cognitive | 0, 4, 8, 10 | 20 |
| Anxiety | 1, 5 | 10 |
| Emotional | 6, 7, 9, 11, 12 | 25 |
| Sleep | 2, 3, 13 | 15 |

Round 2 answers are merged into the same dimensions in order: cognitive → anxiety → emotional → sleep (cycling).

### Weighted Score Formula

```
w = (sleep × 1.2) + (anxiety × 1.5) + (emotional × 1.4) + (cognitive × 1.3)
```

### Stress Level Classification

| Level | Condition | Recommendation |
|-------|-----------|----------------|
| **Low** | w ≤ 35 | Maintain current habits |
| **Moderate** | 35 < w ≤ 60 | Lifestyle adjustments |
| **High** | w > 60 **or** anxiety ≥ 8 | Clinical consultation advised |

---

## Persistence

HPAlytics supports two storage modes, selected automatically:

### MongoDB (Primary)
Set `MONGO_URI` in `backend/.env`. All submissions are stored in the `hpalytics.users` collection. Required for the `/users` admin endpoint.

### JSON File (Fallback)
When `MONGO_URI` is absent, the app writes to `backend/data/users.json`. Each user's sessions are stored under their email key:

```json
{
  "jane@example.com": {
    "name": "Jane Doe",
    "role": "student",
    "sessions": [
      {
        "session_id": "uuid",
        "date": "2025-01-15T10:30:00",
        "score": 52,
        "level": "Moderate",
        "breakdown": { "cognitive": 14, "anxiety": 8, "emotional": 18, "sleep": 12 }
      }
    ]
  }
}
```

---

## Frontend — localStorage Keys

| Key | Type | Description |
|-----|------|-------------|
| `logged_in_email` | string | Currently authenticated user's email |
| `user` | JSON object | Full user profile (name, age, gender, phone, email, role) |
| `mp_name` | string | User's name (quick access) |
| `mp_email` | string | User's email (quick access) |
| `mp_phone` | string | User's phone (quick access) |
| `score` | string | Numeric score from latest assessment |
| `result` | string | `"Low"` / `"Moderate"` / `"High"` |
| `report` | string | Clinical interpretation paragraph |
| `breakdown` | JSON object | `{ cognitive, anxiety, emotional, sleep }` |
| `remedies` | JSON array | Array of remedy objects with `title`, `icon`, `details[]` |
| `hp_history` | JSON array | All past sessions for history chart |
| `hp_returning` | string | `"true"` / `"false"` — returning user flag |

---

## Frontend — Page Guide

### `auth.html` — Authentication
- Tab-based Sign In / Create Account UI
- On login, stores user profile to `localStorage` and redirects to `index.html`
- Redirects to `profile.html` if already logged in

### `index.html` — Entry
- Requires login; redirects to `auth.html` otherwise
- Pre-fills name, email, phone from `localStorage`
- Logout clears all `APP_KEYS` from `localStorage`

### `profile.html` — Profile Setup
- Collects age, gender (visual selector), and role (Student / Professional / Homemaker)
- Role selection is required — determines which question bank is used
- Pre-selects values for returning users

### `questions.html` — Assessment Engine
- **Round 1:** 15 role-specific questions displayed one at a time
- **Round 2:** 5–8 Gemini-generated follow-up questions (POST `/generate-questions`)
- Sidebar shows all questions with answered/current states
- Previous/Next navigation allows answer review before submission
- Running score shown live in sidebar
- On completion, POSTs to `/submit` and stores result to `localStorage`

### `result.html` — Clinical Report
- Animated score ring with colour-coded level pill
- Stress intensity meter (visual gauge)
- Animated dimension breakdown bars
- Accordion remedy protocol cards
- Daily micro-habits grid
- **Stress History chart** — rendered as inline SVG from session history (requires ≥2 sessions)
  - Pulls from backend `/users/me/sessions` first; falls back to `hp_history` in localStorage
- **PDF Export** — client-side jsPDF report including user info, scores, breakdown, and remedies

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend framework | FastAPI |
| ASGI server | Uvicorn |
| Data validation | Pydantic v2 |
| Database (primary) | MongoDB via Motor (async) |
| Database (fallback) | JSON file (`backend/data/users.json`) |
| AI integration | Google Gemini 1.5 Flash (`google-generativeai`) |
| Environment config | python-dotenv |
| Frontend | Vanilla HTML, CSS, JavaScript (no framework) |
| Fonts | Playfair Display + Nunito (Google Fonts) |
| PDF export | jsPDF (CDN) |

---

## Role-Specific Question Banks

Each role has 15 questions mapping to the same 4 dimensions:

| Role value | Description |
|-----------|-------------|
| `student` | Academic pressure, exam anxiety, study fatigue |
| `working` | Workplace demands, deadlines, burnout |
| `home` | Household responsibilities, family expectations, isolation |

Questions are defined in `questions.html` (`QUESTIONS` object) and mirrored in `script.js` (legacy). The backend's `/generate-questions` endpoint uses the role value to contextualise Gemini's follow-up prompts.

---

## Gemini Integration

When `GEMINI_API_KEY` is set and `google-generativeai` is installed:

1. After Round 1, the frontend sends `role`, `answers`, `breakdown`, and `level` to `POST /generate-questions`.
2. The backend builds a clinical prompt and calls `gemini-1.5-flash`.
3. The model returns 5–8 JSON questions `{ "q": "...", "cat": "cognitive|anxiety|emotional|sleep" }`.
4. Responses are validated — questions with invalid categories or fewer than 5 valid items fall back to the hardcoded `FALLBACK_FOLLOWUP_QUESTIONS` list.

If `GEMINI_API_KEY` is absent, or if the API call fails for any reason, the fallback list is used silently.

---

## Running Without MongoDB or Gemini

The app is fully functional offline:

- **No `MONGO_URI`** → sessions saved to `backend/data/users.json`
- **No `GEMINI_API_KEY`** → Round 2 uses 5 hardcoded follow-up questions
- **Backend unreachable** → `questions.html` falls back to local scoring and stores results in `localStorage` without a server round-trip

---

## Troubleshooting

**Port already in use:**
```bash
uvicorn backend.main:app --port 8000
```
Then update the `fetch()` URLs in `frontend/questions.html` and `frontend/result.html` from `5000` to `8000`.

**CORS errors in browser:**
The backend allows all origins (`allow_origins=["*"]`). If you see CORS errors, ensure the backend is running and the URL in fetch calls matches the actual port.

**MongoDB connection fails:**
The app falls back to JSON file storage automatically. Check your `MONGO_URI` string and MongoDB Atlas network access if you need Mongo.

**`ModuleNotFoundError`:**
```bash
pip install -r requirements.txt --break-system-packages
```

**Gemini `google-generativeai` not found:**
```bash
pip install google-generativeai
```

**Users.json not created:**
The `backend/data/` directory is auto-created on first use. Ensure the process has write permission to the `backend/` directory.

---

## Development Notes

- The `frontend/script.js` file is a legacy file from an earlier version. All active logic lives in inline `<script>` blocks inside each HTML file.
- `compute_breakdown()` and `compute_level()` are defined in both `questions.html` (frontend) and `backend/main.py` (backend) for consistency. The backend result is always the authoritative one when the server is reachable.
- The `hp_history` array in localStorage grows unbounded. Consider trimming it to the latest N sessions if storage becomes a concern.
- Passwords are stored in plain text in `users.json`. This is suitable for development/demo only — hash passwords before any production deployment.