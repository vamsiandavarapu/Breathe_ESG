# TRADEOFFS.md — Three Things I Deliberately Did Not Build

## 1. PDF Bill Parser for Utility Data

**What it would do:** Parse scanned or digital utility bills (MSEDCL, BESCOM, TSSPDCL) directly from PDF instead of requiring a portal CSV export.

**Why I didn't build it:**

PDF parsing for bills is genuinely hard and not a 4-day problem. The challenges are:
- Every utility has a different bill layout. MSEDCL's bill looks nothing like BESCOM's.
- Many bills are scanned images of printed papers, requiring OCR (optical character recognition).
- Even for digital PDFs, table extraction is unreliable — a column shift of a few pixels breaks the parser.
- Utilities change their bill formats without notice. A production PDF parser breaks silently and you don't know until the numbers are wrong.

**The real cost of doing it badly:** A brittle PDF parser that extracts wrong numbers is worse than no parser at all. It would create incorrect RawRecords with no obvious error signal.

**The right production approach:** AWS Textract or Google Document AI with a review step. These services extract tables with confidence scores. Low-confidence extractions are routed to a human reviewer. The infrastructure cost (API calls + review workflow) is justified in production but not in a 4-day prototype.

**What we built instead:** Portal CSV export — more reliable, available from all major Indian utilities, and what facilities teams actually use today.

---

## 2. Real-Time SAP OData Pull

**What it would do:** Connect directly to the client's SAP system via SAP Gateway's OData service, pulling new purchase order receipts automatically every night rather than requiring a manual file upload.

**Why I didn't build it:**

This requires client infrastructure that cannot be replicated in a prototype:
- SAP Gateway must be configured and exposed externally (with firewall rules, TLS certificates, IP whitelisting)
- An SAP Basis administrator must create a technical user with the appropriate authorization objects
- OAuth 2.0 or Basic authentication must be configured on the SAP side
- The client's IT security team must approve the integration

This is typically a 4–8 week IT project at an enterprise client. Blocking the prototype on this would be the wrong tradeoff.

**The real cost of not having it:** Clients must manually export and upload files each reporting period. For monthly reporting, that is 12 uploads per source per year — manageable for an analyst, but adds a failure mode (forgetting to upload).

**The right production approach:** Once the client relationship is established and the data model is validated, invest in the OData integration. It makes the platform dramatically stickier. The prototype demonstrates the value first; the automation comes after.

---

## 3. Emission Factor Versioning

**What it would do:** Store emission factors in a database table with `valid_from` and `valid_to` date ranges. When DEFRA publishes updated factors every June, the system would: (1) load the new factors, (2) identify all EmissionRecords created with the old factors, (3) run a bulk recomputation job to update `co2e_kg` for any unlocked records, (4) flag approved/locked records as "factor update available" for analyst review.

**Why I didn't build it:**

The prototype uses a static Python dictionary (`FACTORS` in `emission_factors.py`). This is wrong for production but acceptable for a prototype because:
- DEFRA 2024 factors are accurate for calendar year 2024 activity
- The prototype covers a single reporting year (2024)
- No records will be recomputed in the demo

**The real cost of not having it:**

When DEFRA publishes 2025 factors in June 2025, every emission record ingested in 2024 is technically using stale factors. More importantly, if a client wants to recompute last year's numbers with updated factors (for a restated report), there is no mechanism to do this without touching the code.

**What breaks in production:** If a client ingests 2023 data today (using 2024 DEFRA factors) and then again in 2026 (using 2026 factors), the same physical activity produces different CO2e numbers. An auditor will notice this inconsistency.

**The right production approach:**

```python
class EmissionFactor(Model):
    material_key = CharField(max_length=50)    # e.g. 'DIESEL'
    factor = DecimalField(max_digits=12, decimal_places=6)
    unit = CharField(max_length=10)
    source = CharField(max_length=100)         # 'DEFRA 2024'
    valid_from = DateField()
    valid_to = DateField(null=True)            # null = currently active
    scope = CharField(max_length=10)
    category = CharField(max_length=50)
```

EmissionRecord stores `emission_factor_id` (FK) not just the float value. Recomputation becomes a filtered update query. Annual factor updates become a data operation, not a code deployment.
