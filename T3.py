import pandas as pd
import requests
from datetime import datetime
import time

# 1. הגדרות וקלט
ticker = input("Enter stock symbol (e.g., MSFT, AAPL, GOOGL): ").strip().upper()
api_key = "YOUR_ALPHA_VANTAGE_KEY_HERE"

print(f"Fetching financial data for {ticker}...")


# 2. פונקציה לשליפת נתונים עם טיפול שגיאות
def fetch_data(url, data_type):
    try:
        response = requests.get(url)
        data = response.json()

        # בדיקת שגיאות API
        if "Error Message" in data:
            print(f"❌ Error: {data['Error Message']}")
            return None

        if "Note" in data:
            print(f"⚠️ API Limit: {data['Note']}")
            print("Please wait 60 seconds or upgrade your API plan...")
            return None

        if "Information" in data:
            print(f"ℹ️ {data['Information']}")
            return None

        return data
    except Exception as e:
        print(f"❌ Error fetching {data_type}: {str(e)}")
        return None


# 3. פנייה ל-Alpha Vantage עם המתנה בין קריאות
print("Fetching Income Statement...")
income_data = fetch_data(
    f'https://www.alphavantage.co/query?function=INCOME_STATEMENT&symbol={ticker}&apikey={api_key}',
    "Income Statement"
)
time.sleep(12)

print("Fetching Balance Sheet...")
balance_data = fetch_data(
    f'https://www.alphavantage.co/query?function=BALANCE_SHEET&symbol={ticker}&apikey={api_key}',
    "Balance Sheet"
)
time.sleep(12)

print("Fetching Cash Flow...")
cashflow_data = fetch_data(
    f'https://www.alphavantage.co/query?function=CASH_FLOW&symbol={ticker}&apikey={api_key}',
    "Cash Flow"
)
time.sleep(12)

print("Fetching Overview...")
overview_data = fetch_data(
    f'https://www.alphavantage.co/query?function=OVERVIEW&symbol={ticker}&apikey={api_key}',
    "Overview"
)

# בדיקה שכל הנתונים התקבלו
if not income_data or "annualReports" not in income_data:
    print("\n❌ Error: Could not fetch income data.")
    print("Possible reasons:")
    print("1. Invalid API Key")
    print("2. Invalid Ticker Symbol")
    print("3. API Rate Limit (free tier: 5 calls/minute, 500 calls/day)")
    print("\nPlease check your API key at: https://www.alphavantage.co/support/#api-key")
    exit()

if not balance_data or "annualReports" not in balance_data:
    print("⚠️ Warning: Could not fetch balance sheet data")
    balance_data = {"annualReports": [], "quarterlyReports": []}

if not cashflow_data or "annualReports" not in cashflow_data:
    print("⚠️ Warning: Could not fetch cash flow data")
    cashflow_data = {"annualReports": [], "quarterlyReports": []}

if not overview_data:
    print("⚠️ Warning: Could not fetch overview data")
    overview_data = {}


# 4. פונקציה לעיבוד נתונים
def process_financial_data(reports, divide_by_million=True):
    if not reports or len(reports) == 0:
        return pd.DataFrame()

    df = pd.DataFrame(reports)

    if 'fiscalDateEnding' not in df.columns:
        return pd.DataFrame()

    df = df.set_index('fiscalDateEnding').transpose()

    # המרה למספרים
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    # חלוקה במיליון
    if divide_by_million:
        df = df / 1_000_000

    return df


# 5. עיבוד נתונים שנתיים
print("\nProcessing annual data...")
df_income_annual = process_financial_data(income_data.get('annualReports', []))
df_balance_annual = process_financial_data(balance_data.get('annualReports', []))
df_cashflow_annual = process_financial_data(cashflow_data.get('annualReports', []))

# 6. עיבוד נתונים רבעוניים
print("Processing quarterly data...")
df_income_quarterly = process_financial_data(income_data.get('quarterlyReports', [])[:8])
df_balance_quarterly = process_financial_data(balance_data.get('quarterlyReports', [])[:8])
df_cashflow_quarterly = process_financial_data(cashflow_data.get('quarterlyReports', [])[:8])

