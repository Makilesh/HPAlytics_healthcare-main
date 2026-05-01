# HPAlytics — Python Backend

FastAPI rewrite of the original Express backend.  
Same API surface, same routes — drop-in replacement.

## Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```bash
# Development (auto-reload)
uvicorn main:app --reload --port 5000

# Production
uvicorn main:app --host 0.0.0.0 --port 5000
```

## Environment

Create a `.env` file (optional — needed only for MongoDB persistence):

```
MONGO_URI=mongodb+srv://<user>:<pass>@cluster.mongodb.net/hpalytics
```

Without `MONGO_URI`, the app runs fully in-memory.

## Endpoints

| Method | Path        | Description                        |
|--------|-------------|------------------------------------|
| GET    | /           | Health check / welcome message     |
| GET    | /health     | Uptime info                        |
| POST   | /submit     | Submit assessment answers          |
| GET    | /sessions   | In-memory session log (debug)      |
| GET    | /patients   | All patients from MongoDB          |

## Interactive docs

FastAPI auto-generates Swagger UI at:  
`http://localhost:5000/docs`

## Payload — POST /submit

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