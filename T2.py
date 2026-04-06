"""
================================================================================
  PROFESSIONAL FINANCIAL ANALYSIS REPORT GENERATOR
  Macrotrends-Style | Value Investing Edition
  Powered by Alpha Vantage API + xlsxwriter
================================================================================
"""

import pandas as pd
import requests
import time
import os
import math
import sys
from datetime import datetime

# ──────────────────────────────────────────────────────────────────────────────
# 0.  CONFIGURATION
# ──────────────────────────────────────────────────────────────────────────────

OUTPUT_DIR   = r"C:\Users\User\iCloudDrive\PycharmProjects\PythonProject"
API_WAIT_SEC = 13          # free tier: 5 req/min → 12-13 s between calls
MAX_ANNUAL_YEARS   = 10    # cap history shown in charts/sheets

# ── Corporate color palette (Macrotrends-inspired) ──────────────────────────
C = {
    "navy":       "#1F3864",
    "blue":       "#2E75B6",
    "slate":      "#44546A",
    "light_blue": "#BDD7EE",
    "orange":     "#E67E22",
    "green":      "#27AE60",
    "red":        "#C0392B",
    "yellow":     "#F9E04B",
    "white":      "#FFFFFF",
    "light_gray": "#F2F2F2",
    "mid_gray":   "#D9D9D9",
    "dark_gray":  "#595959",
    "gold":       "#FFC000",
}

# ──────────────────────────────────────────────────────────────────────────────
# 1.  INPUT
# ──────────────────────────────────────────────────────────────────────────────

ticker  = input("Enter stock symbol (e.g., MSFT, AAPL, GOOGL): ").strip().upper()
api_key = input("Enter your Alpha Vantage API key: ").strip()

os.makedirs(OUTPUT_DIR, exist_ok=True)
output_file = os.path.join(OUTPUT_DIR, f"{ticker}_Pro_Financial_Report.xlsx")
print(f"\n{'='*60}")
print(f"  Generating professional report for: {ticker}")
print(f"  Output: {output_file}")
print(f"{'='*60}\n")


# ──────────────────────────────────────────────────────────────────────────────
# 2.  API HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def fetch_av(function: str, extra: str = "") -> dict | None:
    url = (f"https://www.alphavantage.co/query?function={function}"
           f"&symbol={ticker}&apikey={api_key}{extra}")
    try:
        resp = requests.get(url, timeout=30)
        data = resp.json()
    except Exception as e:
        print(f"  ❌ Network error [{function}]: {e}")
        return None

    for bad_key in ("Error Message", "Note", "Information"):
        if bad_key in data:
            print(f"  ⚠️  API [{function}]: {data[bad_key][:120]}")
            return None
    return data


def safe_float(val, default=0.0):
    try:
        f = float(val)
        return f if math.isfinite(f) else default
    except (TypeError, ValueError):
        return default


# ──────────────────────────────────────────────────────────────────────────────
# 3.  FETCH ALL DATA
# ──────────────────────────────────────────────────────────────────────────────

endpoints = [
    ("INCOME_STATEMENT",  "income_data"),
    ("BALANCE_SHEET",     "balance_data"),
    ("CASH_FLOW",         "cashflow_data"),
    ("OVERVIEW",          "overview_data"),
    ("TIME_SERIES_MONTHLY_ADJUSTED", "price_data"),
]

fetched = {}
for func, key in endpoints:
    extra = "&outputsize=full" if func == "TIME_SERIES_MONTHLY_ADJUSTED" else ""
    print(f"  Fetching {func}…")
    fetched[key] = fetch_av(func, extra)
    if func != endpoints[-1][0]:
        time.sleep(API_WAIT_SEC)

income_data   = fetched["income_data"]   or {}
balance_data  = fetched["balance_data"]  or {}
cashflow_data = fetched["cashflow_data"] or {}
overview_data = fetched["overview_data"] or {}
price_data    = fetched["price_data"]    or {}

if not income_data.get("annualReports"):
    print("\n❌  Could not fetch income statement. Check API key / ticker.")
    sys.exit(1)

balance_data.setdefault("annualReports",    [])
balance_data.setdefault("quarterlyReports", [])
cashflow_data.setdefault("annualReports",   [])
cashflow_data.setdefault("quarterlyReports",[])


# ──────────────────────────────────────────────────────────────────────────────
# 4.  DATA PROCESSING
# ──────────────────────────────────────────────────────────────────────────────

def reports_to_df(reports: list, n: int | None = None) -> pd.DataFrame:
    if not reports:
        return pd.DataFrame()
    if n:
        reports = reports[:n]
    df = pd.DataFrame(reports)
    if "fiscalDateEnding" not in df.columns:
        return pd.DataFrame()
    df = df.set_index("fiscalDateEnding").transpose()
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df / 1_000_000          # → $M
    df.columns = pd.to_datetime(df.columns)
    df = df.sort_index(axis=1)   # oldest → newest
    return df


# Annual (cap to MAX years) ───────────────────────────────────────────────────
inc_a  = reports_to_df(income_data.get("annualReports",   []), MAX_ANNUAL_YEARS)
bal_a  = reports_to_df(balance_data.get("annualReports",  []), MAX_ANNUAL_YEARS)
cf_a   = reports_to_df(cashflow_data.get("annualReports", []), MAX_ANNUAL_YEARS)

# Quarterly (last 12 quarters for TTM + display) ──────────────────────────────
inc_q  = reports_to_df(income_data.get("quarterlyReports",   []), 12)
bal_q  = reports_to_df(balance_data.get("quarterlyReports",  []), 12)
cf_q   = reports_to_df(cashflow_data.get("quarterlyReports", []), 12)


# ── TTM Calculation ───────────────────────────────────────────────────────────
def calc_ttm(flow_df: pd.DataFrame, balance_df: pd.DataFrame) -> pd.Series:
    """Sum last 4 quarters for flow items; latest quarter for balance sheet."""
    ttm = {}
    if not flow_df.empty:
        last4 = flow_df.iloc[:, -4:] if flow_df.shape[1] >= 4 else flow_df
        for row in flow_df.index:
            ttm[row] = last4.loc[row].sum()
    if not balance_df.empty:
        latest = balance_df.iloc[:, -1]
        for row in balance_df.index:
            ttm[row] = latest[row]        # balance sheet: spot, not sum
    return pd.Series(ttm, name="TTM")


