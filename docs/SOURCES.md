# SOURCES.md — Research, Sample Data Design, and Production Gaps

## Source 1: SAP Fuel and Procurement

### What real-world format was researched

SAP Materials Management (MM) module stores procurement data in several tables. The most relevant for fuel tracking:

- **EKKO** — Purchase Order Header (vendor, company code, date)
- **EKPO** — Purchase Order Item (material number, quantity, unit)
- **MSEG / MKPF** — Material Document (goods receipts — actual delivery confirmation)
- **MARA** — Material Master (material description, material group)

Transaction **ME2M** (Purchase Orders by Material) produces an export with exactly the fields needed for emissions: material, quantity, unit, plant, date, description. Transaction **SE16N** (Table Browser) gives direct access to EKPO.

SAP exports are pipe-delimited (`|`) by default in German-configured systems, comma-delimited in English configurations. Column headers appear in the language of the SAP logon — a system configured in German shows `WERKS` (not `PLANT`), `MENGE` (not `QUANTITY`), `MEINS` (not `UOM`).

Dates are stored internally as `YYYYMMDD` (e.g. `20240115`). German locale configurations display them as `DD.MM.YYYY`. US locale shows `MM/DD/YYYY`.

### What the sample data looks like and why

```
MANDT|BUKRS|WERKS|MATNR|MENGE|MEINS|WRBTR|WAERS|BLDAT|TXZ01
100|1000|PL01|DIESEL-001|12500.000|L|1125000.00|INR|20240115|Diesel Kraftstoff
100|1000|PL05|HSD-002|6750.000|GAL|607500.00|INR|20240210|High Speed Diesel
```

**Design decisions in the sample data:**

1. **German column headers** — SAP exports from Indian clients often still have German headers because the SAP system was originally configured by German SAP consultants. `TXZ01` = short text, `BLDAT` = document date.

2. **Mixed units** — PL01 records diesel in litres (L). PL05 records the same fuel in gallons (GAL) because their SAP was configured by a US-based implementation partner. This is the real-world inconsistency our normalizer handles.

3. **Row 750,000 litres** — One row has `MENGE = 750000.000 L` for diesel. This is intentionally suspicious — it would be a ₹67.5 million single purchase order line, unrealistic for a routine fuel order. It tests our suspicious flagging logic (threshold: >500,000 litres).

4. **UNKNOWN-007 row** — One row has material `UNKNOWN-007` with description `Industrial Solvent`. This cannot be mapped to any fuel type and will be flagged as SUSPICIOUS with the error "Cannot classify material." This tests the unclassifiable material path.

5. **German description** — `Diesel Kraftstoff` (German for "diesel fuel") tests that our material lookup works on descriptions regardless of language.

### What would break in a real deployment

- **Material master not provided:** Real SAP systems have thousands of material numbers. Our MATERIAL_LOOKUP has ~15 patterns. A client might have materials like `10000123` with description `FUEL OIL TYPE A` that does not match any keyword. We would need the client to provide a mapping table: material number → fuel type.
- **Plant master not provided:** Our PLANT_LOOKUP has 6 plant codes. A real client might have 200 plants across India. Every unknown plant code generates a parse warning. The client must provide a plant-to-location CSV.
- **Thousand separator in German locale:** German SAP uses period as thousand separator (1.000,50 = one thousand point five). Our parser does `.replace(",", ".")` which would mishandle this. Production parser needs locale-aware decimal handling.
- **Multi-company code exports:** Large groups export data across multiple BUKRS (company codes). We treat all company codes from one file as one tenant, which may be wrong if the group has separate legal entities needing separate carbon reporting.

---

## Source 2: Utility Electricity

### What real-world format was researched

Indian utility customer portals researched:

- **MSEDCL** (Maharashtra State Electricity Distribution Co. Ltd) — Portal at mahadiscom.in. Provides CSV download with account number, meter ID, billing period, consumption in kWh, demand in kW, and tariff code.
- **BESCOM** (Bangalore Electricity Supply Company) — Similar portal, slightly different column names. Uses "Bill from Date" / "Bill to Date" instead of "Billing Period Start/End".
- **TSSPDCL** (Telangana State Southern Power Distribution Co.) — Export available, uses "Units Consumed" instead of "Consumption (kWh)".

All use comma-delimited CSV. None use the Green Button standard (US-only as of 2024).

HT (High Tension) connections are billed monthly on HT-I, HT-II, or HT-IIA tariff categories. LT (Low Tension) connections use LT-I through LT-V. HT connections consume in kWh; demand is measured in kVA or kW.

### What the sample data looks like and why

```
Account Number,Meter ID,Billing Period Start,Billing Period End,Consumption (kWh),...
ACC-MH-001234,MTR-PL01-HT,01/01/2024,31/01/2024,245300,620.5,...
ACC-MH-001235,MTR-PL02-HT,15/12/2023,14/01/2024,198450,510.3,...
ACC-MH-001236,MTR-HO01-LT,01/01/2024,31/01/2024,0,0,...
```

**Design decisions in the sample data:**

1. **Cross-month billing period** — `MTR-PL02-HT` has a billing period from December 15, 2023 to January 14, 2024. This is realistic — utilities do not always read meters on the 1st. Our midpoint attribution assigns activity_date = December 30, 2023. This tests the cross-month billing logic.

