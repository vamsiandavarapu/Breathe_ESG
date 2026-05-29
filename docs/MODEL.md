# MODEL.md — Data Model and Why

## Core Design Philosophy

The data model is built around one principle: **what you received must never be confused with what you reported**.

This creates two immutable facts:
1. What came in from the source system (RawRecord)
2. What an analyst certified as correct (EmissionRecord, after approval)

Every other design decision flows from this.

---

## Entity Overview

```
Tenant (with User and Role directly associated)
└── IngestionJob (one per file upload)
    └── RawRecord (one per CSV row — IMMUTABLE)
        └── EmissionRecord (normalized, analyst-facing)
            └── AuditLog (every action — append-only)
```

---

## Multi-Tenancy

**How it works:** Every model (IngestionJob, RawRecord, EmissionRecord) has a direct FK to `Tenant`. API views filter by `tenant_id` from query params, validated against the authenticated user's access via `verify_tenant_access`. A user with access to Tenant A cannot retrieve Tenant B's data.

**Why direct FK instead of schema-per-tenant:** Schema-per-tenant is overkill for a prototype and complicates Django ORM queries. Row-level isolation with a properly indexed `tenant_id` column is adequate for enterprise ESG volumes (tens of thousands of records per year, not millions).

**Tenant roles (defined directly on the Tenant relationship):**
- `admin` — manage ingestion jobs, approve records, manage users
- `analyst` — review and approve records
- `viewer` — read-only access to approved records

---

## Scope 1 / 2 / 3 Categorization

Scope is assigned at parse time by the parser, not inferred later. The logic is:

| Source | Default Scope | Category |
|--------|--------------|----------|
| SAP — diesel, petrol, furnace oil | SCOPE_1 | STATIONARY_COMBUSTION |
| SAP — CNG/petrol for vehicles | SCOPE_1 | MOBILE_COMBUSTION |
| Utility CSV — electricity | SCOPE_2 | PURCHASED_ELECTRICITY |
| Travel — flights | SCOPE_3 | BUSINESS_TRAVEL_AIR |
| Travel — hotels | SCOPE_3 | BUSINESS_TRAVEL_HOTEL |
| Travel — taxi/train/bus | SCOPE_3 | BUSINESS_TRAVEL_GROUND |

This is encoded in the `FACTORS` dictionary: each factor key maps to a scope and category. The parser looks up the factor key, gets the scope, and writes it to the EmissionRecord. No separate classification step needed.

---

## Source-of-Truth Tracking

Every EmissionRecord links back through:
```
EmissionRecord.raw_record → RawRecord.raw_data (JSON blob, exact original row)
EmissionRecord.job → IngestionJob (which file, when, who uploaded)
EmissionRecord.source_type → 'SAP_FUEL' | 'UTILITY_ELECTRICITY' | 'TRAVEL_CORPORATE'
```

The `quantity_original` and `unit_original` fields on EmissionRecord preserve exactly what the source said before normalization. For example:
- SAP sent: `MENGE = 6750, MEINS = GAL`
- We stored: `quantity_original = 6750.0, unit_original = 'GAL'`
- We normalized: `quantity = 25563.2235, unit = 'LITRE'`

An analyst can see both values in the review UI.

---

## Unit Normalization

All quantities are stored in canonical units:

| Dimension | Canonical Unit | Why |
|-----------|---------------|-----|
| Liquid fuels | LITRE | Most emission factors per litre |
| Gas | M3 | Standard cubic metre |
| Electricity | KWH | Standard for energy accounting |
| Weight | KG | SI base unit |
| Distance | KM | DEFRA factors per km |
| Hotel | NIGHT | Factor is per room-night |

The `unit_normalizer.py` module handles 35 source unit variants. Conversion uses Python `Decimal` (not `float`) throughout to avoid floating-point precision errors in CO2e calculations.

---

## Audit Trail

`AuditLog` is append-only. Every action on an EmissionRecord creates a new row:

```python
AuditLog(
    record=record,
    user=request.user,
    action='APPROVED',           # CREATED | EDITED | APPROVED | FLAGGED | REJECTED | LOCKED
    changes={'review_status': ['PENDING', 'APPROVED']},  # field: [old, new]
    note='Verified against plant logbook',
    timestamp=timezone.now()
)
```

No DELETE endpoint exists for AuditLog. No API exposes any mutating operation on it. This satisfies GHG Protocol Appendix B traceability requirements.

---

## Audit Lock

When a record is `APPROVED`, two things happen atomically:
1. `review_status = 'APPROVED'`
2. `is_locked = True`, `locked_at = now()`, `locked_by = user`

The review API checks `is_locked` before processing any action:
```python
if record.is_locked:
    return Response({'error': 'Record is locked for audit — cannot change'}, status=403)
```

Locked records are immutable through the API. Only a superuser with direct database access could modify them — which would be detectable via database audit logs in production.

---

## What Was Deliberately Not Modeled

**Vendor / supplier master:** SAP procurement data contains vendor codes (LIFNR). For Scope 3 Category 1 (purchased goods), vendor emissions matter. We ignored this — our Scope 3 only covers business travel, which is Category 6.

**Emission factor versioning:** DEFRA publishes new factors every June. Storing factors as a static Python dict means historical records cannot be recomputed automatically. A production model would have `EmissionFactor(material, valid_from, valid_to, factor, source)`.

**Net metering / renewable energy:** If a facility has solar panels, exported energy reduces Scope 2. We did not model renewable energy certificates (RECs) or power purchase agreements (PPAs).
