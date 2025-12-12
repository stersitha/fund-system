# ================== CONFIG ==================

# Daily MER rate: 6% / 365
MER_DAILY_RATE = 0.06 / 365

HISTORY_FILE = "nav_history.csv"

st.title("Private Fund NAV Engine – Daily NAV & AUM Control")
fund_choice = st.selectbox(
    "Select the fund:",
    ["SCENQ (TQQQ)", "SCENB (BITU)", "SCENU (UPRO)", "SCENT (TECL)"]
)

# Map display name → filename
fund_map = {
    "SCENQ (TQQQ)": "nav_history_SCENQ.csv",
    "SCENB (BITU)": "nav_history_SCENB.csv",
    "SCENU (UPRO)": "nav_history_SCENU.csv",
    "SCENT (TECL)": "nav_history_SCENT.csv",
}

HISTORY_FILE = fund_map[fund_choice]

st.write("""
This app calculates the daily NAV of your private fund using a logic close to your Excel model:

- Initial AUM of each day = Final AUM of the previous day
- Deposits / Withdrawals affect units (mint / burn), not AUM directly
- Daily MER rate = 6% / 365
- Servicing Fee is based on:
  Servicing Fee = (Close Price per Unit × Post Mov Aum) × MER_DAILY_RATE
- Price per Unit with MER = Close Price per Unit − (Servicing Fee per Unit)
- Final AUM = Price per Unit with MER × Units
""")


# ================== LOAD HISTORY ==================

if os.path.exists(HISTORY_FILE):
    history_df = pd.read_csv(HISTORY_FILE, parse_dates=["Date"])
    history_df = history_df.sort_values("Date")
else:
    history_df = pd.DataFrame()


# ================== INITIAL SETUP ==================

if history_df.empty:
    st.subheader("Initial Setup – First NAV Day")

    st.write("""
This is the technical first line of your NAV history.

It should represent the fund right after the first deposit, before any fee or performance.
Usually:

- Date = first NAV date
- Initial AUM = first AUM value
- Initial Units = same value (so initial price per unit = 1.00000)
""")

    with st.form("initial_setup"):
        init_date = st.date_input("Initial NAV Date")
        init_aum = st.number_input("Initial AUM", min_value=0.0, value=10733.50, step=100.0)
        init_units = st.number_input("Initial Units", min_value=0.000001, value=10733.50, step=100.0)

        submitted = st.form_submit_button("Create Initial NAV")

        if submitted:
            initial_ppu = init_aum / init_units

            data = {
                "Date": [pd.to_datetime(init_date)],
                "Initial AUM": [init_aum],
                "Deposits": [0.0],
                "Withdrawals": [0.0],
                "Units to Mint": [0.0],
                "Units to Burn": [0.0],
                "Net Units": [0.0],
                "Units": [init_units],
                "Post Mov Aum": [init_aum],
                "Unrealized Performance $": [0.0],
                "Unrealized Performance %": [0.0],
                "Realized Performance $": [0.0],
                "Realized Performance %": [0.0],
                "Initial Price per Unit": [initial_ppu],
                "Close Price per Unit": [initial_ppu],
                "Servicing Fee": [0.0],
                "Trading Costs": [0.0],
                "Price per Unit with MER": [initial_ppu],
                "PPU Change": [0.0],
                "Final AUM": [init_aum],
                "Total Performance %": [0.0],
                "AUM_Change": [0.0],
                "AUM_Change_%": [0.0],
                "PPU_MER_Change": [0.0],
                "PPU_MER_Change_%": [0.0],
            }

            history_df = pd.DataFrame(data)
            history_df.to_csv(HISTORY_FILE, index=False)
            st.success("Initial NAV created and saved to nav_history.csv. Please reload the app.")
            st.stop()

else:
    st.subheader("Current NAV History (Latest 10 days)")
    st.dataframe(history_df.tail(10))


# ================== DAILY NAV INPUT FORM ==================

st.subheader("New Daily NAV – Inputs")

if not history_df.empty:
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

with st.form("daily_nav"):
    nav_date = st.date_input("NAV Date (today)")
    deposits = st.number_input("Deposits", min_value=0.0, value=0.0, step=1000.0)
    withdrawals = st.number_input("Withdrawals", min_value=0.0, value=0.0, step=1000.0)

    unrealized_perf_d = st.number_input("Unrealized Performance $", value=0.0, step=1000.0)
    realized_perf_d = st.number_input("Realized Performance $", value=0.0, step=1000.0)
    trading_costs = st.number_input("Trading Costs", value=0.0, step=100.0)

    submitted_daily = st.form_submit_button("Calculate and Save NAV")


# ================== DAILY NAV CALCULATION ==================

