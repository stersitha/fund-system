import streamlit as st
import pandas as pd
import os

# ================== CONFIG ==================

# Daily MER rate: 6% / 365
MER_DAILY_RATE = 0.06 / 365

# One CSV per asset
ASSET_FILES = {
    "SCENQ (TQQQ)": "nav_SCENQ.csv",
    "SCENB (BITU)": "nav_SCENB.csv",
    "SCENU (UPRO)": "nav_SCENU.csv",
    "SCENT (TECL)": "nav_SCENT.csv",
}

# ================== APP HEADER ==================

st.set_page_config(page_title="Scenium NAV Engine", layout="wide")

st.title("Private Fund NAV Engine – Daily NAV & AUM Control")

asset_label = st.sidebar.selectbox(
    "Select Asset",
    list(ASSET_FILES.keys()),
    index=0,
)

HISTORY_FILE = ASSET_FILES[asset_label]

st.caption(f"Current asset: **{asset_label}**  ·  File: `{HISTORY_FILE}`")

st.write(
    """
This app calculates the daily NAV of your private fund using a logic close to your Excel model:

- Initial AUM of each day = Final AUM of the previous day  
- Deposits / Withdrawals affect units (mint / burn), not AUM directly  
- Daily MER rate = 6% / 365  
- Servicing Fee is based on:  

  `Servicing Fee = (Close Price per Unit × Post Mov Aum) × MER_DAILY_RATE`  

- Price per Unit with MER = Close Price per Unit − (Servicing Fee per Unit)  
- Final AUM = Price per Unit with MER × Units
"""
)

# ================== LOAD HISTORY ==================

if os.path.exists(HISTORY_FILE) and os.path.getsize(HISTORY_FILE) > 0:
    history_df = pd.read_csv(HISTORY_FILE, parse_dates=["Date"])
    history_df = history_df.sort_values("Date")
else:
    history_df = pd.DataFrame()

# ================== INITIAL SETUP (FIRST DAY) ==================

if history_df.empty:
    st.subheader("Initial Setup – First NAV Day")

    st.write(
        """
This is the **technical first line** of your NAV history for this asset.

It should represent the fund **right after the first deposit**, already with the **daily fee applied**, but with **no performance yet**.

Usually:

- Date = first NAV date  
- Initial AUM = AUM after the first deposit  
- Initial Units = same value (so initial price per unit = 1.00000)
"""
    )

    with st.form("initial_setup"):
        init_date = st.date_input("Initial NAV Date")
        init_aum = st.number_input(
            "Initial AUM", min_value=0.0, value=10733.50, step=100.0
        )
        init_units = st.number_input(
            "Initial Units", min_value=0.000001, value=10733.50, step=100.0
        )

        submitted = st.form_submit_button("Create Initial NAV Row")

        if submitted:
            if init_units <= 0:
                st.error("Initial Units must be greater than zero.")
                st.stop()

            # ----- Base prices -----
            initial_ppu = init_aum / init_units

            # No extra flows on this first line
            net_flow = 0.0
            post_mov_aum = init_aum + net_flow  # = init_aum

            # No performance yet
            unreal_perf = 0.0
            realized_perf = 0.0
            trading_costs = 0.0

            gross_aum = init_aum + unreal_perf + realized_perf - trading_costs
            close_ppu = gross_aum / init_units  # = initial_ppu

            # Daily fee on the first day (this is what Excel does)
            servicing_fee = (close_ppu * post_mov_aum) * MER_DAILY_RATE
            fee_per_unit = servicing_fee / init_units
            price_with_mer = close_ppu - fee_per_unit
            final_aum = price_with_mer * init_units

            # Percentages (performance side is still 0)
            unreal_pct = 0.0
            realized_pct = 0.0
            total_perf_pct = 0.0

            aum_change = final_aum - init_aum
            aum_change_pct = (aum_change / init_aum * 100.0) if init_aum != 0 else 0.0

            ppu_change = price_with_mer - initial_ppu
            ppu_mer_change = ppu_change
            ppu_mer_change_pct = (
                ppu_mer_change / initial_ppu * 100.0 if initial_ppu != 0 else 0.0
            )

            data = {
                "Date": [pd.to_datetime(init_date)],
                "Initial AUM": [init_aum],
                "Deposits": [0.0],
                "Withdrawals": [0.0],
                "Units to Mint": [0.0],
                "Units to Burn": [0.0],
                "Net Units": [0.0],
                "Units": [init_units],
                "Post Mov Aum": [post_mov_aum],
                "Unrealized Performance $": [unreal_perf],
                "Unrealized Performance %": [unreal_pct],
                "Realized Performance $": [realized_perf],
                "Realized Performance %": [realized_pct],
                "Initial Price per Unit": [initial_ppu],
                "Close Price per Unit": [close_ppu],
                "Servicing Fee": [servicing_fee],
                "Trading Costs": [trading_costs],
                "Price per Unit with MER": [price_with_mer],
                "PPU Change": [ppu_change],
                "Final AUM": [final_aum],
                "Total Performance %": [total_perf_pct],
                "AUM_Change": [aum_change],
                "AUM_Change_%": [aum_change_pct],
                "PPU_MER_Change": [ppu_mer_change],
                "PPU_MER_Change_%": [ppu_mer_change_pct],
            }

            history_df = pd.DataFrame(data)
            history_df.to_csv(HISTORY_FILE, index=False)

            st.success(
                f"Initial NAV row created for **{asset_label}** and saved to `{HISTORY_FILE}`. "
                "Reload the app and then start adding the next days."
            )
            st.stop()

