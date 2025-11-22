# utils.py (complete rewritten version)
import math
from datetime import datetime, timedelta, time

# ---------------------------------------------------------------
# BASE RATES (you can edit these from Home page)
# ---------------------------------------------------------------
DEFAULT_BASE_RATES = {
    "ordinary": 49.81842,
    "afternoon_penalty": 4.84,
    "night_penalty": 5.69,
}

def build_rate_constants(base):
    """Builds rate dict from user-provided base numbers."""
    ordinary = base["ordinary"]
    aft = base["afternoon_penalty"]
    night = base["night_penalty"]

    return {
        "Ordinary Hours": ordinary,

        # loading percentages (multipliers)
        "Night Loading %": night / ordinary,
        "Saturday Loading %": 0.5,
        "Sunday Loading %": 1.0,

        # OT multipliers
        "OT weekday %": 1.5,
        "OT sat %": 2.0,
        "OT sun %": 2.5,

        # WOBOD (50% extra)
        "WOBOD %": 0.5,
    }

rate_constants = build_rate_constants(DEFAULT_BASE_RATES)

NSW_PUBLIC_HOLIDAYS = {
    "2025-01-01", "2025-01-27", "2025-04-18",
    "2025-04-19", "2025-04-20", "2025-04-21",
    "2025-04-25", "2025-06-09", "2025-10-06",
    "2025-12-25", "2025-12-26"
}

# ---------------------------------------------------------------
# PARSING
# ---------------------------------------------------------------
def parse_time(text):
    text = (text or "").strip()
    if not text: return None
    try:
        if ":" in text:
            return datetime.strptime(text, "%H:%M").time()
        if text.isdigit() and len(text) in [3, 4]:
            h, m = int(text[:-2]), int(text[-2:])
            return time(h, m)
    except:
        return None
    return None

def parse_duration(text):
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

# ---------------------------------------------------------------
# SHIFT SPLITTING / CLASSIFICATION
# ---------------------------------------------------------------
def split_shift_by_midnight(start_dt, end_dt):
    """Split into segments that do not cross midnight."""
    segs = []
    cur = start_dt

    while cur.date() < end_dt.date():
        nxt = datetime.combine(cur.date() + timedelta(days=1), time(0,0))
        segs.append((cur, nxt))
        cur = nxt

    segs.append((cur, end_dt))
    return segs

def hours(a, b):
    return (b - a).total_seconds() / 3600

def classify_day(d):
    wd = d.weekday()  # Monday=0
    if wd == 5:  return "sat"
    if wd == 6:  return "sun"
    return "weekday"

def overlap(start_dt, end_dt, w_start, w_end):
    day = start_dt.date()
    ws = datetime.combine(day, w_start)
    we = datetime.combine(day, w_end)
    st = max(start_dt, ws)
    en = min(end_dt, we)
    if en <= st: return 0
    return hours(st, en)

NIGHT_START = time(18,0)
NIGHT_END   = time(23,59,59)

def calculate_shift_components(start_dt, end_dt):
    segs = split_shift_by_midnight(start_dt, end_dt)

    result = {
        "weekday": 0.0,
        "sat": 0.0,
        "sun": 0.0,
        "night": 0.0,
    }

    for s, e in segs:
        d = classify_day(s.date())
        h = hours(s, e)

        result[d] += h

        # night only on weekdays
        if d == "weekday":
            result["night"] += overlap(s, e, NIGHT_START, NIGHT_END)

    return result

# ---------------------------------------------------------------
# OVERTIME + WOBOD
# ---------------------------------------------------------------
def calculate_ot(start_dt, end_dt, rates, ot_enabled, wobod_enabled):
    if not ot_enabled:
        return {"ot_hours": 0, "ot_pay": 0, "wobod": 0}

    segs = split_shift_by_midnight(start_dt, end_dt)
    ord_rate = rates["Ordinary Hours"]

    ot_hours = 0
    ot_pay   = 0
    wobod    = 0

    for s, e in segs:
        h = hours(s, e)
        ot_hours += h
        d = classify_day(s.date())

        mult = rates[f"OT {d} %"]   # 1.5 / 2.0 / 2.5
        ot_pay += h * ord_rate * (mult - 1)

        if wobod_enabled:
            wobod += h * ord_rate * rates["WOBOD %"]

    return {"ot_hours": ot_hours, "ot_pay": ot_pay, "wobod": wobod}

# ---------------------------------------------------------------
# DAILY PAY ENGINE
# ---------------------------------------------------------------
def calculate_daily_pay(comp, rates, ot):
    ord_rate = rates["Ordinary Hours"]

    base = (
        comp["weekday"] * ord_rate +
        comp["sat"]     * ord_rate +
        comp["sun"]     * ord_rate
    )

    night = comp["night"] * ord_rate * rates["Night Loading %"]
    sat_ldg = comp["sat"] * ord_rate * rates["Saturday Loading %"]
    sun_ldg = comp["sun"] * ord_rate * rates["Sunday Loading %"]

    total = base + night + sat_ldg + sun_ldg + ot["ot_pay"] + ot["wobod"]
    return round(total, 2)

# ---------------------------------------------------------------
# WRAPPER FOR REVIEW PAGE
# ---------------------------------------------------------------
def calculate_row(day, values, sick, penalty, special, unit, rates):
    """Keeps your Review page working with new engine."""
    if values[0].upper() in ["OFF", "ADO"] or sick:
        return 0, 0, 0, 0, 0, 0, 0

    date_str = values[6]
    date = datetime.strptime(date_str, "%Y-%m-%d").date()

    AS_ON  = parse_time(values[1])
    AS_OFF = parse_time(values[3])

    a_start = datetime.combine(date, AS_ON)
    a_end = datetime.combine(date, AS_OFF)
    if AS_OFF < AS_ON:
        a_end += timedelta(days=1)

    comp = calculate_shift_components(a_start, a_end)

    ot = calculate_ot(
        a_start, a_end,
        rates,
        ot_enabled=True,
        wobod_enabled=True
    )

    daily = calculate_daily_pay(comp, rates, ot)

    return (
        ot["ot_hours"],
        0, 0, 0,      # penalty / special placeholder
        daily,
        daily,
        daily
    )
