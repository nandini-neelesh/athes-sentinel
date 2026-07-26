# NSL-KDD Network IDS Mode

This guide documents Athes Sentinel's second analysis mode: authenticated ingestion and persisted binary classification of NSL-KDD-compatible connection records.

The mode is a reproducible benchmark-backed portfolio implementation. It is not real-time packet inspection, does not ingest PCAP files, and does not claim that NSL-KDD represents current production traffic.

## Why NSL-KDD

NSL-KDD was selected because it provides a structured, labelled, widely studied connection-record benchmark suitable for demonstrating a complete supervised-learning lifecycle:

- a fixed official training file;
- a distinct official test file with attack labels not seen in training;
- mixed categorical and numeric features;
- enough rows to exercise full-stack ingestion, batched inference, persistence, and analytics;
- benchmark families that expose where a binary detector succeeds and struggles.

Its age is also an important limitation. Results on NSL-KDD are evidence about this benchmark, not proof of modern network-detection effectiveness.

## Supported uploads

The authenticated upload endpoint accepts one UTF-8 `.txt` or `.csv` file up to 50 MiB.

| Structure | Header | Columns | Stored source type |
| --- | --- | ---: | --- |
| Official labelled benchmark | none | 43 | `nsl_kdd_labelled` |
| Inference-only features | none | 41 | `nsl_kdd_inference` |
| Labelled CSV | exact official names; order may differ | 43 | `nsl_kdd_labelled` |
| Inference-only CSV | exact official names; order may differ | 41 | `nsl_kdd_inference` |

The 43-column structure contains the 41 official features followed by `label` and `difficulty_level`. A 42-column partial structure is rejected.

The backend:

- detects a valid exact header or assigns the official headerless schema;
- validates every row before committing;
- trims categorical strings and converts required numeric values;
- rejects missing values, infinities, invalid difficulty values, and unmapped labels;
- preserves duplicate records and source row order;
- stores normalized benchmark labels/families only when supplied;
- inserts flows in batches of 2,000;
- does not retain the physical upload after parsing;
- does not run analysis automatically.

Arbitrary firewall exports, packet captures, and unrelated CSV schemas are not supported.

## Dataset placement for reproducibility

Raw NSL-KDD files are intentionally Git-ignored and are not redistributed by this repository. Obtain the dataset independently and place complete files at:

```text
data/external/nsl-kdd/KDDTrain+.txt
data/external/nsl-kdd/KDDTest+.txt
```

Do not substitute `KDDTrain+_20Percent.txt`, `KDDTest-21.txt`, ARFF files, images, or sampled subsets when reproducing the committed reports.

## Feature and target policy

- Complete training rows: 125,973.
- Complete official-test rows: 22,544.
- Binary target: `normal → 0`; every mapped attack label → `1`.
- Original stored features: 41.
- Model inputs before encoding: 40.
- Categorical inputs: 3.
- Numeric inputs: 37.
- Transformed fitted inputs: 121.
- Excluded from the model: `label`, `difficulty_level`, and constant `num_outbound_cmds`.
- Unknown inference categories: handled by the fitted `OneHotEncoder`.

Benchmark families (`normal`, `dos`, `probe`, `r2l`, and `u2r`) are derived from supplied actual labels for evaluation only. The fitted detector predicts only `normal` or `attack`.

## Controlled model development

### N2 fixed baseline

The first supervised baseline fitted preprocessing and a 200-tree Random Forest on every row of `KDDTrain+.txt`, then evaluated once at threshold 0.50 on every row of `KDDTest+.txt`.

| Metric | Baseline result |
| --- | ---: |
| Precision | 0.966767 |
| Recall | 0.600717 |
| F1 | 0.741001 |
| F2 | 0.649934 |
| False-positive rate | 0.027289 |

The F2 value is calculated from the committed baseline precision and recall using the standard beta-2 formula.

### N2.1 selected detector

N2.1 used one reproducible 80/20 stratified split of the complete training file (`random_state=42`) to compare three fixed end-to-end pipelines:

1. the N2 baseline Random Forest;
2. a recall-oriented Random Forest;
3. an Extra Trees classifier.

For each candidate, validation thresholds from 0.10 through 0.90 were compared. Selection preferred false-positive rate at or below 0.05 and then maximized F2 using the declared tie-break policy. Official-test metrics did not select or revise the N2.1 candidate or threshold.

Candidate B was selected:

```text
RandomForestClassifier(
    n_estimators=300,
    max_depth=None,
    min_samples_leaf=1,
    class_weight={0: 1.0, 1: 2.0},
    random_state=42,
    n_jobs=-1,
)
threshold = 0.38
```

It was refitted on all 125,973 official training records. The complete test file was evaluated after the model and threshold were fixed.

Phase N2 had already established a baseline on the official test set. The honest claim is therefore narrower: N2.1 model and threshold choices used only the new training/validation split, and no N2.1 test result was used to revise those choices.

### N2.2 rejected hybrid

A controlled Random Forest plus Isolation Forest fusion experiment used training-only partitions of 70% detector fitting, 15% fusion selection, and 15% untouched acceptance holdout. Isolation Forest was fitted only on normal-labelled detector-fitting rows.