# 7. סדר השורות לפי דוח רווח והפסד
income_order = [
    'totalRevenue',
    'costOfRevenue',
    'grossProfit',
    'operatingExpenses',
    'sellingGeneralAndAdministrative',
    'researchAndDevelopment',
    'operatingIncome',
    'interestIncome',
    'interestExpense',
    'netInterestIncome',
    'otherNonOperatingIncome',
    'incomeBeforeTax',
    'incomeTaxExpense',
    'netIncome',
    'ebitda',
    'depreciation',
    'depreciationAndAmortization'
]


# 8. פונקציה לסידור הדוח
def arrange_financial_statement(df_income, df_balance, df_cashflow):
    combined = pd.concat([df_income, df_balance, df_cashflow])
    combined = combined[~combined.index.duplicated(keep='first')]

    existing_rows = [r for r in income_order if r in combined.index]
    other_rows = [r for r in combined.index if r not in income_order]

    final_df = combined.reindex(existing_rows + other_rows)

    # הוספת שורת מניות נסחרות
    if 'commonStockSharesOutstanding' in final_df.index:
        shares_row = final_df.loc[['commonStockSharesOutstanding']].copy()
        final_df = final_df.drop('commonStockSharesOutstanding')

        # חישוב רווח למניה
        if 'netIncome' in final_df.index:
            eps_row = final_df.loc[['netIncome']].copy()
            eps_row.index = ['earningsPerShare']
            for col in eps_row.columns:
                if col in shares_row.columns and shares_row.loc['commonStockSharesOutstanding', col] > 0:
                    eps_row.loc['earningsPerShare', col] = (
                            final_df.loc['netIncome', col] / shares_row.loc['commonStockSharesOutstanding', col]
                    )

            final_df = pd.concat([shares_row, eps_row, final_df])
        else:
            final_df = pd.concat([shares_row, final_df])

    return final_df


# 9. סידור הנתונים
annual_report = arrange_financial_statement(df_income_annual, df_balance_annual, df_cashflow_annual)
quarterly_report = arrange_financial_statement(df_income_quarterly, df_balance_quarterly, df_cashflow_quarterly)


# 10. חישוב יחסים פיננסים
def calculate_ratios(df_income, df_balance, df_cashflow, overview):
    ratios = {}

    for col in df_income.columns:
        col_ratios = {}

        revenue = df_income.loc['totalRevenue', col] if 'totalRevenue' in df_income.index else 0
        net_income = df_income.loc['netIncome', col] if 'netIncome' in df_income.index else 0
        total_assets = df_balance.loc['totalAssets', col] if 'totalAssets' in df_balance.index else 0
        total_equity = df_balance.loc[
            'totalShareholderEquity', col] if 'totalShareholderEquity' in df_balance.index else 0
        current_assets = df_balance.loc['totalCurrentAssets', col] if 'totalCurrentAssets' in df_balance.index else 0
        current_liabilities = df_balance.loc[
            'totalCurrentLiabilities', col] if 'totalCurrentLiabilities' in df_balance.index else 0
        total_debt = df_balance.loc[
            'shortLongTermDebtTotal', col] if 'shortLongTermDebtTotal' in df_balance.index else 0
        cash = df_balance.loc[
            'cashAndCashEquivalentsAtCarryingValue', col] if 'cashAndCashEquivalentsAtCarryingValue' in df_balance.index else 0
        inventory = df_balance.loc['inventory', col] if 'inventory' in df_balance.index else 0
        fcf = df_cashflow.loc['operatingCashflow', col] if 'operatingCashflow' in df_cashflow.index else 0

        market_cap = float(overview.get('MarketCapitalization', 0)) / 1_000_000 if overview.get(
            'MarketCapitalization') else 0

        col_ratios['P/E Ratio'] = market_cap / net_income if net_income != 0 else None
        col_ratios['P/S Ratio'] = market_cap / revenue if revenue != 0 else None
        col_ratios['P/B Ratio'] = market_cap / total_equity if total_equity != 0 else None
        col_ratios['ROE (%)'] = (net_income / total_equity * 100) if total_equity != 0 else None
        col_ratios['ROA (%)'] = (net_income / total_assets * 100) if total_assets != 0 else None
        col_ratios['ROIC (%)'] = (net_income / (total_equity + total_debt) * 100) if (
                                                                                                 total_equity + total_debt) != 0 else None
        col_ratios['Current Ratio'] = current_assets / current_liabilities if current_liabilities != 0 else None
        col_ratios['Quick Ratio'] = (
                                                current_assets - inventory) / current_liabilities if current_liabilities != 0 else None
        col_ratios['Debt to Equity'] = total_debt / total_equity if total_equity != 0 else None
        col_ratios['FCF Yield (%)'] = (fcf / market_cap * 100) if market_cap != 0 else None

        # Dividend Yield
        dividend_per_share = float(overview.get('DividendPerShare', 0)) if overview.get('DividendPerShare') else 0
        current_price = float(overview.get('50DayMovingAverage', 0)) if overview.get('50DayMovingAverage') else 0
        col_ratios['Dividend Yield (%)'] = (dividend_per_share / current_price * 100) if current_price != 0 else None

        if 'PEGRatio' in overview:
            col_ratios['PEG Ratio'] = float(overview['PEGRatio']) if overview['PEGRatio'] != 'None' else None

        ratios[col] = col_ratios

    return pd.DataFrame(ratios).T


