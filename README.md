# Breathe ESG — Carbon Data Ingestion Platform

A Django + React prototype that ingests emissions data from three enterprise sources, normalizes it, and surfaces a review dashboard where analysts can approve records before they are locked for audit.

## Demo Credentials

| Username | Password | Role |
|----------|----------|------|
| analyst | demo1234 | Analyst (review + approve) |
| admin | admin1234 | Admin (all access) |

**Tenant:** Tata Steel Ltd - India Operations (ID: 1)

---

## Quick Start (Local)

### Backend

```bash
cd backend
pip install -r requirements.txt
python manage.py migrate
python manage.py shell < seed_data.py
python manage.py runserver
```

API runs at `http://localhost:8000`

### Frontend

```bash
cd frontend
npm install
npm start
```

App runs at `http://localhost:3000`

---

## Project Structure

```
breathe-esg/
├── backend/
│   ├── config/               # Django settings, URLs, WSGI
│   ├── apps/
│   │   ├── tenants/          # Tenant model, auth (login), memberships
│   │   ├── ingestion/        # File upload API + all parsers
│   │   │   └── parsers/
│   │   │       ├── sap_parser.py        # SAP flat file → EmissionRecord
│   │   │       ├── utility_parser.py    # Utility CSV → EmissionRecord
│   │   │       ├── travel_parser.py     # Concur CSV → EmissionRecord
│   │   │       ├── unit_normalizer.py   # 35 unit conversions
│   │   │       └── emission_factors.py  # DEFRA 2024 + CEA 2023 factors
│   │   ├── emissions/        # Core models + list/summary API
│   │   └── review/           # Approve/flag/reject + audit log API
│   └── db.sqlite3            # Local dev database (pre-seeded)
│
├── frontend/
│   └── src/
│       ├── pages/
│       │   ├── Dashboard.jsx   # Summary metrics + scope bars
│       │   ├── ReviewPage.jsx  # Filterable record table + modal
│       │   └── UploadPage.jsx  # File upload + job history
│       └── components/         # Shared UI components
│
├── sample_data/
│   ├── sap/sap_fuel_procurement.csv      # 14 rows, realistic SAP ME2M export
│   ├── utility/electricity_bills.csv     # 9 rows, MSEDCL-format portal export
│   └── travel/concur_expense_export.csv  # 14 rows, Concur expense export
│
└── docs/
    ├── MODEL.md       # Data model decisions
    ├── DECISIONS.md   # Every ambiguity resolved
    ├── TRADEOFFS.md   # Three deliberate omissions
    ├── SOURCES.md     # Research per data source
    ├── SIMPLE_GUIDE.docx       # Plain-language explanation
    └── TECHNICAL_REFERENCE.docx # Professional technical reference
```

---

## The Three Data Sources

### 1. SAP — Fuel & Procurement (Scope 1)

**Format:** Pipe-delimited CSV from transaction ME2M / SE16N  
**Sample file:** `sample_data/sap/sap_fuel_procurement.csv`

What the parser handles:
- German column headers (WERKS, MENGE, MEINS, BLDAT, TXZ01)
- Six date formats including YYYYMMDD (SAP internal) and DD.MM.YYYY (German locale)
- German decimal separators (1.250,50 → 1250.50)
- Unit normalization: GAL→L, BBL→L, MSCM→M3, MT→KG
- Plant code lookup (PL01 → "Mumbai - Andheri Factory")
- Material-to-fuel-type classification (DIESEL-001 → DIESEL → 2.51 kgCO2e/L)
- Auto-suspicious: unknown plant codes, unclassifiable materials, quantity > 500,000

### 2. Utility Portal — Electricity (Scope 2)

**Format:** CSV download from MSEDCL / BESCOM / TSSPDCL customer portal  
**Sample file:** `sample_data/utility/electricity_bills.csv`

What the parser handles:
- Column name variants across utilities (Consumption, Units, Energy kWh, Net Consumption)
- Six date formats
- Cross-month billing periods → midpoint attribution
- Unit normalization: UNIT→KWH, MWH→KWH
- Auto-suspicious: zero consumption, billing period > 90 days, daily average < 1 kWh

### 3. Concur — Corporate Travel (Scope 3)

