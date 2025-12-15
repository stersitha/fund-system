import streamlit as st
import pandas as pd
import os
import numpy as np

st.set_page_config(page_title="Private Fund NAV Engine", layout="wide")

# ================== CONFIG ==================
MER_DAILY_RATE_DEFAULT = 0.06 / 365  # 6% / 365

FUNDS = ["SCENQ (TQQQ)", "SCENB (BITU)", "SCENU (UPRO)", "SCENT (TECL)"]
FUND_MAP = {
    "SCENQ (TQQQ)": "nav_history_SCENQ.csv",
    "SCENB (BITU)": "nav_history_SCENB.csv",
    "SCENU (UPRO)": "nav_history_SCENU.csv",
    "SCENT (TECL)": "nav_history_SCENT.csv",
}

OUTPUT_COLS = [
    "Initial AUM",
    "Units to Mint", "Units to Burn", "Net Units", "Units",
    "Post Mov Aum",
    "Initial Price per Unit",
    "Close Price per Unit",
    "Servicing Fee",
    "Price per Unit with MER",
    "Final AUM",
    "PPU Change",
    "AUM_Change",
    "AUM_Change_%",
    "PPU_MER_Change",
    "PPU_MER_Change_%",
]

# Inputs we expect user to control day-by-day:
INPUT_COLS = [
    "Deposits",
    "Withdrawals",
    "Unrealized Performance $",
    "Realized Performance $",
    "Trading Costs",
    "Servicing Fee Override",  # optional, can be blank
]

ALL_COLS = ["Date"] + INPUT_COLS + OUTPUT_COLS


# ================== HELPERS ==================
def empty_history():
    df = pd.DataFrame(columns=ALL_COLS)
    return df


def load_history(path: str) -> pd.DataFrame:
    if os.path.exists(path):
        df = pd.read_csv(path)
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"])
        # Ensure all columns exist
        for c in ALL_COLS:
            if c not in df.columns:
                df[c] = np.nan
        df = df[ALL_COLS]
        df = df.sort_values("Date").reset_index(drop=True)
        return df
    return empty_history()


def save_history(path: str, df: pd.DataFrame):
    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").reset_index(drop=True)
    df.to_csv(path, index=False)


def calc_day(prev_final_aum: float,
             prev_units: float,
             prev_ppu_with_mer: float,
             deposits: float,
             withdrawals: float,
             unrealized: float,
             realized: float,
             trading_costs: float,
             mer_daily_rate: float,
             servicing_fee_override: float | None):
    """
    Excel-aligned logic:

    - Initial AUM of each day = previous day's Final AUM
    - Initial PPU of each day = previous day's Price per Unit with MER
    - Units mint/burn based on Initial PPU
    - Close PPU computed on gross AUM (initial + perf - trading) / ending units
    - Servicing Fee = (Close PPU * Post Mov Aum) * mer_daily_rate  (unless override)
    - Price with MER = Close PPU - (Fee / Units)
    - Final AUM = Price with MER * Units
    """

    initial_aum = float(prev_final_aum)
    initial_units = float(prev_units)
    initial_ppu = float(prev_ppu_with_mer)

    # flows
    net_flow = float(deposits) - float(withdrawals)

    units_to_mint = float(deposits) / initial_ppu if deposits > 0 else 0.0
    units_to_burn = float(withdrawals) / initial_ppu if withdrawals > 0 else 0.0
    net_units = units_to_mint - units_to_burn
    units_end = initial_units + net_units

    if units_end <= 0:
        raise ValueError("Ending Units <= 0. Check deposits/withdrawals.")

    # Post movement AUM (fee base)
    post_mov_aum = initial_aum + net_flow

    # gross AUM before fee
    gross_aum = initial_aum + float(unrealized) + float(realized) - float(trading_costs)

    close_ppu = gross_aum / units_end

    # servicing fee (override optional)
    if servicing_fee_override is not None and not np.isnan(servicing_fee_override):
        servicing_fee = float(servicing_fee_override)
    else:
        servicing_fee = (close_ppu * post_mov_aum) * float(mer_daily_rate)

    fee_per_unit = servicing_fee / units_end
    price_with_mer = close_ppu - fee_per_unit

    final_aum = price_with_mer * units_end

    # changes
    ppu_change = price_with_mer - initial_ppu
    aum_change = final_aum - initial_aum
    aum_change_pct = (aum_change / initial_aum * 100.0) if initial_aum != 0 else 0.0

    ppu_mer_change = price_with_mer - initial_ppu
    ppu_mer_change_pct = (ppu_mer_change / initial_ppu * 100.0) if initial_ppu != 0 else 0.0

    return {
        "Initial AUM": initial_aum,
        "Units to Mint": units_to_mint,
        "Units to Burn": units_to_burn,
        "Net Units": net_units,
        "Units": units_end,
        "Post Mov Aum": post_mov_aum,
        "Initial Price per Unit": initial_ppu,
        "Close Price per Unit": close_ppu,
        "Servicing Fee": servicing_fee,
        "Price per Unit with MER": price_with_mer,
        "Final AUM": final_aum,
        "PPU Change": ppu_change,
        "AUM_Change": aum_change,
        "AUM_Change_%": aum_change_pct,
        "PPU_MER_Change": ppu_mer_change,
        "PPU_MER_Change_%": ppu_mer_change_pct,
    }


