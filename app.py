import streamlit as st
import pandas as pd
import os

# ================== CONFIG ==================

MER_DAILY_RATE = 0.06 / 365  # 6% / 365 = 0.00016438356...
FUNDS = ["SCENQ (TQQQ)", "SCENB (BITU)", "SCENU (UPRO)", "SCENT (TECL)"]

FUND_MAP = {
    "SCENQ (TQQQ)": "nav_history_SCENQ.csv",
    "SCENB (BITU)": "nav_history_SCENB.csv",
    "SCENU (UPRO)": "nav_history_SCENU.csv",
    "SCENT (TECL)": "nav_history_SCENT.csv",
}

REQUIRED_INPUT_COLS = [
    "Date",
    "Deposits",
    "Withdrawals",
    "Unrealized Performance $",
    "Realized Performance $",
    "Trading Costs",
]

# ================== HELPERS ==================

def safe_float(x, default=0.0):
    try:
        if pd.isna(x):
            return default
        return float(x)
    except Exception:
        return default

def ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    # ensure all columns exist (inputs + outputs)
    cols = [
        "Date",
        "Deposits",
        "Withdrawals",
        "Initial AUM",
        "Units to Mint",
        "Units to Burn",
        "Net Units",
        "Units",
        "Post Mov Aum",
        "Unrealized Performance $",
        "Unrealized Performance %",
        "Realized Performance $",
        "Realized Performance %",
        "Initial Price per Unit",
        "Close Price per Unit",
        "Servicing Fee",
        "Trading Costs",
        "Price per Unit with MER",
        "PPU Change",
        "Final AUM",
    ]
    for c in cols:
        if c not in df.columns:
            df[c] = pd.NA
    return df

def normalize_dates(df: pd.DataFrame) -> pd.DataFrame:
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    return df

