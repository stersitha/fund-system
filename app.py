import os
from datetime import timedelta

import pandas as pd
import streamlit as st

# ================== CONFIG ==================
MER_DAILY_RATE = 0.06 / 365  # 6% / 365

FUNDS = ["SCENQ (TQQQ)", "SCENB (BITU)", "SCENU (UPRO)", "SCENT (TECL)"]
FUND_MAP = {
    "SCENQ (TQQQ)": "nav_history_SCENQ.csv",
    "SCENB (BITU)": "nav_history_SCENB.csv",
    "SCENU (UPRO)": "nav_history_SCENU.csv",
    "SCENT (TECL)": "nav_history_SCENT.csv",
}

# ================== UI HEADER ==================
st.title("Private Fund NAV Engine – Daily NAV & AUM Control")

fund_choice = st.selectbox("Select the fund:", FUNDS)
HISTORY_FILE = FUND_MAP[fund_choice]

st.write(f"**Active fund:** {fund_choice}  |  **History file:** `{HISTORY_FILE}`")

st.write("""
This app follows your Excel logic:

- Initial AUM of each day = Final AUM of the previous day
- Deposits / Withdrawals affect units (mint / burn), not AUM directly
- Daily MER rate = 6% / 365
- Servicing Fee = (Close Price per Unit × Post Mov AUM) × MER_DAILY_RATE
- Price per Unit with MER = Close Price per Unit − (Servicing Fee per Unit)
- Final AUM = Price per Unit with MER × Units

Important:
- The FIRST DAY (seed) can charge Servicing Fee immediately (so Day 1 already has PPU < 1).
""")

# ================== HELPERS ==================
COLUMNS = [
    "Date",
    "Initial AUM",
    "Deposits",
    "Withdrawals",
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
    "Total Performance %",
    "AUM_Change",
    "AUM_Change_%",
    "PPU_MER_Change",
    "PPU_MER_Change_%",
]

def empty_history() -> pd.DataFrame:
    return pd.DataFrame(columns=COLUMNS)

def safe_read_history(path: str) -> pd.DataFrame:
    if os.path.exists(path):
        df = pd.read_csv(path, parse_dates=["Date"])
        # Ensure all expected columns exist
        for c in COLUMNS:
            if c not in df.columns:
                df[c] = 0.0
        df = df[COLUMNS].copy()
        df["Date"] = pd.to_datetime(df["Date"])
        return df.sort_values("Date")
    return empty_history()

def safe_write_history(df: pd.DataFrame, path: str) -> None:
    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date")
    df.to_csv(path, index=False)

# ================== LOAD HISTORY ==================
history_df = safe_read_history(HISTORY_FILE)