ttm_series = calc_ttm(
    pd.concat([inc_q, cf_q]),
    bal_q
)


# ── Merge annual sheets ───────────────────────────────────────────────────────
def merge_statements(*dfs) -> pd.DataFrame:
    frames = [d for d in dfs if not d.empty]
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames)
    combined = combined[~combined.index.duplicated(keep="first")]
    return combined

annual   = merge_statements(inc_a, bal_a, cf_a)
quarterly= merge_statements(inc_q, bal_q, cf_q)

# Prepend TTM as first column
if not annual.empty:
    ttm_df = ttm_series.to_frame().T
    ttm_df.index = ["TTM"]
    annual = pd.concat([ttm_df, annual.T]).T if False else annual  # keep annual cols
    # Insert TTM column at position 0
    annual.insert(0, "TTM", ttm_series.reindex(annual.index))


# ── Friendly column labels (Year only for annual, Q-YYYY for quarterly) ───────
def label_columns(df: pd.DataFrame, mode: str = "annual") -> pd.DataFrame:
    new_cols = []
    for c in df.columns:
        if c == "TTM":
            new_cols.append("TTM")
        elif mode == "annual":
            new_cols.append(str(pd.Timestamp(c).year))
        else:
            ts = pd.Timestamp(c)
            q  = (ts.month - 1) // 3 + 1
            new_cols.append(f"Q{q}-{ts.year}")
    df.columns = new_cols
    return df

annual    = label_columns(annual,    "annual")
quarterly = label_columns(quarterly, "quarterly")


# ── Row ordering ─────────────────────────────────────────────────────────────
INCOME_ORDER = [
    "totalRevenue","costOfRevenue","grossProfit",
    "operatingExpenses","sellingGeneralAndAdministrative","researchAndDevelopment",
    "operatingIncome","ebitda","depreciation","depreciationAndAmortization",
    "interestExpense","interestIncome","otherNonOperatingIncome",
    "incomeBeforeTax","incomeTaxExpense","netIncome",
]
BALANCE_ORDER = [
    "totalCurrentAssets","cashAndCashEquivalentsAtCarryingValue",
    "currentNetReceivables","inventory",
    "totalNonCurrentAssets","propertyPlantEquipmentNet","goodwill","intangibleAssets",
    "totalAssets",
    "totalCurrentLiabilities","currentAccountsPayable","shortTermDebt",
    "totalNonCurrentLiabilities","longTermDebtNoncurrent",
    "totalLiabilities","totalShareholderEquity","commonStockSharesOutstanding",
    "retainedEarnings",
]
CF_ORDER = [
    "operatingCashflow","capitalExpenditures","freeCashFlow",
    "cashflowFromInvestment","cashflowFromFinancing",
    "dividendPayout","proceedsFromRepurchaseOfEquity",
    "changeInCash",
]

FULL_ORDER = INCOME_ORDER + BALANCE_ORDER + CF_ORDER

def reorder_df(df: pd.DataFrame) -> pd.DataFrame:
    existing_ordered = [r for r in FULL_ORDER if r in df.index]
    remaining        = [r for r in df.index if r not in FULL_ORDER]
    return df.reindex(existing_ordered + remaining)

annual    = reorder_df(annual)
quarterly = reorder_df(quarterly)


# ── Financial Ratios ──────────────────────────────────────────────────────────
def build_ratios(inc: pd.DataFrame, bal: pd.DataFrame, cf: pd.DataFrame,
                 ov: dict) -> pd.DataFrame:
    rows = {}
    mkt_cap = safe_float(ov.get("MarketCapitalization", 0)) / 1e6

    for col in inc.columns:
        r = {}
        def g(df, key): return safe_float(df.loc[key, col]) if (not df.empty and key in df.index) else 0.0

        rev   = g(inc, "totalRevenue");       ni   = g(inc, "netIncome")
        op    = g(inc, "operatingIncome");    ebit = g(inc, "ebitda")
        ta    = g(bal, "totalAssets");        eq   = g(bal, "totalShareholderEquity")
        ca    = g(bal, "totalCurrentAssets"); cl   = g(bal, "totalCurrentLiabilities")
        inv   = g(bal, "inventory");          ltd  = g(bal, "longTermDebtNoncurrent")
        std   = g(bal, "shortTermDebt");      cash = g(bal, "cashAndCashEquivalentsAtCarryingValue")
        ocf   = g(cf,  "operatingCashflow");  capex= g(cf,  "capitalExpenditures")
        shares= g(bal, "commonStockSharesOutstanding")  # already /1M

        td  = ltd + std
        bvps= (eq / shares) if shares > 0 else 0
        fcf = ocf + capex   # capex is typically negative in the data

        # ── Profitability ────────────────────────────────────────────────────
        r["Gross Margin (%)"]    = (g(inc,"grossProfit") / rev * 100) if rev else None
        r["Operating Margin (%)"]= (op / rev * 100) if rev else None
        r["Net Margin (%)"]      = (ni / rev * 100) if rev else None
        r["EBITDA Margin (%)"]   = (ebit/ rev * 100) if rev else None
        r["ROE (%)"]             = (ni / eq  * 100) if eq  else None
        r["ROA (%)"]             = (ni / ta  * 100) if ta  else None
        r["ROIC (%)"]            = (op * (1-0.21) / max(eq+td, 1) * 100)

        # ── Liquidity / Leverage ─────────────────────────────────────────────
        r["Current Ratio"]       = (ca / cl) if cl else None
        r["Quick Ratio"]         = ((ca - inv) / cl) if cl else None
        r["Debt to Equity"]      = (td / eq) if eq else None
        r["Net Debt ($M)"]       = td - cash

        # ── Valuation ────────────────────────────────────────────────────────
        r["P/E Ratio"]           = (mkt_cap / ni) if ni else None
        r["P/S Ratio"]           = (mkt_cap / rev) if rev else None
        r["P/B Ratio"]           = (mkt_cap / eq) if eq else None
        r["EV/EBITDA"]           = ((mkt_cap + td - cash) / ebit) if ebit else None
        r["FCF Yield (%)"]       = (fcf / mkt_cap * 100) if mkt_cap else None

        # ── Per-Share ────────────────────────────────────────────────────────
        r["EPS ($)"]             = (ni  / shares) if shares else None
        r["FCF per Share ($)"]   = (fcf / shares) if shares else None
        r["Book Value/Share ($)"]= bvps

        # ── Value Metrics ────────────────────────────────────────────────────
        eps  = r["EPS ($)"] or 0
        graham = math.sqrt(max(22.5 * eps * bvps, 0)) if (eps > 0 and bvps > 0) else None
        r["Graham Number ($)"]   = graham

        # Owner Earnings = Net Income + D&A – Maintenance CapEx (≈ 70% total capex)
        da   = g(inc, "depreciationAndAmortization")
        maint_capex = abs(capex) * 0.70
        r["Owner Earnings ($M)"] = ni + da - maint_capex

        # Dividend
        div_ps = safe_float(ov.get("DividendPerShare", 0))
        price  = safe_float(ov.get("50DayMovingAverage", 0))
        r["Dividend Yield (%)"]  = (div_ps / price * 100) if price else None
        peg = ov.get("PEGRatio")
        r["PEG Ratio"]           = safe_float(peg) if (peg and peg != "None") else None

        rows[col] = r

    # ✅ תיקון: הסרת .T — ה-DataFrame כבר בכיוון הנכון
    return pd.DataFrame(rows)


