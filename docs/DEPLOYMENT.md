# Deployment Review Guide

This document describes a planned release sequence for Athes Sentinel's verified dual-mode branch. It does not indicate that the branch has been merged or deployed.

## Current topology

- Backend: Render web service running Uvicorn/FastAPI.
- Database: Render PostgreSQL.
- Frontend: Vercel React/Vite deployment.
- Model: tracked repository-relative joblib artifact loaded lazily by the backend.

The current deployed `master` remains the original application-log version. The network IDS mode should be released only after branch review.

## Required environment variables

### Render backend

| Variable | Required in production | Purpose | Example placeholder |
| --- | --- | --- | --- |
| `DATABASE_URL` | yes | SQLAlchemy database connection | supplied by Render PostgreSQL |
| `ATHES_SECRET_KEY` | yes | JWT signing secret | generate a long random secret |
| `ATHES_ENV` | yes | Enables production validation | `production` |
| `ATHES_ALLOWED_ORIGINS` | yes | Comma-separated credentialed CORS origins | `https://your-project.vercel.app` |

`render.yaml` obtains `DATABASE_URL` from the declared database, generates `ATHES_SECRET_KEY`, sets `ATHES_ENV=production`, and leaves `ATHES_ALLOWED_ORIGINS` for explicit configuration.

Production startup fails clearly when the JWT secret or allowed origins are absent. Development retains local defaults. Never use wildcard `*` as a credentialed production origin.

### Vercel frontend

| Variable | Required in production | Purpose | Example placeholder |
| --- | --- | --- | --- |
| `VITE_API_BASE_URL` | yes | Render API origin used by Axios | `https://your-render-service.onrender.com` |

The production client requires this value and raises a clear initialization error when it is absent. The localhost backend fallback is development-only.

The Vercel project should build from `frontend/`, use the existing Vite build, publish `dist`, and retain `frontend/vercel.json` so client-side route refreshes rewrite to `index.html`.

## Planned release sequence

1. Review and merge the verified `nsl-kdd-integration` branch.
2. Push the reviewed merge to the repository.
3. Confirm Render environment variables without displaying their values.
4. Confirm the Render PostgreSQL `DATABASE_URL`.
5. Deploy the backend.
6. Verify `/`, `/openapi.json`, authentication, and the protected dataset list.
7. Set Vercel `VITE_API_BASE_URL` to the deployed Render backend origin.
8. Deploy the frontend.
9. Set Render `ATHES_ALLOWED_ORIGINS` to the final Vercel origin and restart if required.
10. Run a small authenticated 41-column upload and explicit analysis smoke test.
11. Review dashboard, analytics, incident detail, and one reversible status update.
12. Only then consider testing a complete benchmark upload against the actual hosting plan.

Do not place secrets, tokens, passwords, or live database URLs in Git.

## Backend build and startup

The committed Render configuration uses:

```text
pip install -r requirements.txt
```

```text
uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT
```

The frozen artifact was created with scikit-learn 1.9.0, which is pinned in `requirements.txt`; `joblib` is declared directly. The artifact path is repository-relative and its SHA-256 is checked before loading.

Startup:

- imports all application and network SQLAlchemy models;
- calls `Base.metadata.create_all()`;
- seeds the existing public demo users;
- registers application-log and network routes;
- does not load the model until inference.

The public demo credentials are not suitable for a real production authentication system. A non-demo deployment would require a separate user-provisioning and credential-management design.

## Database rollout

The deployed `master` database does not currently contain the four additive network tables. On first reviewed deployment, `create_all()` can create:

- `network_datasets`;
- `network_flows`;
- `network_predictions`;
- `network_incidents`.

This is acceptable for creating missing tables in the current project, but `create_all()` is not a versioned migration system. Any future change to an existing persistent constraint or column should use a formal migration rather than assuming `create_all()` will alter it.

All nine SQLAlchemy tables, constraints, and indexes compiled successfully with the PostgreSQL dialect during readiness verification. No deployed PostgreSQL connection was used.

## CORS checklist

- Use the exact HTTPS Vercel origin; do not include a path.
- Add multiple origins as comma-separated values when needed.
- Do not use `*` with credentials.
- Confirm browser preflight for:
  - authenticated GET requests;
  - POST analysis;
  - multipart POST upload;
  - PATCH incident status.

## Initial live smoke test

Use a small valid inference-only file rather than the complete benchmark:

1. authenticate;
2. upload a small 41-column headered CSV;
3. confirm status `uploaded`;
4. explicitly run analysis;
5. confirm one prediction per flow;
6. inspect one generated incident when an attack is predicted;
7. update and restore an incident status;
8. confirm the model version matches the tracked artifact hash.

Do not use benchmark labels as inference features.

## Operational limitations

- The application enforces a 50 MiB upload limit, but the provider may impose a lower limit.
- Parsing a complete file and synchronous analysis must fit the selected Render plan's memory and request timeout.
- Network analysis is synchronous, although flow reads/persistence are batched.
- Large production workloads should later use object storage, a background worker, and progress polling.
- There is no automatic traffic blocking.
- There is no formal Alembic migration history.
- Free-tier services may sleep or have resource constraints.

These items require real hosting-plan validation after deployment approval; the local readiness audit cannot guarantee provider-specific limits.

## Verification before release

Run locally before merging:

```powershell
.\venv\Scripts\python.exe -m unittest discover -s backend/app/tests -p "test*.py" -v
.\venv\Scripts\python.exe -m ml_pipeline.verify_final_model
.\venv\Scripts\python.exe scripts\verify_network_e2e.py
.\venv\Scripts\python.exe scripts\verify_deployment_readiness.py
```

Then build the production frontend with a non-secret test URL:

```powershell
cd frontend
$env:VITE_API_BASE_URL="https://api-verification.example.invalid"
npm.cmd run build
Remove-Item -LiteralPath dist -Recurse -Force
```

The model and E2E verifiers require the ignored complete `KDDTest+.txt`; readiness verification does not.
