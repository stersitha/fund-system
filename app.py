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
    st.subheader("Initial NAV Setup")

    with st.form("init_form"):
        init_date = st.date_input("Initial NAV Date")
        init_aum = st.number_input("Initial AUM", value=10000.00)
        init_units = st.number_input("Initial Units", value=10000.00)

        create_btn = st.form_submit_button("Create Initial NAV")

    if create_btn:
        ppu = init_aum / init_units

        df = pd.DataFrame([{
            "Date": pd.to_datetime(init_date),
            "Initial AUM": init_aum,
            "Deposits": 0.0,
            "Withdrawals": 0.0,
            "Units to Mint": 0.0,
            "Units to Burn": 0.0,
            "Net Units": 0.0,
            "Units": init_units,
            "Post Mov Aum": init_aum,
            "Unrealized Performance $": 0.0,
            "Unrealized Performance %": 0.0,
            "Realized Performance $": 0.0,
            "Realized Performance %": 0.0,
            "Initial Price per Unit": ppu,
            "Close Price per Unit": ppu,
            "Servicing Fee": 0.0,
            "Trading Costs": 0.0,
            "Price per Unit with MER": ppu,
            "PPU Change": 0.0,
            "Final AUM": init_aum,
        }])

        df.to_csv(csv_file, index=False)
        st.success("Initial NAV created! Reload the page.")
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