ratios = build_ratios(
    inc_a if not inc_a.empty else pd.DataFrame(),
    bal_a if not bal_a.empty else pd.DataFrame(),
    cf_a  if not cf_a.empty  else pd.DataFrame(),
    overview_data,
)
ratios = label_columns(ratios, "annual")


# ──────────────────────────────────────────────────────────────────────────────
# 5.  EXCEL WRITER SETUP
# ──────────────────────────────────────────────────────────────────────────────

writer   = pd.ExcelWriter(output_file, engine="xlsxwriter")
wb       = writer.book


# ── Shared format factory ─────────────────────────────────────────────────────
def fmt(**kw):
    base = {"font_name": "Arial", "font_size": 10, "border": 1, "border_color": C["mid_gray"]}
    base.update(kw)
    return wb.add_format(base)

# Core formats
F_HEADER       = fmt(bold=True, bg_color=C["navy"],     font_color=C["white"],    align="center", valign="vcenter", font_size=10)
F_SUBHEADER    = fmt(bold=True, bg_color=C["blue"],     font_color=C["white"],    align="center")
F_ROW_LABEL    = fmt(bold=False,bg_color=C["light_gray"],                         align="left",  indent=1)
F_ROW_LABEL_H  = fmt(bold=True, bg_color=C["light_blue"],                         align="left",  indent=1)
F_NUM          = fmt(num_format='#,##0.0;(#,##0.0);"-"',  bg_color=C["white"])
F_NUM_H        = fmt(num_format='#,##0.0;(#,##0.0);"-"',  bg_color=C["light_blue"], bold=True)
F_PCT          = fmt(num_format='0.0%;(0.0%);"-"',         bg_color=C["white"])
F_PCT_H        = fmt(num_format='0.0%;(0.0%);"-"',         bg_color=C["light_blue"], bold=True)
F_RATIO        = fmt(num_format='0.0x;(0.0x);"-"',         bg_color=C["white"])
F_DOLLAR       = fmt(num_format='"$"#,##0.00;("$"#,##0.00);"-"', bg_color=C["white"])
F_TTM          = fmt(bold=True, bg_color="#E8F4FD",     num_format='#,##0.0;(#,##0.0);"-"')
F_TTM_H        = fmt(bold=True, bg_color="#BDD7EE",     num_format='#,##0.0;(#,##0.0);"-"')
F_GREEN_TXT    = fmt(font_color=C["green"], bold=True, num_format='0.0%')
F_RED_TXT      = fmt(font_color=C["red"],   bold=True, num_format='0.0%')
F_SECTION      = fmt(bold=True, bg_color=C["slate"],    font_color=C["white"],    align="left", indent=1)
F_DASHBOARD_H  = fmt(bold=True, bg_color=C["navy"],     font_color=C["gold"],     font_size=12, align="center", valign="vcenter")
F_DASHBOARD_V  = fmt(bold=True, bg_color=C["light_blue"], font_size=11, align="center", num_format='#,##0.00')
F_DASHBOARD_L  = fmt(bold=False,bg_color=C["white"],    font_size=10, align="left", indent=1)


# ──────────────────────────────────────────────────────────────────────────────
# 6.  HELPER: write a dataframe to a worksheet
# ──────────────────────────────────────────────────────────────────────────────

SECTION_LABELS = {
    "totalRevenue":               "── Income Statement ──────────────────",
    "totalCurrentAssets":         "── Balance Sheet ─────────────────────",
    "operatingCashflow":          "── Cash Flow Statement ───────────────",
}
KEY_METRICS = {
    "totalRevenue","grossProfit","operatingIncome","netIncome",
    "ebitda","operatingCashflow","freeCashFlow","totalAssets",
    "totalShareholderEquity","commonStockSharesOutstanding",
}


