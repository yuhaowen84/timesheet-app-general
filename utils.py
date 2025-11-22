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

# -------------------- internal helpers for OT / loading split -------------------- #
def _hours_between(a: datetime, b: datetime) -> float:
    return (b - a).total_seconds() / 3600.0

def _split_shift_by_midnight(start_dt: datetime, end_dt: datetime):
    """
    Split a shift into segments that don't cross midnight.
    Example: 2025-11-15 19:00 -> 2025-11-16 02:33
    becomes: [ (15th 19:00, 16th 00:00), (16th 00:00, 16th 02:33) ]
    """
    segments = []
    cur = start_dt
    while cur.date() < end_dt.date():
        midnight = datetime.combine(cur.date() + timedelta(days=1), time(0, 0))
        segments.append((cur, midnight))
        cur = midnight
    segments.append((cur, end_dt))
    return segments

def _ot_multiplier_for_day(day_index: int) -> float:
    """
    Monday=0 ... Sunday=6
    Weekday OT = 150%, Saturday = 200%, Sunday = 250%.
    """
    if day_index == 5:   # Saturday
        return 2.0
    if day_index == 6:   # Sunday
        return 2.5
    return 1.5           # Weekdays

# -------------------- main row calculation -------------------- #
def calculate_row(day, date_obj, values, sick, penalty_value, special_value, unit_val, rates=None):
    """
    day:       "Monday"..."Sunday"
    date_obj:  datetime.date for that row (from Review_Calculations)
    values:    [rs_on, as_on, rs_off, as_off, worked, extra, ...]
    unit_val:  your existing 'Unit' value (already computed in Review_Calculations)
    rates:     dict of rate constants; if None, use module default

    OT logic has TWO layers:

    1) Daily OT (unit-based, original behaviour) – runs when OT checkbox is NOT ticked.
    2) OT shift (OT checkbox ticked) – whole worked hours that day at OT%,
       split by actual day (Fri/Sat/Sun…) if the shift crosses midnight.

    WOBOD = extra 50% ordinary * worked_hours when OT shift + WOBOD checkbox.

    Weekend loading (Sat 50%, Sun 100%) is also split by midnight for non-OT shifts.
    Daily Rate uses actual worked hours, not fixed 8h.
    """
    R = rates or rate_constants

    # Flags injected from Review_Calculations via:
    # rates={**rates, "OT": ot_enabled, "WOBOD": wobod_enabled}
    ot_shift_flag = R.get("OT", False)        # OT tickbox → whole-day OT shift
    wobod_flag    = R.get("WOBOD", False)     # WOBOD tickbox

    rs_on = (values[0] or "").upper()

    # Worked hours = actual hours (or 8 if blank)
    worked_hours = parse_duration(values[4]) or 8
    ordinary = R["Ordinary Hours"]

    # Pre-parse actual shift times once (used for weekend loading & OT split)
    AS_ON  = parse_time(values[1])
    AS_OFF = parse_time(values[3])

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

    # ---------- WEEKEND LOADING (Sat 50% / Sun 100%), split over midnight if needed ----------
    loading = 0.0
    if rs_on not in ["OFF", "ADO"] and not ot_shift_flag:
        if AS_ON and AS_OFF and date_obj:
            start_dt = datetime.combine(date_obj, AS_ON)
            end_dt   = datetime.combine(date_obj, AS_OFF)
            if AS_OFF < AS_ON:
                end_dt += timedelta(days=1)

            segments = _split_shift_by_midnight(start_dt, end_dt)
            total_load = 0.0
            for s, e in segments:
                h = _hours_between(s, e)
                # Match your behaviour: round segment hours to 2 decimals
                h = round(h, 2)
                dow = s.weekday()  # 0=Mon ... 5=Sat, 6=Sun
                if dow == 5:      # Saturday
                    rate = R["Sat Loading 50%"]
                elif dow == 6:    # Sunday
                    rate = R["Sun Loading 100%"]
                else:
                    rate = 0.0
                total_load += h * rate
            loading = round(total_load, 2)
        else:
            # Fallback if we can't parse times/date: old behaviour
            if day == "Saturday":
                loading = round(worked_hours * R["Sat Loading 50%"], 2)
            elif day == "Sunday":
                loading = round(worked_hours * R["Sun Loading 100%"], 2)

    # ============================================================
    # 1) DAILY OT (original unit-based logic) — only if NOT OT-shift
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
    # 2) OT SHIFT PAY (tickbox: whole day at OT rate, split by date_obj)
    # ============================================================
    ot_shift_pay = 0.0

    if ot_shift_flag and rs_on not in ["OFF", "ADO"]:
        start_dt = end_dt = None

        if AS_ON and AS_OFF and date_obj:
            start_dt = datetime.combine(date_obj, AS_ON)
            end_dt   = datetime.combine(date_obj, AS_OFF)
            if AS_OFF < AS_ON:
                # crosses midnight → add 1 day
                end_dt += timedelta(days=1)

        if start_dt and end_dt:
            # Split at midnight, apply correct day-based OT% to each segment
            segments = _split_shift_by_midnight(start_dt, end_dt)
            total_ot = 0.0
            for s, e in segments:
                h = _hours_between(s, e)
                mult = _ot_multiplier_for_day(s.weekday())
                total_ot += h * ordinary * mult
            ot_shift_pay = round(total_ot, 2)
        else:
            # Fallback: treat entire worked_hours as being on 'day'
            if day == "Sunday":
                mult = 2.5
            elif day == "Saturday":
                mult = 2.0
            else:
                mult = 1.5
            ot_shift_pay = round(worked_hours * ordinary * mult, 2)

        # In OT-shift mode we suppress normal ordinary+weekend loading for these hours
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
