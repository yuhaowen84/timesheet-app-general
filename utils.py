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
    # round to 5 decimals for parity with previous constants
    return {k: round(v, 5) for k, v in rates.items()}

# Keep a default set available (used if user doesn't customize)
rate_constants = build_rate_constants(DEFAULT_BASE_RATES)

NSW_PUBLIC_HOLIDAYS = {
    "2025-01-01", "2025-01-27", "2025-04-18", "2025-04-19", "2025-04-20", "2025-04-21",
    "2025-04-25", "2025-06-09", "2025-10-06", "2025-12-25", "2025-12-26"
}

# -------------------- parsing helpers -------------------- #
def parse_time(text: str):
    text = (text or "").strip()
    if not text:
        return None
    try:
        if ":" in text:
            return datetime.strptime(text, "%H:%M").time()
        if text.isdigit() and len(text) in [3, 4]:
            h, m = int(text[:-2]), int(text[-2:])
            return time(h, m)
    except:
        return None
    return None

def parse_duration(text: str) -> float:
    text = (text or "").strip()
    if not text:
        return 0
    try:
        if ":" in text:
            h, m = map(int, text.split(":"))
            return h + m / 60
        if text.isdigit():
            h, m = int(text[:-2]), int(text[-2:])
            return h + m / 60
    except:
        return 0
    return 0

# -------------------- main row calculation -------------------- #
def calculate_row(day, values, sick, penalty_value, special_value, unit_val, rates=None):
    """
    values: [rs_on, as_on, rs_off, as_off, worked, extra, (date_str optional as values[6])]
    unit_val: your existing 'Unit' value (already computed in Review_Calculations)
    rates: dict of rate constants; if None, use module default

    OT logic has TWO layers:

    1) "Daily OT"  = original behaviour using unit_val (extra over 8h etc.).
       - This runs when OT checkbox is NOT ticked.

    2) "OT shift"  = when OT checkbox is ticked, the whole worked day is
       treated as overtime at 150% / 200% / 250% (weekday / Saturday / Sunday).

    WOBOD (when WOBOD box ticked) = extra 50% ordinary * worked_hours
    on top of any OT shift pay.

    Afternoon/Night/Morning penalties, Special, Sick, Weekend loading are preserved.
    Daily Rate uses actual worked hours instead of a fixed 8 hours.
    """
    R = rates or rate_constants

    # Flags injected from Review_Calculations via:
    # rates={**rates, "OT": ot_enabled, "WOBOD": wobod_enabled}
    ot_shift_flag = R.get("OT", False)        # OT tickbox: treat whole shift as OT
    wobod_flag    = R.get("WOBOD", False)     # WOBOD tickbox

    rs_on = (values[0] or "").upper()

    # Worked hours = actual hours (or 8 if blank)
    worked_hours = parse_duration(values[4]) or 8
    ordinary = R["Ordinary Hours"]

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

    # ---------- BASE DAILY RATE (ordinary pay) ----------
    daily_rate = 0.0
    if rs_on not in ["OFF", "ADO"]:
        # base pay uses actual worked hours
        daily_rate = round(worked_hours * ordinary, 2)

    # ADO bonus (same as your original logic: +4h ordinary)
    if any((v or "").upper() == "ADO" for v in values):
        daily_rate += round(4 * ordinary, 2)

    # ---------- WEEKEND LOADING (on top of ordinary for Sat/Sun) ----------
    loading = 0.0
    if rs_on not in ["OFF", "ADO"]:
        if day == "Saturday":
            loading = round(worked_hours * R["Sat Loading 50%"], 2)
        elif day == "Sunday":
            loading = round(worked_hours * R["Sun Loading 100%"], 2)

    # ============================================================
    # 1) DAILY OT (original unit-based logic)  — only if NOT OT-shift
    # ============================================================
    ot_daily_pay = 0.0

    if not ot_shift_flag:
        if rs_on == "ADO" and unit_val >= 0:
            ot_daily_pay = round(unit_val * R["ADO Adjustment"], 2)

        elif rs_on not in ["OFF", "ADO"] and unit_val >= 0:
            # Regular daily OT: weekday 150%, Sat/Sun 200%
            if day in ["Saturday", "Sunday"]:
                ot_daily_pay = round(unit_val * R["OT 200%"], 2)
            else:
                ot_daily_pay = round(unit_val * R["OT 150%"], 2)

        else:
            # negative or OFF/ADO -> ordinary + applicable loading (your original fallbacks)
            if day == "Saturday":
                ot_daily_pay = round(unit_val * (R["Sat Loading 50%"] + ordinary), 2)
            elif day == "Sunday":
                ot_daily_pay = round(unit_val * (R["Sun Loading 100%"] + ordinary), 2)
            else:
                if penalty_value in ["Afternoon", "Morning"]:
                    ot_daily_pay = round(unit_val * (R["Afternoon Shift"] + ordinary), 2)
                elif penalty_value == "Night":
                    ot_daily_pay = round(unit_val * (R["Night Shift"] + ordinary), 2)
                else:
                    ot_daily_pay = round(unit_val * ordinary, 2)

    # ============================================================
    # 2) OT SHIFT PAY (tickbox: whole day at OT rate)
    # ============================================================
    ot_shift_pay = 0.0

    if ot_shift_flag and rs_on not in ["OFF", "ADO"]:
        # Multiplier based on day
        if day == "Sunday":
            mult = 2.5  # 250%
        elif day == "Saturday":
            mult = 2.0  # 200%
        else:
            mult = 1.5  # 150%

        # Whole worked day paid at OT rate:
        ot_shift_pay = round(worked_hours * ordinary * mult, 2)

        # In this OT-shift mode, we do NOT also pay ordinary/day loading for the same hours,
        # otherwise we double count. So suppress them:
        daily_rate = 0.0
        loading    = 0.0

    # ============================================================
    # 3) WOBOD — extra 50% ordinary * worked_hours on OT shift
    # ============================================================
    wobod_extra = 0.0
    if wobod_flag and ot_shift_flag and rs_on not in ["OFF", "ADO"]:
        wobod_extra = round(worked_hours * ordinary * 0.5, 2)

    # ============================================================
    # TOTALS
    # ============================================================
    # OT column shows ALL OT-related money (daily OT + OT shift + WOBOD)
    ot_total_for_column = ot_daily_pay + ot_shift_pay + wobod_extra

    daily_count = (
        ot_daily_pay +
        ot_shift_pay +
        wobod_extra +
        penalty_rate +
        special_loading +
        sick_rate +
        daily_rate +
        loading
    )

    return ot_total_for_column, penalty_rate, special_loading, sick_rate, daily_rate, loading, daily_count
