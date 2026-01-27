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
        total_equity = df_balance.loc['totalShareholderEquity', col] if 'totalShareholderEquity' in df_balance.index else 0
        current_assets = df_balance.loc['totalCurrentAssets', col] if 'totalCurrentAssets' in df_balance.index else 0
        current_liabilities = df_balance.loc['totalCurrentLiabilities', col] if 'totalCurrentLiabilities' in df_balance.index else 0
        total_debt = df_balance.loc['shortLongTermDebtTotal', col] if 'shortLongTermDebtTotal' in df_balance.index else 0
        cash = df_balance.loc['cashAndCashEquivalentsAtCarryingValue', col] if 'cashAndCashEquivalentsAtCarryingValue' in df_balance.index else 0
        inventory = df_balance.loc['inventory', col] if 'inventory' in df_balance.index else 0
        fcf = df_cashflow.loc['operatingCashflow', col] if 'operatingCashflow' in df_cashflow.index else 0
        
        market_cap = float(overview.get('MarketCapitalization', 0)) / 1_000_000 if overview.get('MarketCapitalization') else 0
        
        col_ratios['P/E Ratio'] = market_cap / net_income if net_income != 0 else None
        col_ratios['P/S Ratio'] = market_cap / revenue if revenue != 0 else None
        col_ratios['P/B Ratio'] = market_cap / total_equity if total_equity != 0 else None
        col_ratios['ROE (%)'] = (net_income / total_equity * 100) if total_equity != 0 else None
        col_ratios['ROA (%)'] = (net_income / total_assets * 100) if total_assets != 0 else None
        col_ratios['ROIC (%)'] = (net_income / (total_equity + total_debt) * 100) if (total_equity + total_debt) != 0 else None
        col_ratios['Current Ratio'] = current_assets / current_liabilities if current_liabilities != 0 else None
        col_ratios['Quick Ratio'] = (current_assets - inventory) / current_liabilities if current_liabilities != 0 else None
        col_ratios['Debt to Equity'] = total_debt / total_equity if total_equity != 0 else None
        col_ratios['FCF Yield (%)'] = (fcf / market_cap * 100) if market_cap != 0 else None
        
        # Dividend Yield - FIXED BY MANUS
        div_val = overview.get('DividendPerShare')
        dividend_per_share = float(div_val) if div_val and div_val != 'None' else 0
        col_ratios['Dividend Yield (%)'] = (dividend_per_share / (market_cap / (df_income.loc['commonStockSharesOutstanding', col] if 'commonStockSharesOutstanding' in df_income.index else 1)) * 100) if market_cap != 0 else 0
        
        ratios[col] = col_ratios
        
    return pd.DataFrame(ratios)

# 11. חישוב יחסים
print("Calculating financial ratios...")
ratios_df = calculate_ratios(df_income_annual, df_balance_annual, df_cashflow_annual, overview_data)

# 12. שמירה לאקסל
output_file = f"{ticker}_financial_report.xlsx"
with pd.ExcelWriter(output_file, engine='xlsxwriter') as writer:
    annual_report.to_excel(writer, sheet_name='Annual')
    quarterly_report.to_excel(writer, sheet_name='Quarterly')
    ratios_df.to_excel(writer, sheet_name='Financial Ratios')
    
    # הוספת גרפים (אופציונלי)
    workbook = writer.book
    worksheet = writer.sheets['Annual']
    
print(f"\n✅ SUCCESS! Complete report created: {output_file}")
