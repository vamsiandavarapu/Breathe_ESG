"""
Unit Normalizer — converts any unit from any source to our standard units.

SAP exports are infamous for inconsistent units. The same material (diesel)
might appear as:
  - L (litres) from one plant
  - GAL (gallons) from another configured in US settings
  - M3 (cubic metres) from a tank measurement system
  - KG (kilograms, for gas delivery by weight)

We normalize everything to a canonical unit before storing.
This means all calculations are consistent regardless of source.

Canonical units:
  Liquids → LITRE
  Gases → M3
  Electricity → KWH
  Distances → KM
  Weight → KG
"""
from decimal import Decimal


# Conversion table to canonical unit
# Format: 'SOURCE_UNIT': (multiplier_to_canonical, canonical_unit)
UNIT_CONVERSIONS = {
    # ── Liquid Volume → Litres ────────────────────────────────
    'L':    (Decimal('1'),        'LITRE'),
    'LTR':  (Decimal('1'),        'LITRE'),
    'LT':   (Decimal('1'),        'LITRE'),
    'LITRE':(Decimal('1'),        'LITRE'),
    'GAL':  (Decimal('3.78541'), 'LITRE'),   # US gallon
    'IGAL': (Decimal('4.54609'), 'LITRE'),   # Imperial (UK) gallon
    'BBL':  (Decimal('158.987'), 'LITRE'),   # Barrel (petroleum)
    'ML':   (Decimal('0.001'),   'LITRE'),

    # ── Gas Volume → Cubic Metres ─────────────────────────────
    'M3':   (Decimal('1'),        'M3'),
    'M³':   (Decimal('1'),        'M3'),
    'SCM':  (Decimal('1'),        'M3'),     # Standard cubic metre
    'MSCM': (Decimal('1000'),     'M3'),     # Thousand SCM
    'CF':   (Decimal('0.02832'), 'M3'),     # Cubic feet
    'MCF':  (Decimal('28.317'),  'M3'),     # Thousand cubic feet

    # ── Electricity → kWh ─────────────────────────────────────
    'KWH':  (Decimal('1'),        'KWH'),
    'UNIT': (Decimal('1'),        'KWH'),   # India: "1 unit" = 1 kWh
    'MWH':  (Decimal('1000'),     'KWH'),
    'GWH':  (Decimal('1000000'), 'KWH'),
    'KVH':  (Decimal('1'),        'KWH'),   # Some SAP configs export as KVH

    # ── Weight → Kilograms ────────────────────────────────────
    'KG':   (Decimal('1'),        'KG'),
    'G':    (Decimal('0.001'),   'KG'),
    'MT':   (Decimal('1000'),    'KG'),     # Metric tonne
    'TON':  (Decimal('907.185'), 'KG'),    # US short ton
    'LB':   (Decimal('0.45359'), 'KG'),
    'LBS':  (Decimal('0.45359'), 'KG'),

    # ── Distance → Kilometres ─────────────────────────────────
    'KM':   (Decimal('1'),        'KM'),
    'MI':   (Decimal('1.60934'), 'KM'),
    'MILE': (Decimal('1.60934'), 'KM'),
    'NM':   (Decimal('1.852'),   'KM'),    # Nautical miles (aviation)

    # ── Time ──────────────────────────────────────────────────
    'NIGHT': (Decimal('1'),      'NIGHT'),
    'NITE':  (Decimal('1'),      'NIGHT'),
    'DAY':   (Decimal('1'),      'NIGHT'), # Hotel days treated as nights
}


def normalize_unit(quantity: float, unit: str) -> tuple:
    """
    Convert quantity+unit to canonical unit.
    Returns (normalized_quantity, canonical_unit, was_converted).
    
    Example:
        normalize_unit(100, 'GAL') → (Decimal('378.541'), 'LITRE', True)
        normalize_unit(500, 'L')   → (Decimal('500'), 'LITRE', False)
    
    Raises ValueError if unit is unknown.
    """
    unit_upper = unit.strip().upper()
    
    if unit_upper not in UNIT_CONVERSIONS:
        raise ValueError(f"Unknown unit: '{unit}'. Add it to unit_normalizer.py if valid.")
    
    multiplier, canonical = UNIT_CONVERSIONS[unit_upper]
    normalized = Decimal(str(quantity)) * multiplier
    was_converted = (unit_upper != canonical)
    
    return normalized, canonical, was_converted


def parse_sap_date(date_str: str):
    """
    SAP dates come in multiple formats depending on client configuration.
    We try all known formats before giving up.
    
    Formats seen in real SAP exports:
      YYYYMMDD  (standard SAP internal format)
      DD.MM.YYYY (German locale, very common in SAP)
      MM/DD/YYYY (US locale)
      DD-MM-YYYY (some custom configs)
    """
    from datetime import datetime, date
    
    date_str = str(date_str).strip()
    formats = [
        '%Y%m%d',      # 20240115  (SAP internal)
        '%d.%m.%Y',   # 15.01.2024 (German locale)
        '%m/%d/%Y',   # 01/15/2024 (US locale)
        '%d-%m-%Y',   # 15-01-2024
        '%Y-%m-%d',   # 2024-01-15 (ISO)
        '%d/%m/%Y',   # 15/01/2024 (Indian format)
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    
    raise ValueError(f"Cannot parse date: '{date_str}'. None of the known SAP date formats matched.")
