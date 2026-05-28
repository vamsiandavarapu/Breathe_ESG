"""
Emission Factors — DEFRA 2024 / IEA 2023 values.

All factors are in kgCO2e per unit.
These are static for the prototype. In production, factors would be versioned
in a database table so you can recompute historical records when DEFRA publishes
updated values annually.

Sources:
- DEFRA 2024: https://www.gov.uk/government/collections/government-conversion-factors-for-company-reporting
- IEA 2023: India grid emission factor
- ICAO Carbon Emissions Calculator methodology for aviation
"""

FACTORS = {
    # ── Scope 1: Fuels (kgCO2e per litre unless noted) ──────────────────
    'DIESEL':          {'factor': 2.51,    'unit': 'LITRE', 'scope': 'SCOPE_1', 'category': 'STATIONARY_COMBUSTION'},
    'PETROL':          {'factor': 2.31,    'unit': 'LITRE', 'scope': 'SCOPE_1', 'category': 'MOBILE_COMBUSTION'},
    'LPG':             {'factor': 1.51,    'unit': 'LITRE', 'scope': 'SCOPE_1', 'category': 'STATIONARY_COMBUSTION'},
    'NATURAL_GAS':     {'factor': 2.04,    'unit': 'M3',    'scope': 'SCOPE_1', 'category': 'STATIONARY_COMBUSTION'},
    'HSD':             {'factor': 2.51,    'unit': 'LITRE', 'scope': 'SCOPE_1', 'category': 'STATIONARY_COMBUSTION'},  # High-Speed Diesel = Diesel
    'FURNACE_OIL':     {'factor': 3.18,    'unit': 'LITRE', 'scope': 'SCOPE_1', 'category': 'STATIONARY_COMBUSTION'},

    # ── Scope 2: Electricity ─────────────────────────────────────────────
    # India grid factor from CEA (Central Electricity Authority) 2023: 0.82 kgCO2e/kWh
    # Note: DEFRA uses UK grid (0.20733). For Indian clients, CEA is more appropriate.
    'ELECTRICITY_IN':  {'factor': 0.820,   'unit': 'KWH',   'scope': 'SCOPE_2', 'category': 'PURCHASED_ELECTRICITY'},
    'ELECTRICITY_UK':  {'factor': 0.20733, 'unit': 'KWH',   'scope': 'SCOPE_2', 'category': 'PURCHASED_ELECTRICITY'},
    'ELECTRICITY_US':  {'factor': 0.3860,  'unit': 'KWH',   'scope': 'SCOPE_2', 'category': 'PURCHASED_ELECTRICITY'},

    # ── Scope 3: Business Travel ─────────────────────────────────────────
    # Flights: kgCO2e per passenger-km (includes radiative forcing multiplier of 1.9x per DEFRA)
    'FLIGHT_ECONOMY_SHORT':   {'factor': 0.2554, 'unit': 'KM', 'scope': 'SCOPE_3', 'category': 'BUSINESS_TRAVEL_AIR'},
    'FLIGHT_ECONOMY_LONG':    {'factor': 0.1951, 'unit': 'KM', 'scope': 'SCOPE_3', 'category': 'BUSINESS_TRAVEL_AIR'},
    'FLIGHT_BUSINESS_SHORT':  {'factor': 0.3829, 'unit': 'KM', 'scope': 'SCOPE_3', 'category': 'BUSINESS_TRAVEL_AIR'},
    'FLIGHT_BUSINESS_LONG':   {'factor': 0.4290, 'unit': 'KM', 'scope': 'SCOPE_3', 'category': 'BUSINESS_TRAVEL_AIR'},
    'FLIGHT_FIRST_LONG':      {'factor': 0.5765, 'unit': 'KM', 'scope': 'SCOPE_3', 'category': 'BUSINESS_TRAVEL_AIR'},

    # Hotels: kgCO2e per room-night (DEFRA 2024, average global)
    'HOTEL_UK':        {'factor': 31.0,    'unit': 'NIGHT', 'scope': 'SCOPE_3', 'category': 'BUSINESS_TRAVEL_HOTEL'},
    'HOTEL_INDIA':     {'factor': 18.5,    'unit': 'NIGHT', 'scope': 'SCOPE_3', 'category': 'BUSINESS_TRAVEL_HOTEL'},
    'HOTEL_GLOBAL':    {'factor': 23.8,    'unit': 'NIGHT', 'scope': 'SCOPE_3', 'category': 'BUSINESS_TRAVEL_HOTEL'},

    # Ground transport: kgCO2e per km
    'TAXI':            {'factor': 0.1489, 'unit': 'KM', 'scope': 'SCOPE_3', 'category': 'BUSINESS_TRAVEL_GROUND'},
    'CAR_RENTAL':      {'factor': 0.1678, 'unit': 'KM', 'scope': 'SCOPE_3', 'category': 'BUSINESS_TRAVEL_GROUND'},
    'RAIL':            {'factor': 0.0354, 'unit': 'KM', 'scope': 'SCOPE_3', 'category': 'BUSINESS_TRAVEL_GROUND'},
    'BUS':             {'factor': 0.0782, 'unit': 'KM', 'scope': 'SCOPE_3', 'category': 'BUSINESS_TRAVEL_GROUND'},
}


# Airport coordinates for great-circle distance calculation
# Only including airports commonly used in Indian corporate travel
AIRPORTS = {
    'BOM': (19.0896, 72.8656),   # Mumbai
    'DEL': (28.5665, 77.1031),   # Delhi
    'BLR': (13.1986, 77.7066),   # Bangalore
    'HYD': (17.2403, 78.4294),   # Hyderabad
    'MAA': (12.9941, 80.1709),   # Chennai
    'CCU': (22.6520, 88.4463),   # Kolkata
    'LHR': (51.4775, -0.4614),   # London Heathrow
    'JFK': (40.6413, -73.7781),  # New York JFK
    'DXB': (25.2532, 55.3657),   # Dubai
    'SIN': (1.3644,  103.9915),  # Singapore
    'FRA': (50.0379, 8.5622),    # Frankfurt
    'NRT': (35.7720, 140.3929),  # Tokyo Narita
    'CDG': (49.0097, 2.5479),    # Paris CDG
    'SYD': (-33.9461, 151.1772), # Sydney
}


import math

def haversine_km(iata1: str, iata2: str) -> float:
    """
    Calculate great-circle distance between two airports using Haversine formula.
    Returns distance in km.
    
    Why Haversine? The Earth is a sphere. Straight-line Euclidean distance would
    be wrong for long distances. Haversine gives the shortest path on a sphere.
    
    DEFRA recommends multiplying by 1.08 to account for actual flight paths being
    longer than great-circle (routing, air traffic control, weather avoidance).
    """
    if iata1 not in AIRPORTS or iata2 not in AIRPORTS:
        return None

    lat1, lon1 = [math.radians(x) for x in AIRPORTS[iata1]]
    lat2, lon2 = [math.radians(x) for x in AIRPORTS[iata2]]

    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    R = 6371  # Earth radius in km
    great_circle = R * c
    
    # Apply DEFRA's 1.08 routing factor
    return round(great_circle * 1.08, 1)


def classify_flight(distance_km: float) -> str:
    """
    Short-haul: < 3700 km | Long-haul: >= 3700 km
    Based on DEFRA 2024 methodology.
    """
    return 'SHORT' if distance_km < 3700 else 'LONG'
