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
st.set_page_config(
page_title="سفارش غذای روزانه",
page_icon="🍚",
layout="centered",
initial_sidebar_state="collapsed"
)

st.markdown("""

""", unsafe_allow_html=True)

st.title("🍚 سفارش غذای روزانه")

try:
sh = get_sheet()
except Exception:
st.warning("برای اجرای کامل نیاز به تنظیمات گوگل شیت دارید.")
sh = None

if "logged_in" not in st.session_state:
st.session_state.logged_in = False
st.session_state.user_code = None
st.session_state.user_name = None
st.session_state.is_admin = False

if not st.session_state.logged_in:
st.markdown("### ورود با کد اختصاصی")
code_input = st.text_input("کد خود را وارد کنید", placeholder="مثلاً 1234 یا ADMIN", key="login_code")

col1, col2 = st.columns(2)
with col1:
    if st.button("ورود", type="primary", use_container_width=True):
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
                if not match.empty and match.iloc[0].get("active", True):
                    st.session_state.logged_in = True
                    st.session_state.is_admin = False
                    st.session_state.user_code = code
                    st.session_state.user_name = match.iloc[0]["name"]
                    st.rerun()
                else:
                    st.error("کد نامعتبر است یا غیرفعال شده")
            else:
                st.session_state.logged_in = True
                st.session_state.is_admin = False
                st.session_state.user_code = code
                st.session_state.user_name = f"کاربر {code}"
                st.rerun()

with col2:
    st.caption("کد را از مدیر سیستم بگیرید")

st.stop()

now = get_tehran_now()
today_str = now.strftime("%Y-%m-%d")
menu_item, day_name = get_today_menu(now)
before_deadline = is_before_deadline(now)