if submitted_daily:
    if history_df.empty:
        st.error("No history found. Please create the initial NAV first.")
        st.stop()

    history_df = history_df.sort_values("Date")
    last_row = history_df.iloc[-1]

    # Initial values from previous day
    initial_aum = last_row["Final AUM"]
    initial_units = last_row["Units"]

    if initial_units == 0:
        st.error("Previous Units is zero. Cannot compute price per unit.")
        st.stop()

    initial_ppu = last_row["Price per Unit with MER"]

    # Flows (mint / burn)
    net_flow = deposits - withdrawals

    units_to_mint = deposits / initial_ppu if deposits > 0 else 0.0
    units_to_burn = withdrawals / initial_ppu if withdrawals > 0 else 0.0
    net_units = units_to_mint - units_to_burn
    units_end = initial_units + net_units

    if units_end <= 0:
        st.error("Ending Units is zero or negative. Cannot compute NAV.")
        st.stop()

    # Post Mov Aum = Initial AUM +/- flows
    post_mov_aum = initial_aum + net_flow

    # Gross AUM before MER
    gross_aum = (
        initial_aum
        + unrealized_perf_d
        + realized_perf_d
        - trading_costs
    )

    # Close Price per Unit (before MER)
    close_ppu = gross_aum / units_end

    # Servicing Fee
    servicing_fee = (close_ppu * post_mov_aum) * MER_DAILY_RATE

    # Fee per unit and Price per Unit with MER
    fee_per_unit = servicing_fee / units_end
    price_with_mer = close_ppu - fee_per_unit

    # Final AUM
    final_aum = price_with_mer * units_end

    # Performance percentages
    if post_mov_aum != 0:
        unrealized_perf_pct = (unrealized_perf_d / post_mov_aum) * 100.0
        realized_perf_pct = (realized_perf_d / post_mov_aum) * 100.0
        total_perf_pct = ((unrealized_perf_d + realized_perf_d) / post_mov_aum) * 100.0
    else:
        unrealized_perf_pct = 0.0
        realized_perf_pct = 0.0
        total_perf_pct = 0.0

    # AUM change vs "Initial AUM" of the day
    aum_change = final_aum - initial_aum
    aum_change_pct = (aum_change / initial_aum * 100.0) if initial_aum != 0 else 0.0

    # PPU changes
    ppu_change = price_with_mer - initial_ppu

    prev_close_ppu = initial_ppu
    ppu_mer_change = price_with_mer - prev_close_ppu
    ppu_mer_change_pct = (
        (ppu_mer_change / prev_close_ppu * 100.0)
        if prev_close_ppu != 0
        else 0.0
    )

    # Build new row
    new_row = {
        "Date": pd.to_datetime(nav_date),
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
    history_df.to_csv(HISTORY_FILE, index=False)

    st.success("Daily NAV calculated and saved to nav_history.csv.")


# ================== DASHBOARD + MANUAL EDIT ==================

if history_df.empty:
    st.info("No NAV history yet. Create the initial NAV first.")
else:
    st.subheader("Full NAV History")
    history_sorted = history_df.sort_values("Date")
    st.dataframe(history_sorted)

    df_chart = history_sorted.set_index("Date")

    if "Price per Unit with MER" in df_chart.columns:
        st.subheader("Price per Unit with MER Over Time")
        st.line_chart(df_chart["Price per Unit with MER"])

    if "Final AUM" in df_chart.columns:
        st.subheader("Final AUM Over Time")
        st.line_chart(df_chart["Final AUM"])

    if "Units" in df_chart.columns:
        st.subheader("Units Over Time")
        st.line_chart(df_chart["Units"])

    if "Total Performance %" in df_chart.columns:
        st.subheader("Total Performance % Over Time")
        st.line_chart(df_chart["Total Performance %"])

    st.subheader("Manual NAV Corrections (Edit Mistakes)")

    st.write("""
You can use this table to fix mistakes such as:
- wrong dates (e.g. duplicated 2025-10-26)
- wrong performance values
- rows that should not exist

How to use:
- Click on a cell to edit its value (including the Date).
- Use the trash icon on the left to delete a row.
- When finished, click Save edited history below.
""")

    edited_df = st.data_editor(
        history_sorted,
        num_rows="dynamic",
        key="nav_editor"
    )

    if st.button("Save edited history"):
        try:
            edited_df["Date"] = pd.to_datetime(edited_df["Date"])
        except Exception:
            st.error("Could not parse Date column. Please use format YYYY-MM-DD.")
            st.stop()

        edited_df = edited_df.sort_values("Date")
        edited_df.to_csv(HISTORY_FILE, index=False)

        st.success("Edited NAV history saved. Reload the page to see the updated table.")

