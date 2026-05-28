"""
Corporate Travel Parser — Concur Expense Export CSV

WHY CONCUR CSV: Three options were considered:
1. Concur API (OAuth) — requires enterprise integration, IT dependency, out of scope
2. Navan API — same problem
3. Concur expense report CSV export — available to any admin via Reports menu

We chose CSV export because:
- Any expense admin can export it in 2 minutes
- Contains all fields we need: expense type, origin, destination, amount, class
- Industry standard for ESG data collection from travel platforms

REAL CONCUR EXPORT FORMAT researched from:
- Concur documentation: expense_type, transaction_date, vendor_name
- SAP Concur Expense Report Export template (Standard Entity)

KEY CHALLENGE — MISSING DISTANCES:
Concur records flights by origin/destination (airport codes), not distance.
Hotels record city, not km.
Ground transport sometimes has distance, sometimes doesn't.

Our approach:
- Flights: Haversine distance from IATA codes + DEFRA routing factor
- Hotels: city → country → appropriate hotel emission factor
- Ground: if distance missing, estimate from amount ÷ average rate
  (e.g., INR 2500 taxi ÷ INR 15/km avg = 167 km estimate, flagged as estimated)

WHAT WE IGNORE:
- Meal expenses (not Scope 3 for GHG Protocol purposes)
- Conference registration fees
- Visa/travel insurance costs
- Mileage claims (employee personal car — different methodology needed)
"""
import csv
import io
import re
from decimal import Decimal
from datetime import datetime

from .emission_factors import FACTORS, haversine_km, classify_flight


# Map Concur expense type strings to our categories
EXPENSE_TYPE_MAP = {
    # Air travel
    'AIR': 'FLIGHT',
    'AIRFARE': 'FLIGHT',
    'AIRLINE': 'FLIGHT',
    'FLIGHT': 'FLIGHT',
    'AIR TRAVEL': 'FLIGHT',
    'DOMESTIC AIR': 'FLIGHT',
    'INTERNATIONAL AIR': 'FLIGHT',
    
    # Hotels
    'HOTEL': 'HOTEL',
    'LODGING': 'HOTEL',
    'ACCOMMODATION': 'HOTEL',
    'HOTEL/MOTEL': 'HOTEL',
    
    # Ground transport
    'TAXI': 'GROUND',
    'CAB': 'GROUND',
    'UBER': 'GROUND',
    'OLA': 'GROUND',
    'RIDESHARE': 'GROUND',
    'GROUND TRANSPORT': 'GROUND',
    'CAR RENTAL': 'GROUND',
    'CAR HIRE': 'GROUND',
    'TRAIN': 'GROUND',
    'RAIL': 'GROUND',
    'BUS': 'GROUND',
    'METRO': 'GROUND',
}

# Average taxi rate per km in INR (for distance estimation when missing)
TAXI_RATE_INR_PER_KM = 15.0

# Typical hotel location mapping → emission factor key
HOTEL_FACTOR_MAP = {
    'IN': 'HOTEL_INDIA',   # India
    'UK': 'HOTEL_UK',
    'GB': 'HOTEL_UK',
    'DEFAULT': 'HOTEL_GLOBAL',
}


def _classify_expense(expense_type: str) -> str:
    """Normalize expense type string to FLIGHT/HOTEL/GROUND/UNKNOWN."""
    if not expense_type:
        return 'UNKNOWN'
    upper = expense_type.strip().upper()
    for key, val in EXPENSE_TYPE_MAP.items():
        if key in upper:
            return val
    return 'UNKNOWN'


def _get_flight_factor_key(distance_km: float, travel_class: str) -> str:
    """Select correct DEFRA emission factor based on distance and class."""
    haul = classify_flight(distance_km)
    cls = (travel_class or '').upper()
    
    if 'FIRST' in cls:
        return f'FLIGHT_FIRST_{haul}'
    elif 'BUSINESS' in cls or 'BUS' in cls:
        return f'FLIGHT_BUSINESS_{haul}'
    else:
        return f'FLIGHT_ECONOMY_{haul}'