def write_financial_sheet(ws_name: str, df: pd.DataFrame, is_quarterly: bool = False):
    if df.empty:
        return

    df.to_excel(writer, sheet_name=ws_name, startrow=1, startcol=0)
    ws = writer.sheets[ws_name]

    n_cols = len(df.columns)

    # ── Column widths ─────────────────────────────────────────────────────────
    ws.set_column(0, 0, 38)          # metric name
    ws.set_column(1, n_cols, 13)     # data columns
    ws.set_column(n_cols + 1, n_cols + 1, 14)  # sparkline column

    # ── Freeze panes: row 1 + col A ──────────────────────────────────────────
    ws.freeze_panes(2, 1)

    # ── Top header row ───────────────────────────────────────────────────────
    ws.merge_range(0, 0, 0, n_cols + 1,
                   f"{ticker}  —  {'Quarterly' if is_quarterly else 'Annual'} Financial Statements  ($ Millions)",
                   F_DASHBOARD_H)

    # ── Column header row ────────────────────────────────────────────────────
    ws.write(1, 0, "Metric", F_HEADER)
    for ci, col in enumerate(df.columns):
        hdr_fmt = F_TTM_H if col == "TTM" else F_SUBHEADER
        ws.write(1, ci + 1, col, hdr_fmt)
    ws.write(1, n_cols + 1, "Trend", F_SUBHEADER)

    # ── Data rows ────────────────────────────────────────────────────────────
    for ri, (row_name, row_data) in enumerate(df.iterrows()):
        excel_row = ri + 2   # 0-indexed, offset by 2 header rows

        # Section divider
        if row_name in SECTION_LABELS:
            ws.merge_range(excel_row, 0, excel_row, n_cols + 1, SECTION_LABELS[row_name], F_SECTION)
            continue

        is_key  = row_name in KEY_METRICS
        lbl_fmt = F_ROW_LABEL_H if is_key else F_ROW_LABEL
        ws.write(excel_row, 0, row_name, lbl_fmt)

        for ci, col in enumerate(df.columns):
            val = row_data[col]
            is_ttm = (col == "TTM")
            if pd.isna(val):
                num_fmt = F_TTM_H if (is_ttm and is_key) else F_TTM if is_ttm else F_NUM_H if is_key else F_NUM
                ws.write_blank(excel_row, ci + 1, None, num_fmt)
            else:
                num_fmt = F_TTM_H if (is_ttm and is_key) else F_TTM if is_ttm else F_NUM_H if is_key else F_NUM
                ws.write_number(excel_row, ci + 1, val, num_fmt)

        # ── Sparkline at end of row ──────────────────────────────────────────
        data_range = f"'{ws_name}'!{xl_col(1)}{excel_row+1}:{xl_col(n_cols)}{excel_row+1}"
        ws.add_sparkline(excel_row, n_cols + 1, {
            "range":       data_range,
            "type":        "line",
            "high_point":  True,
            "low_point":   True,
            "markers":     True,
            "series_color": C["blue"],
            "high_color":   C["green"],
            "low_color":    C["red"],
        })

    # ── YoY Conditional Formatting for Revenue, Net Income, FCF ─────────────
    yoy_targets = ["totalRevenue", "netIncome", "freeCashFlow", "operatingCashflow"]
    for row_name in yoy_targets:
        if row_name not in df.index:
            continue
        ri = list(df.index).index(row_name) + 2
        if n_cols >= 2:
            for ci in range(2, n_cols + 1):   # skip TTM, start at second year
                col_letter_curr = xl_col(ci)
                col_letter_prev = xl_col(ci - 1)
                ws.conditional_format(ri, ci, ri, ci, {
                    "type":     "formula",
                    "criteria": f"={col_letter_curr}{ri+1}>{col_letter_prev}{ri+1}",
                    "format":   wb.add_format({"font_color": C["green"], "bold": True}),
                })
                ws.conditional_format(ri, ci, ri, ci, {
                    "type":     "formula",
                    "criteria": f"={col_letter_curr}{ri+1}<{col_letter_prev}{ri+1}",
                    "format":   wb.add_format({"font_color": C["red"]}),
                })

    ws.hide_gridlines(2)


def xl_col(n: int) -> str:
    """Convert 0-based column index to Excel letter(s)."""
    result = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        result = chr(65 + r) + result
    return result


# ──────────────────────────────────────────────────────────────────────────────
# 7.  WRITE FINANCIAL SHEETS
# ──────────────────────────────────────────────────────────────────────────────

print("  Writing Annual sheet…")
write_financial_sheet("Annual", annual, is_quarterly=False)

print("  Writing Quarterly sheet…")
write_financial_sheet("Quarterly", quarterly, is_quarterly=True)


# ──────────────────────────────────────────────────────────────────────────────
# 8.  FINANCIAL RATIOS SHEET
# ──────────────────────────────────────────────────────────────────────────────

print("  Writing Ratios sheet…")

RATIO_SECTIONS = {
    "Gross Margin (%)":     ("── Profitability",     True),
    "Operating Margin (%)": (None,                   False),
    "Net Margin (%)":       (None,                   False),
    "EBITDA Margin (%)":    (None,                   False),
    "ROE (%)":              (None,                   True),
    "ROA (%)":              (None,                   False),
    "ROIC (%)":             (None,                   True),
    "Current Ratio":        ("── Liquidity / Leverage", False),
    "Quick Ratio":          (None,                   False),
    "Debt to Equity":       (None,                   False),
    "Net Debt ($M)":        (None,                   False),
    "P/E Ratio":            ("── Valuation",         True),
    "P/S Ratio":            (None,                   False),
    "P/B Ratio":            (None,                   False),
    "EV/EBITDA":            (None,                   False),
    "FCF Yield (%)":        (None,                   True),
    "EPS ($)":              ("── Per Share",         True),
    "FCF per Share ($)":    (None,                   False),
    "Book Value/Share ($)": (None,                   False),
    "Graham Number ($)":    ("── Value Metrics",     True),
    "Owner Earnings ($M)":  (None,                   True),
    "Dividend Yield (%)":   (None,                   False),
    "PEG Ratio":            (None,                   False),
}

if not ratios.empty:
    ratios.to_excel(writer, sheet_name="Ratios", startrow=1, startcol=0)
    ws_r = writer.sheets["Ratios"]
    n_r  = len(ratios.columns)

    ws_r.set_column(0, 0, 24)
    ws_r.set_column(1, n_r, 12)
    ws_r.set_column(n_r + 1, n_r + 1, 14)
    ws_r.freeze_panes(2, 1)
    ws_r.hide_gridlines(2)

    ws_r.merge_range(0, 0, 0, n_r + 1, f"{ticker}  —  Financial Ratios & Value Metrics", F_DASHBOARD_H)
    ws_r.write(1, 0, "Metric", F_HEADER)
    for ci, col in enumerate(ratios.columns):
        ws_r.write(1, ci + 1, col, F_SUBHEADER)
    ws_r.write(1, n_r + 1, "Trend", F_SUBHEADER)

    prev_section = None
    for ri, row_name in enumerate(ratios.index):
        excel_row = ri + 2
        section_label, is_key = RATIO_SECTIONS.get(row_name, (None, False))

        if section_label and section_label != prev_section:
            ws_r.merge_range(excel_row, 0, excel_row, n_r + 1, section_label, F_SECTION)
            prev_section = section_label
            continue

        lbl_fmt = F_ROW_LABEL_H if is_key else F_ROW_LABEL
        ws_r.write(excel_row, 0, row_name, lbl_fmt)

        # choose number format by row name
        if "(%)" in row_name:
            val_fmt = F_PCT_H if is_key else F_PCT
        elif "$" in row_name:
            val_fmt = F_DOLLAR
        elif "Ratio" in row_name or "ROIC" in row_name or "EV/" in row_name:
            val_fmt = F_RATIO
        else:
            val_fmt = F_NUM_H if is_key else F_NUM

        for ci, col in enumerate(ratios.columns):
            val = ratios.loc[row_name, col]
            if pd.isna(val):
                ws_r.write_blank(excel_row, ci + 1, None, val_fmt)
            else:
                v = val / 100 if "(%)" in row_name else val
                ws_r.write_number(excel_row, ci + 1, v, val_fmt)

        data_range = f"'Ratios'!{xl_col(1)}{excel_row+1}:{xl_col(n_r)}{excel_row+1}"
        ws_r.add_sparkline(excel_row, n_r + 1, {
            "range":       data_range,
            "type":        "line",
            "high_point":  True,
            "low_point":   True,
            "series_color": C["navy"],
        })


