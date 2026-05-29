"""
SAP Fuel & Procurement Parser

WHY FLAT FILE: SAP has many export mechanisms. We chose flat file (pipe-delimited)
because:
1. IDoc requires SAP middleware (XI/PI/CPI) — most clients can't expose this externally
2. OData services require SAP Gateway configuration and firewall exceptions
3. BAPI calls need RFC connections — too much IT dependency for onboarding
4. Flat file: the client's SAP Basis admin runs transaction SE16N or MB52, exports CSV.
   Takes 5 minutes. No IT project required. That's the realistic mode for new clients.

WHAT WE'RE MODELING: SAP MM (Materials Management) goods receipt records.
Transaction MB52 gives warehouse stocks. Transaction ME2M gives purchase orders.
We process ME2M-style exports — purchase order history with quantities.

REAL SAP FIELD NAMES (localized column headers in German is common):
  MANDT   = Client (always 100 in single-client systems)
  BUKRS   = Buchungskreis (Company Code)
  WERKS   = Werk (Plant) 
  MATNR   = Materialnummer (Material Number)
  MENGE   = Menge (Quantity)
  MEINS   = Basismengeneinheit (Base Unit of Measure)
  WRBTR   = Betrag (Amount in local currency)
  WAERS   = Währung (Currency)
  BLDAT   = Belegdatum (Document Date)
  TXZ01   = Kurztext (Short Description)

WHAT WE IGNORE: Vendor details (LIFNR), account assignment (KOSTL/AUFNR),
purchase org (EKORG), storage locations (LGORT). These matter for procurement
analytics but not for carbon calculation.
"""
import csv
import io
import xml.etree.ElementTree as ET
from decimal import Decimal
from datetime import date

from .emission_factors import FACTORS
from .unit_normalizer import normalize_unit, parse_sap_date


# Map SAP material numbers/descriptions to our emission factor keys
# In a real deployment this would be a database table maintained by analysts
MATERIAL_LOOKUP = {
    # Material patterns → emission factor key
    'DIESEL':      'DIESEL',
    'DIESEL-':     'DIESEL',
    'HSD':         'HSD',
    'HIGHSPEED':   'DIESEL',
    'PETROL':      'PETROL',
    'GASOIL':      'DIESEL',
    'LPG':         'LPG',
    'PNG':         'NATURAL_GAS',
    'CNG':         'NATURAL_GAS',
    'NATGAS':      'NATURAL_GAS',
    'FURNACE':     'FURNACE_OIL',
    'FUELOIL':     'FURNACE_OIL',
    # German material descriptions (common in SAP configurations)
    'DIESEL KRAFTSTOFF': 'DIESEL',
    'HEIZÖL':            'FURNACE_OIL',
    'ERDGAS':            'NATURAL_GAS',
}

# Plant code lookup — in real life, client provides this
PLANT_LOOKUP = {
    'PL01': 'Mumbai - Andheri Factory',
    'PL02': 'Pune - Hinjewadi Facility',
    'PL03': 'Chennai - Guindy Plant',
    'PL04': 'Delhi - Okhla Warehouse',
    'PL05': 'Hyderabad - Uppal Unit',
    'HO01': 'Head Office - Mumbai',
}

# These SAP column headers map to our canonical field names
# SAP can export English or German headers — handle both
COLUMN_ALIASES = {
    'MANDT':    'client',
    'BUKRS':    'company_code',
    'WERKS':    'plant_code',
    'MATNR':    'material_number',
    'MENGE':    'quantity',
    'MEINS':    'unit',
    'WRBTR':    'amount',
    'WAERS':    'currency',
    'BLDAT':    'document_date',
    'CPUDT':    'entry_date',
    'TXZ01':    'description',
    # English variants (some SAP versions)
    'PLANT':       'plant_code',
    'MATERIAL':    'material_number',
    'QTY':         'quantity',
    'UOM':         'unit',
    'DOC_DATE':    'document_date',
    'SHORT_TEXT':  'description',
}


def _resolve_material(material_number: str, description: str) -> str:
    """
    Map a SAP material number or description to an emission factor key.
    Tries description first (more readable), then material number.
    Returns None if we can't classify it (will be flagged as suspicious).
    """
    search_text = (description or '').upper().replace(' ', '')
    mat_upper = (material_number or '').upper()
    
    for keyword, factor_key in MATERIAL_LOOKUP.items():
        kw_clean = keyword.upper().replace(' ', '')
        if kw_clean in search_text or kw_clean in mat_upper:
            return factor_key
    
    return None


