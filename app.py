import streamlit as st
import pandas as pd
import os

st.set_page_config(page_title="Scenium NAV Engine", layout="wide")

# ======================================================
# CONFIG
# ======================================================

MER_DAILY_RATE = 0.06 / 365  # 6% anual / 365

ASSETS = {
    "SCENQ (TQQQ)": "nav_SCENQ.csv",
    "SCENB (BITU)": "nav_SCENB.csv",
    "SCENU (UPRO)": "nav_SCENU.csv",
    "SCENT (TECL)": "nav_SCENT.csv",
}

st.title("📊 Scenium Multi-Asset NAV Engine")

st.write("""
This system calculates daily NAV for **four independent assets**, using the same logic as your Excel model:

- Initial AUM of each day = Final AUM of the previous day  
- Deposits / Withdrawals mint or burn units  
- Servicing Fee = (Close Price Per Unit × Post Mov AUM) × MER_DAILY_RATE  
- Price per Unit with MER = Close Price – fee_per_unit  
- Final AUM = Price per Unit with MER × Units  

Each asset has **its own CSV file** stored separately.
""")

# ======================================================
# SELECT ASSET
# ======================================================

asset_selected = st.selectbox("Select Asset", list(ASSETS.keys()))
csv_file = ASSETS[asset_selected]

st.success(f"Active NAV File: **{csv_file}**")


# ======================================================
# LOAD HISTORY
# ======================================================

if os.path.exists(csv_file):
    history_df = pd.read_csv(csv_file, parse_dates=["Date"])
    history_df = history_df.sort_values("Date")
else:
    history_df = pd.DataFrame()


# ======================================================
# INITIAL SETUP
# ======================================================

if history_df.empty:
    st.subheader("Initial Setup – First NAV Day")

    st.write("""
This is the **first official NAV day** of the fund.

It should represent the fund **right after the first deposit**, and the Servicing Fee
will already be charged, just like in your Excel:

- Date = first NAV date
- Initial AUM = first AUM value (after subscription)
- Initial Units = same value (so initial price per unit = 1.00000)
""")

    with st.form("initial_setup"):
        init_date = st.date_input("Initial NAV Date")
        init_aum = st.number_input("Initial AUM", min_value=0.0, value=10733.50, step=100.0)
        init_units = st.number_input("Initial Units", min_value=0.000001, value=10733.50, step=100.0)

        submitted = st.form_submit_button("Create Initial NAV")

        if submitted:
            # Preço inicial por unidade (antes do MER)
            initial_ppu = init_aum / init_units

            # No primeiro dia não tem fluxo nem performance,
            # então o Post Mov Aum é igual ao Initial AUM
            post_mov_aum = init_aum

            # Gross AUM (antes do MER) = Initial AUM
            gross_aum = init_aum

            # Close PPU (antes do MER)
            close_ppu = gross_aum / init_units

            # Servicing Fee = (Close PPU × Post Mov Aum) × MER_DAILY_RATE
            servicing_fee = (close_ppu * post_mov_aum) * MER_DAILY_RATE

            # Fee por unidade e PPU com MER
            fee_per_unit = servicing_fee / init_units
            price_with_mer = close_ppu - fee_per_unit

            # Final AUM já com fee descontada
            final_aum = price_with_mer * init_units

            # Variações (performance continua 0 – fee não é performance)
            aum_change = final_aum - init_aum
            aum_change_pct = (aum_change / init_aum * 100.0) if init_aum != 0 else 0.0

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
                "Unrealized Performance $": [0.0],
                "Unrealized Performance %": [0.0],
                "Realized Performance $": [0.0],
                "Realized Performance %": [0.0],
                "Initial Price per Unit": [initial_ppu],
                "Close Price per Unit": [close_ppu],
                "Servicing Fee": [servicing_fee],
                "Trading Costs": [0.0],
                "Price per Unit with MER": [price_with_mer],
                "PPU Change": [0.0],
                "Final AUM": [final_aum],
                "Total Performance %": [0.0],
                "AUM_Change": [aum_change],
                "AUM_Change_%": [aum_change_pct],
                "PPU_MER_Change": [0.0],
                "PPU_MER_Change_%": [0.0],
            }

            history_df = pd.DataFrame(data)
            history_df.to_csv(HISTORY_FILE, index=False)
            st.success("Initial NAV created with Servicing Fee applied and saved to nav_history.csv. Please reload the app.")
            st.stop()


