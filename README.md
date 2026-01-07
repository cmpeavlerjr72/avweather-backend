# AvWeather Backend (MVP)

FastAPI backend for route corridor weather + passenger-friendly briefing.

## Local dev
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
uvicorn app.main:app --reload
```

## Endpoints
- POST /api/forecast
- GET /maps/{id}.html
- GET /healthz
