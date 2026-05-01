# HPAlytics — Clinical Stress Assessment Platform

Python FastAPI backend for comprehensive mental health stress assessment. Provides psychometric scoring, personalized remedies, and clinical reporting.

---

## Quick Start

### 1. Setup Python Environment

Navigate to the backend directory and create a virtual environment:

```bash
cd backend
python -m venv venv
```

**Activate the virtual environment:**

- **Windows (PowerShell/CMD):**
  ```bash
  venv\Scripts\activate
  ```
- **macOS/Linux:**
  ```bash
  source venv/bin/activate
  ```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment (Optional)

Create a `.env` file in the `backend/` directory for MongoDB persistence:

```env
MONGO_URI=mongodb+srv://<username>:<password>@cluster.mongodb.net/hpalytics
```

> **Note:** Without `MONGO_URI`, the app runs in-memory (sessions lost on restart).

### 4. Run the Server

**Development (with auto-reload):**
```bash
uvicorn main:app --reload --port 5000
uvicorn backend.main:app --reload --port 5000
```

**Production:**
```bash
uvicorn main:app --host 0.0.0.0 --port 5000
```

The server starts at **`http://localhost:5000`**

---

## API Endpoints

| Method | Path        | Description                          |
|--------|-------------|--------------------------------------|
| GET    | `/`         | Welcome message & API status         |
| GET    | `/health`   | Server health & uptime               |
| POST   | `/submit`   | Submit assessment & get score        |
| GET    | `/sessions` | View in-memory session logs (debug)  |
| GET    | `/users` | Retrieve all user records         |

---

## Interactive API Documentation

FastAPI auto-generates **Swagger UI** at:  
🔗 **`http://localhost:5000/docs`**

Also available: **ReDoc** at `http://localhost:5000/redoc`

---

## POST /submit — Request Payload

```json
{
  "answers": [1, 2, 3, 4, 5, 1, 2, 3, 4, 5, 1, 2, 3, 4, 5],
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
  "score": 45,
  "level": "Moderate",
  "report": "Moderate stress levels identified...",
  "breakdown": {
    "cognitive": 12,
    "anxiety": 8,
    "emotional": 15,
    "sleep": 10
  },
  "remedies": [
    {
      "title": "Sleep Regulation Protocol",
      "icon": "💤",
      "details": ["Maintain 7-8 hour sleep schedule", "Avoid screens before bed", ...]
    }
  ]
}
```

---

## Stress Level Classification

| Level     | Score Indicator | Recommendation                          |
|-----------|-----------------|----------------------------------------|
| **Low**   | w ≤ 35          | Stable wellness; maintain current habits |
| **Moderate** | 35 < w ≤ 60  | Lifestyle adjustments recommended       |
| **High**  | w > 60 or anxiety ≥ 8 | Clinical consultation strongly advised   |

---

## Frontend Integration

The frontend (`/frontend`) connects to this backend:

```javascript
// Example: Submit assessment from frontend
const response = await fetch('http://localhost:5000/submit', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    answers: [1, 2, 3, ...],
    user: { name: 'Jane', email: 'jane@example.com', ... }
  })
});

const result = await response.json();
console.log(result.level, result.remedies);
```

---

## Troubleshooting

**Port already in use?**
```bash
uvicorn main:app --port 8000
```

**MongoDB connection fails?**
- Check `MONGO_URI` in `.env`
- Verify network access in MongoDB Atlas
- App will still work in-memory mode

**ModuleNotFoundError?**
```bash
pip install -r requirements.txt
```

---

## Tech Stack

- **Framework:** FastAPI
- **Database:** MongoDB (optional)
- **ASGI Server:** Uvicorn
- **Async Driver:** Motor (motor-asyncio)

## What's new (recent updates)

- Frontend: Bidirectional question navigation (Previous/Next) with answer preselection, progress, and running score (frontend/questions.html)
- Frontend: Returning user recognition using localStorage (hp_history) and hp_returning flag; profile pre-fill and returning-user banner (frontend/index.html, frontend/profile.html)
- Frontend: Stress History graph and session persistence to hp_history in localStorage (frontend/result.html)
- Frontend: PDF export refactored to use incremental y positioning for maintainability (frontend/result.html)
- Frontend: Fixed fetch() syntax in frontend/script.js
- Backend: POST /submit now validates answer values and returns HTTP 422 when any value is outside 1–5 (backend/main.py)
- Code quality: compute_breakdown() and compute_level() functions consolidated and reused on both frontend and backend.

## LocalStorage keys

- Existing: mp_name, mp_email, mp_phone, user, score, result, report, breakdown, remedies
- New: hp_history — JSON array of past sessions
- New flag: hp_returning — 'true'|'false'

## Session object schema (hp_history)

{
  "date": "ISO 8601 string",
  "name": string,
  "email": string,
  "score": number,
  "level": "Low" | "Moderate" | "High",
  "breakdown": { "cognitive": number, "anxiety": number, "emotional": number, "sleep": number }
}

## Developer notes

- Key frontend files: frontend/questions.html, frontend/result.html, frontend/profile.html, frontend/index.html, frontend/script.js
- Backend validation enforced in backend/main.py at POST /submit
- To run locally:
  1. Start backend: `uvicorn backend.main:app --reload --port 5000`
  2. Open `frontend/index.html` in a browser, or serve `/frontend` with a static server (e.g., `python -m http.server`)
- No new external dependencies were added. jsPDF is included for PDF export on the result page.
