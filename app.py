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

st.set_page_config(page_title="سفارش غذای روزانه", page_icon="🍚", layout="centered")

st.title("🍚 سفارش غذای روزانه")

try:
    sh = get_sheet()
    st.success("اتصال به گوگل شیت برقرار شد")
except Exception as e:
    st.error(f"خطای اتصال به شیت: {e}")
    sh = None

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_code = None
    st.session_state.user_name = None
    st.session_state.is_admin = False

if not st.session_state.logged_in:
    st.markdown("### ورود با کد اختصاصی")
    code_input = st.text_input("کد خود را وارد کنید", placeholder="مثلاً 1234 یا ADMIN")
    
    if st.button("ورود", type="primary"):
        if not code_input:
            st.error("کد را وارد کنید")
        else:
            code = code_input.strip()
            if code.upper() == st.secrets.get("ADMIN_CODE", "ADMIN").upper():
                st.session_state.logged_in = True
                st.session_state.is_admin = True
                st.session_state.user_code = "ADMIN"
                st.session_state.user_name = "مدیر"
                st.rerun()
            elif sh is not None:
                users_df = load_users(sh)
                match = users_df[users_df["code"].astype(str).str.strip() == code]
                if not match.empty:
                    st.session_state.logged_in = True
                    st.session_state.is_admin = False
                    st.session_state.user_code = code
                    st.session_state.user_name = match.iloc[0]["name"]
                    st.rerun()
                else:
                    st.error("کد نامعتبر است")
            else:
                st.session_state.logged_in = True
                st.session_state.user_code = code
                st.session_state.user_name = f"کاربر {code}"
                st.rerun()
    st.stop()

now = get_tehran_now()
today_str = now.strftime("%Y-%m-%d")
menu_item, day_name = get_today_menu(now)
before_deadline = is_before_deadline(now)

st.markdown(f"**سلام {st.session_state.user_name}** 👋")
if st.button("خروج"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

st.divider()

if st.session_state.is_admin:
    st.header("🛠️ پنل مدیریت")
    tab1, tab2, tab3 = st.tabs(["سفارش‌های امروز", "مدیریت کاربران", "تاریخچه"])
    
    with tab1:
        st.subheader(f"سفارش‌های {day_name}")
        if menu_item:
            st.info(f"منوی امروز: **{menu_item}**")
        if sh is not None:
            orders_df = load_orders(sh)
            today_orders = orders_df[orders_df["date"] == today_str] if not orders_df.empty else pd.DataFrame()
            if today_orders.empty:
                st.write("هنوز سفارشی ثبت نشده.")
            else:
                today_orders = today_orders.sort_values("timestamp").drop_duplicates(subset=["code"], keep="last")
                yes_df = today_orders[today_orders["wants"].isin(["بله", True, "TRUE", "yes", 1])]
                st.metric("تعداد بله", len(yes_df))
                st.dataframe(yes_df[["name", "code", "timestamp"]])
    
    with tab2:
        with st.form("add_user"):
            new_code = st.text_input("کد کاربر")
            new_name = st.text_input("نام")
            if st.form_submit_button("افزودن") and new_code and new_name and sh:
                if add_user(sh, new_code, new_name):
                    st.success("کاربر اضافه شد")
                else:
                    st.error("کد تکراری است")
        if sh is not None:
            st.dataframe(load_users(sh))
    
    with tab3:
        if sh is not None:
            orders_df = load_orders(sh)
            if not orders_df.empty:
                st.dataframe(orders_df)
else:
    st.markdown(f"### امروز: **{day_name}**")
    
    if menu_item is None:
        st.warning("امروز سرویس نداریم.")
        st.stop()
    
    st.markdown(f"### منوی امروز: **{menu_item}**")
    
    if before_deadline:
        st.success("مهلت ثبت سفارش باز است (تا ۱۱:۳۰)")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("بله، می‌خواهم", type="primary"):
                try:
                    if sh is not None:
                        save_order(sh, today_str, st.session_state.user_code, st.session_state.user_name, True)
                        st.success("✅ سفارش شما ثبت شد: بله")
                        st.balloons()
                        st.rerun()
                    else:
                        st.error("اتصال به شیت برقرار نیست")
                except Exception as e:
                    st.error(f"خطا در ثبت سفارش: {e}")
        with col2:
            if st.button("خیر، نمی‌خواهم"):
                try:
                    if sh is not None:
                        save_order(sh, today_str, st.session_state.user_code, st.session_state.user_name, False)
                        st.success("✅ اعلام شما ثبت شد: خیر")
                        st.rerun()
                    else:
                        st.error("اتصال به شیت برقرار نیست")
                except Exception as e:
                    st.error(f"خطا در ثبت: {e}")
    else:
        st.error("مهلت تمام شده است.")
