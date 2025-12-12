import streamlit as st
import pandas as pd
import os

# ================== CONFIG ==================

# Daily MER rate: 6% / 365
MER_DAILY_RATE = 0.06 / 365

st.set_page_config(page_title="Private Fund NAV Engine", layout="wide")

st.title("Private Fund NAV Engine – Daily NAV & AUM Control")

fund_choice = st.selectbox(
    "Select the fund:",
    ["SCENQ (TQQQ)", "SCENB (BITU)", "SCENU (UPRO)", "SCENT (TECL)"]
)

fund_map = {
    "SCENQ (TQQQ)": "nav_history_SCENQ.csv",
    "SCENB (BITU)": "nav_history_SCENB.csv",
    "SCENU (UPRO)": "nav_history_SCENU.csv",
    "SCENT (TECL)": "nav_history_SCENT.csv",
}

HISTORY_FILE = fund_map[fund_choice]

st.write("""
This app calculates the daily NAV of your private fund using the same logic as your Excel model:

- Initial AUM of each day = Final AUM of the previous day
- Deposits / Withdrawals affect units (mint / burn), not AUM directly
- Daily MER rate = 6% / 365
- Servicing Fee = (Close Price per Unit × Post Mov Aum) × MER_DAILY_RATE
- Price per Unit with MER = Close Price per Unit − (Servicing Fee per Unit)
- Final AUM = Price per Unit with MER × Units
""")

# ================== HELPERS ==================