# 11. חישוב יחסים
ratios_df = calculate_ratios(df_income_annual, df_balance_annual, df_cashflow_annual, overview_data)

# 12. יצירת קובץ Excel
output_file = f"{ticker}_Complete_Financial_Report.xlsx"
writer = pd.ExcelWriter(output_file, engine='xlsxwriter')

# כתיבת הגליונות
quarterly_report.to_excel(writer, sheet_name='Quarterly')
annual_report.to_excel(writer, sheet_name='Annual')
ratios_df.to_excel(writer, sheet_name='Financial Ratios')

workbook = writer.book

# פורמטים
header_fmt = workbook.add_format({
    'bold': True,
    'bg_color': '#4472C4',
    'font_color': 'white',
    'border': 1,
    'align': 'center'
})

highlight_fmt = workbook.add_format({
    'bold': True,
    'bg_color': '#FFF2CC',
    'border': 1,
    'num_format': '#,##0.00'
})

num_fmt = workbook.add_format({
    'num_format': '#,##0.00',
    'border': 1
})

ratio_fmt = workbook.add_format({
    'num_format': '#,##0.00',
    'border': 1,
    'align': 'center'
})

# 13. עיצוב גליון רבעוני
worksheet_q = writer.sheets['Quarterly']
worksheet_q.set_column('A:A', 35)
worksheet_q.set_column('B:Z', 15, num_fmt)

key_metrics = ['totalRevenue', 'grossProfit', 'operatingIncome', 'netIncome',
               'commonStockSharesOutstanding', 'earningsPerShare']

for row_num, row_name in enumerate(quarterly_report.index):
    if row_name in key_metrics:
        for col_num in range(len(quarterly_report.columns)):
            worksheet_q.write(row_num + 1, col_num + 1, quarterly_report.iloc[row_num, col_num], highlight_fmt)

# 14. עיצוב גליון שנתי
worksheet_a = writer.sheets['Annual']
worksheet_a.set_column('A:A', 35)
worksheet_a.set_column('B:Z', 15, num_fmt)

for row_num, row_name in enumerate(annual_report.index):
    if row_name in key_metrics:
        for col_num in range(len(annual_report.columns)):
            worksheet_a.write(row_num + 1, col_num + 1, annual_report.iloc[row_num, col_num], highlight_fmt)

# 15. עיצוב גליון יחסים
worksheet_r = writer.sheets['Financial Ratios']
worksheet_r.set_column('A:A', 25)
worksheet_r.set_column('B:Z', 15, ratio_fmt)

# ===== 16. יצירת גליון גרפים =====
print("\nCreating charts...")

# הכנת נתונים לגרפים - מיון לפי שנים (מהישן לחדש)
chart_data = annual_report.copy()
chart_data = chart_data[sorted(chart_data.columns, reverse=False)]  # מיון עולה

years = [col[:4] for col in chart_data.columns]  # שנים בלבד

# יצירת גליון Charts
worksheet_charts = workbook.add_worksheet('Charts')
worksheet_charts.set_column('A:Z', 2)  # עמודות צרות למראה נקי

# === גרף 1: Revenue, Gross, Operating & Net Income ===
chart1 = workbook.add_chart({'type': 'line'})

metrics_1 = {
    'totalRevenue': 'Total Revenue',
    'grossProfit': 'Gross Profit',
    'operatingIncome': 'Operating Income',
    'netIncome': 'Net Income'
}