# ──────────────────────────────────────────────────────────────────────────────
# 9.  VALUE DASHBOARD SHEET
# ──────────────────────────────────────────────────────────────────────────────

print("  Writing Value Dashboard…")

ws_d = wb.add_worksheet("Dashboard")
wb.set_properties({"title": f"{ticker} Financial Report"})

# make Dashboard first tab
ws_d.activate()

ws_d.set_column("A:A", 3)
ws_d.set_column("B:B", 28)
ws_d.set_column("C:C", 18)
ws_d.set_column("D:D", 18)
ws_d.set_column("E:E", 18)
ws_d.set_column("F:F", 18)
ws_d.set_column("G:G", 3)
ws_d.hide_gridlines(2)
ws_d.set_zoom(90)

# Title banner
ws_d.set_row(0, 50)
ws_d.merge_range("A1:G1",
                 f"  {ticker}   |   Professional Investment Dashboard   |   {datetime.today().strftime('%B %d, %Y')}",
                 F_DASHBOARD_H)

ov = overview_data
name    = ov.get("Name", ticker)
sector  = ov.get("Sector", "—")
indus   = ov.get("Industry", "—")
exch    = ov.get("Exchange", "—")
desc    = ov.get("Description", "")[:300] + "…"

F_LABEL_SMALL = fmt(bold=True,  bg_color=C["slate"], font_color=C["white"], align="left", indent=1, font_size=9)
F_VALUE_SMALL = fmt(bold=False, bg_color=C["light_gray"], align="left", indent=1, font_size=10)
F_VALUE_BIG   = fmt(bold=True,  bg_color=C["white"], align="center", font_size=13, num_format='#,##0.00')
F_KPI_LABEL   = fmt(bold=True,  bg_color=C["navy"],  font_color=C["white"], align="center", font_size=9)
F_KPI_VAL     = fmt(bold=True,  bg_color="#E8F4FD",  align="center", font_size=14, num_format='#,##0.00')
F_KPI_VAL_PCT = fmt(bold=True,  bg_color="#E8F4FD",  align="center", font_size=14, num_format='0.0%')
F_SECTION_D   = fmt(bold=True,  bg_color=C["blue"],  font_color=C["white"], align="left", indent=1, font_size=10)
F_DESC        = fmt(bold=False, bg_color=C["white"],  align="left", text_wrap=True, indent=1, font_size=9)

# Company info block
row = 2
ws_d.set_row(row, 20)
ws_d.write(row, 1, "Company",  F_LABEL_SMALL)
ws_d.write(row, 2, name,        F_VALUE_SMALL)
ws_d.write(row, 3, "Sector",   F_LABEL_SMALL)
ws_d.write(row, 4, sector,      F_VALUE_SMALL)
ws_d.write(row, 5, "Exchange", F_LABEL_SMALL)

row += 1
ws_d.write(row, 1, "Industry", F_LABEL_SMALL)
ws_d.write(row, 2, indus,       F_VALUE_SMALL)
ws_d.write(row, 3, "Ticker",   F_LABEL_SMALL)
ws_d.write(row, 4, ticker,      F_VALUE_SMALL)
ws_d.write(row, 5, exch,        F_VALUE_SMALL)

row += 1
ws_d.set_row(row, 45)
ws_d.merge_range(row, 1, row, 5, desc, F_DESC)

row += 2

# ── KPI tiles ────────────────────────────────────────────────────────────────
def ov_float(key): return safe_float(ov.get(key, 0))
price      = ov_float("50DayMovingAverage")
mkt_cap    = ov_float("MarketCapitalization") / 1e9
pe         = ov_float("PERatio")
eps_ttm    = ov_float("EPS")
bvps       = ov_float("BookValue")
div_yield  = ov_float("DividendYield") * 100
graham_num = math.sqrt(max(22.5 * eps_ttm * bvps, 0)) if eps_ttm > 0 and bvps > 0 else 0
margin_of_safety = ((graham_num - price) / graham_num * 100) if graham_num > 0 else 0

kpis = [
    ("Price",            price,            "$#,##0.00"),
    ("Market Cap ($B)",  mkt_cap,          "$#,##0.0"),
    ("P/E Ratio",        pe,               "0.0x"),
    ("EPS (TTM)",        eps_ttm,          "$#,##0.00"),
    ("Graham Number",    graham_num,       "$#,##0.00"),
    ("Margin of Safety", margin_of_safety, '0.0"%"'),
]

ws_d.set_row(row, 18)
ws_d.merge_range(row, 1, row, 5, "  Key Performance Indicators", F_SECTION_D)
row += 1

F_KPI_TILES = [
    fmt(bold=True, bg_color=C["navy"],   font_color=C["gold"],  align="center", font_size=10),
    fmt(bold=True, bg_color=C["blue"],   font_color=C["white"], align="center", font_size=10),
    fmt(bold=True, bg_color=C["slate"],  font_color=C["white"], align="center", font_size=10),
    fmt(bold=True, bg_color=C["navy"],   font_color=C["gold"],  align="center", font_size=10),
    fmt(bold=True, bg_color=C["green"],  font_color=C["white"], align="center", font_size=10),
    fmt(bold=True, bg_color=C["orange"],font_color=C["white"], align="center", font_size=10),
]
F_KPI_VAL_TILES = [
    fmt(bold=True, bg_color="#E8F4FD", align="center", font_size=14, num_format=kpis[i][2])
    for i in range(len(kpis))
]