def _parse_travel_date(date_str: str):
    formats = ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y', '%d.%m.%Y']
    for fmt in formats:
        try:
            return datetime.strptime(str(date_str).strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: '{date_str}'")


def parse_travel_csv(file_content: str, tenant) -> list:
    """
    Parse Concur expense export CSV.
    
    Handles three expense types: flights, hotels, ground transport.
    Each type has different fields available and different calculation logic.
    """
    results = []
    
    delimiter = ',' if file_content[:200].count(',') >= file_content[:200].count('\t') else '\t'
    reader = csv.DictReader(io.StringIO(file_content), delimiter=delimiter)
    
    for row_number, row in enumerate(reader, start=2):
        raw_data = dict(row)
        result = {
            'row_number': row_number,
            'raw_data': raw_data,
            'parse_status': 'OK',
            'parse_errors': [],
            'source_type': 'TRAVEL_CORPORATE',
        }
        
        # Normalize column names
        col = {k.strip().lower().replace(' ', '_').replace('(', '').replace(')', ''): 
               (v or '').strip() for k, v in row.items()}
        
        try:
            expense_type_raw = col.get('expense_type') or col.get('category') or col.get('type', '')
            category = _classify_expense(expense_type_raw)
            
            date_raw = col.get('travel_date') or col.get('transaction_date') or col.get('date', '')
            activity_date = _parse_travel_date(date_raw)
            
            employee = col.get('employee_id') or col.get('employee_name') or col.get('employee', 'UNKNOWN')
            
            if category == 'FLIGHT':
                origin = (col.get('origin') or col.get('from') or col.get('departure', '')).upper().strip()
                dest = (col.get('destination') or col.get('to') or col.get('arrival', '')).upper().strip()
                travel_class = col.get('class') or col.get('cabin_class') or col.get('fare_class', 'Economy')
                
                # Distance: use provided or calculate
                dist_raw = col.get('distance_km') or col.get('distance') or ''
                if dist_raw and dist_raw.replace('.', '').isdigit():
                    distance_km = float(dist_raw)
                    dist_source = 'provided'
                else:
                    # Calculate from airport codes
                    distance_km = haversine_km(origin, dest)
                    if distance_km is None:
                        raise ValueError(f"Unknown airport code(s): '{origin}' or '{dest}'. Add to AIRPORTS dict.")
                    dist_source = f'calculated (Haversine × 1.08 routing factor)'
                
                factor_key = _get_flight_factor_key(distance_km, travel_class)
                if factor_key not in FACTORS:
                    factor_key = 'FLIGHT_ECONOMY_LONG'  # fallback
                    result['parse_errors'].append(f"Factor key {factor_key} not found, used FLIGHT_ECONOMY_LONG")
                
                factor_info = FACTORS[factor_key]
                co2e_kg = distance_km * factor_info['factor']
                
                result.update({
                    'scope': 'SCOPE_3',
                    'category': 'BUSINESS_TRAVEL_AIR',
                    'activity_description': f"Flight {origin}→{dest} ({travel_class}) — {employee}",
                    'activity_date': activity_date,
                    'location': f"{origin} → {dest}",
                    'quantity': round(distance_km, 1),
                    'unit': 'KM',
                    'quantity_original': float(dist_raw) if (dist_raw and dist_raw.replace('.', '').isdigit()) else distance_km,
                    'unit_original': 'KM',
                    'emission_factor': factor_info['factor'],
                    'emission_factor_source': f'DEFRA 2024 ({dist_source})',
                    'co2e_kg': round(co2e_kg, 4),
                    'is_suspicious': False,
                    'suspicious_reason': '',
                })
                
                if dist_source.startswith('calculated'):
                    result['parse_errors'].append(f"Distance calculated ({distance_km:.0f} km), not provided in source")
            
            elif category == 'HOTEL':
                nights_raw = col.get('nights') or col.get('duration') or '1'
                try:
                    nights = int(float(nights_raw))
                except Exception:
                    nights = 1
                    result['parse_errors'].append(f"Cannot parse nights '{nights_raw}', assumed 1")
                
                city = col.get('city') or col.get('location') or col.get('hotel_city', '')
                country = col.get('country') or col.get('hotel_country', 'IN')
                vendor = col.get('vendor') or col.get('hotel_name') or 'Unknown Hotel'
                
                factor_key = HOTEL_FACTOR_MAP.get(country.upper(), 'HOTEL_GLOBAL')
                factor_info = FACTORS[factor_key]
                co2e_kg = nights * factor_info['factor']
                
                result.update({
                    'scope': 'SCOPE_3',
                    'category': 'BUSINESS_TRAVEL_HOTEL',
                    'activity_description': f"Hotel: {vendor} — {city} ({nights} nights) — {employee}",
                    'activity_date': activity_date,
                    'location': f"{city}, {country}",
                    'quantity': float(nights),
                    'unit': 'NIGHT',
                    'quantity_original': float(nights),
                    'unit_original': 'NIGHT',
                    'emission_factor': factor_info['factor'],
                    'emission_factor_source': 'DEFRA 2024 (Hotel avg)',
                    'co2e_kg': round(co2e_kg, 4),
                    'is_suspicious': nights > 30,
                    'suspicious_reason': f'Hotel stay of {nights} nights is unusually long' if nights > 30 else '',
                })
            
            elif category == 'GROUND':
                dist_raw = col.get('distance_km') or col.get('distance') or ''
                amount_raw = col.get('amount') or col.get('transaction_amount') or '0'
                vendor = col.get('vendor') or col.get('transport_type') or 'Ground Transport'
                
                estimated = False
                if dist_raw and str(dist_raw).replace('.', '').isdigit():
                    distance_km = float(dist_raw)
                else:
                    # Estimate from amount — proxy method
                    try:
                        amount = float(amount_raw.replace(',', ''))
                        distance_km = amount / TAXI_RATE_INR_PER_KM
                        estimated = True
                    except Exception:
                        raise ValueError("No distance provided and cannot estimate from amount")
                
                # Classify ground transport type
                vendor_upper = vendor.upper()
                if 'TRAIN' in vendor_upper or 'RAIL' in vendor_upper:
                    factor_key = 'RAIL'
                elif 'BUS' in vendor_upper:
                    factor_key = 'BUS'
                elif 'RENTAL' in vendor_upper or 'HIRE' in vendor_upper:
                    factor_key = 'CAR_RENTAL'
                else:
                    factor_key = 'TAXI'
                
                factor_info = FACTORS[factor_key]
                co2e_kg = distance_km * factor_info['factor']
                
                result.update({
                    'scope': 'SCOPE_3',
                    'category': 'BUSINESS_TRAVEL_GROUND',
                    'activity_description': f"{vendor} — {distance_km:.0f} km {'(estimated)' if estimated else ''} — {employee}",
                    'activity_date': activity_date,
                    'location': col.get('city') or '',
                    'quantity': round(distance_km, 1),
                    'unit': 'KM',
                    'quantity_original': distance_km,
                    'unit_original': 'KM',
                    'emission_factor': factor_info['factor'],
                    'emission_factor_source': 'DEFRA 2024',
                    'co2e_kg': round(co2e_kg, 4),
                    'is_suspicious': estimated,
                    'suspicious_reason': 'Distance estimated from expense amount — verify with traveller' if estimated else '',
                })
            
            else:
                result['parse_status'] = 'SUSPICIOUS'
                result['parse_errors'].append(f"Unknown expense type: '{expense_type_raw}'. Skipped CO2 calculation.")
        
        except Exception as e:
            result['parse_status'] = 'FAILED'
            result['parse_errors'].append(str(e))
        
        results.append(result)
    
    return results
