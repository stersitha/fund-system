import streamlit as st
import pandas as pd
import os
from datetime import timedelta

# ================== CONFIG ==================

# Daily MER rate: 6% / 365
MER_DAILY_RATE = 0.06 / 365

ASSETS = {
    "SCENQ (TQQQ)": "SCENQ",
    "SCENB (BITU)": "SCENB",
    "SCENU (UPRO)": "SCENU",
    "SCENT (TECL)": "SCENT",
}

st.set_page_config(page_title="Private Fund NAV Engine", layout="wide")

st.title("Private Fund NAV Engine – Daily NAV & AUM Control")

# ================== ASSET SELECTION ==================

asset_label = st.selectbox("Select Asset", list(ASSETS.keys()))
asset_code = ASSETS[asset_label]

HISTORY_FILE = f"nav_history_{asset_code}.csv"

st.caption(f"Current asset file: `{HISTORY_FILE}`")

st.write(
    """
This app follows your Excel-style daily NAV logic:

- Initial AUM (day t) = Final AUM (day t-1)
- Deposits / Withdrawals only affect units (mint / burn), not AUM directly
- Daily MER rate = 6% / 365
- Servicing Fee = (Close Price per Unit × Post Mov Aum) × MER_DAILY_RATE
- Price per Unit with MER = Close Price per Unit − (Servicing Fee per Unit)
- Final AUM = Price per Unit with MER × Units
"""
)

# ================== HELPERS ==================