# ================== INITIAL SEED (DAY 1) ==================
if history_df.empty:
    st.subheader("Initial Setup – Seed / First NAV Day (charges Servicing Fee)")

    st.write("""
Use this when you are starting the fund history.

Recommended:
- Seed Units = Seed AUM (so initial Close PPU = 1.00000)
- No performance on Day 1 (unless you explicitly want)
- Servicing Fee is charged on Day 1
""")

    with st.form("seed_setup"):
        seed_date = st.date_input("Seed NAV Date")
        seed_aum = st.number_input("Seed AUM (USD)", min_value=0.0, value=10733.50, step=100.0)
        seed_units = st.number_input("Seed Units", min_value=0.000001, value=10733.50, step=100.0)

        seed_trading_costs = st.number_input("Trading Costs (Day 1)", value=0.0, step=100.0)
        seed_unrealized = st.number_input("Unrealized Performance $ (Day 1)", value=0.0, step=1000.0)
        seed_realized = st.number_input("Realized Performance $ (Day 1)", value=0.0, step=1000.0)

        create_seed = st.form_submit_button("Create Seed Day")

        if create_seed:
            if seed_units <= 0:
                st.error("Seed Units must be > 0.")
                st.stop()

            # Day 1 logic:
            initial_aum = seed_aum
            units_end = seed_units
            post_mov_aum = initial_aum  # no flows on seed row

            gross_aum = initial_aum + seed_unrealized + seed_realized - seed_trading_costs
            close_ppu = gross_aum / units_end

            servicing_fee = (close_ppu * post_mov_aum) * MER_DAILY_RATE
            fee_per_unit = servicing_fee / units_end
            price_with_mer = close_ppu - fee_per_unit
            final_aum = price_with_mer * units_end

            unrealized_pct = (seed_unrealized / post_mov_aum * 100.0) if post_mov_aum != 0 else 0.0
            realized_pct = (seed_realized / post_mov_aum * 100.0) if post_mov_aum != 0 else 0.0
            total_perf_pct = ((seed_unrealized + seed_realized) / post_mov_aum * 100.0) if post_mov_aum != 0 else 0.0

            new_row = {
                "Date": pd.to_datetime(seed_date),
                "Initial AUM": initial_aum,
                "Deposits": 0.0,
                "Withdrawals": 0.0,
                "Units to Mint": 0.0,
                "Units to Burn": 0.0,
                "Net Units": 0.0,
                "Units": units_end,
                "Post Mov Aum": post_mov_aum,
                "Unrealized Performance $": seed_unrealized,
                "Unrealized Performance %": unrealized_pct,
                "Realized Performance $": seed_realized,
                "Realized Performance %": realized_pct,
                "Initial Price per Unit": close_ppu,  # seed start PPU before MER
                "Close Price per Unit": close_ppu,
                "Servicing Fee": servicing_fee,
                "Trading Costs": seed_trading_costs,
                "Price per Unit with MER": price_with_mer,
                "PPU Change": 0.0,
                "Final AUM": final_aum,
                "Total Performance %": total_perf_pct,
                "AUM_Change": final_aum - initial_aum,
                "AUM_Change_%": ((final_aum - initial_aum) / initial_aum * 100.0) if initial_aum != 0 else 0.0,
                "PPU_MER_Change": price_with_mer - close_ppu,
                "PPU_MER_Change_%": ((price_with_mer - close_ppu) / close_ppu * 100.0) if close_ppu != 0 else 0.0,
            }

            history_df = pd.DataFrame([new_row], columns=COLUMNS)
            safe_write_history(history_df, HISTORY_FILE)
            st.success(f"Seed day created for {fund_choice}. Reload the app.")
            st.stop()

# ================== CURRENT HISTORY ==================
st.subheader("Current NAV History (Latest 10 days)")
st.dataframe(history_df.tail(10), use_container_width=True)

# ================== DAILY NAV INPUT FORM ==================
st.subheader("New Daily NAV – Inputs")

history_df = history_df.sort_values("Date")
last_row = history_df.iloc[-1]
last_date = pd.to_datetime(last_row["Date"]).date()

default_next_date = last_date + timedelta(days=1)

st.markdown(
    f"""
**Last NAV Day**
- Date: `{last_date}`
- Final AUM: `{float(last_row['Final AUM']):,.2f}`
- Units: `{float(last_row['Units']):,.6f}`
- Price per Unit with MER: `{float(last_row['Price per Unit with MER']):,.6f}`
"""
)

with st.form("daily_nav"):
    nav_date = st.date_input("NAV Date", value=default_next_date)
    deposits = st.number_input("Deposits", min_value=0.0, value=0.0, step=1000.0)
    withdrawals = st.number_input("Withdrawals", min_value=0.0, value=0.0, step=1000.0)

    unrealized_perf_d = st.number_input("Unrealized Performance $", value=0.0, step=1000.0)
    realized_perf_d = st.number_input("Realized Performance $", value=0.0, step=1000.0)
    trading_costs = st.number_input("Trading Costs", value=0.0, step=100.0)

    submitted_daily = st.form_submit_button("Calculate and Save NAV")