ws_d.set_row(row, 18)
ws_d.set_row(row + 1, 28)

for ci, (label, val, fmt_str) in enumerate(kpis):
    col_idx = ci + 1
    ws_d.write(row,     col_idx, label, F_KPI_TILES[ci])
    ws_d.write_number(row + 1, col_idx, val,
                      wb.add_format({"bold": True, "bg_color": "#E8F4FD",
                                     "align": "center", "font_size": 14,
                                     "num_format": fmt_str, "font_name": "Arial"}))
row += 3

# ── Value Metrics block ───────────────────────────────────────────────────────
ws_d.merge_range(row, 1, row, 5, "  Intrinsic Value & Value Metrics", F_SECTION_D)
row += 1

F_VM_L = fmt(bold=True,  bg_color=C["light_blue"], align="left", indent=1, font_size=10)
F_VM_V = fmt(bold=False, bg_color=C["white"],      align="center", font_size=10, num_format="#,##0.00")

# Pull latest annual values for owner earnings
latest = {}
if not inc_a.empty:
    col_latest = inc_a.columns[-1]
    latest["ni"]   = safe_float(inc_a.loc["netIncome", col_latest])  if "netIncome"  in inc_a.index else 0
    latest["da"]   = safe_float(inc_a.loc["depreciationAndAmortization", col_latest]) if "depreciationAndAmortization" in inc_a.index else 0
if not cf_a.empty:
    col_latest = cf_a.columns[-1]
    latest["ocf"]  = safe_float(cf_a.loc["operatingCashflow",   col_latest]) if "operatingCashflow"   in cf_a.index else 0
    latest["capex"]= safe_float(cf_a.loc["capitalExpenditures", col_latest]) if "capitalExpenditures" in cf_a.index else 0

owner_earnings = (latest.get("ni",0) + latest.get("da",0) - abs(latest.get("capex",0)) * 0.70)
fcf_latest     = latest.get("ocf",0) + latest.get("capex",0)
fcf_yield      = (fcf_latest / (mkt_cap * 1000)) * 100 if mkt_cap else 0

vm_rows = [
    ("Graham Number ($)",       f"= √(22.5 × EPS × BVPS)",      graham_num,      "$#,##0.00"),
    ("Margin of Safety (%)",    "vs. Current Price",              margin_of_safety,'0.0"%"'),
    ("FCF Yield (%)",           "Free Cash Flow / Mkt Cap",       fcf_yield,       '0.0"%"'),
    ("Owner Earnings ($M)",     "Buffett: NI + D&A – 70% CapEx", owner_earnings,  "#,##0.0"),
    ("Book Value / Share ($)",  "From Latest Annual",              bvps,            "$#,##0.00"),
    ("P/B Ratio",               "Price / Book Value",              (price/bvps if bvps else 0), "0.0x"),
]

for label, note, val, nf in vm_rows:
    ws_d.set_row(row, 18)
    ws_d.write(row, 1, label, F_VM_L)
    ws_d.write(row, 2, note,
               fmt(bg_color=C["white"], align="left", indent=1, font_size=9, font_color=C["dark_gray"]))
    ws_d.write_number(row, 3, val,
                      wb.add_format({"bold": True, "bg_color": "#E8F4FD",
                                     "align": "center", "font_size": 11,
                                     "num_format": nf, "font_name": "Arial"}))
    row += 1

row += 1

# ── 10-year ROIC / ROE / D/E table ──────────────────────────────────────────
if not ratios.empty:
    ws_d.merge_range(row, 1, row, 5, "  Capital Allocation — 10-Year Trend  (ROIC / ROE / Debt-to-Equity)", F_SECTION_D)
    row += 1

    ws_d.set_row(row, 16)
    ws_d.write(row, 1, "Metric", F_HEADER)
    for ci, col in enumerate(ratios.columns[-10:]):
        ws_d.write(row, ci + 2, col, F_SUBHEADER)
    row += 1

    ca_metrics = ["ROIC (%)", "ROE (%)", "ROA (%)", "Debt to Equity"]
    for metric in ca_metrics:
        if metric not in ratios.index:
            continue
        ws_d.set_row(row, 16)
        is_pct = "(%)" in metric
        ws_d.write(row, 1, metric, F_ROW_LABEL_H)
        last10 = ratios.loc[metric].iloc[-10:]
        for ci, val in enumerate(last10):
            nf = '0.0%' if is_pct else '0.00x'
            v  = (val / 100) if (is_pct and not pd.isna(val)) else val
            cell_fmt = wb.add_format({
                "num_format": nf, "bold": True,
                "bg_color": C["white"], "align": "center",
                "font_name": "Arial", "font_size": 10, "border": 1,
                "border_color": C["mid_gray"],
            })
            if pd.isna(val):
                ws_d.write_blank(row, ci + 2, None, cell_fmt)
            else:
                ws_d.write_number(row, ci + 2, v, cell_fmt)
        row += 1


# ──────────────────────────────────────────────────────────────────────────────
# 10.  CHARTS SHEET
# ──────────────────────────────────────────────────────────────────────────────

print("  Building charts…")

CHART_SHEET = "Charts"
ws_c = wb.add_worksheet(CHART_SHEET)
ws_c.hide_gridlines(2)

# Write chart data to a hidden staging area (far-right columns)
STAGE_COL  = 60   # column BJ onwards (far right, won't be seen)
stage_row  = 0
labels_row = None

def stage_series(df: pd.DataFrame, row_name: str, label: str):
    """Write a series into the staging area; return (data_row, cats_row)."""
    global stage_row, labels_row

    # Write years / labels once
    if labels_row is None:
        labels_row = stage_row
        years = [c for c in df.columns if c != "TTM"]
        ws_c.write(labels_row, STAGE_COL, "Period")
        for ci, y in enumerate(years):
            ws_c.write(labels_row, STAGE_COL + 1 + ci, y)
        stage_row += 1

    data_row = stage_row
    ws_c.write(data_row, STAGE_COL, label)
    if row_name in df.index:
        cols = [c for c in df.columns if c != "TTM"]
        for ci, col in enumerate(cols):
            val = safe_float(df.loc[row_name, col], None) if col in df.columns else None
            if val is not None and math.isfinite(val):
                ws_c.write_number(data_row, STAGE_COL + 1 + ci, val)
            else:
                ws_c.write_blank(data_row, STAGE_COL + 1 + ci, None)
    stage_row += 1
    data_years = [c for c in df.columns if c != "TTM"]
    return data_row, labels_row, len(data_years)


