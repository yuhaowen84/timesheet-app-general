# Home.py
import streamlit as st
from utils import build_rate_constants, DEFAULT_BASE_RATES

st.set_page_config(page_title="Timesheet Calculator", page_icon="🗓️", layout="wide")

st.title("🗓️ Timesheet Calculator")

# ---------- Quick Guide ----------
st.markdown("""
### How to use
1. **Set your rates (optional):** enter your *Ordinary*, *Afternoon penalty*, and *Night penalty* below.  
   - 💡 *Hint:* Open your latest payslip and look for **Ordinary rate** and **Afternoon penalty** (and **Night** if shown).
2. Go to **Enter Timesheet**. You'll enter **one day per screen** (14 days total).  
   - Use **Save Day** or **Save & Next** to move forward.  
   - **Sick / Off / ADO** checkboxes are available (precedence: **ADO** > **Sick/Off**).  
   - You can **Copy previous day** to speed things up.
3. Open **Review Calculations** to see your **total earnings** for the fortnight and a **detailed breakdown**.
""")

# ---------- Base-rate form ----------
st.subheader("Set Base Rates (optional)")
st.caption("Only three inputs are needed. All other rates are auto-derived using your existing multipliers.")

base = st.session_state.get("base_rates", DEFAULT_BASE_RATES.copy())

c1, c2, c3 = st.columns(3)
with c1:
    ordinary = c1.number_input("Ordinary rate (per hour, AUD)", min_value=0.0, value=float(base["ordinary"]), step=0.01, format="%.2f")
with c2:
    afternoon = c2.number_input("Afternoon penalty (per hour, AUD)", min_value=0.0, value=float(base["afternoon_penalty"]), step=0.01, format="%.2f")
with c3:
    night = c3.number_input("Night penalty (per hour, AUD)", min_value=0.0, value=float(base["night_penalty"]), step=0.01, format="%.2f")

if st.button("Save Rates"):
    new_base = {
        "ordinary": float(ordinary),
        "afternoon_penalty": float(afternoon),
        "night_penalty": float(night),
    }
    st.session_state["base_rates"] = new_base
    st.session_state["rate_constants"] = build_rate_constants(new_base)
    st.success("Rates saved. Calculations will use your custom rates.")

# Show current effective rates (read-only)
effective = st.session_state.get("rate_constants", build_rate_constants(base))
with st.expander("Show derived rates (read-only)"):
    st.json(effective)

# ---------- Progress snapshot (one-day-per-page entry) ----------
entries = st.session_state.get("entries", [])
done = 0
if entries:
    for r in entries:
        if any([r.get("rs_on"), r.get("as_on"), r.get("rs_off"), r.get("as_off"),
                r.get("worked"), r.get("extra"), r.get("sick"), r.get("off"), r.get("ado")]):
            done += 1
st.progress(done / 14 if entries else 0, text=f"Progress: {done}/14 days entered" if entries else "Progress: 0/14")

# Helpful page links
st.page_link("pages/1_Enter_Timesheet.py", label="➡️ Enter Timesheet (one day per page)")
st.page_link("pages/2_Review_Calculations.py", label="➡️ Review Calculations")
