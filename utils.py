# utils.py
import math
from datetime import datetime, timedelta, time

# -------- Defaults (same structure as your original) --------
DEFAULT_BASE_RATES = {
    "ordinary": 49.81842,
    "afternoon_penalty": 4.84,
    "night_penalty": 5.69,
}

def build_rate_constants(base: dict):
    """
    Build the full rate table from three base inputs.
    Multipliers match your existing constants.
    """
    ordinary = base["ordinary"]
    aft = base["afternoon_penalty"]
    night = base["night_penalty"]

    rates = {
        # penalties (per-hour adders)
        "Afternoon Shift": aft,
        "Early Morning": aft,          # same as Afternoon in your app
        "Night Shift": night,
        "Special Loading": night,      # same as Night in your app

        # OT / loadings (multiples of ordinary)
        "OT 150%": ordinary * 1.5,
        "OT 200%": ordinary * 2.0,
        "ADO Adjustment": ordinary,
        "Sat Loading 50%": ordinary * 0.5,
        "Sun Loading 100%": ordinary * 1.0,
        "Public Holiday": ordinary,
        "PH Loading 50%": ordinary * 0.5,
        "PH Loading 100%": ordinary * 1.0,

        # other ordinary-based
        "Sick With MC": ordinary,
        "Ordinary Hours": ordinary,
    }
    # round to 5 decimals for parity with your previous constants
    return {k: round(v, 5) for k, v in rates.items()}

# Keep a default set available (used if user doesn't customize)
rate_constants = build_rate_constants(DEFAULT_BASE_RATES)

NSW_PUBLIC_HOLIDAYS = {
    "2025-01-01", "2025-01-27", "2025-04-18", "2025-04-19", "2025-04-20", "2025-04-21",
    "2025-04-25", "2025-06-09", "2025-10-06", "2025-12-25", "2025-12-26"
}

def parse_time(text: str):
    text = (text or "").strip()
    if not text: return None
    try:
        if ":" in text:
            return datetime.strptime(text, "%H:%M").time()
        if text.isdigit() and len(text) in [3,4]:
            h, m = int(text[:-2]), int(text[-2:])
            return time(h, m)
    except:
        return None
    return None

def parse_duration(text: str) -> float:
    text = (text or "").strip()
    if not text: return 0
    try:
        if ":" in text:
            h, m = map(int, text.split(":"))
            return h + m/60
        if text.isdigit():
            h, m = int(text[:-2]), int(text[-2:])
            return h + m/60
    except:
        return 0
    return 0

def calculate_row(day, values, sick, penalty_value, special_value, unit_val, rates=None):
    """
    values: [rs_on, as_on, rs_off, as_off, worked, extra, (date_str optional as values[6])]
    unit_val: your existing 'Unit' value (already computed in Review_Calculations)
    rates: dict of rate constants; if None, use module default

    Changes from your original:
    - Daily Rate now uses *actual worked hours* (or 8 if blank)
    - Weekend loading uses worked hours instead of hard-coded 8
    - OT only applied when rates["OT"] flag is True
    - WOBOD adds an extra 50% ordinary on OT hours when rates["WOBOD"] is True
    - Afternoon/Night/Morning penalty logic is preserved
    """
    R = rates or rate_constants

    # Flag coming from Review page (injected into rates)
    ot_flag = R.get("OT", False)
    wobod_flag = R.get("WOBOD", False)

    # Worked hours = the actual hours for this day (or 8 if blank)
    worked_hours = parse_duration(values[4]) or 8

    # ---------- OVERTIME (OT) + WOBOD ----------
    ot_rate = 0.0    # money in the "OT Rate" column
    wobod_extra = 0.0

    # Only if OT checkbox ticked, unit is positive, and not OFF/ADO
    if ot_flag and unit_val > 0 and values[0].upper() not in ["OFF", "ADO"]:
        # Decide OT multiplier based on day of week
        if day == "Sunday":
            multiplier = 2.5   # 250%
        elif day == "Saturday":
            multiplier = 2.0   # 200%
        else:
            multiplier = 1.5   # 150%

        # Interpret unit_val as OT hours
        ordinary = R["Ordinary Hours"]

        # OT component: (multiplier - 1) * ordinary * OT hours
        ot_rate = round(unit_val * ordinary * (multiplier - 1.0), 2)

        # WOBOD: extra 50% ordinary on OT hours
        if wobod_flag:
            wobod_extra = round(unit_val * ordinary * 0.5, 2)

    # ---------- PENALTY (Afternoon / Night / Morning) ----------
    penalty_hours = math.floor(worked_hours)
    penalty_rate = 0.0

    if penalty_value == "Afternoon":
        penalty_rate = round(penalty_hours * R["Afternoon Shift"], 2)
    elif penalty_value == "Night":
        penalty_rate = round(penalty_hours * R["Night Shift"], 2)
    elif penalty_value == "Morning":
        penalty_rate = round(penalty_hours * R["Early Morning"], 2)

    # ---------- SPECIAL LOADING ----------
    special_loading = round(R["Special Loading"], 2) if special_value == "Yes" else 0.0

    # ---------- SICK ----------
    sick_rate = round(8 * R["Sick With MC"], 2) if sick else 0.0

    # ---------- DAILY RATE (BASE PAY) ----------
    daily_rate = 0.0
    # OFF/ADO days don't get ordinary base here
    if values[0].upper() not in ["OFF", "ADO"]:
        # Use actual worked hours instead of fixed 8
        daily_rate = round(worked_hours * R["Ordinary Hours"], 2)

    # ADO adds an extra 4 hours of ordinary pay (same as your original)
    if any((v or "").upper() == "ADO" for v in values):
        daily_rate += round(4 * R["Ordinary Hours"], 2)

    # ---------- WEEKEND LOADING ----------
    loading = 0.0
    if values[0].upper() not in ["OFF", "ADO"]:
        if day == "Saturday":
            loading = round(worked_hours * R["Sat Loading 50%"], 2)
        elif day == "Sunday":
            loading = round(worked_hours * R["Sun Loading 100%"], 2)

    # ---------- TOTAL DAILY COUNT ----------
    # OT column shows OT + WOBOD
    ot_total_for_column = ot_rate + wobod_extra

    daily_count = (
        ot_rate +
        wobod_extra +
        penalty_rate +
        special_loading +
        sick_rate +
        daily_rate +
        loading
    )

    return ot_total_for_column, penalty_rate, special_loading, sick_rate, daily_rate, loading, daily_count