**Format:** CSV export from Concur Expense Reports menu  
**Sample file:** `sample_data/travel/concur_expense_export.csv`

What the parser handles:
- Three expense categories: Air Travel, Hotel, Ground Transport
- Flight distance via Haversine formula from IATA codes (× 1.08 DEFRA routing factor)
- Economy / Business / First class emission factors (long-haul business = 2.2× economy)
- Short-haul (<3,700 km) vs long-haul split
- Hotel emission factor by country (India: 18.5, UK: 31.0, global: 23.8 kgCO2e/night)
- Ground distance estimation from expense amount when distance not provided
- Non-carbon expense types (meals, conference fees) → SUSPICIOUS, preserved for analyst

---

## Data Pipeline

```
CSV Upload
    ↓
IngestionJob created (status: PROCESSING)
    ↓
Parser runs (SAP / Utility / Travel)
    ↓
For each row:
    RawRecord saved (immutable — exact original data)
    ↓
    Parse: resolve material/unit/date
    Normalize: convert to canonical units
    Calculate: quantity × emission_factor = co2e_kg
    Flag: check suspicious conditions
    ↓
    EmissionRecord saved (normalized, editable)
    AuditLog entry: CREATED
    ↓
IngestionJob updated (status: DONE, counts)
    ↓
Analyst reviews records in dashboard
    ↓
Approve → is_locked=True, AuditLog: APPROVED
Flag → review_status=FLAGGED, AuditLog: FLAGGED
Reject → review_status=REJECTED, AuditLog: REJECTED
```

---

## Emission Factors Used

All from DEFRA 2024. India grid from CEA 2023.

| Activity | Factor | Unit | Scope |
|----------|--------|------|-------|
| Diesel | 2.51 kgCO2e | / litre | 1 |
| Petrol | 2.31 kgCO2e | / litre | 1 |
| LPG | 1.51 kgCO2e | / litre | 1 |
| Natural Gas | 2.04 kgCO2e | / m³ | 1 |
| Furnace Oil | 3.18 kgCO2e | / litre | 1 |
| India Grid Electricity | 0.82 kgCO2e | / kWh | 2 |
| Flight economy short-haul | 0.2554 kgCO2e | / km/pax | 3 |
| Flight economy long-haul | 0.1951 kgCO2e | / km/pax | 3 |
| Flight business long-haul | 0.4290 kgCO2e | / km/pax | 3 |
| Hotel India | 18.5 kgCO2e | / night | 3 |
| Taxi | 0.149 kgCO2e | / km | 3 |
| Rail | 0.035 kgCO2e | / km | 3 |

---

## API Endpoints

All endpoints require `Authorization: Token <token>` header except login.

```
POST /api/auth/login/                    → token + tenant list
GET  /api/tenants/                       → user's tenants
POST /api/ingest/upload/                 → upload CSV file
GET  /api/ingest/jobs/?tenant_id=1       → ingestion job history
GET  /api/emissions/?tenant_id=1         → list records (filterable)
GET  /api/emissions/summary/?tenant_id=1 → aggregate CO2e by scope/status/source
POST /api/review/{id}/                   → approve / flag / reject
POST /api/review/bulk/                   → bulk action
GET  /api/review/{id}/audit-log/         → audit trail for one record
```

---

## Deployment

### Backend → Railway

1. Push to GitHub
2. Connect repo to railway.app
3. Set env vars: `SECRET_KEY`, `DEBUG=False`
4. Railway auto-detects Python via `Procfile`
5. Run post-deploy: `python manage.py migrate && python manage.py shell < seed_data.py`

**Procfile:**
```
web: gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 2
```

### Frontend → Vercel

1. Set `REACT_APP_API_URL=https://your-railway-backend.railway.app/api`
2. `vercel deploy`

---

## Submission Documents

| File | Purpose |
|------|---------|
| `docs/MODEL.md` | Data model design and rationale |
| `docs/DECISIONS.md` | Every ambiguity and how it was resolved |
| `docs/TRADEOFFS.md` | Three deliberate omissions and why |
| `docs/SOURCES.md` | Research, sample data design, production gaps |
| `docs/SIMPLE_GUIDE.docx` | Plain-language explanation of the entire project |
| `docs/TECHNICAL_REFERENCE.docx` | Professional technical reference for evaluators |
