import streamlit as st
import pandas as pd
import os

# ================== CONFIG ==================

MER_DAILY_RATE = 0.06 / 365

FUNDS = [
    "SCENQ (TQQQ)",
    "SCENB (BITU)",
    "SCENU (UPRO)",
    "SCENT (TECL)",
]

fund_map = {
    "SCENQ (TQQQ)": "nav_history_SCENQ.csv",
    "SCENB (BITU)": "nav_history_SCENB.csv",
    "SCENU (UPRO)": "nav_history_SCENU.csv",
    "SCENT (TECL)": "nav_history_SCENT.csv",
}

# ================== UI HEADER ==================

st.title("Private Fund NAV Engine – Daily NAV & AUM Control")

fund_choice = st.selectbox("Select the fund:", FUNDS)
HISTORY_FILE = fund_map[fund_choice]

st.write("""
This app calculates the daily NAV of your private fund using a logic aligned with your Excel model:

- Initial AUM of each day = Final AUM of the previous day
- Deposits / Withdrawals affect units (mint / burn), not AUM directly
- Daily MER rate = 6% / 365
- Servicing Fee = (Close Price per Unit × Post Mov Aum) × MER_DAILY_RATE
- Price per Unit with MER = Close Price per Unit − (Servicing Fee per Unit)
- Final AUM = Price per Unit with MER × Units
""")

# ================== HELPERS ==================