row_start = 2
for metric_key, metric_name in metrics_1.items():
    if metric_key in chart_data.index:
        values = chart_data.loc[metric_key].tolist()

        # כתיבת הנתונים לגליון
        worksheet_charts.write(row_start, 0, metric_name)
        for col_idx, val in enumerate(values):
            # טיפול ב-NaN/INF
            if pd.isna(val) or val == float('inf') or val == float('-inf'):
                worksheet_charts.write(row_start, col_idx + 1, None)
            else:
                worksheet_charts.write(row_start, col_idx + 1, val)

        chart1.add_series({
            'name': metric_name,
            'categories': ['Charts', row_start + 1, 1, row_start + 1, len(years)],
            'values': ['Charts', row_start, 1, row_start, len(values)],
            'line': {'width': 2.5},
            'marker': {'type': 'circle', 'size': 6}
        })

        row_start += 1

# כתיבת שנים
worksheet_charts.write_row(row_start, 1, years)

chart1.set_title({'name': f'{ticker} - Revenue & Profitability ($ Millions)'})
chart1.set_x_axis({'name': 'Year', 'num_font': {'size': 10}})
chart1.set_y_axis({'name': '$ Millions', 'num_format': '#,##0'})
chart1.set_legend({'position': 'bottom'})
chart1.set_size({'width': 720, 'height': 400})
worksheet_charts.insert_chart('B2', chart1)

# === גרף 2: EPS & Share Count ===
chart2 = workbook.add_chart({'type': 'line'})
chart2_secondary = workbook.add_chart({'type': 'line'})

row_start += 3

if 'earningsPerShare' in chart_data.index:
    eps_values = chart_data.loc['earningsPerShare'].tolist()
    worksheet_charts.write(row_start, 0, 'EPS')
    for col_idx, val in enumerate(eps_values):
        if pd.isna(val) or val == float('inf') or val == float('-inf'):
            worksheet_charts.write(row_start, col_idx + 1, None)
        else:
            worksheet_charts.write(row_start, col_idx + 1, val)

    chart2.add_series({
        'name': 'Earnings Per Share',
        'categories': ['Charts', row_start + 2, 1, row_start + 2, len(years)],
        'values': ['Charts', row_start, 1, row_start, len(eps_values)],
        'line': {'color': '#4472C4', 'width': 2.5},
        'marker': {'type': 'circle', 'size': 6}
    })
    row_start += 1

if 'commonStockSharesOutstanding' in chart_data.index:
    shares_values = chart_data.loc['commonStockSharesOutstanding'].tolist()
    worksheet_charts.write(row_start, 0, 'Shares Outstanding')
    for col_idx, val in enumerate(shares_values):
        if pd.isna(val) or val == float('inf') or val == float('-inf'):
            worksheet_charts.write(row_start, col_idx + 1, None)
        else:
            worksheet_charts.write(row_start, col_idx + 1, val)

    chart2.add_series({
        'name': 'Shares Outstanding (M)',
        'categories': ['Charts', row_start + 1, 1, row_start + 1, len(years)],
        'values': ['Charts', row_start, 1, row_start, len(shares_values)],
        'y2_axis': True,
        'line': {'color': '#ED7D31', 'width': 2.5},
        'marker': {'type': 'square', 'size': 6}
    })
    row_start += 1

worksheet_charts.write_row(row_start, 1, years)

chart2.set_title({'name': f'{ticker} - EPS & Share Count'})
chart2.set_x_axis({'name': 'Year'})
chart2.set_y_axis({'name': 'EPS ($)', 'num_format': '#,##0.00'})
chart2.set_y2_axis({'name': 'Shares (Millions)', 'num_format': '#,##0'})
chart2.set_legend({'position': 'bottom'})
chart2.set_size({'width': 720, 'height': 400})
worksheet_charts.insert_chart('B25', chart2)

# === גרף 3: Return Ratios (ROE, ROA, ROIC) ===
chart3 = workbook.add_chart({'type': 'column'})

row_start += 3

ratios_to_plot = ['ROE (%)', 'ROA (%)', 'ROIC (%)']
colors = ['#70AD47', '#FFC000', '#5B9BD5']