# ======================================================
# DAILY NAV INPUT FORM
# ======================================================

st.subheader("Enter New Daily NAV")

if not history_df.empty:
    last = history_df.iloc[-1]

    st.info(f"""
**Last NAV**
- Date: {last['Date'].date()}
- Final AUM: {last['Final AUM']:.2f}
- Units: {last['Units']:.6f}
- PPU with MER: {last['Price per Unit with MER']:.6f}
""")

with st.form("daily_form"):
    nav_date = st.date_input("NAV Date")
    deposits = st.number_input("Deposits", min_value=0.0, value=0.0)
    withdrawals = st.number_input("Withdrawals", min_value=0.0, value=0.0)
    unrealized = st.number_input("Unrealized Performance $", value=0.0)
    realized = st.number_input("Realized Performance $", value=0.0)
    trading_costs = st.number_input("Trading Costs", value=0.0)

    submit_daily = st.form_submit_button("Save NAV")


# ======================================================
# NAV CALCULATION
# ======================================================

if submit_daily:

    last = history_df.iloc[-1]

    initial_aum = last["Final AUM"]
    initial_units = last["Units"]
    initial_ppu = last["Price per Unit with MER"]

    # Mint / Burn
    units_mint = deposits / initial_ppu if deposits else 0
    units_burn = withdrawals / initial_ppu if withdrawals else 0
    net_units = units_mint - units_burn
    ending_units = initial_units + net_units

    post_mov_aum = initial_aum + (deposits - withdrawals)

    # Gross AUM
    gross_aum = initial_aum + unrealized + realized - trading_costs
    close_ppu = gross_aum / ending_units

    # Fee
    servicing_fee = (close_ppu * post_mov_aum) * MER_DAILY_RATE
    fee_per_unit = servicing_fee / ending_units
    ppu_with_mer = close_ppu - fee_per_unit

    final_aum = ppu_with_mer * ending_units

    # Build row
    new = {
        "Date": pd.to_datetime(nav_date),
        "Initial AUM": initial_aum,
        "Deposits": deposits,
        "Withdrawals": withdrawals,
        "Units to Mint": units_mint,
        "Units to Burn": units_burn,
        "Net Units": net_units,
        "Units": ending_units,
        "Post Mov Aum": post_mov_aum,
        "Unrealized Performance $": unrealized,
        "Unrealized Performance %": (unrealized / post_mov_aum * 100) if post_mov_aum else 0,
        "Realized Performance $": realized,
        "Realized Performance %": (realized / post_mov_aum * 100) if post_mov_aum else 0,
        "Initial Price per Unit": initial_ppu,
        "Close Price per Unit": close_ppu,
        "Servicing Fee": servicing_fee,
        "Trading Costs": trading_costs,
        "Price per Unit with MER": ppu_with_mer,
        "PPU Change": ppu_with_mer - initial_ppu,
        "Final AUM": final_aum,
    }

    history_df = pd.concat([history_df, pd.DataFrame([new])], ignore_index=True)
    history_df.to_csv(csv_file, index=False)

    st.success("NAV saved successfully!")


# ======================================================
# DASHBOARD + EDITOR
# ======================================================

if not history_df.empty:
    st.subheader("Full NAV History")
    st.dataframe(history_df)

    # NAV Chart
    st.line_chart(history_df.set_index("Date")["Price per Unit with MER"])

    # Editor
    st.subheader("Manual Edits")
    edited = st.data_editor(history_df, num_rows="dynamic", key="editor")

    if st.button("Save Changes"):
        edited.to_csv(csv_file, index=False)
        st.success("Changes saved! Refresh the page.")