def _flag_suspicious(quantity: Decimal, unit: str, factor_key: str) -> tuple:
    """
    Auto-flag records that look wrong. Returns (is_suspicious, reason).
    
    Thresholds are based on realistic enterprise consumption:
    - A factory using > 100,000 litres diesel in one purchase order is unusual
    - A generator using < 1 litre per record is probably a test entry
    - Wrong units for fuel type (e.g. diesel in kWh) is always suspicious
    """
    reasons = []
    
    # Quantity sanity checks
    if quantity <= 0:
        reasons.append(f"Quantity is {quantity} — must be positive")
    
    if quantity > 500000:
        reasons.append(f"Quantity {quantity} is extremely high for a single PO line — verify")
    
    # Unit-material mismatch
    if factor_key in ('DIESEL', 'PETROL', 'LPG', 'HSD', 'FURNACE_OIL'):
        if unit not in ('LITRE', 'KG', 'M3'):
            reasons.append(f"Fuel material has unit '{unit}' — expected LITRE/KG/M3")
    
    if factor_key == 'NATURAL_GAS' and unit not in ('M3', 'KG'):
        reasons.append(f"Natural gas has unit '{unit}' — expected M3 or KG")
    
    return bool(reasons), '; '.join(reasons)


def parse_sap_csv(file_content: str, tenant) -> list:
    """
    Main parser entry point.
    
    Takes raw CSV content (string), returns list of dicts suitable for
    creating EmissionRecord objects.
    
    Each returned dict includes:
      - raw_data: the original row (for RawRecord)
      - normalized fields: scope, category, quantity, unit, co2e_kg, etc.
      - parse_status and parse_errors
    """
    # Auto-detect XML format
    stripped = file_content.strip()
    if stripped.startswith('<'):
        return parse_sap_idoc_xml(file_content, tenant)
        
    results = []
    
    # SAP exports can use pipe (|), semicolon (;), or comma (,) as delimiter
    # Detect automatically
    sample = file_content[:500]
    delimiter = '|' if sample.count('|') > sample.count(',') else (';' if sample.count(';') > sample.count(',') else ',')
    
    reader = csv.DictReader(io.StringIO(file_content), delimiter=delimiter)
    
    for row_number, row in enumerate(reader, start=2):  # start=2 because row 1 is header
        raw_data = dict(row)
        result = {
            'row_number': row_number,
            'raw_data': raw_data,
            'parse_status': 'OK',
            'parse_errors': [],
            'source_type': 'SAP_FUEL',
        }
        
        # Normalize column names (SAP German → our English names)
        normalized_row = {}
        for col, value in row.items():
            col_clean = col.strip().upper()
            canonical = COLUMN_ALIASES.get(col_clean, col_clean.lower())
            normalized_row[canonical] = (value or '').strip()
        
        try:
            # ── Required fields ───────────────────────────────────
            plant_code = normalized_row.get('plant_code', '').strip()
            material_number = normalized_row.get('material_number', '').strip()
            description = normalized_row.get('description', '').strip()
            quantity_raw = normalized_row.get('quantity', '0').replace(',', '.')  # German decimal
            unit_raw = normalized_row.get('unit', '').strip().upper()
            date_raw = normalized_row.get('document_date', '')
            
            if not quantity_raw or not unit_raw or not date_raw:
                raise ValueError("Missing required fields: quantity, unit, or date")
            
            # ── Parse date ────────────────────────────────────────
            activity_date = parse_sap_date(date_raw)
            
            # ── Parse quantity ────────────────────────────────────
            try:
                quantity_decimal = Decimal(quantity_raw)
            except Exception:
                raise ValueError(f"Cannot parse quantity: '{quantity_raw}'")
            
            # ── Normalize unit ────────────────────────────────────
            try:
                normalized_qty, normalized_unit, was_converted = normalize_unit(float(quantity_decimal), unit_raw)
            except ValueError as e:
                raise ValueError(f"Unit normalization failed: {e}")
            
            # ── Classify material → emission factor ───────────────
            factor_key = _resolve_material(material_number, description)
            if not factor_key:
                result['parse_status'] = 'SUSPICIOUS'
                result['parse_errors'].append(
                    f"Cannot classify material '{material_number}' ({description}) as a fuel type. "
                    f"Add to MATERIAL_LOOKUP in sap_parser.py"
                )
                factor_info = {
                    'factor': 0.0,
                    'scope': 'SCOPE_1',
                    'category': 'STATIONARY_COMBUSTION'
                }
                display_factor_key = 'UNCLASSIFIED'
            else:
                factor_info = FACTORS[factor_key]
                display_factor_key = factor_key
            
            # ── Calculate CO2e ────────────────────────────────────
            co2e_kg = float(normalized_qty) * factor_info['factor']
            
            # ── Location ──────────────────────────────────────────
            location = PLANT_LOOKUP.get(plant_code, f"Unknown Plant: {plant_code}")
            if plant_code not in PLANT_LOOKUP:
                result['parse_errors'].append(f"Plant code '{plant_code}' not in lookup table")
            
            # ── Suspicious check ──────────────────────────────────
            is_suspicious, suspicious_reason = _flag_suspicious(normalized_qty, normalized_unit, factor_key or 'DIESEL')
            if not factor_key:
                is_suspicious = True
                suspicious_reason = f"Cannot classify material '{material_number}' as a fuel type; " + suspicious_reason
                result['parse_status'] = 'SUSPICIOUS'
            elif is_suspicious:
                result['parse_status'] = 'SUSPICIOUS'
            
            result.update({
                'scope': factor_info['scope'],
                'category': factor_info['category'],
                'activity_description': f"{description or display_factor_key} — {location}",
                'activity_date': activity_date,
                'location': location,
                'quantity': float(normalized_qty),
                'unit': normalized_unit,
                'quantity_original': float(quantity_decimal),
                'unit_original': unit_raw,
                'emission_factor': factor_info['factor'],
                'emission_factor_source': 'DEFRA 2024',
                'co2e_kg': round(co2e_kg, 4),
                'is_suspicious': is_suspicious,
                'suspicious_reason': suspicious_reason,
            })
            
        except Exception as e:
            result['parse_status'] = 'FAILED'
            result['parse_errors'].append(str(e))
        
        results.append(result)
    
    return results