def recalc_from_inputs(inputs_df: pd.DataFrame, init_date, init_aum, init_units) -> pd.DataFrame:
    """
    Recalculate the entire NAV history sequentially, using Excel-like logic.

    Day 1 (initial day):
    - Units = init_units
    - Initial AUM = init_aum
    - Initial PPU = init_aum / init_units (usually 1.0)
    - Close PPU = Initial PPU (no performance unless user sets it)
    - Servicing Fee = (Close PPU * Initial AUM) * MER_DAILY_RATE
    - Price with MER = Close PPU - (Fee / Units)
    - Final AUM = Price with MER * Units

    Next days:
    - Initial AUM = prior Final AUM
    - Initial PPU = prior Price with MER
    - Units are adjusted only by mint/burn using Initial PPU
    - Gross AUM = Initial AUM + unrealized + realized - trading_costs
    - Close PPU = Gross AUM / Units_end
    - Post Mov Aum = Initial AUM + (Deposits - Withdrawals)
    - Servicing Fee = (Close PPU * Post Mov Aum) * MER_DAILY_RATE
    - Price with MER = Close PPU - (Fee / Units_end)
    - Final AUM = Price with MER * Units_end
    """

    inputs_df = inputs_df.copy()
    inputs_df = normalize_dates(inputs_df)
    inputs_df = inputs_df.dropna(subset=["Date"])
    inputs_df = inputs_df.sort_values("Date")

    # Deduplicate by date: keep last row per date (user edits may create duplicates)
    inputs_df = inputs_df.groupby("Date", as_index=False).last()

    rows = []

    # --- DAY 1 row (initial) ---
    init_ppu = init_aum / init_units if init_units != 0 else 0.0
    day1_close_ppu = init_ppu  # by default, no performance in setup day
    day1_fee = (day1_close_ppu * init_aum) * MER_DAILY_RATE
    day1_price_with_mer = day1_close_ppu - (day1_fee / init_units if init_units != 0 else 0.0)
    day1_final_aum = day1_price_with_mer * init_units

    day1 = {
        "Date": pd.to_datetime(init_date),
        "Deposits": safe_float(inputs_df.loc[inputs_df["Date"] == pd.to_datetime(init_date), "Deposits"].values[0], 0.0)
                    if (pd.to_datetime(init_date) in set(inputs_df["Date"])) else 0.0,
        "Withdrawals": 0.0,
        "Initial AUM": init_aum,
        "Units to Mint": 0.0,
        "Units to Burn": 0.0,
        "Net Units": 0.0,
        "Units": init_units,
        "Post Mov Aum": init_aum,
        "Unrealized Performance $": 0.0,
        "Unrealized Performance %": 0.0,
        "Realized Performance $": 0.0,
        "Realized Performance %": 0.0,
        "Initial Price per Unit": init_ppu,
        "Close Price per Unit": day1_close_ppu,
        "Servicing Fee": day1_fee,
        "Trading Costs": 0.0,
        "Price per Unit with MER": day1_price_with_mer,
        "PPU Change": day1_price_with_mer - init_ppu,
        "Final AUM": day1_final_aum,
    }
    rows.append(day1)

    # --- Remove initial day from inputs (so we don't double-calc it) ---
    inputs_df = inputs_df[inputs_df["Date"] != pd.to_datetime(init_date)].copy()
    inputs_df = inputs_df.sort_values("Date")

    # --- Iterate subsequent days ---
    prev_final_aum = day1_final_aum
    prev_units = init_units
    prev_price_with_mer = day1_price_with_mer

    for _, r in inputs_df.iterrows():
        date = r["Date"]

        deposits = safe_float(r.get("Deposits", 0.0))
        withdrawals = safe_float(r.get("Withdrawals", 0.0))
        unreal = safe_float(r.get("Unrealized Performance $", 0.0))
        realized = safe_float(r.get("Realized Performance $", 0.0))
        trading_costs = safe_float(r.get("Trading Costs", 0.0))

        initial_aum = prev_final_aum
        initial_ppu = prev_price_with_mer
        initial_units = prev_units

        net_flow = deposits - withdrawals

        units_to_mint = deposits / initial_ppu if deposits > 0 and initial_ppu != 0 else 0.0
        units_to_burn = withdrawals / initial_ppu if withdrawals > 0 and initial_ppu != 0 else 0.0
        net_units = units_to_mint - units_to_burn
        units_end = initial_units + net_units

        if units_end <= 0:
            # invalid state; still record but avoid crash
            units_end = 0.0

        post_mov_aum = initial_aum + net_flow

        gross_aum = initial_aum + unreal + realized - trading_costs
        close_ppu = gross_aum / units_end if units_end != 0 else 0.0

        servicing_fee = (close_ppu * post_mov_aum) * MER_DAILY_RATE
        fee_per_unit = servicing_fee / units_end if units_end != 0 else 0.0
        price_with_mer = close_ppu - fee_per_unit

        final_aum = price_with_mer * units_end

        unreal_pct = (unreal / post_mov_aum) * 100.0 if post_mov_aum != 0 else 0.0
        realized_pct = (realized / post_mov_aum) * 100.0 if post_mov_aum != 0 else 0.0

        new_row = {
            "Date": date,
            "Deposits": deposits,
            "Withdrawals": withdrawals,
            "Initial AUM": initial_aum,
            "Units to Mint": units_to_mint,
            "Units to Burn": units_to_burn,
            "Net Units": net_units,
            "Units": units_end,
            "Post Mov Aum": post_mov_aum,
            "Unrealized Performance $": unreal,
            "Unrealized Performance %": unreal_pct,
            "Realized Performance $": realized,
            "Realized Performance %": realized_pct,
            "Initial Price per Unit": initial_ppu,
            "Close Price per Unit": close_ppu,
            "Servicing Fee": servicing_fee,
            "Trading Costs": trading_costs,
            "Price per Unit with MER": price_with_mer,
            "PPU Change": price_with_mer - initial_ppu,
            "Final AUM": final_aum,
        }

        rows.append(new_row)

        # update prevs
        prev_final_aum = final_aum
        prev_units = units_end
        prev_price_with_mer = price_with_mer

    out = pd.DataFrame(rows)
    out = ensure_columns(out)
    out = out.sort_values("Date")
    return out

def load_inputs_csv(file_path: str) -> pd.DataFrame:
    if os.path.exists(file_path):
        df = pd.read_csv(file_path)
        df = ensure_columns(df)
        df = normalize_dates(df)
        df = df.dropna(subset=["Date"])
        return df.sort_values("Date")
    return pd.DataFrame(columns=ensure_columns(pd.DataFrame()).columns)

def save_csv(df: pd.DataFrame, file_path: str):
    df = df.copy()
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
    df.to_csv(file_path, index=False)

# ================== UI ==================

st.title("Private Fund NAV Engine – Daily NAV & AUM Control")

fund_choice = st.selectbox("Select the fund:", FUNDS)
HISTORY_FILE = FUND_MAP[fund_choice]

st.write("""
This app calculates the daily NAV using your Excel-like logic:

- Initial AUM (day t) = Final AUM (day t-1)
- Deposits / Withdrawals affect Units (mint / burn), not AUM directly
- Daily MER rate = 6% / 365
- Servicing Fee = (Close Price per Unit × Post Mov Aum) × MER_DAILY_RATE
- Price per Unit with MER = Close Price per Unit − (Servicing Fee / Units)
- Final AUM = Price per Unit with MER × Units
""")

# ================== INITIAL SETTINGS (per fund) ==================

st.subheader("Fund Initialization (first NAV day)")
col1, col2, col3 = st.columns(3)
with col1:
    init_date = st.date_input("Initial NAV Date", value=pd.to_datetime("2025-10-21"))
with col2:
    init_aum = st.number_input("Initial AUM (base)", min_value=0.0, value=10733.50, step=100.0)
with col3:
    init_units = st.number_input("Initial Units", min_value=0.000001, value=10733.50, step=100.0)

