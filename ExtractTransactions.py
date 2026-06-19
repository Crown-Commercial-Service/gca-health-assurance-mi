import os
import shutil
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
import urllib.parse
import struct
from sqlalchemy import create_engine
from azure.identity import InteractiveBrowserCredential
from dotenv import load_dotenv

load_dotenv()

DB_SERVER = os.getenv('DB_SERVER')
DB_DRIVER = os.getenv('DB_DRIVER')
TABLE_NAME_CUSTOMERS = os.getenv('TABLE_NAME_CUSTOMERS')
TABLE_NAME_SUPPLIERS = os.getenv('TABLE_NAME_SUPPLIERS')

export_directory = "./data"

# this is the number of months from the present day that you want to look back across
n_months = 9

# Format the query
query = {}
with open("sample.tsv") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        supplier, rm_numbers = line.split('\t', 1)
        query[supplier.strip()] = [r.strip() for r in rm_numbers.split(',')]

# Function to calculate financial year and month
def calculate_financial_year_and_month(n_months):

    today = datetime.today()
    date = today - relativedelta(months=n_months)

    if date.month >= 4:
        financial_year = f"{date.year}/{date.year + 1}"
        financial_month = date.month - 3
    else:
        financial_year = f"{date.year - 1}/{date.year}"
        financial_month = date.month + 9
    return financial_year, financial_month

F_year, F_month = calculate_financial_year_and_month(n_months)
present_year, present_month = calculate_financial_year_and_month(0)
print(f"Start of time period of interest: financial year {F_year}, financial month {F_month}")
print(f"End of time period of interest: financial year {present_year}, financial month {present_month}")
date_today = datetime.today().strftime("%Y-%m-%d")

def get_token_based_engine(db_server, db_name, db_driver):
    """
    Create a SQLAlchemy engine with token-based authentication for Purview compatibility.
    """
    # We do not include the UID or Authentication type in the string anymore,
    # because the token handles the identity payload securely.
    odbc_conn_str = (
        f"DRIVER={db_driver};"
        f"SERVER={db_server};"
        f"DATABASE={db_name};"
        f"Encrypt=yes;"
        f"TrustServerCertificate=no;"
    )
    # 1. Trigger the browser prompt to get the token
    credential = InteractiveBrowserCredential()
    # The scope specifically required for Azure SQL Database
    token_obj = credential.get_token("https://database.windows.net/.default")
    
    # 2. Format the token exactly how the ODBC driver requires it (UTF-16-LE + length)
    token_bytes = token_obj.token.encode("UTF-16-LE")
    token_struct = struct.pack(f'<I{len(token_bytes)}s', len(token_bytes), token_bytes)
    
    # 3. Apply the token to the connection arguments (1256 is the constant for SQL_COPT_SS_ACCESS_TOKEN)
    SQL_COPT_SS_ACCESS_TOKEN = 1256
    connect_args = {"attrs_before": {SQL_COPT_SS_ACCESS_TOKEN: token_struct}}

    # 4. Create the SQLAlchemy engine
    params = urllib.parse.quote_plus(odbc_conn_str)
    engine = create_engine(
        f"mssql+pyodbc:///?odbc_connect={params}", 
        connect_args=connect_args
    )
    return engine

# Connect to the database using token-based authentication
engine = get_token_based_engine(DB_SERVER, os.getenv('DB_NAME_CUSTOMERS'), DB_DRIVER)
# Open a connection
conn_customer = engine.connect()

# Read in customers
sql = f"""
SELECT DISTINCT 
    "CustomerKey" AS "CustomerURN", 
    "Country", 
    "MarketSector", 
    "RecordExpiredDate", 
    "SectorNew", 
    "NUTSRegion2"  -- Added double quotes here for consistency
FROM {TABLE_NAME_CUSTOMERS} 
WHERE "Country" IN ('England', 'GBR', 'United Kingdom') 
  AND "RecordExpiredDate" IS NULL 
  AND "MarketSector" = 'Health' 
  AND "SectorNew" = 'Wider Public Sector'
"""
eng_customers = pd.read_sql(sql, conn_customer)
print(eng_customers.shape)
eng_customers['CustomerURN'] = eng_customers['CustomerURN'].astype(int).astype(str)
print(eng_customers.shape)


