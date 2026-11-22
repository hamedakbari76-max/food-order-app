import streamlit as st
import pandas as pd
from datetime import datetime, time
from zoneinfo import ZoneInfo
import gspread
from google.oauth2.service_account import Credentials
from google.oauth2 import service_account

TEHRAN_TZ = ZoneInfo("Asia/Tehran")
DEADLINE = time(11, 30)

MENU = {
    5: "کوبیده",
    6: "قرمه سبزی",
    0: "جوجه کباب",
    1: "قیمه",
    2: "عدس پلو",
    3: "جوجه کباب",
}

DAY_NAMES = {
    5: "شنبه",
    6: "یکشنبه",
    0: "دوشنبه",
    1: "سه‌شنبه",
    2: "چهارشنبه",
    3: "پنجشنبه",
    4: "جمعه",
}
@st.cache_resource
def get_gspread_client():
try:
if "gcp_service_account" in st.secrets:
creds_dict = dict(st.secrets["gcp_service_account"])
scopes = [
"https://www.googleapis.com/auth/spreadsheets",
"https://www.googleapis.com/auth/drive"
]
credentials = service_account.Credentials.from_service_account_info(
creds_dict, scopes=scopes
)
return gspread.authorize(credentials)

    credentials = Credentials.from_service_account_file(
        "credentials.json",
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
    )
    return gspread.authorize(credentials)
except Exception as e:
    st.error(f"Error connecting to Google Sheet: {e}")
    st.stop()
def get_sheet():
client = get_gspread_client()
sheet_name = st.secrets.get("SHEET_NAME", "FoodOrders")
try:
sh = client.open(sheet_name)
except gspread.SpreadsheetNotFound:
st.error(f"Sheet '{sheet_name}' not found.")
st.stop()
return sh

def get_or_create_worksheet(sh, title, headers):
try:
ws = sh.worksheet(title)
except gspread.WorksheetNotFound:
ws = sh.add_worksheet(title=title, rows=1000, cols=10)
ws.append_row(headers)
return ws

def get_tehran_now():
return datetime.now(TEHRAN_TZ)

def is_before_deadline(now=None):
if now is None:
now = get_tehran_now()
return now.time() < DEADLINE

def get_today_menu(now=None):
if now is None:
now = get_tehran_now()
wd = now.weekday()
return MENU.get(wd, None), DAY_NAMES.get(wd, "")

def load_users(sh):
ws = get_or_create_worksheet(sh, "Users", ["code", "name", "active"])
data = ws.get_all_records()
df = pd.DataFrame(data)
if df.empty:
return pd.DataFrame(columns=["code", "name", "active"])
if "active" in df.columns:
df["active"] = df["active"].astype(str).str.lower().isin(["true", "1", "yes", "بله"])
return df

def load_orders(sh):
ws = get_or_create_worksheet(sh, "Orders", ["date", "code", "name", "wants", "timestamp"])
data = ws.get_all_records()
df = pd.DataFrame(data)
if df.empty:
return pd.DataFrame(columns=["date", "code", "name", "wants", "timestamp"])
return df

def save_order(sh, date_str, code, name, wants):
ws = get_or_create_worksheet(sh, "Orders", ["date", "code", "name", "wants", "timestamp"])
now_str = get_tehran_now().strftime("%Y-%m-%d %H:%M:%S")
ws.append_row([date_str, code, name, "بله" if wants else "خیر", now_str])

def add_user(sh, code, name):
ws = get_or_create_worksheet(sh, "Users", ["code", "name", "active"])
existing = ws.get_all_records()
for row in existing:
if str(row.get("code", "")).strip() == str(code).strip():
return False
ws.append_row([str(code).strip(), name.strip(), "TRUE"])
return True