On the acceptance holdout:

- Random Forest only: 8,788 TP and 13 FP, F2 `0.999068`;
- selected hybrid: 8,790 TP and 31 FP, F2 `0.998841`.

The hybrid detected two additional attacks but generated 18 additional false positives and did not strictly improve F2. It was rejected before official-test loading. This evidence-based rejection kept N2.1 as the final detector.

## Final official-test benchmark

| Metric | Result |
| --- | ---: |
| Test records | 22,544 |
| Accuracy | 0.811968 |
| Precision | 0.968185 |
| Recall | 0.692434 |
| F1 | 0.807414 |
| F2 | 0.734259 |
| False-positive rate | 0.030069 |
| False-negative rate | 0.307566 |
| TN | 9,419 |
| FP | 292 |
| FN | 3,947 |
| TP | 8,886 |

Family-level detection of supplied benchmark attacks:

| Supplied benchmark family | Recall |
| --- | ---: |
| DoS | 0.857105 |
| Probe | 0.888063 |
| R2L | 0.112652 |
| U2R | 0.253731 |

These family values are evaluation breakdowns from actual labels, not model outputs. R2L and U2R recall remains weak and is not presented as solved.

## Frozen artifact

The repository tracks only the selected final pipeline:

```text
ml_pipeline/artifacts/nsl_kdd_improved_binary_pipeline.joblib
```

- Size: 6,705,637 bytes.
- SHA-256: `09b4cac3372256c3122bcfb5555706d63397e8449385470a283427e688691c13`.
- Contents: fitted `ColumnTransformer` plus fitted `RandomForestClassifier`.
- Serialization compatibility: scikit-learn 1.9.0.

`backend/app/ml/nsl_kdd_inference.py` resolves the artifact and metadata relative to the repository, verifies the hash and threshold, validates 41- or 43-column DataFrames, and loads the model lazily once per application process. It never fits during inference.

## Predictions and incidents

Analysis reads persisted flows in source order and processes batches of 5,000 in one logical child-write transaction. Each flow receives one persisted probability and binary result. A consistent completed analysis is returned idempotently without rerunning prediction.

Every predicted attack creates one `network_incident` with:

- the Random Forest attack probability on a 0–1 scale;
- `risk_score = probability × 100`;
- a probability-derived analyst severity;
- actual protocol, service, flag, byte, login, count, and error-rate context;
- evidence phrased as a suspicious model signal rather than certainty;
- restrained recommended investigation actions;
- persistent workflow status.

Severity mapping:

| Probability | Severity |
| --- | --- |
| `>= 0.90` | `critical` |
| `>= 0.75` and `< 0.90` | `high` |
| `>= 0.60` and `< 0.75` | `medium` |
| `>= 0.38` and `< 0.60` | `low` |

Severity is product triage, not an attack-family prediction. Athes Sentinel does not automatically block traffic.

## Authenticated network API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| POST | `/network/datasets/upload` | Validate and persist one 41- or 43-column dataset |
| GET | `/network/datasets` | List datasets with pagination |
| GET | `/network/datasets/{dataset_id}` | Read dataset metadata and child counts |
| GET | `/network/datasets/{dataset_id}/flows` | Read source-ordered original flows |
| POST | `/network/datasets/{dataset_id}/analyze` | Run or idempotently reuse frozen analysis |
| GET | `/network/datasets/{dataset_id}/analysis` | Read persisted analysis summary |
| GET | `/network/datasets/{dataset_id}/dashboard` | Read persisted KPIs and priority incidents |
| GET | `/network/datasets/{dataset_id}/analytics` | Read persisted SQL aggregations |
| GET | `/network/datasets/{dataset_id}/incidents` | Filter and paginate risk-ordered incidents |
| GET | `/network/incidents/{incident_id}` | Read incident, prediction, and original flow detail |
| PATCH | `/network/incidents/{incident_id}/status` | Persist one supported analyst status |

Every endpoint requires the existing bearer JWT authentication.

## Verification

From the repository root:

```powershell
.\venv\Scripts\python.exe -m ml_pipeline.verify_final_model
.\venv\Scripts\python.exe scripts\verify_network_e2e.py
.\venv\Scripts\python.exe scripts\verify_deployment_readiness.py
```

The full E2E verifier uses disposable SQLite, uploads all 22,544 `KDDTest+` rows through the real FastAPI application, invokes the frozen model, reconciles dashboard and analytics totals, exercises incident filters/detail/status persistence, checks inference-only data, and confirms idempotent reuse. It does not modify the normal local database or contact deployed services.

The first two commands require the ignored complete `KDDTest+.txt`. The deployment-readiness verifier intentionally does not require raw datasets.

## Limitations

- NSL-KDD is old and subject to substantial distribution shift.
- R2L and U2R benchmark recall is weak.
- The detector is binary, not an attack-family classifier.
- NSL-KDD records do not provide source or destination IP addresses.
- PCAP files and arbitrary network/firewall logs are unsupported.
- Analysis is synchronous and has no worker queue.
- There is no automated blocking or remediation.
- Hosting-plan upload, memory, and timeout behavior still needs live validation.
- Benchmark performance is not evidence of modern production effectiveness.