def add_chart(chart_type, subtype=None):
    opts = {"type": chart_type}
    if subtype:
        opts["subtype"] = subtype
    ch = wb.add_chart(opts)
    ch.set_chartarea({"border": {"none": True}, "fill": {"color": C["white"]}})
    ch.set_plotarea({
        "border": {"none": True},
        "fill":   {"color": C["white"]},
    })
    ch.set_legend({"position": "bottom", "font": {"name": "Arial", "size": 9}})
    return ch


def set_axes(ch, x_name, y_name, y2_name=None):
    ch.set_x_axis({
        "name": x_name, "num_font": {"size": 9},
        "line": {"color": C["mid_gray"]},
        "major_gridlines": {"visible": False},
    })
    ch.set_y_axis({
        "name": y_name, "num_font": {"size": 9},
        "line": {"none": True},
        "major_gridlines": {"visible": True, "line": {"color": C["light_gray"], "dash_type": "dash"}},
    })
    if y2_name:
        ch.set_y2_axis({"name": y2_name, "num_font": {"size": 9}})


# ────────────────────────────────────────────────────────────────────
# Chart 1: Revenue (Bar) + Net Income Margin (Line) — Macrotrends combo
# ────────────────────────────────────────────────────────────────────
ch1 = add_chart("column")
ch1_overlay = add_chart("line")

rev_row,   cats_row, ncols = stage_series(annual, "totalRevenue",  "Revenue ($M)")
gp_row,    _,        _     = stage_series(annual, "grossProfit",   "Gross Profit ($M)")
ni_row,    _,        _     = stage_series(annual, "netIncome",     "Net Income ($M)")
margin_row                 = stage_row          # computed below

# Net Margin series
ws_c.write(margin_row, STAGE_COL, "Net Margin (%)")
if "totalRevenue" in annual.index and "netIncome" in annual.index:
    cols = [c for c in annual.columns if c != "TTM"]
    for ci, col in enumerate(cols):
        rev_v = safe_float(annual.loc["totalRevenue", col])
        ni_v  = safe_float(annual.loc["netIncome",    col])
        margin= (ni_v / rev_v * 100) if rev_v else None
        if margin is not None:
            ws_c.write_number(margin_row, STAGE_COL + 1 + ci, margin)
stage_row += 1

def make_ref(r, n): return [CHART_SHEET, r, STAGE_COL + 1, r, STAGE_COL + n]
def make_cats(n):   return [CHART_SHEET, cats_row, STAGE_COL + 1, cats_row, STAGE_COL + n]

ch1.add_series({
    "name":       [CHART_SHEET, rev_row, STAGE_COL],
    "categories": make_cats(ncols),
    "values":     make_ref(rev_row, ncols),
    "fill":       {"color": C["blue"]},
    "gap":        80,
})
ch1.add_series({
    "name":       [CHART_SHEET, gp_row, STAGE_COL],
    "categories": make_cats(ncols),
    "values":     make_ref(gp_row, ncols),
    "fill":       {"color": C["light_blue"]},
    "gap":        80,
})
ch1.add_series({
    "name":       [CHART_SHEET, ni_row, STAGE_COL],
    "categories": make_cats(ncols),
    "values":     make_ref(ni_row, ncols),
    "fill":       {"color": C["orange"]},
    "gap":        80,
})
# Overlay: Net Margin line
ch1.add_series({
    "name":       [CHART_SHEET, margin_row, STAGE_COL],
    "categories": make_cats(ncols),
    "values":     make_ref(margin_row, ncols),
    "type":       "line",
    "y2_axis":    True,
    "line":       {"color": C["red"], "width": 2.5, "dash_type": "solid"},
    "marker":     {"type": "circle", "size": 5, "fill": {"color": C["red"]},
                   "border": {"color": C["red"]}},
})

ch1.set_title({"name": f"{ticker}  —  Revenue, Gross Profit & Net Income  ($ Millions)",
               "name_font": {"bold": True, "size": 12, "color": C["navy"]}})
set_axes(ch1, "Year", "$ Millions", "Net Margin (%)")
ch1.set_size({"width": 740, "height": 380})
ws_c.insert_chart("B2", ch1)


# ────────────────────────────────────────────────────────────────────
# Chart 2: EPS (Bar) + Share Count (Line)
# ────────────────────────────────────────────────────────────────────
ch2 = add_chart("column")

eps_row,    _, _ = stage_series(ratios, "EPS ($)",                         "EPS ($)")
sh_row,     _, _ = stage_series(annual,  "commonStockSharesOutstanding",   "Shares Outstanding (M)")

ch2.add_series({
    "name":       [CHART_SHEET, eps_row, STAGE_COL],
    "categories": make_cats(ncols),
    "values":     make_ref(eps_row, ncols),
    "fill":       {"color": C["navy"]},
    "gap":        80,
})
ch2.add_series({
    "name":       [CHART_SHEET, sh_row, STAGE_COL],
    "categories": make_cats(ncols),
    "values":     make_ref(sh_row, ncols),
    "type":       "line",
    "y2_axis":    True,
    "line":       {"color": C["orange"], "width": 2},
    "marker":     {"type": "square", "size": 5,
                   "fill": {"color": C["orange"]}, "border": {"color": C["orange"]}},
})

ch2.set_title({"name": f"{ticker}  —  EPS & Shares Outstanding",
               "name_font": {"bold": True, "size": 12, "color": C["navy"]}})
set_axes(ch2, "Year", "EPS ($)", "Shares (M)")
ch2.set_size({"width": 740, "height": 380})
ws_c.insert_chart("B22", ch2)


# ────────────────────────────────────────────────────────────────────
# Chart 3: ROIC / ROE / ROA — Grouped column (capital allocation)
# ────────────────────────────────────────────────────────────────────
ch3 = add_chart("column")