def parse_sap_idoc_xml(file_content: str, tenant) -> list:
    """
    Parses SAP IDoc XML content.
    Looks for item segments (elements containing quantity and material fields)
    and header fields (like date, company code) to construct EmissionRecords.
    """
    try:
        root = ET.fromstring(file_content)
    except Exception as e:
        raise ValueError(f"XML Parsing Error: {str(e)}")
    
    # Helper to recursively find global/header values in the XML
    def find_global_value(tag_name):
        for elem in root.iter():
            tag_clean = elem.tag.split('}')[-1].strip().upper()  # Handle namespaces
            if tag_clean == tag_name:
                return (elem.text or '').strip()
        return ''

    # Get global values if available
    global_date = find_global_value('BLDAT') or find_global_value('DOC_DATE')
    global_company = find_global_value('BUKRS') or find_global_value('MANDT')
    
    results = []
    row_counter = 1
    
    # We will search for all elements that have a quantity child.
    item_candidates = []
    
    for elem in root.iter():
        if elem == root:
            continue
            
        tag_clean = elem.tag.split('}')[-1].strip().upper()
        children_tags = {child.tag.split('}')[-1].strip().upper() for child in elem}
        has_qty = any(t in children_tags for t in ['MENGE', 'QTY', 'QUANTITY'])
        has_mat = any(t in children_tags for t in ['MATNR', 'MATERIAL', 'MATERIAL_NUMBER', 'TXZ01', 'DESCRIPTION', 'SHORT_TEXT'])
        
        is_standard_segment = tag_clean in ['E1EDP01', 'ZE1EDP01', 'ITEM', 'RECORD']
        if (has_qty and has_mat) or is_standard_segment:
            item_candidates.append(elem)
            
    # If no nested item candidate segments found, fallback to check if root itself is a single item
    if not item_candidates:
        children_tags = {child.tag.split('}')[-1].strip().upper() for child in root}
        if any(t in children_tags for t in ['MENGE', 'QTY', 'QUANTITY']):
            item_candidates = [root]

    for item in item_candidates:
        row_number = row_counter
        row_counter += 1
        
        raw_data = {}
        for child in item:
            tag_name = child.tag.split('}')[-1].strip().upper()
            raw_data[tag_name] = (child.text or '').strip()
            
        # Reconstruct full row details including global metadata if missing
        if 'BLDAT' not in raw_data and 'DOC_DATE' not in raw_data and global_date:
            raw_data['BLDAT'] = global_date
        if 'BUKRS' not in raw_data and global_company:
            raw_data['BUKRS'] = global_company
            
        result = {
            'row_number': row_number,
            'raw_data': raw_data,
            'parse_status': 'OK',
            'parse_errors': [],
            'source_type': 'SAP_FUEL',
        }
        
        normalized_row = {}
        for col, value in raw_data.items():
            col_clean = col.strip().upper()
            canonical = COLUMN_ALIASES.get(col_clean, col_clean.lower())
            normalized_row[canonical] = value
            
        try:
            plant_code = normalized_row.get('plant_code', '').strip()
            material_number = normalized_row.get('material_number', '').strip()
            description = normalized_row.get('description', '').strip()
            quantity_raw = normalized_row.get('quantity', '0').replace(',', '.')
            unit_raw = normalized_row.get('unit', '').strip().upper()
            date_raw = normalized_row.get('document_date', '')
            
            if not quantity_raw or not unit_raw or not date_raw:
                raise ValueError("Missing required fields: quantity, unit, or date")
                
            activity_date = parse_sap_date(date_raw)
            
            try:
                quantity_decimal = Decimal(quantity_raw)
            except Exception:
                raise ValueError(f"Cannot parse quantity: '{quantity_raw}'")
                
            try:
                normalized_qty, normalized_unit, was_converted = normalize_unit(float(quantity_decimal), unit_raw)
            except ValueError as e:
                raise ValueError(f"Unit normalization failed: {e}")
                
            factor_key = _resolve_material(material_number, description)
            if not factor_key:
                result['parse_status'] = 'SUSPICIOUS'
                result['parse_errors'].append(
                    f"Cannot classify material '{material_number}' ({description}) as a fuel type. "
                    f"Add to MATERIAL_LOOKUP in sap_parser.py"
                )
                factor_info = {
                    'factor': 0.0,
                    'scope': 'SCOPE_1',
                    'category': 'STATIONARY_COMBUSTION'
                }
                display_factor_key = 'UNCLASSIFIED'
            else:
                factor_info = FACTORS[factor_key]
                display_factor_key = factor_key
                
            co2e_kg = float(normalized_qty) * factor_info['factor']
            
            location = PLANT_LOOKUP.get(plant_code, f"Unknown Plant: {plant_code}")
            if plant_code not in PLANT_LOOKUP:
                result['parse_errors'].append(f"Plant code '{plant_code}' not in lookup table")
                
            is_suspicious, suspicious_reason = _flag_suspicious(normalized_qty, normalized_unit, factor_key or 'DIESEL')
            if not factor_key:
                is_suspicious = True
                suspicious_reason = f"Cannot classify material '{material_number}' as a fuel type; " + suspicious_reason
                result['parse_status'] = 'SUSPICIOUS'
            elif is_suspicious:
                result['parse_status'] = 'SUSPICIOUS'
                
            result.update({
                'scope': factor_info['scope'],
                'category': factor_info['category'],
                'activity_description': f"{description or display_factor_key} — {location}",
                'activity_date': activity_date,
                'location': location,
                'quantity': float(normalized_qty),
                'unit': normalized_unit,
                'quantity_original': float(quantity_decimal),
                'unit_original': unit_raw,
                'emission_factor': factor_info['factor'],
                'emission_factor_source': 'DEFRA 2024',
                'co2e_kg': round(co2e_kg, 4),
                'is_suspicious': is_suspicious,
                'suspicious_reason': suspicious_reason,
            })
            
        except Exception as e:
            result['parse_status'] = 'FAILED'
            result['parse_errors'].append(str(e))
            
        results.append(result)
        
    if not results:
        raise ValueError("No valid SAP IDoc data segments found in XML")
        
    return results
