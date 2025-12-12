import streamlit as st
import pandas as pd
import os

# ================== CONFIG ==================
MER_DAILY_RATE = 0.06 / 365  # 6% / 365

FUNDS = ["SCENQ (TQQQ)", "SCENB (BITU)", "SCENU (UPRO)", "SCENT (TECL)"]
FUND_MAP = {
    "SCENQ (TQQQ)": "nav_history_SCENQ.csv",
    "SCENB (BITU)": "nav_history_SCENB.csv",
    "SCENU (UPRO)": "nav_history_SCENU.csv",
    "SCENT (TECL)": "nav_history_SCENT.csv",
}

st.set_page_config(page_title="NAV Engine", layout="wide")

st.title("Private Fund NAV Engine – Daily NAV & AUM Control")

fund_choice = st.selectbox("Select the fund:", FUNDS)
HISTORY_FILE = FUND_MAP[fund_choice]

st.write(
    """
This app calculates the daily NAV of your private fund using a logic close to your Excel model:

- Initial AUM of each day = Final AUM of the previous day
- Deposits / Withdrawals affect units (mint / burn), not AUM directly
- Daily MER rate = 6% / 365
- Servicing Fee = (Close Price per Unit × Post Mov Aum) × MER_DAILY_RATE
- Price per Unit with MER = Close Price per Unit − (Servicing Fee per Unit)
- Final AUM = Price per Unit with MER × Units
"""
)

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


def load_history(path: str) -> pd.DataFrame:
    if os.path.exists(path):
        df = pd.read_csv(path)
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"])
        return df.sort_values("Date").reset_index(drop=True)
    return pd.DataFrame(columns=REQUIRED_COLS)


def save_history(df: pd.DataFrame, path: str) -> None:
    df = df.sort_values("Date").reset_index(drop=True)
    df.to_csv(path, index=False)


def compute_day(
    last_final_aum: float,
    last_units: float,
    last_price_w_mer: float,
    deposits: float,
    withdrawals: float,
    unrealized_perf: float,
    realized_perf: float,
    trading_costs: float,
):
    # Initial AUM of the day = yesterday Final AUM
    initial_aum = float(last_final_aum)
    initial_ppu = float(last_price_w_mer)

    # Units mint/burn at INITIAL PPU (Excel style)
    units_to_mint = deposits / initial_ppu if deposits > 0 else 0.0
    units_to_burn = withdrawals / initial_ppu if withdrawals > 0 else 0.0
    net_units = units_to_mint - units_to_burn
    units_end = float(last_units) + net_units

    if units_end <= 0:
        raise ValueError("Ending Units is zero or negative. Check withdrawals / initial PPU.")

    net_flow = deposits - withdrawals
    post_mov_aum = initial_aum + net_flow

    # Gross AUM before MER (performance & costs)
    gross_aum = initial_aum + unrealized_perf + realized_perf - trading_costs

    # Close Price per Unit (before fee)
    close_ppu = gross_aum / units_end

    # Servicing Fee per Excel logic
    servicing_fee = (close_ppu * post_mov_aum) * MER_DAILY_RATE
    fee_per_unit = servicing_fee / units_end

    price_w_mer = close_ppu - fee_per_unit
    final_aum = price_w_mer * units_end

    # Performance %
    unrealized_pct = (unrealized_perf / post_mov_aum * 100.0) if post_mov_aum != 0 else 0.0
    realized_pct = (realized_perf / post_mov_aum * 100.0) if post_mov_aum != 0 else 0.0

    ppu_change = price_w_mer - initial_ppu

    return {
        "Initial AUM": initial_aum,
        "Deposits": deposits,
        "Withdrawals": withdrawals,
        "Units to Mint": units_to_mint,
        "Units to Burn": units_to_burn,
        "Net Units": net_units,
        "Units": units_end,
        "Post Mov Aum": post_mov_aum,
        "Unrealized Performance $": unrealized_perf,
        "Unrealized Performance %": unrealized_pct,
        "Realized Performance $": realized_perf,
        "Realized Performance %": realized_pct,
        "Initial Price per Unit": initial_ppu,
        "Close Price per Unit": close_ppu,
        "Servicing Fee": servicing_fee,
        "Trading Costs": trading_costs,
        "Price per Unit with MER": price_w_mer,
        "PPU Change": ppu_change,
        "Final AUM": final_aum,
    }


# ================== LOAD ==================
history_df = load_history(HISTORY_FILE)