# ================== DAILY NAV CALCULATION ==================
if submitted_daily:
    nav_date_dt = pd.to_datetime(nav_date)

    # Prevent duplicates / out-of-order days
    if nav_date_dt <= pd.to_datetime(last_row["Date"]):
        st.error("NAV Date must be AFTER the last saved date (to avoid duplicates).")
        st.stop()

    initial_aum = float(last_row["Final AUM"])
    initial_units = float(last_row["Units"])
    initial_ppu = float(last_row["Price per Unit with MER"])

    if initial_units <= 0 or initial_ppu <= 0:
        st.error("Previous Units/PPU invalid (<= 0).")
        st.stop()

    # Flows only affect units (mint/burn)
    net_flow = deposits - withdrawals
    units_to_mint = deposits / initial_ppu if deposits > 0 else 0.0
    units_to_burn = withdrawals / initial_ppu if withdrawals > 0 else 0.0
    net_units = units_to_mint - units_to_burn
    units_end = initial_units + net_units

    if units_end <= 0:
        st.error("Ending Units is zero or negative.")
        st.stop()

    # Post Mov Aum is used as fee base in your Excel
    post_mov_aum = initial_aum + net_flow

    # AUM before MER does NOT include flows (Excel logic you described)
    gross_aum = initial_aum + unrealized_perf_d + realized_perf_d - trading_costs

    close_ppu = gross_aum / units_end

    servicing_fee = (close_ppu * post_mov_aum) * MER_DAILY_RATE
    fee_per_unit = servicing_fee / units_end
    price_with_mer = close_ppu - fee_per_unit
    final_aum = price_with_mer * units_end

    if post_mov_aum != 0:
        unrealized_perf_pct = (unrealized_perf_d / post_mov_aum) * 100.0
        realized_perf_pct = (realized_perf_d / post_mov_aum) * 100.0
        total_perf_pct = ((unrealized_perf_d + realized_perf_d) / post_mov_aum) * 100.0
    else:
        unrealized_perf_pct = realized_perf_pct = total_perf_pct = 0.0

    aum_change = final_aum - initial_aum
    aum_change_pct = (aum_change / initial_aum * 100.0) if initial_aum != 0 else 0.0

    ppu_change = price_with_mer - initial_ppu
    ppu_mer_change = price_with_mer - close_ppu
    ppu_mer_change_pct = (ppu_mer_change / close_ppu * 100.0) if close_ppu != 0 else 0.0

    new_row = {
        "Date": nav_date_dt,
        "Initial AUM": initial_aum,
        "Deposits": deposits,
        "Withdrawals": withdrawals,
        "Units to Mint": units_to_mint,
        "Units to Burn": units_to_burn,
        "Net Units": net_units,
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
        "Total Performance %": total_perf_pct,
        "AUM_Change": aum_change,
        "AUM_Change_%": aum_change_pct,
        "PPU_MER_Change": ppu_mer_change,
        "PPU_MER_Change_%": ppu_mer_change_pct,
    }

    history_df = pd.concat([history_df, pd.DataFrame([new_row])], ignore_index=True)
    history_df = history_df.sort_values("Date")
    safe_write_history(history_df, HISTORY_FILE)

    st.success("Daily NAV calculated and saved.")
    st.rerun()

# ================== DASHBOARD + MANUAL EDIT ==================
st.subheader("Full NAV History")
history_sorted = history_df.sort_values("Date")
st.dataframe(history_sorted, use_container_width=True)

st.subheader("Charts")
df_chart = history_sorted.set_index("Date")
if "Price per Unit with MER" in df_chart.columns:
    st.line_chart(df_chart["Price per Unit with MER"])
if "Final AUM" in df_chart.columns:
    st.line_chart(df_chart["Final AUM"])
if "Units" in df_chart.columns:
    st.line_chart(df_chart["Units"])

st.subheader("Manual NAV Corrections (Edit Mistakes)")
st.write("""
You can edit any cell (including **Servicing Fee**) and save.

Tip:
- If you want to match Excel exactly, edit **Date**, **Deposits**, **Withdrawals**, **Realized/Unrealized**, **Trading Costs**, and even **Servicing Fee** if needed.
""")

edited_df = st.data_editor(
    history_sorted,
    num_rows="dynamic",
    key=f"nav_editor_{fund_choice}",
    use_container_width=True
)

if st.button("Save edited history"):
    try:
        edited_df["Date"] = pd.to_datetime(edited_df["Date"])
    except Exception:
        st.error("Could not parse Date column. Use format YYYY-MM-DD.")
        st.stop()

    edited_df = edited_df.sort_values("Date")
    safe_write_history(edited_df, HISTORY_FILE)
    st.success("Edited history saved. Reloading…")
    st.rerun()
