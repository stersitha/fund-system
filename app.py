import os
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Private Fund NAV Engine", layout="wide")

# ================== CONFIG ==================
DEFAULT_MER_ANNUAL = 0.06  # 6% / year

FUNDS = ["SCENQ (TQQQ)", "SCENB (BITU)", "SCENU (UPRO)", "SCENT (TECL)"]
FUND_MAP = {
    "SCENQ (TQQQ)": "SCENQ",
    "SCENB (BITU)": "SCENB",
    "SCENU (UPRO)": "SCENU",
    "SCENT (TECL)": "SCENT",
}

def inputs_file_for(fund_code: str) -> str:
    return f"nav_inputs_{fund_code}.csv"

def safe_read_csv(path: str) -> pd.DataFrame:
    if os.path.exists(path):
        df = pd.read_csv(path)
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"])
        return df
    return pd.DataFrame()

def safe_write_csv(df: pd.DataFrame, path: str) -> None:
    df.to_csv(path, index=False)

def normalize_inputs(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure required columns exist + proper types."""
    required_cols = [
        "Date",
        "Deposits",
        "Withdrawals",
        "Unrealized Performance $",
        "Realized Performance $",
        "Trading Costs",
    ]
    for c in required_cols:
        if c not in df.columns:
            df[c] = 0.0

    df = df[required_cols].copy()
    df["Date"] = pd.to_datetime(df["Date"])

    num_cols = required_cols[1:]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)

    df = df.sort_values("Date").drop_duplicates(subset=["Date"], keep="last").reset_index(drop=True)
    return df

def rebuild_nav_from_inputs(
    inputs_df: pd.DataFrame,
    initial_date: pd.Timestamp,
    initial_aum: float,
    initial_units: float,
    mer_annual: float,
) -> pd.DataFrame:
    """
    Rebuild full NAV history day-by-day (Excel-style).
    Logic (matches your written spec):
      - Initial AUM of each day = Final AUM of previous day
      - Deposits/Withdrawals mint/burn units at previous day's PPU(with MER)
      - Post Mov AUM = Initial AUM + net flow
      - Close Price per Unit (gross) = (Post Mov AUM + unrealized + realized - trading costs) / Units_end
      - Servicing Fee $ = (Close PPU * Post Mov AUM) * (MER/365)
      - Fee per unit = fee$ / Units_end
      - PPU with MER = Close PPU - fee_per_unit
      - Final AUM = PPU with MER * Units_end
    """
    if initial_units <= 0:
        raise ValueError("Initial Units must be > 0")

    mer_daily = mer_annual / 365.0

    # We create a calendar of NAV dates:
    # - Start with initial_date (first NAV line)
    # - Then append every input row date strictly >= initial_date
    inputs_df = normalize_inputs(inputs_df)
    inputs_df = inputs_df[inputs_df["Date"] >= initial_date].copy()

    # Build date list (initial date always included)
    dates = [pd.to_datetime(initial_date)]
    for d in inputs_df["Date"].tolist():
        if pd.to_datetime(d) not in dates:
            dates.append(pd.to_datetime(d))
    dates = sorted(dates)

    # Helper to fetch inputs for a date
    inputs_by_date = {pd.to_datetime(r["Date"]): r for _, r in inputs_df.iterrows()}

    rows = []

    # Day 0 setup
    prev_final_aum = float(initial_aum)
    prev_units = float(initial_units)
    prev_ppu_with_mer = float(initial_aum) / float(initial_units)  # usually 1.0

    for i, d in enumerate(dates):
        inp = inputs_by_date.get(d, None)

        deposits = float(inp["Deposits"]) if inp is not None else 0.0
        withdrawals = float(inp["Withdrawals"]) if inp is not None else 0.0
        unreal_d = float(inp["Unrealized Performance $"]) if inp is not None else 0.0
        real_d = float(inp["Realized Performance $"]) if inp is not None else 0.0
        trading_costs = float(inp["Trading Costs"]) if inp is not None else 0.0

        initial_aum_day = prev_final_aum
        initial_units_day = prev_units
        initial_ppu_day = prev_ppu_with_mer

        # Mint/Burn at previous day's PPU(with MER)
        units_to_mint = deposits / initial_ppu_day if deposits > 0 else 0.0
        units_to_burn = withdrawals / initial_ppu_day if withdrawals > 0 else 0.0
        net_units = units_to_mint - units_to_burn
        units_end = initial_units_day + net_units

        if units_end <= 0:
            raise ValueError(f"Units would be <= 0 on {d.date()} (check withdrawals).")

        net_flow = deposits - withdrawals
        post_mov_aum = initial_aum_day + net_flow

        # Gross AUM BEFORE fee (but after performance/costs)
        gross_aum = post_mov_aum + unreal_d + real_d - trading_costs

        close_ppu = gross_aum / units_end

        # Servicing fee (your formula)
        servicing_fee = (close_ppu * post_mov_aum) * mer_daily

        fee_per_unit = servicing_fee / units_end
        ppu_with_mer = close_ppu - fee_per_unit
        final_aum = ppu_with_mer * units_end

        # %s
        unreal_pct = (unreal_d / post_mov_aum) * 100.0 if post_mov_aum != 0 else 0.0
        real_pct = (real_d / post_mov_aum) * 100.0 if post_mov_aum != 0 else 0.0
        total_perf_pct = ((unreal_d + real_d) / post_mov_aum) * 100.0 if post_mov_aum != 0 else 0.0

        ppu_change = ppu_with_mer - initial_ppu_day
        aum_change = final_aum - initial_aum_day
        aum_change_pct = (aum_change / initial_aum_day) * 100.0 if initial_aum_day != 0 else 0.0

        rows.append({
            "Date": d,
            "Deposits": deposits,
            "Withdrawals": withdrawals,
            "Initial AUM": initial_aum_day,
            "Units to Mint": units_to_mint,
            "Units to Burn": units_to_burn,
            "Net Units": net_units,
            "Units": units_end,
            "Post Mov Aum": post_mov_aum,
            "Unrealized Performance $": unreal_d,
            "Unrealized Performance %": unreal_pct,
            "Realized Performance $": real_d,
            "Realized Performance %": real_pct,
            "Initial Price per Unit": initial_ppu_day,
            "Close Price per Unit": close_ppu,
            "Servicing Fee": servicing_fee,
            "Trading Costs": trading_costs,
            "Price per Unit with MER": ppu_with_mer,
            "PPU Change": ppu_change,
            "Final AUM": final_aum,
            "Total Performance %": total_perf_pct,
            "AUM_Change": aum_change,
            "AUM_Change_%": aum_change_pct,
        })

        # carry forward
        prev_final_aum = final_aum
        prev_units = units_end
        prev_ppu_with_mer = ppu_with_mer

    out = pd.DataFrame(rows).sort_values("Date").reset_index(drop=True)
    return out

# ================== UI ==================
st.title("Private Fund NAV Engine – Daily NAV & AUM Control")

fund_choice = st.selectbox("Select the fund:", FUNDS)
fund_code = FUND_MAP[fund_choice]
INPUTS_FILE = inputs_file_for(fund_code)

with st.sidebar:
    st.header("Settings")
    mer_annual = st.number_input("Servicing Fee (annual MER) — default 6%", min_value=0.0, max_value=1.0, value=float(DEFAULT_MER_ANNUAL), step=0.01)
    st.caption("Daily rate used = MER / 365")

st.write("""
This app calculates the daily NAV of your private fund using the same logic as your Excel model:

- Initial AUM of each day = Final AUM of the previous day
- Deposits / Withdrawals affect units (mint / burn), not NAV fairness
- Daily MER rate = 6% / 365 (editable in Settings)
- Servicing Fee = (Close Price per Unit × Post Mov Aum) × MER_DAILY_RATE
- Price per Unit with MER = Close Price per Unit − (Servicing Fee per Unit)
- Final AUM = Price per Unit with MER × Units
""")

# Load inputs
inputs_df = safe_read_csv(INPUTS_FILE)
inputs_df = normalize_inputs(inputs_df) if not inputs_df.empty else pd.DataFrame(columns=[
    "Date","Deposits","Withdrawals","Unrealized Performance $","Realized Performance $","Trading Costs"
])

# Store initial setup in session (per fund)
init_key = f"init_{fund_code}"
if init_key not in st.session_state:
    st.session_state[init_key] = {
        "initialized": False,
        "initial_date": None,
        "initial_aum": None,
        "initial_units": None,
    }

# Reset button
colA, colB = st.columns([1, 2])
with colA:
    if st.button("Reset (delete) ALL data for this fund"):
        if os.path.exists(INPUTS_FILE):
            os.remove(INPUTS_FILE)
        st.session_state[init_key] = {"initialized": False, "initial_date": None, "initial_aum": None, "initial_units": None}
        st.success("Reset done. Reloading…")
        st.rerun()

with colB:
    st.info(f"Current fund file: `{INPUTS_FILE}`")

# INITIAL SETUP
if not st.session_state[init_key]["initialized"]:
    st.subheader("Initial Setup – First NAV Day (Start Point)")

    st.write("""
This first line should represent the fund **right after the first deposit**, before any performance.
Tip to match your Excel:
- Set Initial AUM = Initial Units (so initial PPU = 1.00000)
- Do NOT re-enter the same deposit again as a 'Deposits' input on this same first day (or it will double count).
""")

    with st.form("initial_setup_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            initial_date = st.date_input("Initial NAV Date", value=pd.to_datetime("2025-10-21"))
        with c2:
            initial_aum = st.number_input("Initial AUM", min_value=0.0, value=10733.50, step=100.0)
        with c3:
            initial_units = st.number_input("Initial Units", min_value=0.000001, value=10733.50, step=100.0)

        ok = st.form_submit_button("Save Initial Setup")

    if ok:
        st.session_state[init_key] = {
            "initialized": True,
            "initial_date": pd.to_datetime(initial_date),
            "initial_aum": float(initial_aum),
            "initial_units": float(initial_units),
        }
        st.success("Initial setup saved. Now add daily inputs below.")
        st.rerun()

# MAIN (when initialized)
if st.session_state[init_key]["initialized"]:
    initial_date = pd.to_datetime(st.session_state[init_key]["initial_date"])
    initial_aum = float(st.session_state[init_key]["initial_aum"])
    initial_units = float(st.session_state[init_key]["initial_units"])

    st.subheader("Daily Inputs (Editable) — this is what you should edit")
    st.caption("Edit inputs, then click **Save inputs & Rebuild NAV**. The NAV table below is recomputed automatically from scratch.")

    # Add row helper
    with st.expander("Add a new day (optional helper)"):
        with st.form("add_day_form"):
            d = st.date_input("Date")
            c1, c2, c3 = st.columns(3)
            with c1:
                dep = st.number_input("Deposits", min_value=0.0, value=0.0, step=1000.0)
                wdr = st.number_input("Withdrawals", min_value=0.0, value=0.0, step=1000.0)
            with c2:
                unreal = st.number_input("Unrealized Performance $", value=0.0, step=1000.0)
                real = st.number_input("Realized Performance $", value=0.0, step=1000.0)
            with c3:
                tc = st.number_input("Trading Costs", value=0.0, step=100.0)
            add_ok = st.form_submit_button("Add/Update day in inputs")

        if add_ok:
            new = pd.DataFrame([{
                "Date": pd.to_datetime(d),
                "Deposits": float(dep),
                "Withdrawals": float(wdr),
                "Unrealized Performance $": float(unreal),
                "Realized Performance $": float(real),
                "Trading Costs": float(tc),
            }])
            inputs_df = pd.concat([inputs_df, new], ignore_index=True)
            inputs_df = normalize_inputs(inputs_df)
            safe_write_csv(inputs_df, INPUTS_FILE)
            st.success("Inputs updated. Rebuilding…")
            st.rerun()

    edited_inputs = st.data_editor(
        inputs_df,
        num_rows="dynamic",
        use_container_width=True,
        key=f"inputs_editor_{fund_code}"
    )

    if st.button("Save inputs & Rebuild NAV"):
        edited_inputs = normalize_inputs(pd.DataFrame(edited_inputs))
        safe_write_csv(edited_inputs, INPUTS_FILE)
        st.success("Saved inputs. Rebuilding NAV…")
        st.rerun()

    # Rebuild output
    try:
        nav_df = rebuild_nav_from_inputs(
            inputs_df=inputs_df,
            initial_date=initial_date,
            initial_aum=initial_aum,
            initial_units=initial_units,
            mer_annual=float(mer_annual),
        )
    except Exception as e:
        st.error(f"Rebuild error: {e}")
        st.stop()

    st.subheader("Rebuilt NAV (Computed) — do NOT edit here")
    st.dataframe(nav_df, use_container_width=True)

    # Quick last day summary
    last = nav_df.iloc[-1]
    st.markdown(f"""
**Latest NAV**
- Date: `{pd.to_datetime(last["Date"]).date()}`
- Final AUM: `{last["Final AUM"]:.2f}`
- Units: `{last["Units"]:.6f}`
- PPU with MER: `{last["Price per Unit with MER"]:.6f}`
- Servicing Fee: `{last["Servicing Fee"]:.6f}`
""")

    # Charts
    nav_chart = nav_df.copy()
    nav_chart["Date"] = pd.to_datetime(nav_chart["Date"])
    nav_chart = nav_chart.set_index("Date")

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("PPU with MER Over Time")
        st.line_chart(nav_chart["Price per Unit with MER"])
    with c2:
        st.subheader("Final AUM Over Time")
        st.line_chart(nav_chart["Final AUM"])