# ================== INITIAL SETUP ==================
if history_df.empty:
    st.subheader("Initial Setup – First NAV Day (Day 1)")

    st.info(
        """
Day 1 will ALSO charge the daily servicing fee (MER) — matching your Excel behavior.
You set the initial Units. If you want PPU = 1.00000, use Units = Initial AUM.
"""
    )

    with st.form("initial_setup"):
        init_date = st.date_input("Initial NAV Date")
        init_aum = st.number_input("Initial AUM", min_value=0.0, value=10733.50, step=100.0)
        init_units = st.number_input("Initial Units", min_value=0.000001, value=10733.50, step=100.0)

        # Optional inputs day 1
        day1_realized = st.number_input("Day 1 Realized Performance $", value=0.0, step=100.0)
        day1_unrealized = st.number_input("Day 1 Unrealized Performance $", value=0.0, step=100.0)
        day1_trading_costs = st.number_input("Day 1 Trading Costs", value=0.0, step=50.0)

        submitted = st.form_submit_button("Create Day 1 (with MER fee)")

        if submitted:
            if init_units <= 0:
                st.error("Initial Units must be > 0.")
                st.stop()

            # Day 1 "previous day" is itself (we treat initial_ppu = init_aum/init_units)
            initial_ppu = init_aum / init_units

            # Day 1 uses zero deposits/withdrawals by definition in this setup.
            # Fee base: post_mov_aum = init_aum
            gross_aum = init_aum + day1_unrealized + day1_realized - day1_trading_costs
            close_ppu = gross_aum / init_units
            servicing_fee = (close_ppu * init_aum) * MER_DAILY_RATE
            price_w_mer = close_ppu - (servicing_fee / init_units)
            final_aum = price_w_mer * init_units

            row = {
                "Date": pd.to_datetime(init_date),
                "Deposits": 0.0,
                "Withdrawals": 0.0,
                "Initial AUM": float(init_aum),
                "Units to Mint": 0.0,
                "Units to Burn": 0.0,
                "Net Units": 0.0,
                "Units": float(init_units),
                "Post Mov Aum": float(init_aum),
                "Unrealized Performance $": float(day1_unrealized),
                "Unrealized Performance %": (day1_unrealized / init_aum * 100.0) if init_aum != 0 else 0.0,
                "Realized Performance $": float(day1_realized),
                "Realized Performance %": (day1_realized / init_aum * 100.0) if init_aum != 0 else 0.0,
                "Initial Price per Unit": float(initial_ppu),
                "Close Price per Unit": float(close_ppu),
                "Servicing Fee": float(servicing_fee),
                "Trading Costs": float(day1_trading_costs),
                "Price per Unit with MER": float(price_w_mer),
                "PPU Change": float(price_w_mer - initial_ppu),
                "Final AUM": float(final_aum),
            }

            history_df = pd.DataFrame([row], columns=REQUIRED_COLS)
            save_history(history_df, HISTORY_FILE)
            st.success(f"Day 1 created for {fund_choice}. Reload the app.")
            st.stop()

else:
    st.subheader("Current NAV History (Latest 10 days)")
    st.dataframe(history_df.tail(10), use_container_width=True)

# ================== NEW DAY FORM ==================
st.subheader("New Daily NAV – Inputs")

if not history_df.empty:
    last = history_df.sort_values("Date").iloc[-1]
    last_date = pd.to_datetime(last["Date"]).date()

    st.markdown(
        f"""
**Last NAV Day**
- Date: `{last_date}`
- Final AUM: `{float(last['Final AUM']):,.2f}`
- Units: `{float(last['Units']):,.6f}`
- Price per Unit with MER: `{float(last['Price per Unit with MER']):,.6f}`
"""
    )

    with st.form("daily_nav"):
        nav_date = st.date_input("NAV Date", value=pd.to_datetime(last_date) + pd.Timedelta(days=1))

        deposits = st.number_input("Deposits", min_value=0.0, value=0.0, step=1000.0)
        withdrawals = st.number_input("Withdrawals", min_value=0.0, value=0.0, step=1000.0)

        unrealized_perf = st.number_input("Unrealized Performance $", value=0.0, step=100.0)
        realized_perf = st.number_input("Realized Performance $", value=0.0, step=100.0)
        trading_costs = st.number_input("Trading Costs", value=0.0, step=50.0)

        submitted_daily = st.form_submit_button("Calculate and Save NAV")

    if submitted_daily:
        # Prevent duplicates (this was causing your “double day” bug)
        nav_date_dt = pd.to_datetime(nav_date)
        if (history_df["Date"].dt.date == nav_date_dt.date()).any():
            st.error("This date already exists in history. Fix it in Manual Corrections (edit/delete) first.")
            st.stop()

        try:
            computed = compute_day(
                last_final_aum=float(last["Final AUM"]),
                last_units=float(last["Units"]),
                last_price_w_mer=float(last["Price per Unit with MER"]),
                deposits=float(deposits),
                withdrawals=float(withdrawals),
                unrealized_perf=float(unrealized_perf),
                realized_perf=float(realized_perf),
                trading_costs=float(trading_costs),
            )
        except Exception as e:
            st.error(str(e))
            st.stop()

        new_row = {"Date": nav_date_dt, **computed}

        history_df = pd.concat([history_df, pd.DataFrame([new_row])], ignore_index=True)
        save_history(history_df, HISTORY_FILE)

        st.success(f"Saved {fund_choice} NAV for {nav_date_dt.date()}.")
        st.rerun()

# ================== DASHBOARD + MANUAL EDIT ==================
if not history_df.empty:
    st.subheader("Full NAV History")
    history_sorted = history_df.sort_values("Date").reset_index(drop=True)
    st.dataframe(history_sorted, use_container_width=True)

    st.subheader("Charts")
    df_chart = history_sorted.set_index("Date")
    st.line_chart(df_chart["Price per Unit with MER"])
    st.line_chart(df_chart["Final AUM"])

    st.subheader("Manual NAV Corrections (Edit Mistakes)")
    st.caption("You can edit values, fix wrong dates, or delete rows. Then click Save edited history.")

    edited_df = st.data_editor(
        history_sorted,
        num_rows="dynamic",
        use_container_width=True,
        key=f"editor_{fund_choice}",
    )

    if st.button("Save edited history"):
        try:
            edited_df["Date"] = pd.to_datetime(edited_df["Date"])
        except Exception:
            st.error("Could not parse Date. Use format YYYY-MM-DD.")
            st.stop()

        # Keep required columns (in case Streamlit added index columns)
        for c in REQUIRED_COLS:
            if c not in edited_df.columns:
                edited_df[c] = 0.0

        edited_df = edited_df[REQUIRED_COLS].sort_values("Date").reset_index(drop=True)
        save_history(edited_df, HISTORY_FILE)
        st.success("Saved. Reloading...")
        st.rerun()