st.caption("Tip: In your Excel sample, day 1 used Initial AUM = 10,733.50 and Units = 10,733.50 (so Initial PPU = 1.00000).")

# ================== LOAD + RECALC ==================

raw_df = load_inputs_csv(HISTORY_FILE)

# Keep only input columns editable; outputs are recalculated
if raw_df.empty:
    inputs_df = pd.DataFrame(columns=REQUIRED_INPUT_COLS)
else:
    # If file contains full history, reduce to required input columns for editing
    cols = ["Date"] + [c for c in REQUIRED_INPUT_COLS if c != "Date"]
    for c in cols:
        if c not in raw_df.columns:
            raw_df[c] = 0.0
    inputs_df = raw_df[cols].copy()
    inputs_df = normalize_dates(inputs_df)
    inputs_df = inputs_df.sort_values("Date")

# ================== ADD NEW DAY ==================

st.subheader("Add / Edit Daily Inputs (then Recalculate)")

with st.form("add_day"):
    dcol1, dcol2, dcol3 = st.columns(3)
    with dcol1:
        nav_date = st.date_input("NAV Date", value=pd.to_datetime("2025-10-22"))
    with dcol2:
        deposits = st.number_input("Deposits", min_value=0.0, value=0.0, step=1000.0)
    with dcol3:
        withdrawals = st.number_input("Withdrawals", min_value=0.0, value=0.0, step=1000.0)

    ucol1, ucol2, ucol3 = st.columns(3)
    with ucol1:
        unreal = st.number_input("Unrealized Performance $", value=0.0, step=100.0)
    with ucol2:
        realized = st.number_input("Realized Performance $", value=0.0, step=100.0)
    with ucol3:
        trading_costs = st.number_input("Trading Costs", value=0.0, step=10.0)

    overwrite = st.checkbox("Overwrite if this date already exists", value=True)
    submitted = st.form_submit_button("Save Inputs")

if submitted:
    nav_date_ts = pd.to_datetime(nav_date)

    # remove existing row same date if overwrite
    if overwrite and not inputs_df.empty:
        inputs_df = inputs_df[inputs_df["Date"] != nav_date_ts].copy()

    new_input = pd.DataFrame([{
        "Date": nav_date_ts,
        "Deposits": deposits,
        "Withdrawals": withdrawals,
        "Unrealized Performance $": unreal,
        "Realized Performance $": realized,
        "Trading Costs": trading_costs,
    }])

    inputs_df = pd.concat([inputs_df, new_input], ignore_index=True)
    inputs_df = normalize_dates(inputs_df).sort_values("Date")
    # Save inputs back into same file (we store full history, but we'll overwrite with recalculated outputs below)
    st.success("Inputs saved. Now click 'Recalculate & Save NAV' below.")

# ================== MANUAL EDIT TABLE (INPUTS) ==================

st.subheader("Manual Input Corrections (this WILL recalculate)")

st.write("""
Edit only the INPUTS below. Then click **Recalculate & Save NAV**.
This solves the problem you reported: changing a row must update all following days.
""")

edited_inputs = st.data_editor(
    inputs_df,
    num_rows="dynamic",
    key=f"inputs_editor_{fund_choice}",
)

# ================== ACTION BUTTONS ==================

colA, colB = st.columns(2)

with colA:
    if st.button("Recalculate & Save NAV"):
        edited_inputs = normalize_dates(edited_inputs)
        # Remove invalid dates
        edited_inputs = edited_inputs.dropna(subset=["Date"])
        # Recalculate full history
        full_history = recalc_from_inputs(
            edited_inputs,
            init_date=init_date,
            init_aum=init_aum,
            init_units=init_units
        )
        save_csv(full_history, HISTORY_FILE)
        st.success("Recalculated and saved successfully. Refresh the page to see updated outputs.")

with colB:
    if st.button("Reset history for this fund"):
        # wipe the CSV (start fresh)
        empty = pd.DataFrame(columns=ensure_columns(pd.DataFrame()).columns)
        save_csv(empty, HISTORY_FILE)
        st.success("History reset. Refresh the page and start again from the initial date.")

# ================== SHOW OUTPUTS ==================

st.subheader("Calculated NAV Output (read-only)")

calc_df = load_inputs_csv(HISTORY_FILE)
calc_df = ensure_columns(calc_df)
calc_df = normalize_dates(calc_df).sort_values("Date")

if calc_df.empty:
    st.info("No NAV history yet for this fund. Add inputs and click Recalculate.")
else:
    st.dataframe(calc_df)

    # Charts
    df_chart = calc_df.set_index("Date")

    if "Price per Unit with MER" in df_chart.columns:
        st.subheader("Price per Unit with MER")
        st.line_chart(df_chart["Price per Unit with MER"])

    if "Final AUM" in df_chart.columns:
        st.subheader("Final AUM")
        st.line_chart(df_chart["Final AUM"])
