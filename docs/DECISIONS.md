# DECISIONS.md — Every Ambiguity Resolved

## SAP Export Format

**Decision:** Pipe-delimited flat file (ME2M / SE16N export), not IDoc, OData, or BAPI.

**Why:**
- IDoc requires SAP middleware (XI/PI/CPI). Most clients do not have an exposed integration layer. Configuring one is a weeks-long IT project.
- OData (SAP Gateway) requires firewall exceptions, SSL certificates, and SAP Basis configuration. Same problem.
- BAPI calls require RFC connections — again, an IT project with security implications.
- Flat file: a client's SAP administrator opens transaction SE16N, selects table EKPO or runs ME2M, and clicks Export. Takes 5 minutes. Zero IT dependency.

**What I'd ask the PM:** "Does the client have an SAP Basis team available, and are they willing to set up an OData service? If yes, we should move to OData for automated pulls rather than manual file drops."

**What I ignored in SAP:** Vendor codes (LIFNR), account assignment objects (cost center KOSTL / order AUFNR), purchasing organization (EKORG), storage location (LGORT). These are critical for full procurement analytics but irrelevant for Scope 1 carbon calculation. We only need: material, quantity, unit, plant, date.

---

## Utility Data Format

**Decision:** Portal CSV export, not PDF bill parsing or Green Button API.

**Why:**
- PDF bills: OCR is brittle. Every utility has a different bill layout. A layout change from MSEDCL breaks the parser. Maintenance cost is high. Not worth it for a prototype.
- Green Button API: This is a US standard (DOE). Indian utilities (MSEDCL, BESCOM, TSSPDCL) do not support it yet.
- Portal CSV: Every major Indian utility provides a CSV download from their customer portal. It is consistent enough to parse reliably. This is what facilities teams actually use.

**What I'd ask the PM:** "How many different utilities does this client have? If they operate across states (Maharashtra + Karnataka + Telangana), we have three different CSV formats to handle. Should we build per-utility column mappings?"

**Billing period attribution decision:** Used midpoint of billing period as the activity date. A billing period of Jan 15 – Feb 14 gets activity_date = Jan 30. This is an approximation. True production behaviour would prorate consumption by days: 15 days in January, 14 days in February, split accordingly.

**What I ignored:** Demand charges (kVA billing), power factor penalties, fuel adjustment charges (FAC/FAC surcharge). These affect the invoice amount but not consumption or emissions. Reactive energy (kVARh) does not directly produce emissions.

---

## Corporate Travel Format

**Decision:** Concur expense report CSV export, not Concur API or Navan API.

**Why:**
- Concur API requires OAuth 2.0 enterprise credentials, which the client's IT department must provision. This is a multi-week process with legal/security reviews.
- Navan API has similar requirements.
- Concur CSV export: any expense admin can produce it from the Reports menu in under 2 minutes. No IT dependency.

**What I'd ask the PM:** "Does the client use Concur, Navan, or something else? The column names in the CSV vary by platform. I've built the parser for Concur's format — Navan uses different headers."

**Flight distance decision:** Calculate from airport codes using Haversine formula × 1.08 DEFRA routing factor, rather than accepting provided distances at face value. Reason: Concur does not consistently populate the distance field. We calculate it ourselves for reliability, and use the provided value as a fallback check.

**Hotel emission factor decision:** Used country-level factors (India: 18.5 kgCO2e/night, UK: 31 kgCO2e/night, global average: 23.8 kgCO2e/night). DEFRA 2024 only provides UK factors; global figures are estimated from DEFRA's methodology applied to other regions' energy mixes. This is an acknowledged simplification.

**Ground transport estimation:** When distance is absent, estimated as amount_INR ÷ 15 (average Indian taxi rate). This is explicitly flagged as `is_suspicious=True` with reason "Distance estimated from expense amount." The analyst must verify.

**What I ignored:** Meal expenses, conference registration fees, visa costs. GHG Protocol Scope 3 Category 6 (Business Travel) covers transportation and accommodation only. Meals are personal consumption, not business travel emissions.

---

## Emission Factor Source

**Decision:** DEFRA 2024 for all factors except India grid electricity (CEA 2023).

**Why DEFRA:** Widely accepted by auditors globally. Free. Updated annually. Covers all categories we need. Well-documented methodology.

**Why CEA for India grid:** DEFRA's grid factor is for the UK (0.20733 kgCO2e/kWh). India's grid is coal-heavy; CEA 2023 gives 0.82 kgCO2e/kWh. Using DEFRA's UK factor for an Indian factory would understate emissions by 75%.

**What I'd ask the PM:** "Does the client want market-based or location-based Scope 2 accounting? If they've signed a Power Purchase Agreement (PPA) for renewable energy, their market-based factor could be much lower than the grid average. We'd need their energy procurement team involved."

---

## Suspicious Flagging Thresholds

**SAP — quantity > 500,000 litres:** Based on realistic single purchase order line sizes. A 500 KL diesel delivery would be exceptional even for a large plant. This threshold would be configurable per client in production.

**Utility — consumption > 2,000,000 kWh/month:** Approximately equivalent to a 2.8 MW average load, which is realistic only for very large industrial facilities. Most factories in our demo are in the 200–400 kW range.

**Utility — billing period > 90 days:** Utilities sometimes skip meter readings and catch up the following month. This creates an inflated bill that would spike Scope 2 in one month. The analyst needs to know.

**What I'd ask the PM:** "Should thresholds be global defaults or configurable per tenant? A steel plant's diesel consumption thresholds will be very different from an IT services company."

---

## Review Workflow — Approve Locks the Record

**Decision:** Approval is irreversible (sets `is_locked = True`). Rejections are reversible.

**Why:** Once a record enters the audit submission, it cannot change. Locking at approval time mimics what happens in real audit processes — once you sign off on a number, it is locked. An analyst who approved incorrectly would need to raise an audit amendment, which is a separate (out-of-scope) process.

**What I'd ask the PM:** "Should there be a 'submitted to auditor' batch event that locks all approved records simultaneously? Or is individual locking on approval correct? The GHG Protocol recommends a formal verification step before submission."

---

## Multi-tenancy Implementation

**Decision:** Row-level tenant isolation with direct FK, not schema-per-tenant.

**Why:** Schema-per-tenant requires a separate migration per client onboarding, complex connection routing, and is difficult to query across tenants for internal analytics. Row-level isolation with properly indexed tenant_id is adequate at ESG data volumes (thousands to hundreds of thousands of records per year, not billions).

**Security note:** Bulk review endpoint does not currently validate that all record_ids belong to the requesting user's tenant. This is a production security gap I would fix before deployment.