EXPECTED_COLS = [
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

def safe_float(x, default=0.0):
    try:
        if pd.isna(x):
            return default
        return float(x)
    except Exception:
        return default

def load_history():
    if os.path.exists(HISTORY_FILE):
        df = pd.read_csv(HISTORY_FILE)
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"])
        df = df.sort_values("Date")
        return df
    return pd.DataFrame(columns=EXPECTED_COLS)

def save_history(df):
    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date")
    df.to_csv(HISTORY_FILE, index=False)

def delete_history_file():
    if os.path.exists(HISTORY_FILE):
        os.remove(HISTORY_FILE)

# ================== LOAD HISTORY ==================

history_df = load_history()

# ================== RESET (per asset) ==================

with st.expander("Admin / Reset (this asset only)", expanded=False):
    st.warning("This will delete ALL NAV history for the selected asset.")
    if st.button("Delete all history for this asset"):
        delete_history_file()
        st.success("History deleted. Refresh the page.")
        st.stop()

# ================== DAY 1 (FIRST NAV DAY) ==================

if history_df.empty:
    st.subheader("Day 1 – First NAV Day (Excel baseline)")

    st.write(
        """
Aqui é onde você faz a **primeira linha do seu Excel**, mas já fechando o dia com fee.

Para bater com o seu Excel do 10/21:
- Initial AUM = 10,733.50
- Units = 10,733.50
- Close Price per Unit = 1.00000
- Deposits/Withdrawals = 0 (porque a base já está “dentro” do AUM/Units)
- Unrealized/Realized/Trading = 0 (se for o caso)
"""
    )

    with st.form("first_day_form"):
        day1_date = st.date_input("Date (Day 1)")
        day1_initial_aum = st.number_input("Initial AUM", min_value=0.0, value=10733.50, step=1.0)
        day1_units = st.number_input("Units", min_value=0.000001, value=10733.50, step=1.0)
        day1_close_ppu = st.number_input("Close Price per Unit (before MER)", min_value=0.000001, value=1.0, step=0.00001)

        day1_trading_costs = st.number_input("Trading Costs", value=0.0, step=1.0)
        day1_unreal = st.number_input("Unrealized Performance $", value=0.0, step=1.0)
        day1_realized = st.number_input("Realized Performance $", value=0.0, step=1.0)

        submitted_day1 = st.form_submit_button("Create Day 1 (with fee)")

    if submitted_day1:
        # No flows in Day 1 baseline (to match your Excel style)
        deposits = 0.0
        withdrawals = 0.0

        initial_aum = day1_initial_aum
        units_end = day1_units

        if units_end <= 0:
            st.error("Units must be > 0.")
            st.stop()

        initial_ppu = initial_aum / units_end  # usually 1.0
        post_mov_aum = initial_aum  # no flows baseline

        # Gross AUM before MER (your model adds perf/costs inside the day)
        gross_aum = initial_aum + day1_unreal + day1_realized - day1_trading_costs

        # Close PPU (before MER) can be forced to match Excel baseline
        close_ppu = day1_close_ppu

        # Fee
        servicing_fee = (close_ppu * post_mov_aum) * MER_DAILY_RATE
        fee_per_unit = servicing_fee / units_end

        price_with_mer = close_ppu - fee_per_unit
        final_aum = price_with_mer * units_end

        # Percentages
        unreal_pct = (day1_unreal / post_mov_aum) * 100.0 if post_mov_aum != 0 else 0.0
        realized_pct = (day1_realized / post_mov_aum) * 100.0 if post_mov_aum != 0 else 0.0

        new_row = {
            "Date": pd.to_datetime(day1_date),
            "Deposits": deposits,
            "Withdrawals": withdrawals,
            "Initial AUM": initial_aum,
            "Units to Mint": 0.0,
            "Units to Burn": 0.0,
            "Net Units": 0.0,
            "Units": units_end,
            "Post Mov Aum": post_mov_aum,
            "Unrealized Performance $": day1_unreal,
            "Unrealized Performance %": unreal_pct,
            "Realized Performance $": day1_realized,
            "Realized Performance %": realized_pct,
            "Initial Price per Unit": initial_ppu,
            "Close Price per Unit": close_ppu,
            "Servicing Fee": servicing_fee,
            "Trading Costs": day1_trading_costs,
            "Price per Unit with MER": price_with_mer,
            "PPU Change": price_with_mer - initial_ppu,
            "Final AUM": final_aum,
        }

        history_df = pd.DataFrame([new_row], columns=EXPECTED_COLS)
        save_history(history_df)

        st.success("Day 1 created. Now you can add Day 2 and onward.")
        st.stop()

# ================== SHOW HISTORY ==================

st.subheader("NAV History (latest 10 rows)")
history_df = load_history()
st.dataframe(history_df.tail(10), use_container_width=True)

# ================== NEW DAILY NAV ==================

st.subheader("New Daily NAV – Inputs")

history_df = history_df.sort_values("Date")
last_row = history_df.iloc[-1]
last_date = pd.to_datetime(last_row["Date"]).date()

# Default next date = last_date + 1 day (prevents duplicates)
default_next_date = last_date + timedelta(days=1)

st.markdown(
    f"""
**Last NAV Day**
- Date: `{last_date}`
- Final AUM: `{safe_float(last_row['Final AUM']):,.2f}`
- Units: `{safe_float(last_row['Units']):,.6f}`
- Price per Unit with MER: `{safe_float(last_row['Price per Unit with MER']):,.6f}`
"""
)

with st.form("daily_nav_form"):
    nav_date = st.date_input("NAV Date", value=default_next_date)

    deposits = st.number_input("Deposits", min_value=0.0, value=0.0, step=100.0)
    withdrawals = st.number_input("Withdrawals", min_value=0.0, value=0.0, step=100.0)

    unrealized_perf_d = st.number_input("Unrealized Performance $", value=0.0, step=100.0)
    realized_perf_d = st.number_input("Realized Performance $", value=0.0, step=100.0)
    trading_costs = st.number_input("Trading Costs", value=0.0, step=10.0)

    submitted_daily = st.form_submit_button("Calculate and Save NAV")

if submitted_daily:
    # Prevent duplicate dates
    nav_dt = pd.to_datetime(nav_date)
    if (history_df["Date"].dt.date == nav_dt.date()).any():
        st.error("This date already exists in history. Please choose the next day.")
        st.stop()

    initial_aum = safe_float(last_row["Final AUM"])
    initial_units = safe_float(last_row["Units"])
    initial_ppu = safe_float(last_row["Price per Unit with MER"])

    if initial_units <= 0:
        st.error("Previous Units is zero. Cannot compute NAV.")
        st.stop()

    # Flows only affect units
    units_to_mint = deposits / initial_ppu if deposits > 0 else 0.0
    units_to_burn = withdrawals / initial_ppu if withdrawals > 0 else 0.0
    net_units = units_to_mint - units_to_burn
    units_end = initial_units + net_units

    if units_end <= 0:
        st.error("Ending Units is zero or negative.")
        st.stop()

    post_mov_aum = initial_aum + deposits - withdrawals

    # Gross AUM before MER
    gross_aum = initial_aum + unrealized_perf_d + realized_perf_d - trading_costs

    # Close price per unit (before MER)
    close_ppu = gross_aum / units_end

    # Fee
    servicing_fee = (close_ppu * post_mov_aum) * MER_DAILY_RATE
    fee_per_unit = servicing_fee / units_end

    # PPU with MER (Excel-style)
    price_with_mer = close_ppu - fee_per_unit

    # Final AUM
    final_aum = price_with_mer * units_end

    unreal_pct = (unrealized_perf_d / post_mov_aum) * 100.0 if post_mov_aum != 0 else 0.0
    realized_pct = (realized_perf_d / post_mov_aum) * 100.0 if post_mov_aum != 0 else 0.0

    new_row = {
        "Date": nav_dt,
        "Deposits": deposits,
        "Withdrawals": withdrawals,
        "Initial AUM": initial_aum,
        "Units to Mint": units_to_mint,
        "Units to Burn": units_to_burn,
        "Net Units": net_units,
        "Units": units_end,
        "Post Mov Aum": post_mov_aum,
        "Unrealized Performance $": unrealized_perf_d,
        "Unrealized Performance %": unreal_pct,
        "Realized Performance $": realized_perf_d,
        "Realized Performance %": realized_pct,
        "Initial Price per Unit": initial_ppu,
        "Close Price per Unit": close_ppu,
        "Servicing Fee": servicing_fee,
        "Trading Costs": trading_costs,
        "Price per Unit with MER": price_with_mer,
        "PPU Change": price_with_mer - initial_ppu,
        "Final AUM": final_aum,
    }

    history_df = pd.concat([history_df, pd.DataFrame([new_row])], ignore_index=True)
    history_df = history_df[EXPECTED_COLS]
    save_history(history_df)

    st.success("Daily NAV saved.")
    st.rerun()

# ================== MANUAL CORRECTIONS ==================

st.subheader("Manual NAV Corrections (Edit Mistakes)")

st.write(
    """
Aqui você pode corrigir:
- datas duplicadas
- realized/unrealized
- trading costs
- **servicing fee**
- qualquer valor que você precise ajustar pra bater com o Excel

Depois clique em **Save edited history**.
"""
)

history_df = load_history().sort_values("Date")
edited_df = st.data_editor(
    history_df,
    num_rows="dynamic",
    use_container_width=True,
    key=f"editor_{asset_code}",
)

if st.button("Save edited history"):
    try:
        edited_df["Date"] = pd.to_datetime(edited_df["Date"])
    except Exception:
        st.error("Could not parse Date column. Use YYYY-MM-DD format.")
        st.stop()

    # Ensure columns exist
    for c in EXPECTED_COLS:
        if c not in edited_df.columns:
            edited_df[c] = 0.0

    edited_df = edited_df[EXPECTED_COLS].sort_values("Date")
    save_history(edited_df)

    st.success("Saved. Refreshing...")
    st.rerun()