def recompute_all(df: pd.DataFrame,
                  start_aum: float,
                  start_units: float,
                  start_ppu: float,
                  mer_daily_rate: float) -> pd.DataFrame:
    """
    Rebuild outputs for every row in chronological order using only inputs + previous outputs.
    This is the part that makes your manual edits "become real" and propagate forward.
    """
    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").reset_index(drop=True)

    prev_final_aum = float(start_aum)
    prev_units = float(start_units)
    prev_ppu = float(start_ppu)

    for i in range(len(df)):
        deposits = float(df.loc[i, "Deposits"] or 0)
        withdrawals = float(df.loc[i, "Withdrawals"] or 0)
        unrealized = float(df.loc[i, "Unrealized Performance $"] or 0)
        realized = float(df.loc[i, "Realized Performance $"] or 0)
        trading_costs = float(df.loc[i, "Trading Costs"] or 0)

        override_val = df.loc[i, "Servicing Fee Override"]
        override = None
        try:
            override = float(override_val) if pd.notna(override_val) else None
        except Exception:
            override = None

        out = calc_day(
            prev_final_aum=prev_final_aum,
            prev_units=prev_units,
            prev_ppu_with_mer=prev_ppu,
            deposits=deposits,
            withdrawals=withdrawals,
            unrealized=unrealized,
            realized=realized,
            trading_costs=trading_costs,
            mer_daily_rate=mer_daily_rate,
            servicing_fee_override=override,
        )

        # write outputs
        for k, v in out.items():
            df.loc[i, k] = v

        # update prev for next day
        prev_final_aum = float(df.loc[i, "Final AUM"])
        prev_units = float(df.loc[i, "Units"])
        prev_ppu = float(df.loc[i, "Price per Unit with MER"])

    return df


# ================== UI ==================
st.title("Private Fund NAV Engine – Daily NAV & AUM Control")

fund_choice = st.selectbox("Select the fund:", FUNDS)
HISTORY_FILE = FUND_MAP[fund_choice]

with st.sidebar:
    st.header("Settings")
    mer_daily_rate = st.number_input(
        "Daily Servicing Fee rate (MER_DAILY_RATE)",
        value=float(MER_DAILY_RATE_DEFAULT),
        format="%.12f",
        help="Default is 6%/365. Keep this aligned with your Excel."
    )

    st.divider()
    st.subheader("Reset (this fund)")
    confirm_reset = st.checkbox("I understand this will delete/restart this fund history")
    if st.button("Reset history for this fund", disabled=not