2. **Multiple meters per plant** — PL01 has both a High Tension meter (`MTR-PL01-HT`, 245,300 kWh) and a Low Tension meter (`MTR-PL01-LT`, 18,200 kWh). Both are separate rows in the same file. Both count as Scope 2.

3. **Zero consumption row** — `MTR-HO01-LT` shows 0 kWh consumption for January 2024. This triggers the suspicious flag with reason "Consumption is 0 kWh." The head office building was either closed, had a meter replacement, or the reading was missed.

4. **Tariff codes** — HT-II (High Tension Industrial), LT-III (Low Tension Commercial), HT-IIA (High Tension Industry Above 1000 kW). These are stored in raw_data but not used in the emission calculation — they would be relevant for market-based accounting.

### What would break in a real deployment

- **Multi-state utilities:** A national company might have bills from 12 different state utilities. Each has different CSV formats. We would need a column mapping profile per utility.
- **Bi-monthly billing:** Some utilities (especially in rural areas) read meters every two months. Our parser handles billing periods up to 90 days, but would flag a 60-day period as suspicious due to the >90-day check. The thresholds need to be configurable.
- **Maximum demand charges:** Some tariff structures bill in kVA (kilovolt-amperes, reactive power) not kW. Consumption in kVAh is not directly comparable to kWh. We assumed all consumption is active energy (kWh), which is correct for most HT industrial tariffs.
- **Net metering:** If a facility has rooftop solar with net metering, the bill shows net consumption (import minus export). We would need gross import figure for accurate Scope 2 reporting.

---

## Source 3: Corporate Travel

### What real-world format was researched

**Concur Expense Report Export** (SAP Concur) was the primary reference. The standard Concur export schema includes:

- `Report ID`, `Employee ID`, `Employee Name`
- `Transaction Date`, `Expense Type` (configurable per client — common values: "Air Travel", "Lodging", "Taxi", "Car Rental", "Train")
- `Vendor Name`, `City`, `Country`
- `Transaction Amount`, `Currency`
- For travel: `Origin`, `Destination` (airport codes or city names)
- `Travel Class` (Economy, Business, First)
- The `Distance` field exists in Concur but is rarely populated

**Navan (formerly TripActions)** uses similar fields but different column names:
- `Departure Airport Code`, `Arrival Airport Code` (explicit IATA codes, unlike Concur's freetext Origin/Destination)
- `Cabin Class` instead of `Travel Class`
- `Duration (Nights)` for hotels (explicit, unlike Concur)

**Why Concur:** More common in Indian enterprises (part of SAP ecosystem). HDFC Bank, Infosys, TCS, Wipro all use Concur.

### What the sample data looks like and why

```
RPT-001,EMP-101,2024-01-10,Air Travel,BOM,LHR,,85000,INR,Air India,Economy,,,
RPT-002,EMP-102,2024-01-12,Air Travel,DEL,DXB,,28000,INR,Emirates,Business,,,
RPT-007,EMP-107,2024-02-01,Air Travel,DEL,LHR,,89000,INR,British Airways,First,,,
```

**Design decisions in the sample data:**

1. **Missing distance column** — All flight rows have empty Distance(km). This is realistic — Concur does not auto-calculate distances. Our Haversine calculator kicks in and we record in `parse_errors` that "Distance was calculated (not provided)".

2. **Different travel classes** — EMP-101 flies Economy (BOM→LHR), EMP-102 flies Business (DEL→DXB), EMP-107 flies First class (DEL→LHR). Business class long-haul = 2.2× the economy factor. First class long-haul = 2.96× economy. This tests our factor selection logic.

3. **Different hotel countries** — London (GB, 31 kgCO2e/night), Dubai (AE, global average 23.8), Tokyo (JP, global average 23.8). This tests country-based factor selection.

4. **Taxi with only distance** — EMP-101 London taxi has distance (45 km) provided. EMP-104 Delhi taxi has distance (28 km). EMP-108 Hyderabad taxi also has distance. We use provided distances when available.

5. **Ground transport — train** — EMP-106 uses "Train" (INR 3,200 fare, no distance). This is flagged as suspicious (distance estimated: 3200 ÷ 15 = 213 km). Rail has a significantly lower emission factor (0.035 kgCO2e/km) than taxi (0.149 kgCO2e/km) — getting this right matters.

### What would break in a real deployment

- **Airport code not in our database:** We have 14 airports. The real world has ~10,000 IATA codes. A flight through Kochi (COK), Coimbatore (CJB), or Guwahati (GAU) would fail with "Unknown airport code." Production would use the full OurAirports.com dataset (free, open data, ~10,000 airports with coordinates).
- **Freetext origin/destination:** Some Concur configurations record "Mumbai" instead of "BOM". Mapping city names to IATA codes requires a fuzzy match or a lookup table with hundreds of entries per country.
- **Multi-leg trips:** A trip from Hyderabad to London via Dubai is three expense rows (HYD→DXB, DXB→LHR, hotel in London) under one Report ID. We process each row independently. We do not currently aggregate multi-leg trips into a journey.
- **Currency conversion:** All amounts are in INR in our sample. In practice, employees file expenses in local currency (GBP for UK trips, USD for US trips). The amount is recorded in the transaction currency. If we were using amounts to estimate ground distances, we would need FX conversion.
- **Personal travel tacked on:** An employee who extends a business trip by 2 personal days would have the full flight cost reimbursed but only part of the hotel nights are business travel. We attribute all nights to business travel, which overstates Scope 3.