# If we arrive here, either there is history already, or we just loaded it
if not history_df.empty:
    st.subheader("Current NAV History (Latest 10 rows)")
    st.dataframe(history_df.tail(10))

# ================== DAILY NAV INPUT FORM ==================

st.subheader("New Daily NAV – Inputs")

if history_df.empty:
    st.info("No NAV history yet. Create the **Initial NAV** above first.")
else:
    last_row = history_df.sort_values("Date").iloc[-1]
    st.markdown(
        f"""
**Last NAV Day for {asset_label}:**

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

    unrealized_perf_d = st.number_input(
        "Unrealized Performance $", value=0.0, step=1000.0
    )
    realized_perf_d = st.number_input(
        "Realized Performance $", value=0.0, step=1000.0
    )
    trading_costs = st.number_input("Trading Costs", value=0.0, step=100.0)

    submitted_daily = st.form_submit_button("Calculate and Save NAV")

# ================== DAILY NAV CALCULATION ==================

if submitted_daily:
    if history_df.empty:
        st.error("No history found. Please create the initial NAV first.")
        st.stop()

    # Sort history and get last day
    history_df = history_df.sort_values("Date")
    last_row = history_df.iloc[-1]

    # ----- INITIAL VALUES FROM PREVIOUS DAY -----
    initial_aum = last_row["Final AUM"]
    initial_units = last_row["Units"]

    if initial_units == 0:
        st.error("Previous Units is zero. Cannot compute price per unit.")
        st.stop()

    initial_ppu = last_row["Price per Unit with MER"]

    # ----- FLOWS (MINT / BURN) -----
    net_flow = deposits - withdrawals

    units_to_mint = deposits / initial_ppu if deposits > 0 else 0.0
    units_to_burn = withdrawals / initial_ppu if withdrawals > 0 else 0.0
    net_units = units_to_mint - units_to_burn
    units_end = initial_units + net_units

    if units_end <= 0:
        st.error("Ending Units is zero or negative. Cannot compute NAV.")
        st.stop()

    # Post Mov Aum = Initial AUM +/- flows (base for fee & performance %)
    post_mov_aum = initial_aum + net_flow

    # ----- GROSS AUM BEFORE MER -----
    gross_aum = (
        initial_aum
        + unrealized_perf_d
        + realized_perf_d
        - trading_costs
    )

    close_ppu = gross_aum / units_end

    # Servicing Fee = (Close Price per Unit * Post Mov Aum) * daily MER rate
    servicing_fee = (close_ppu * post_mov_aum) * MER_DAILY_RATE

    fee_per_unit = servicing_fee / units_end
    price_with_mer = close_ppu - fee_per_unit

    final_aum = price_with_mer * units_end

    # ----- PERFORMANCE PERCENTAGES -----
    if post_mov_aum != 0:
        unrealized_perf_pct = (unrealized_perf_d / post_mov_aum) * 100.0
        realized_perf_pct = (realized_perf_d / post_mov_aum) * 100.0
        total_perf_pct = (
            (unrealized_perf_d + realized_perf_d) / post_mov_aum * 100.0
        )
    else:
        unrealized_perf_pct = 0.0
        realized_perf_pct = 0.0
        total_perf_pct = 0.0

    aum_change = final_aum - initial_aum
    aum_change_pct = (aum_change / initial_aum * 100.0) if initial_aum != 0 else 0.0

    ppu_change = price_with_mer - initial_ppu
    ppu_mer_change = ppu_change
    ppu_mer_change_pct = (
        ppu_mer_change / initial_ppu * 100.0 if initial_ppu != 0 else 0.0
    )

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

    st.success(f"NAV saved for **{asset_label}** into `{HISTORY_FILE}`.")

# ================== DASHBOARD + MANUAL EDIT ==================

if history_df.empty:
    st.info("No NAV history yet for this asset.")
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

    # --- Manual Corrections ---
    st.subheader("Manual NAV Corrections (Edit Mistakes)")

    st.write(
        """
Use this editor to fix mistakes such as:

- wrong dates  
- wrong Servicing Fee / performance values  
- rows that should not exist  

After editing, click **Save edited history**.
"""
    )

    edited_df = st.data_editor(
        history_sorted,
        num_rows="dynamic",
        key=f"nav_editor_{asset_label}",
    )

    if st.button("Save edited history"):
        try:
            edited_df["Date"] = pd.to_datetime(edited_df["Date"])
        except Exception:
            st.error("Could not parse Date column. Please use format YYYY-MM-DD.")
            st.stop()

        edited_df = edited_df.sort_values("Date")
        edited_df.to_csv(HISTORY_FILE, index=False)

        st.success(
            f"Edited NAV history for **{asset_label}** saved. Reload the page to see the updated table."
        )
