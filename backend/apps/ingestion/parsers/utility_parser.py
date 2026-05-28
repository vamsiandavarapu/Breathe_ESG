"""
Utility Data Parser — Electricity from portal CSV exports

WHY CSV PORTAL EXPORT: Three realistic options exist:
1. PDF bill — requires OCR, brittle, different layout per utility
2. Green Button API — US standard, not available in India yet  
3. Portal CSV export — MSEDCL, BESCOM, TSSPDCL all offer CSV download

We chose portal CSV because:
- Available from all major Indian utilities today
- Consistent enough structure to parse reliably
- What a real facilities team actually does every month

REAL-WORLD CHALLENGES HANDLED:
1. Billing periods that don't align with calendar months
   (e.g., Jan 15 – Feb 14 means consumption spans two reporting months)
2. Multiple meters for the same building (HT and LT connection)
3. Units: "units" is a common Indian utility term for kWh
4. Demand charges vs consumption charges (we only count consumption)
5. Reactive energy (kVARh) is billed but doesn't produce emissions

WHAT WE IGNORE:
- Demand charges (kVA billed)
- Power factor penalties
- Fuel adjustment charges (these affect billing but not consumption)
- Net metering / solar export (would reduce Scope 2)

FORMAT RESEARCHED: MSEDCL (Maharashtra) portal export format
"""
import csv
import io
from decimal import Decimal
from datetime import date, datetime

from .emission_factors import FACTORS
from .unit_normalizer import normalize_unit


ELECTRICITY_FACTOR_KEY = 'ELECTRICITY_IN'  # India grid — CEA 2023


def _parse_billing_period(start_str: str, end_str: str) -> tuple:
    """
    Parse billing period start and end dates.
    Returns (start_date, end_date, activity_date)
    
    activity_date is the midpoint of the billing period.
    Why midpoint? Because if billing period is Jan 15 – Feb 14, attributing
    all consumption to Feb (billing month) would distort monthly reporting.
    Midpoint attribution is the pragmatic choice for a prototype.
    
    In production: you'd apportion consumption proportionally across months.
    E.g., 15 days in Jan, 14 days in Feb → split accordingly.
    """
    formats = ['%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%m/%d/%Y', '%d.%m.%Y']
    
    def try_parse(s):
        for fmt in formats:
            try:
                return datetime.strptime(s.strip(), fmt).date()
            except ValueError:
                continue
        raise ValueError(f"Cannot parse date: '{s}'")
    
    start = try_parse(start_str)
    end = try_parse(end_str)
    
    # Midpoint for activity date
    mid_timestamp = datetime.combine(start, datetime.min.time()).timestamp()
    end_timestamp = datetime.combine(end, datetime.min.time()).timestamp()
    mid = date.fromtimestamp((mid_timestamp + end_timestamp) / 2)
    
    return start, end, mid


def _flag_suspicious(kwh: Decimal, billing_days: int, account: str) -> tuple:
    """
    Flag suspicious electricity readings.
    
    Rules based on real-world plausibility:
    - < 0 kWh: meter reading reversal or data error
    - > 2,000,000 kWh per month: only very large industrial plants (unusual for this template)
    - Daily consumption < 1 kWh for a commercial account: likely meter read error
    - Billing period > 90 days: utility missed a cycle (happens but is suspicious)
    """
    reasons = []
    
    if kwh <= 0:
        reasons.append(f"Consumption is {kwh} kWh — must be positive")
    
    if kwh > 2000000:
        reasons.append(f"Consumption {kwh} kWh is very high — verify with facilities")
    
    if billing_days > 0 and kwh > 0:
        daily_avg = kwh / Decimal(str(billing_days))
        if daily_avg < 1:
            reasons.append(f"Daily average {daily_avg:.1f} kWh is very low for commercial account")
    
    if billing_days > 90:
        reasons.append(f"Billing period is {billing_days} days — utility may have skipped a cycle")
    
    if billing_days < 20:
        reasons.append(f"Billing period is only {billing_days} days — check for duplicate")
    
    return bool(reasons), '; '.join(reasons)


