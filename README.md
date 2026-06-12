# Athes Sentinel

Placement project — Day 1 setup.

## Project structure

- `backend/app/` — FastAPI API and modules (auth, logs, detection, incidents, etc.)
- `frontend/` — Streamlit app (not implemented yet)
- `data/` — Data files

## Setup

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## Run backend

From the project root (`athes-sentinel/`):

```bash
uvicorn backend.app.main:app --reload
```