COLUMNS = [
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

def safe_float(x):
    try:
        if pd.isna(x):
            return 0.0
        return float(x)
    except Exception:
        return 0.0

def calc_nav_row(
    *,
    nav_date,
    deposits,
    withdrawals,
    unrealized_perf_d,
    realized_perf_d,
    trading_costs,
    prev_final_aum,
    prev_units,
    prev_price_with_mer,
):
    # Initial AUM of the day = previous Final AUM
    initial_aum = prev_final_aum
    initial_units = prev_units
    initial_ppu = prev_price_with_mer

    net_flow = deposits - withdrawals

    units_to_mint = deposits / initial_ppu if deposits > 0 else 0.0
    units_to_burn = withdrawals / initial_ppu if withdrawals > 0 else 0.0
    net_units = units_to_mint - units_to_burn
    units_end = initial_units + net_units

    if units_end <= 0:
        raise ValueError("Ending Units is zero or negative. Cannot compute NAV.")

    post_mov_aum = initial_aum + net_flow

    gross_aum = (
        initial_aum
        + unrealized_perf_d
        + realized_perf_d
        - trading_costs
    )

    close_ppu = gross_aum / units_end

    servicing_fee = (close_ppu * post_mov_aum) * MER_DAILY_RATE
    fee_per_unit = servicing_fee / units_end
    price_with_mer = close_ppu - fee_per_unit

    final_aum = price_with_mer * units_end

    if post_mov_aum != 0:
        unrealized_perf_pct = (unrealized_perf_d / post_mov_aum) * 100.0
        realized_perf_pct = (realized_perf_d / post_mov_aum) * 100.0
    else:
        unrealized_perf_pct = 0.0
        realized_perf_pct = 0.0

    ppu_change = price_with_mer - initial_ppu

    return {
        "Date": pd.to_datetime(nav_date),
        "Deposits": deposits,
        "Withdrawals": withdrawals,
        "Initial AUM": initial_aum,
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
    }

def load_history():
    if os.path.exists(HISTORY_FILE):
        df = pd.read_csv(HISTORY_FILE)
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"])
        for col in COLUMNS:
            if col not in df.columns:
                df[col] = 0.0
        df = df[COLUMNS].copy()
        df = df.sort_values("Date").reset_index(drop=True)
        return df
    return pd.DataFrame(columns=COLUMNS)

def save_history(df):
    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").reset_index(drop=True)
    df.to_csv(HISTORY_FILE, index=False)

history_df = load_history()

# ================== INITIAL SETUP (FIRST REAL NAV DAY WITH FEE) ==================

if history_df.empty:
    st.subheader("Initial Setup – First NAV Day (Fee is charged here)")

    st.info("""
This initial setup creates the FIRST real NAV day (not a technical row).
So the Servicing Fee WILL be charged on day 1, matching your Excel.
""")

    with st.form("initial_setup"):
        init_date = st.date_input("First NAV Date")
        init_deposit = st.number_input("Deposits (Day 1)", min_value=0.0, value=0.0, step=100.0)
        init_withdraw = st.number_input("Withdrawals (Day 1)", min_value=0.0, value=0.0, step=100.0)

        init_aum = st.number_input("Initial AUM (Day 1)", min_value=0.0, value=10733.50, step=100.0)
        init_units = st.number_input("Units (Day 1)", min_value=0.000001, value=10733.50, step=100.0)

        init_unreal = st.number_input("Unrealized Performance $ (Day 1)", value=0.0, step=100.0)
        init_realized = st.number_input("Realized Performance $ (Day 1)", value=0.0, step=100.0)
        init_trading = st.number_input("Trading Costs (Day 1)", value=0.0, step=10.0)

        submitted_init = st.form_submit_button("Create Day 1 NAV")

        if submitted_init:
            if init_units <= 0:
                st.error("Units must be > 0.")
                st.stop()

            # Day 1 initial price is AUM / Units (usually 1.00)
            initial_ppu = init_aum / init_units

            # We treat Day 1 as: previous day = same as day 1 opening baseline
            # so Initial AUM = init_aum, Units = init_units, Initial PPU = initial_ppu
            # and then apply deposits/withdrawals/performance/costs + fee.
            try:
                row = calc_nav_row(
                    nav_date=init_date,
                    deposits=float(init_deposit),
                    withdrawals=float(init_withdraw),
                    unrealized_perf_d=float(init_unreal),
                    realized_perf_d=float(init_realized),
                    trading_costs=float(init_trading),
                    prev_final_aum=float(init_aum),
                    prev_units=float(init_units),
                    prev_price_with_mer=float(initial_ppu),
                )
            except Exception as e:
                st.error(str(e))
                st.stop()

            history_df = pd.DataFrame([row], columns=COLUMNS)
            save_history(history_df)
            st.success(f"Day 1 NAV created for {fund_choice}. Reload the app.")
            st.stop()

# ================== CURRENT STATUS ==================

st.subheader("Current NAV History (Latest 10 days)")
st.dataframe(history_df.tail(10), use_container_width=True)

last_row = history_df.sort_values("Date").iloc[-1]
st.markdown(
    f"""
**Last NAV Day:**
- Date: `{last_row['Date'].date()}`
- Final AUM: `{last_row['Final AUM']:.2f}`
- Units: `{last_row['Units']:.6f}`
- Price per Unit with MER: `{last_row['Price per Unit with MER']:.6f}`
"""
)

# ================== DAILY NAV INPUT FORM ==================

st.subheader("New Daily NAV – Inputs")

with st.form("daily_nav"):
    nav_date = st.date_input("NAV Date")
    deposits = st.number_input("Deposits", min_value=0.0, value=0.0, step=1000.0)
    withdrawals = st.number_input("Withdrawals", min_value=0.0, value=0.0, step=1000.0)

    unrealized_perf_d = st.number_input("Unrealized Performance $", value=0.0, step=1000.0)
    realized_perf_d = st.number_input("Realized Performance $", value=0.0, step=1000.0)
    trading_costs = st.number_input("Trading Costs", value=0.0, step=100.0)

    submitted_daily = st.form_submit_button("Calculate and Save NAV")

if submitted_daily:
    try:
        new_row = calc_nav_row(
            nav_date=nav_date,
            deposits=float(deposits),
            withdrawals=float(withdrawals),
            unrealized_perf_d=float(unrealized_perf_d),
            realized_perf_d=float(realized_perf_d),
            trading_costs=float(trading_costs),
            prev_final_aum=safe_float(last_row["Final AUM"]),
            prev_units=safe_float(last_row["Units"]),
            prev_price_with_mer=safe_float(last_row["Price per Unit with MER"]),
        )
    except Exception as e:
        st.error(str(e))
        st.stop()

    # ---- IMPORTANT: Avoid duplicate date (overwrite instead of append) ----
    nav_dt = pd.to_datetime(nav_date)
    history_df["Date"] = pd.to_datetime(history_df["Date"])

    if (history_df["Date"] == nav_dt).any():
        history_df.loc[history_df["Date"] == nav_dt, :] = pd.DataFrame([new_row], columns=COLUMNS).values
        st.warning("Date already existed — row was overwritten (no duplicates).")
    else:
        history_df = pd.concat([history_df, pd.DataFrame([new_row], columns=COLUMNS)], ignore_index=True)

    save_history(history_df)
    st.success(f"Daily NAV saved for {fund_choice}.")

# ================== DASHBOARD ==================

st.subheader("Full NAV History")
history_sorted = history_df.sort_values("Date").reset_index(drop=True)
st.dataframe(history_sorted, use_container_width=True)

df_chart = history_sorted.set_index("Date")

c1, c2, c3 = st.columns(3)
with c1:
    st.subheader("Price per Unit with MER")
    st.line_chart(df_chart["Price per Unit with MER"])
with c2:
    st.subheader("Final AUM")
    st.line_chart(df_chart["Final AUM"])
with c3:
    st.subheader("Units")
    st.line_chart(df_chart["Units"])

# ================== MANUAL EDIT ==================

st.subheader("Manual NAV Corrections (Edit Mistakes)")

st.write("""
You can edit ANY column (including Servicing Fee) and fix wrong dates.
- Click cells to edit
- Delete rows
- Then press Save
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
        st.error("Could not parse Date column. Please use format YYYY-MM-DD.")
        st.stop()

    edited_df = edited_df.sort_values("Date").reset_index(drop=True)
    edited_df = edited_df[COLUMNS].copy()
    save_history(edited_df)
    st.success("Edited NAV history saved. Reload the page to see updates.")

# ================== EXPORT ==================

st.subheader("Export")
csv_bytes = history_sorted.to_csv(index=False).encode("utf-8")
st.download_button("Download CSV", data=csv_bytes, file_name=HISTORY_FILE, mime="text/csv")