def parse_utility_csv(file_content: str, tenant) -> list:
    """
    Parse utility portal CSV export.
    
    Expected columns (flexible — we handle variants):
      Account Number, Meter ID, Billing Period Start, Billing Period End,
      Consumption (kWh), Demand (kW), Amount (INR), Tariff Code
    """
    results = []
    
    # Detect delimiter
    sample = file_content[:500]
    delimiter = ',' if sample.count(',') >= sample.count(';') else ';'
    
    reader = csv.DictReader(io.StringIO(file_content), delimiter=delimiter)
    
    for row_number, row in enumerate(reader, start=2):
        raw_data = dict(row)
        result = {
            'row_number': row_number,
            'raw_data': raw_data,
            'parse_status': 'OK',
            'parse_errors': [],
            'source_type': 'UTILITY_ELECTRICITY',
        }
        
        # Normalize column names — utility portals use wildly different headers
        col_map = {}
        for col in row.keys():
            col_clean = col.strip().lower().replace(' ', '_').replace('(', '').replace(')', '')
            col_map[col_clean] = (row.get(col) or '').strip()
        
        try:
            # Find consumption column — try multiple names
            kwh_raw = None
            for key in ['consumption_kwh', 'consumption', 'kwh', 'units', 'energy_kwh', 'net_consumption']:
                if key in col_map and col_map[key]:
                    kwh_raw = col_map[key].replace(',', '')
                    break
            
            if kwh_raw is None:
                raise ValueError("Cannot find consumption column. Expected: 'Consumption (kWh)' or 'Units'")
            
            consumption_kwh = Decimal(kwh_raw)
            
            # Find date columns
            period_start = col_map.get('billing_period_start') or col_map.get('start_date') or col_map.get('from_date', '')
            period_end = col_map.get('billing_period_end') or col_map.get('end_date') or col_map.get('to_date', '')
            
            if not period_start or not period_end:
                raise ValueError("Cannot find billing period dates")
            
            start_date, end_date, activity_date = _parse_billing_period(period_start, period_end)
            billing_days = (end_date - start_date).days
            
            # Meter and account info
            account = col_map.get('account_number') or col_map.get('account_no') or col_map.get('consumer_no', 'UNKNOWN')
            meter_id = col_map.get('meter_id') or col_map.get('meter_no') or col_map.get('meter_number', '')
            tariff = col_map.get('tariff_code') or col_map.get('tariff') or col_map.get('category', '')
            
            # Unit normalization (some exports say "Units" or "MWh")
            unit_raw = col_map.get('unit') or col_map.get('uom') or 'KWH'
            if unit_raw.upper() in ('UNIT', 'UNITS', ''):
                unit_raw = 'KWH'
            
            try:
                normalized_qty, normalized_unit, _ = normalize_unit(float(consumption_kwh), unit_raw)
            except ValueError:
                # If unit is unrecognized, assume kWh (most common)
                normalized_qty = consumption_kwh
                normalized_unit = 'KWH'
                result['parse_errors'].append(f"Unknown unit '{unit_raw}', assumed KWH")
            
            # Emission calculation
            factor_info = FACTORS[ELECTRICITY_FACTOR_KEY]
            co2e_kg = float(normalized_qty) * factor_info['factor']
            
            # Suspicious check
            is_suspicious, suspicious_reason = _flag_suspicious(normalized_qty, billing_days, account)
            if is_suspicious:
                result['parse_status'] = 'SUSPICIOUS'
            
            location_desc = f"Meter {meter_id}" if meter_id else f"Account {account}"
            
            result.update({
                'scope': 'SCOPE_2',
                'category': 'PURCHASED_ELECTRICITY',
                'activity_description': f"Electricity — {location_desc} | Period: {start_date} to {end_date}",
                'activity_date': activity_date,
                'location': location_desc,
                'quantity': float(normalized_qty),
                'unit': 'KWH',
                'quantity_original': float(consumption_kwh),
                'unit_original': unit_raw.upper(),
                'emission_factor': factor_info['factor'],
                'emission_factor_source': 'CEA 2023 (India Grid)',
                'co2e_kg': round(co2e_kg, 4),
                'is_suspicious': is_suspicious,
                'suspicious_reason': suspicious_reason,
                # Extra metadata stored in raw_data
                'billing_period_start': start_date.isoformat(),
                'billing_period_end': end_date.isoformat(),
                'billing_days': billing_days,
            })
            
        except Exception as e:
            result['parse_status'] = 'FAILED'
            result['parse_errors'].append(str(e))
        
        results.append(result)
    
    return results