# Connect to the database using token-based authentication
engine = get_token_based_engine(DB_SERVER, os.getenv('DB_NAME_SUPPLIERS'), DB_DRIVER)
# Open a connection
conn_supplier = engine.connect()

# Get supplier details
sql = f"""
SELECT DISTINCT 
    "SupplierKey", 
    "DUNSNumber", 
    "SupplierName" 
FROM {TABLE_NAME_SUPPLIERS}
"""
suppliers = pd.read_sql(sql, conn_supplier)
suppliers = suppliers.dropna(axis=0)
# Format columns
suppliers['SupplierKey'] = suppliers['SupplierKey'].astype(int).astype(str)
# Remove duplicates
suppliers = suppliers.drop_duplicates(subset = 'SupplierKey')
# Set index
suppliers.set_index('SupplierKey', drop = True, inplace = True)

# Connect to the database using token-based authentication
engine = get_token_based_engine(DB_SERVER, os.getenv('DB_NAME_MI'), DB_DRIVER)
# Open a connection
conn_RM = engine.connect()

sup_list = list(set(suppliers['SupplierName']))

for i in query.items():
    print(i)

# Check that suppliers exist
for i in query.keys():
    if i not in list(set(suppliers['SupplierName'])):
        print('Supplier ' + i + ' was not found')
possible = [i for i in set(suppliers['SupplierName']) if 'manpower'.lower() in i.lower()]

# Generate a directory
if not os.path.isdir(export_directory):
    os.mkdir(export_directory)
export_directory = os.path.join(export_directory, date_today)
if not os.path.isdir(export_directory):
    os.mkdir(export_directory)

for supplier, frameworks in query.items():
    supplier_temp = supplier.replace("'", "''")
    for framework in frameworks:
        sql_query = f"""
        SELECT * FROM mi.MI_{framework} 
        WHERE SupplierName = '{supplier_temp}' 
        AND (FinancialYear > '{F_year}' OR (FinancialYear = '{F_year}' AND FinancialMonth >= {F_month})) 
        AND (FinancialYear < '{present_year}' OR (FinancialYear = '{present_year}' AND FinancialMonth <= {present_month}))
        """

        # print(sql_query)
        df = pd.read_sql(sql_query, conn_RM)
        # print(df.shape)

        # Keep customers that are in GBR or England
        df['CustomerURN'] = df['CustomerURN'].astype(int).astype(str)
        # print(df.shape)
        df = df.loc[df['CustomerURN'].isin(eng_customers['CustomerURN'])]
        # print(df.shape)
        # Delete columns
        for col in ['EvidencedSpend', 'Shift', 'Rate of Pay', 'Rate of Pay to Worker',
                    'Supplier Fee', 'Management Fees', 'Agency Fee']:
            if col in df.columns:
                del df[col]

        few_jobs = False
        if framework in ['RM6161','RM6160']:
            if len(set(df['Job Title'])) < 5:
                few_jobs = True
        else:
            if 'Staff or Fee Type ' in df.columns:
                if len(set(df['Staff or Fee Type '])) < 5:
                    few_jobs = True

        full_sample = False
        if len(df) == 0:
            print('No records for', supplier, 'on framework', framework)
            continue
        elif len(df) > 1000:
            sample = df.sample(1000)
            full_sample = True
            request = sample.sample(int(len(sample)/100*60))
        elif 1000 >= len(df) > 600:
            request = df.sample(600)
        else:
            request = df.copy()

        # URN Request
        if 'DatePopulated' in request.columns:
            del request['DatePopulated']
        request['Worker Unique Reference Number'] = None

        # Export the data
        if full_sample and few_jobs:
            sample.to_csv(os.path.join(export_directory, supplier + '_' + framework + '_FullSample_FewJobs.csv'), index = False)
        elif full_sample:
            sample.to_csv(os.path.join(export_directory, supplier + '_' + framework + '_FullSample.csv'), index = False)

        request.to_csv(os.path.join(export_directory, supplier + '_' + framework + '_URNRequest.csv'), index = False)

# Compress the export directory into a zip archive
zip_path = shutil.make_archive(export_directory, 'zip', export_directory)
print(f"Export compressed to: {zip_path}")
        