roic_row, _, _ = stage_series(ratios, "ROIC (%)", "ROIC (%)")
roe_row,  _, _ = stage_series(ratios, "ROE (%)",  "ROE (%)")
roa_row,  _, _ = stage_series(ratios, "ROA (%)",  "ROA (%)")

for drow, color in [(roic_row, C["navy"]),
                    (roe_row,  C["blue"]),
                    (roa_row,  C["light_blue"])]:
    ch3.add_series({
        "name":       [CHART_SHEET, drow, STAGE_COL],
        "categories": make_cats(ncols),
        "values":     make_ref(drow, ncols),
        "fill":       {"color": color},
        "gap":        60,
    })

ch3.set_title({"name": f"{ticker}  —  Return Metrics: ROIC / ROE / ROA",
               "name_font": {"bold": True, "size": 12, "color": C["navy"]}})
set_axes(ch3, "Year", "Return (%)")
ch3.set_size({"width": 740, "height": 380})
ws_c.insert_chart("L2", ch3)


# ────────────────────────────────────────────────────────────────────
# Chart 4: P/E Ratio over time (Valuation Bands) + FCF Yield
# ────────────────────────────────────────────────────────────────────
ch4 = add_chart("line")

pe_row,  _, _ = stage_series(ratios, "P/E Ratio",    "P/E Ratio")
ps_row,  _, _ = stage_series(ratios, "P/S Ratio",    "P/S Ratio")
fcfy_row,_, _ = stage_series(ratios, "FCF Yield (%)", "FCF Yield (%)")

for drow, color, y2 in [
    (pe_row,   C["navy"],   False),
    (ps_row,   C["blue"],   False),
    (fcfy_row, C["green"],  True),
]:
    ch4.add_series({
        "name":       [CHART_SHEET, drow, STAGE_COL],
        "categories": make_cats(ncols),
        "values":     make_ref(drow, ncols),
        "line":       {"color": color, "width": 2.5},
        "marker":     {"type": "circle", "size": 4,
                       "fill": {"color": color}, "border": {"color": color}},
        "y2_axis":    y2,
    })

ch4.set_title({"name": f"{ticker}  —  Historical Valuation: P/E, P/S  &  FCF Yield",
               "name_font": {"bold": True, "size": 12, "color": C["navy"]}})
set_axes(ch4, "Year", "Multiple (x)", "FCF Yield (%)")
ch4.set_size({"width": 740, "height": 380})
ws_c.insert_chart("L22", ch4)


# ────────────────────────────────────────────────────────────────────
# Chart 5: Free Cash Flow & Operating Cash Flow
# ────────────────────────────────────────────────────────────────────
ch5 = add_chart("column")

ocf_row, _, _ = stage_series(annual, "operatingCashflow",  "Operating Cash Flow ($M)")
fcf_row, _, _ = stage_series(annual, "capitalExpenditures","CapEx ($M)")

ch5.add_series({
    "name":       [CHART_SHEET, ocf_row, STAGE_COL],
    "categories": make_cats(ncols),
    "values":     make_ref(ocf_row, ncols),
    "fill":       {"color": C["green"]},
    "gap":        80,
})
ch5.add_series({
    "name":       [CHART_SHEET, fcf_row, STAGE_COL],
    "categories": make_cats(ncols),
    "values":     make_ref(fcf_row, ncols),
    "fill":       {"color": C["red"]},
    "gap":        80,
})

ch5.set_title({"name": f"{ticker}  —  Cash Generation: Operating Cash Flow vs CapEx",
               "name_font": {"bold": True, "size": 12, "color": C["navy"]}})
set_axes(ch5, "Year", "$ Millions")
ch5.set_size({"width": 740, "height": 380})
ws_c.insert_chart("B42", ch5)


# ────────────────────────────────────────────────────────────────────
# Chart 6: Debt-to-Equity + Net Debt Trend
# ────────────────────────────────────────────────────────────────────
ch6 = add_chart("line")

de_row,  _, _ = stage_series(ratios, "Debt to Equity", "Debt-to-Equity")
nd_row,  _, _ = stage_series(ratios, "Net Debt ($M)",  "Net Debt ($M)")

ch6.add_series({
    "name":       [CHART_SHEET, de_row, STAGE_COL],
    "categories": make_cats(ncols),
    "values":     make_ref(de_row, ncols),
    "line":       {"color": C["red"], "width": 2.5},
    "marker":     {"type": "diamond", "size": 5,
                   "fill": {"color": C["red"]}, "border": {"color": C["red"]}},
})
ch6.add_series({
    "name":       [CHART_SHEET, nd_row, STAGE_COL],
    "categories": make_cats(ncols),
    "values":     make_ref(nd_row, ncols),
    "type":       "column",
    "y2_axis":    True,
    "fill":       {"color": C["orange"]},
    "gap":        80,
})

ch6.set_title({"name": f"{ticker}  —  Leverage: Debt-to-Equity & Net Debt",
               "name_font": {"bold": True, "size": 12, "color": C["navy"]}})
set_axes(ch6, "Year", "D/E Ratio (x)", "Net Debt ($M)")
ch6.set_size({"width": 740, "height": 380})
ws_c.insert_chart("L42", ch6)


# ──────────────────────────────────────────────────────────────────────────────
# 11.  REORDER SHEETS: Dashboard first
# ──────────────────────────────────────────────────────────────────────────────
ws_d.activate()
ws_d.set_first_sheet()


# ──────────────────────────────────────────────────────────────────────────────
# 12.  CLOSE & SAVE
# ──────────────────────────────────────────────────────────────────────────────

writer.close()

print(f"\n{'='*60}")
print(f"  ✅  Report saved successfully!")
print(f"  📂  {output_file}")
print(f"{'='*60}")
print(f"  Sheets:  Dashboard | Annual | Quarterly | Ratios | Charts")
print(f"  Charts:  Revenue/Margin combo | EPS/Shares | ROIC/ROE/ROA")
print(f"           P/E Valuation Bands | Cash Flow | Leverage Trend")
print(f"  Extras:  Sparklines | Conditional Formatting | TTM Column")
print(f"           Graham Number | Owner Earnings | FCF Yield")
print(f"{'='*60}\n")