for idx, ratio_name in enumerate(ratios_to_plot):
    if ratio_name in ratios_df.columns:
        ratio_values = [ratios_df.loc[col, ratio_name] if col in ratios_df.index else None
                        for col in chart_data.columns]

        worksheet_charts.write(row_start, 0, ratio_name)
        for col_idx, val in enumerate(ratio_values):
            if val is None or pd.isna(val) or val == float('inf') or val == float('-inf'):
                worksheet_charts.write(row_start, col_idx + 1, None)
            else:
                worksheet_charts.write(row_start, col_idx + 1, val)

        chart3.add_series({
            'name': ratio_name,
            'categories': ['Charts', row_start + 4, 1, row_start + 4, len(years)],
            'values': ['Charts', row_start, 1, row_start, len(ratio_values)],
            'fill': {'color': colors[idx]},
            'gap': 150
        })

        row_start += 1

worksheet_charts.write_row(row_start, 1, years)

chart3.set_title({'name': f'{ticker} - Return on Investment Metrics'})
chart3.set_x_axis({'name': 'Year'})
chart3.set_y_axis({'name': 'Return (%)', 'num_format': '0.0"%"'})
chart3.set_legend({'position': 'bottom'})
chart3.set_size({'width': 720, 'height': 400})
worksheet_charts.insert_chart('L2', chart3)

# === גרף 4: Valuation Ratios (P/E, P/S) ===
chart4 = workbook.add_chart({'type': 'line'})

row_start += 3

valuation_ratios = {
    'P/E Ratio': '#C00000',
    'P/S Ratio': '#7030A0'
}

for ratio_name, color in valuation_ratios.items():
    if ratio_name in ratios_df.columns:
        ratio_values = [ratios_df.loc[col, ratio_name] if col in ratios_df.index else None
                        for col in chart_data.columns]

        worksheet_charts.write(row_start, 0, ratio_name)
        for col_idx, val in enumerate(ratio_values):
            if val is None or pd.isna(val) or val == float('inf') or val == float('-inf'):
                worksheet_charts.write(row_start, col_idx + 1, None)
            else:
                worksheet_charts.write(row_start, col_idx + 1, val)

        chart4.add_series({
            'name': ratio_name,
            'categories': ['Charts', row_start + 3, 1, row_start + 3, len(years)],
            'values': ['Charts', row_start, 1, row_start, len(ratio_values)],
            'line': {'color': color, 'width': 2.5},
            'marker': {'type': 'diamond', 'size': 6}
        })

        row_start += 1

worksheet_charts.write_row(row_start, 1, years)

chart4.set_title({'name': f'{ticker} - Valuation Ratios'})
chart4.set_x_axis({'name': 'Year'})
chart4.set_y_axis({'name': 'Ratio', 'num_format': '#,##0.0'})
chart4.set_legend({'position': 'bottom'})
chart4.set_size({'width': 720, 'height': 400})
worksheet_charts.insert_chart('L25', chart4)

# === גרף 5: Dividend Yield ===
if 'Dividend Yield (%)' in ratios_df.columns:
    chart5 = workbook.add_chart({'type': 'column'})

    row_start += 3

    div_values = [ratios_df.loc[col, 'Dividend Yield (%)'] if col in ratios_df.index else None
                  for col in chart_data.columns]

    worksheet_charts.write(row_start, 0, 'Dividend Yield (%)')
    for col_idx, val in enumerate(div_values):
        if val is None or pd.isna(val) or val == float('inf') or val == float('-inf'):
            worksheet_charts.write(row_start, col_idx + 1, None)
        else:
            worksheet_charts.write(row_start, col_idx + 1, val)
    worksheet_charts.write_row(row_start + 1, 1, years)

    chart5.add_series({
        'name': 'Dividend Yield',
        'categories': ['Charts', row_start + 1, 1, row_start + 1, len(years)],
        'values': ['Charts', row_start, 1, row_start, len(div_values)],
        'fill': {'color': '#00B050'},
        'gap': 100
    })

    chart5.set_title({'name': f'{ticker} - Dividend Yield (%)'})
    chart5.set_x_axis({'name': 'Year'})
    chart5.set_y_axis({'name': 'Yield (%)', 'num_format': '0.0"%"'})
    chart5.set_legend({'position': 'bottom'})
    chart5.set_size({'width': 720, 'height': 400})
    worksheet_charts.insert_chart('B48', chart5)

writer.close()
print(f"\n✅ SUCCESS! Complete report created: {output_file}")
print(f"📊 4 Sheets: Quarterly | Annual | Financial Ratios | Charts")
print(f"📈 Charts include: Revenue/Profit, EPS, ROE/ROA/ROIC, P/E/P/S, Dividend Yield")