# Athes Sentinel Network IDS Release Checklist

Use this checklist only after the `nsl-kdd-integration` branch has passed
review. It describes a planned release; completing this document does not
authorize a merge, push, or deployment.

## Before merge

- Fetch the repository deliberately and confirm local `master` matches the
  current remote `master`. The N8A review compared local `master` only with the
  already-cached `origin/master` reference.
- Review the complete pull-request diff from `master` to
  `nsl-kdd-integration`.
- Confirm backend tests, deployment-readiness checks, the verified model hash,
  and the frontend production build are green.
- Confirm the tracked final artifact is
  `ml_pipeline/artifacts/nsl_kdd_improved_binary_pipeline.joblib`.
- Confirm its SHA-256 is
  `09b4cac3372256c3122bcfb5555706d63397e8449385470a283427e688691c13`.
- Confirm raw NSL-KDD data and experimental joblib artifacts remain ignored.
- Configure secrets only in the hosting providers. Never commit real values.

Required backend variables:

- `ATHES_ENV=production`
- `DATABASE_URL`
- `ATHES_SECRET_KEY`
- `ATHES_ALLOWED_ORIGINS`

Required frontend variable:

- `VITE_API_BASE_URL`

`ATHES_ALLOWED_ORIGINS` must include the final Vercel origin. Do not use an
unrestricted `*` origin with credentialed requests.

## Merge

- Merge `nsl-kdd-integration` into the freshly synchronized `master`.
- Review the resulting tree and required checks again.
- Push only after deliberate approval.

## Backend deployment

- Confirm the Render service has all required backend variables.
- Confirm `DATABASE_URL` points to the intended Render PostgreSQL database.
- Deploy the reviewed backend commit.
- Verify the health endpoint, login, and OpenAPI document.
- Confirm startup created these four missing additive tables:
  - `network_datasets`
  - `network_flows`
  - `network_predictions`
  - `network_incidents`
- Confirm the five existing application tables and application-log routes still
  work.
- Upload a small valid 41-column inference CSV.
- Start analysis explicitly.
- Verify the network dashboard and inspect one generated incident, when the
  small input produces an attack prediction.

Startup `Base.metadata.create_all()` creates missing tables but does not provide
versioned migration history.

## Frontend deployment

- Set `VITE_API_BASE_URL` to the deployed backend origin.
- Build and deploy the reviewed frontend commit to Vercel.
- Update `ATHES_ALLOWED_ORIGINS` to contain the final Vercel origin, then
  redeploy the backend if that value changed.
- Verify shared login.
- Verify both the existing application-log navigation and the new Network IDS
  navigation.

## Live smoke test

Start with a small NSL-KDD-compatible file.

Do not upload complete `KDDTest+.txt` until:

- the small upload and explicit analysis succeed;
- synchronous analysis duration is acceptable;
- the active hosting plan's request-body, timeout, memory, and concurrency
  behavior is understood.

The current implementation is synchronous. A future large-scale design may
need object storage and background workers.

## Rollback

- Redeploy the previously known-good backend and frontend commits.
- Verify application-log login, ingestion, analytics, incidents, and workflow.
- Existing application tables are additive-safe and remain untouched by the
  network schema.
- Newly created network tables may remain present but unused.
- Do not delete production network tables or records casually.
- No automatic rollback migration exists; `create_all()` is not a migration
  rollback system.