REQUIRED_COLS = [
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

def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    for c in REQUIRED_COLS:
        if c not in df.columns:
            df[c] = 0.0
    df["Date"] = pd.to_datetime(df["Date"])
    return df[REQUIRED_COLS].copy()

def load_history() -> pd.DataFrame:
    if os.path.exists(HISTORY_FILE):
        df = pd.read_csv(HISTORY_FILE)
        df = ensure_schema(df)
        df = df.sort_values("Date").reset_index(drop=True)
        return df
    return pd.DataFrame(columns=REQUIRED_COLS)

def save_history(df: pd.DataFrame) -> None:
    df = ensure_schema(df)
    df = df.sort_values("Date").reset_index(drop=True)
    df.to_csv(HISTORY_FILE, index=False)

# ================== LOAD HISTORY ==================

history_df = load_history()

# ================== INITIAL SETUP (DAY 1) ==================

if history_df.empty:
    st.subheader("Initial Setup – First NAV Day (Day 1)")

    st.write("""
This is your first day (Day 1).  
Here you input the initial deposit and the system will:

- Mint Units = Deposit / Initial PPU (usually 1.00000)
- Calculate servicing fee on Day 1
- Compute Final AUM and store the first row
""")

    with st.form("initial_setup"):
        init_date = st.date_input("Initial NAV Date")
        first_deposit = st.number_input("Deposit (Day 1)", min_value=0.0, value=10773.50, step=100.0)
        initial_aum = st.number_input("Initial AUM (Day 1 base)", min_value=0.0, value=10733.50, step=100.0)
        initial_ppu = st.number_input("Initial Price per Unit (PPU)", min_value=0.000001, value=1.00000, step=0.00001, format="%.5f")
        realized_perf_d = st.number_input("Realized Performance $ (Day 1)", value=0.0, step=100.0)
        unrealized_perf_d = st.number_input("Unrealized Performance $ (Day 1)", value=0.0, step=100.0)
        trading_costs = st.number_input("Trading Costs (Day 1)", value=0.0, step=10.0)

        submitted_init = st.form_submit_button("Create Day 1")

        if submitted_init:
            # Mint units from deposit at initial PPU
            units_to_mint = first_deposit / initial_ppu if first_deposit > 0 else 0.0
            units_end = units_to_mint  # Day 1 starts empty, after first deposit we have units
            post_mov_aum = initial_aum  # Excel shows '-' in day 1, but fee uses AUM base; we follow your base

            # Gross AUM before MER (based on initial AUM base + perf - costs)
            gross_aum = initial_aum + unrealized_perf_d + realized_perf_d - trading_costs
            close_ppu = gross_aum / units_end if units_end != 0 else initial_ppu

            servicing_fee = (close_ppu * post_mov_aum) * MER_DAILY_RATE
            fee_per_unit = servicing_fee / units_end if units_end != 0 else 0.0
            price_with_mer = close_ppu - fee_per_unit

            final_aum = price_with_mer * units_end
            ppu_change = price_with_mer - initial_ppu

            unrealized_perf_pct = (unrealized_perf_d / post_mov_aum) * 100.0 if post_mov_aum != 0 else 0.0
            realized_perf_pct = (realized_perf_d / post_mov_aum) * 100.0 if post_mov_aum != 0 else 0.0

            first_row = {
                "Date": pd.to_datetime(init_date),
                "Deposits": first_deposit,
                "Withdrawals": 0.0,
                "Initial AUM": initial_aum,
                "Units to Mint": units_to_mint,
                "Units to Burn": 0.0,
                "Net Units": units_to_mint,
                "Units": units_end,
                "Post Mov Aum": post_mov_aum,
                "Unrealized Performance $": unrealized_perf_d,
                "Unrealized Performance %": unrealized_perf_pct,
                "Realized Performance $": realized_perf_d,
                "Realized Performance %": realized_perf_pct,
                "Initial Price per Unit": initial_ppu,
                "Close Price per Unit": close_ppu,
                "Servicing Fee": servicing_fee,
                "Trading Costs": trading_costs,
                "Price per Unit with MER": price_with_mer,
                "PPU Change": ppu_change,
                "Final AUM": final_aum,
            }

            history_df = pd.DataFrame([first_row], columns=REQUIRED_COLS)
            save_history(history_df)
            st.success(f"Day 1 created for {fund_choice}. Reload the app.")
            st.stop()

else:
    st.subheader("Current NAV History (Latest 10 days)")
    st.dataframe(history_df.tail(10))

# ================== DAILY NAV INPUT FORM (DAY 2+) ==================

st.subheader("New Daily NAV – Inputs (Day 2+)")

if not history_df.empty:
    last_row = history_df.sort_values("Date").iloc[-1]
    st.markdown(
        f"""
**Last NAV Day:**

- Date: `{pd.to_datetime(last_row['Date']).date()}`
- Final AUM: `{float(last_row['Final AUM']):,.2f}`
- Units: `{float(last_row['Units']):,.6f}`
- Price per Unit with MER: `{float(last_row['Price per Unit with MER']):,.6f}`
"""
    )

with st.form("daily_nav"):
    nav_date = st.date_input("NAV Date (today)")
    deposits = st.number_input("Deposits", min_value=0.0, value=0.0, step=1000.0)
    withdrawals = st.number_input("Withdrawals", min_value=0.0, value=0.0, step=1000.0)
    unrealized_perf_d = st.number_input("Unrealized Performance $", value=0.0, step=1000.0)
    realized_perf_d = st.number_input("Realized Performance $", value=0.0, step=1000.0)
    trading_costs = st.number_input("Trading Costs", value=0.0, step=100.0)
    submitted_daily = st.form_submit_button("Calculate and Save NAV")

# ================== DAILY NAV CALCULATION ==================

# ================== DAILY NAV CALCULATION ==================

if submitted_daily:
    history_df = history_df.sort_values("Date")
    last_row = history_df.iloc[-1]

    # 1️⃣ Initial state
    initial_aum = last_row["Final AUM"]
    units_start = last_row["Units"]
    initial_ppu = last_row["Price per Unit with MER"]

    # 2️⃣ Flows → units only
    units_to_mint = deposits / initial_ppu if deposits > 0 else 0.0
    units_to_burn = withdrawals / initial_ppu if withdrawals > 0 else 0.0
    units_end = units_start + units_to_mint - units_to_burn

    # 3️⃣ Post-movement AUM (fee base)
    post_mov_aum = initial_aum + deposits - withdrawals

    # 4️⃣ Gross AUM (performance)
    gross_aum = (
        initial_aum
        + unrealized_perf_d
        + realized_perf_d
        - trading_costs
    )

    # 5️⃣ Close price before fee
    close_ppu = gross_aum / units_end

    # 6️⃣ Servicing fee (EXACT Excel logic)
    servicing_fee = close_ppu * post_mov_aum * MER_DAILY_RATE
    fee_per_unit = servicing_fee / units_end

    # 7️⃣ Final price & AUM
    price_with_mer = close_ppu - fee_per_unit
    final_aum = price_with_mer * units_end

# ================== MANUAL EDIT ==================

if not history_df.empty:
    st.subheader("Manual NAV Corrections (Edit Mistakes)")

    st.write("""
You can edit mistakes including Servicing Fee, dates, deposits, performances, etc.
- Click any cell to edit (including Date)
- You can delete rows
- Click 'Save edited history' to persist
""")

    edited_df = st.data_editor(
        history_df.sort_values("Date"),
        num_rows="dynamic",
        key=f"nav_editor_{fund_choice}"
    )

    if st.button("Save edited history"):
        try:
            edited_df["Date"] = pd.to_datetime(edited_df["Date"])
        except Exception:
            st.error("Could not parse Date column. Please use format YYYY-MM-DD.")
            st.stop()

        save_history(edited_df)
        st.success("Edited NAV history saved. Reload the page to see the updated table.")
