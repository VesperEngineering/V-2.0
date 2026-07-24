#!/usr/bin/env python3
"""
Build a 1000-stock universe: S&P 500 + mid/small caps.
Run once: python scripts/build_universe.py
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import yaml

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
logger = logging.getLogger("universe")

TARGET = 1000
OUTPUT = Path("config/universe.yaml")


def get_sp500() -> list[str]:
    """Scrape S&P 500 constituents from Wikipedia."""
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    tables = pd.read_html(url)
    df = tables[0]
    symbols = df["Symbol"].str.replace(".", "-", regex=False).tolist()
    logger.info("S&P 500: %d symbols", len(symbols))
    return symbols


def get_additional(existing: set[str], needed: int) -> list[str]:
    """
    Fill remaining slots with liquid US equities.

    Uses a curated list of well-known mid-cap and large-cap names
    that are not in the S&P 500. For a production system, pull this
    from your data provider's screener (top 1000 by market cap).
    """
    # Well-known non-S&P-500 names across sectors.
    # In production, replace this with your API's screener endpoint:
    #   GET /screener?market_cap_desc&limit=1000
    candidates = [
        # Mid-cap tech
        "PLTR", "SOFI", "RBLX", "COIN", "MARA", "RIOT", "SQ", "SHOP",
        "SNOW", "DDOG", "ZS", "CRWD", "NET", "BILL", "HUBS", "DOCU",
        "ZM", "DKNG", "ABNB", "RIVN", "LCID", "NIO", "XPEV", "LI",
        # Mid-cap finance
        "HOOD", "AFRM", "UPST", "NU", "PAGS", "GDOT", "ALLY", "KEY",
        "CFG", "MTB", "HBAN", "RF", "FITB", "CMA", "ZIONS", "WAL",
        # Mid-cap healthcare
        "MRNA", "NVAX", "INCY", "EXAS", "VEEV", "HIMS", "CORT",
        "ALKS", "NBIX", "EXEL", "HALO", "RARE", "PCVX", "IMVT",
        # Mid-cap consumer
        "CHWY", "WING", "CAKE", "TXRH", "DINE", "JACK", "SHAK",
        "WEN", "POWW", "GOLF", "MODG", "PLAY", "PRPL", "LOVE",
        # Mid-cap industrial
        "AXON", "TT", "PWR", "EME", "FIX", "BLDR", "TMHC", "MTH",
        "PHM", "LEN", "DHI", "NVR", "TOL", "KBH", "IBP", "PRIM",
        # Mid-cap energy
        "DVN", "FANG", "EQT", "CTRA", "MTDR", "PDCE", "SM", "CRC",
        "CIVI", "TALO", "NOG", "VTLE", "SD", "BORR", "VAL",
        # Small/mid-cap ETFs are NOT included (stocks only)
        # Additional large names that may not be in S&P 500
        "UBER", "LYFT", "DASH", "RBLX", "TTD", "PINS", "SNAP",
        "ROKU", "FUBO", "SIRI", "PARA", "WBD", "FOXA", "NFLX",
        # REITs
        "O", "AMT", "PLD", "CCI", "EQIX", "DLR", "SPG", "PSA",
        "AVB", "EQR", "MAA", "UDR", "ESS", "CPT", "ARE", "BXP",
        # Utilities
        "NEE", "DUK", "SO", "D", "AEP", "SRE", "EXC", "XEL",
        "WEC", "ES", "AWK", "CNP", "CMS", "DTE", "PPL", "ETR",
        # More tech / semis
        "MRVL", "ON", "SWKS", "MCHP", "ENTG", "LSCC", "SITM",
        "ALGM", "POWI", "IRTC", "CALX", "VSAT", "VIAV", "CIEN",
        # More healthcare
        "ZTS", "DXCM", "IDXX", "IQV", "A", "MTD", "WAT", "BIO",
        "TECH", "RGEN", "CRL", "WST", "DHR", "BDX", "BAX", "HOLX",
        # More industrials
        "ODFL", "JBHT", "KNX", "XPO", "SAIA", "OLD", "R", "RYAN",
        "WAB", "GATX", "UNP", "CSX", "NSC", "KSU", "CP", "CNI",
        # More consumer
        "YUM", "CMG", "MCD", "SBUX", "DPZ", "PAPA", "WING",
        "DECK", "ONON", "BIRK", "CROX", "SKX", "CAL", "SHOO",
        # More energy / materials
        "NEM", "GOLD", "AEM", "WPM", "FNV", "AGI", "KGC", "BTG",
        "FCX", "SCCO", "TECK", "AA", "RS", "CLF", "X", "STLD",
        # Fillers — liquid names across sectors
        "F", "GM", "T", "VZ", "PFE", "KO", "PEP", "MO", "BTI",
        "BAC", "WFC", "C", "GS", "MS", "SCHW", "BLK", "BX",
        "KKR", "APO", "ARES", "OWL", "BAM", "BRO", "AON", "MMC",
        "AJG", "L", "AFL", "MET", "PRU", "AIG", "TRV", "ALL",
        "CB", "PGR", "HIG", "CINF", "WRB", "LNC", "GL", "RE",
        "RGA", "UNH", "CI", "ELV", "HUM", "CNC", "MOH", "CVS",
        "WBA", "RAD", "MCK", "ABC", "CAH", "HSIC", "PDCO",
        "COST", "WMT", "TGT", "DG", "DLTR", "KR", "ACI", "SFM",
        "BJ", "CASY", "PAG", "AN", "GPI", "ABG", "SAH", "LAD",
        "KMX", "CAR", "HTZ", "BKNG", "EXPE", "MAR", "HLT", "IHG",
        "H", "WH", "CHH", "RLH", "AIG", "LUV", "DAL", "UAL",
        "AAL", "JBLU", "ALK", "HA", "SAVE", "CPA", "AZUL",
        "FDX", "UPS", "XPO", "GXO", "RXO", "TFC", "PNC", "USB",
        "BKYF", "JPM", "BAC", "WFC", "C", "GS", "MS",
    ]

    # Deduplicate, remove existing, take what we need
    seen = set()
    result = []
    for sym in candidates:
        sym = sym.upper().strip()
        if sym not in existing and sym not in seen:
            seen.add(sym)
            result.append(sym)
        if len(result) >= needed:
            break

    logger.info("Additional symbols: %d", len(result))
    return result


def main():
    sp500 = get_sp500()
    existing = set(sp500)
    needed = TARGET - len(sp500)

    if needed > 0:
        extra = get_additional(existing, needed)
        universe = sp500 + extra
    else:
        universe = sp500[:TARGET]

    # Final dedup
    universe = list(dict.fromkeys(universe))[:TARGET]

    logger.info("Total universe: %d symbols", len(universe))

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w") as f:
        yaml.dump({"universe": universe}, f, default_flow_style=False)

    logger.info("Written to %s", OUTPUT)
    logger.info("")
    logger.info("NOTE: For production, replace the candidate list in")
    logger.info("get_additional() with your data provider's screener:")
    logger.info("  top 1000 US equities by market cap.")
    logger.info("  Your Massive API likely has an endpoint for this.")


if __name__ == "__main__":
    main()