col_header1, col_header2 = st.columns([3, 1])
with col_header1:
st.markdown(f"
سلام {st.session_state.user_name} 👋")
with col_header2:
if st.button("خروج"):
for key in list(st.session_state.keys()):
del st.session_state[key]
st.rerun()

st.divider()

if st.session_state.is_admin:
st.header("🛠️ پنل مدیریت")

tab1, tab2, tab3 = st.tabs(["📊 سفارش‌های امروز", "👥 مدیریت کاربران", "📈 تاریخچه"])

if sh is None:
    st.warning("اتصال به گوگل شیت برقرار نیست.")

with tab1:
    st.subheader(f"سفارش‌های {day_name} ({today_str})")
    if menu_item:
        st.info(f"منوی امروز: **{menu_item}**")
    else:
        st.warning("امروز منو تعریف نشده (جمعه)")
    
    if sh is not None:
        orders_df = load_orders(sh)
        today_orders = orders_df[orders_df["date"] == today_str].copy() if not orders_df.empty else pd.DataFrame()
        
        if today_orders.empty:
            st.write("هنوز هیچ سفارشی ثبت نشده.")
        else:
            today_orders = today_orders.sort_values("timestamp").drop_duplicates(subset=["code"], keep="last")
            
            yes_df = today_orders[today_orders["wants"].isin(["بله", True, "TRUE", "yes", 1])]
            no_df = today_orders[~today_orders["wants"].isin(["بله", True, "TRUE", "yes", 1])]
            
            st.metric("تعداد سفارش (بله)", len(yes_df))
            
            st.markdown("#### ✅ کسانی که غذا می‌خواهند:")
            if not yes_df.empty:
                st.dataframe(yes_df[["name", "code", "timestamp"]].reset_index(drop=True), use_container_width=True)
            else:
                st.write("—")
            
            st.markdown("#### ❌ کسانی که نمی‌خواهند:")
            if not no_df.empty:
                st.dataframe(no_df[["name", "code", "timestamp"]].reset_index(drop=True), use_container_width=True)

users_df = load_users(sh)
            active_users = users_df[users_df.get("active", True) == True] if not users_df.empty else pd.DataFrame()
            if not active_users.empty:
                ordered_codes = set(today_orders["code"].astype(str))
                not_ordered = active_users[~active_users["code"].astype(str).isin(ordered_codes)]
                if not not_ordered.empty:
                    st.markdown("#### ⏳ هنوز اعلام نکرده‌اند:")
                    st.dataframe(not_ordered[["name", "code"]].reset_index(drop=True), use_container_width=True)
    else:
        st.info("در حالت آزمایشی، داده‌ای وجود ندارد.")

with tab2:
    st.subheader("افزودن کاربر جدید")
    with st.form("add_user_form"):
        new_code = st.text_input("کد کاربر (مثلاً 1001)")
        new_name = st.text_input("نام کامل")
        submitted = st.form_submit_button("افزودن")
        if submitted:
            if new_code and new_name and sh is not None:
                success = add_user(sh, new_code, new_name)
                if success:
                    st.success(f"کاربر «{new_name}» با کد {new_code} اضافه شد.")
                    st.cache_data.clear()
                else:
                    st.error("این کد قبلاً وجود دارد.")
            else:
                st.error("کد و نام را پر کنید.")
    
    if sh is not None:
        st.subheader("لیست کاربران")
        users_df = load_users(sh)
        if not users_df.empty:
            st.dataframe(users_df, use_container_width=True)
        else:
            st.write("هنوز کاربری ثبت نشده.")

with tab3:
    st.subheader("تاریخچه سفارش‌ها")
    if sh is not None:
        orders_df = load_orders(sh)
        if not orders_df.empty:
            dates = sorted(orders_df["date"].unique(), reverse=True)
            selected_date = st.selectbox("انتخاب تاریخ", dates)
            filtered = orders_df[orders_df["date"] == selected_date]
            st.dataframe(filtered, use_container_width=True)
            
            yes_count = len(filtered[filtered["wants"].isin(["بله", True, "TRUE", "yes", 1])])
            st.metric(f"تعداد بله در {selected_date}", yes_count)
        else:
            st.write("هنوز سفارشی ثبت نشده.")
    else:
        st.info("اتصال برقرار نیست.")

else:
st.markdown(f"### امروز: 
{day_name}")

if menu_item is None:
    st.warning("امروز (جمعه) سرویس غذایی نداریم.")
    st.stop()

st.markdown(f"""
<div class="menu-box">
    <div style="font-size: 0.9em; color: #666;">منوی امروز</div>
    <div class="big-font">{menu_item}</div>
</div>
""", unsafe_allow_html=True)

now_time_str = now.strftime("%H:%M")
if before_deadline:
    remaining = datetime.combine(now.date(), DEADLINE) - datetime.combine(now.date(), now.time())
    mins = int(remaining.total_seconds() // 60)
    st.success(f"✅ مهلت ثبت سفارش تا ۱۱:۳۰ باز است (الان {now_time_str} — حدود {mins} دقیقه مانده)")
else:
    st.error(f"⏰ مهلت تمام شده (الان {now_time_str}). دیگر نمی‌توانید سفارش ثبت کنید.")

already_ordered = False
previous_wants = None
if sh is not None:
    orders_df = load_orders(sh)
    if not orders_df.empty:
        user_today = orders_df[
            (orders_df["date"] == today_str) & 
            (orders_df["code"].astype(str) == str(st.session_state.user_code))
        ]
        if not user_today.empty:
            already_ordered = True
            last = user_today.sort_values("timestamp").iloc[-1]
            previous_wants = last["wants"] in ["بله", True, "TRUE", "yes", 1]

if already_ordered:
    status = "✅ بله، غذا می‌خواهم" if previous_wants else "❌ خیر، نمی‌خواهم"
    st.info(f"شما قبلاً اعلام کرده‌اید: **{status}**")
    if before_deadline:
        st.caption("می‌توانید نظر خود را تغییر دهید (آخرین اعلام

