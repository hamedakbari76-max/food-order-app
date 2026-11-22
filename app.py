from datetime import datetime, time
from zoneinfo import ZoneInfo

from google.oauth2 import service_account
from google.oauth2.service_account import Credentials
import gspread
import pandas as pd
import streamlit as st

# ==================== تنظیمات ====================
TEHRAN_TZ = ZoneInfo("Asia/Tehran")
DEADLINE = time(11, 30)  # ساعت ۱۱:۳۰

# منوی ثابت هفتگی (weekday پایتون: دوشنبه=0 ... شنبه=5 یکشنبه=6)
MENU = {
    5: "کوبیده",  # شنبه
    6: "قرمه سبزی",  # یکشنبه
    0: "جوجه کباب",  # دوشنبه
    1: "قیمه",  # سه‌شنبه
    2: "عدس پلو",  # چهارشنبه
    3: "جوجه کباب",  # پنجشنبه
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

USERS_HEADERS = ["code", "name", "active"]
ORDERS_HEADERS = ["date", "code", "name", "wants", "timestamp"]
YES_VALUES = {"بله", "true", "1", "yes", "بله می‌خواهم"}


# ==================== اتصال به گوگل شیت ====================
@st.cache_resource
def get_gspread_client():
  """ساخت کلاینت gspread از روی Streamlit Secrets یا فایل محلی."""
  scopes = [
      "https://www.googleapis.com/auth/spreadsheets",
      "https://www.googleapis.com/auth/drive",
  ]
  if "gcp_service_account" in st.secrets:
    creds_dict = dict(st.secrets["gcp_service_account"])
    credentials = service_account.Credentials.from_service_account_info(
        creds_dict, scopes=scopes
    )
    return gspread.authorize(credentials)

  credentials = Credentials.from_service_account_file(
      "credentials.json", scopes=scopes
  )
  return gspread.authorize(credentials)


def get_sheet():
  """باز کردن گوگل شیت با نام تعریف‌شده در Secrets."""
  client = get_gspread_client()
  sheet_name = st.secrets.get("SHEET_NAME", "FoodOrders")
  return client.open(sheet_name)


def get_or_create_worksheet(sh, title, headers):
  """دریافت تب موردنظر یا ساخت آن همراه با ردیف سرستون."""
  try:
    ws = sh.worksheet(title)
  except gspread.WorksheetNotFound:
    ws = sh.add_worksheet(title=title, rows=1000, cols=max(10, len(headers)))
    ws.append_row(headers)
    return ws

  first_row = ws.row_values(1)
  if not first_row:
    ws.append_row(headers)
  return ws


# ==================== توابع کمکی ====================
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


def is_yes(val):
  if isinstance(val, bool):
    return val
  return str(val).strip().lower() in YES_VALUES


def load_users(sh):
  ws = get_or_create_worksheet(sh, "Users", USERS_HEADERS)
  data = ws.get_all_records(expected_headers=USERS_HEADERS)
  if not data:
    return pd.DataFrame(columns=USERS_HEADERS)

  df = pd.DataFrame(data)
  df["code"] = df["code"].astype(str).str.strip()
  df["name"] = df["name"].astype(str).str.strip()
  df["active"] = (
      df["active"]
      .astype(str)
      .str.strip()
      .str.lower()
      .isin(["true", "1", "yes", "بله"])
  )
  return df


def load_orders(sh):
  ws = get_or_create_worksheet(sh, "Orders", ORDERS_HEADERS)
  data = ws.get_all_records(expected_headers=ORDERS_HEADERS)
  if not data:
    return pd.DataFrame(columns=ORDERS_HEADERS)

  df = pd.DataFrame(data)
  df["date"] = df["date"].astype(str).str.strip()
  df["code"] = df["code"].astype(str).str.strip()
  df["name"] = df["name"].astype(str).str.strip()
  df["timestamp"] = df["timestamp"].astype(str).str.strip()
  return df


def save_order(sh, date_str, code, name, wants):
  ws = get_or_create_worksheet(sh, "Orders", ORDERS_HEADERS)
  now_str = get_tehran_now().strftime("%Y-%m-%d %H:%M:%S")
  ws.append_row(
      [str(date_str).strip(), str(code).strip(), str(name).strip(), "بله" if wants else "خیر", now_str]
  )


def add_user(sh, code, name):
  ws = get_or_create_worksheet(sh, "Users", USERS_HEADERS)
  clean_code = str(code).strip()
  clean_name = str(name).strip()

  existing = ws.get_all_records(expected_headers=USERS_HEADERS)
  for row in existing:
    if str(row.get("code", "")).strip() == clean_code:
      return False

  ws.append_row([clean_code, clean_name, "TRUE"])
  return True


# ==================== رابط کاربری ====================
st.set_page_config(
    page_title="سفارش غذای روزانه",
    page_icon="🍚",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
<style>
    .stButton > button {
        width: 100%;
        height: 3em;
        font-size: 1.15em;
    }
    .big-font {
        font-size: 1.4em !important;
        font-weight: bold;
    }
    .menu-box {
        background-color: #f0f2f6;
        color: #111111;
        padding: 1.2em;
        border-radius: 12px;
        text-align: center;
        margin: 1em 0;
    }
</style>
""",
    unsafe_allow_html=True,
)

st.title("🍚 سفارش غذای روزانه")

# اتصال به گوگل شیت
try:
  sh = get_sheet()
except gspread.SpreadsheetNotFound:
  st.error(
      "شیت پیدا نشد. نام شیت در `SHEET_NAME` را بررسی کنید و شیت را با ایمیل"
      " Service Account (با دسترسی Editor) به اشتراک بگذارید."
  )
  st.stop()
except Exception as e:
  st.error(f"خطا در اتصال به گوگل شیت: {e}")
  st.stop()

# وضعیت ورود
if "logged_in" not in st.session_state:
  st.session_state.logged_in = False
  st.session_state.user_code = None
  st.session_state.user_name = None
  st.session_state.is_admin = False

# ==================== صفحه ورود ====================
if not st.session_state.logged_in:
  st.markdown("### ورود با کد اختصاصی")
  code_input = st.text_input(
      "کد خود را وارد کنید", placeholder="مثلاً 1234 یا ADMIN", key="login_code"
  )

  col1, col2 = st.columns(2)
  with col1:
    if st.button("ورود", type="primary", use_container_width=True):
      code = code_input.strip()
      if not code:
        st.error("لطفاً کد را وارد کنید.")
      else:
        admin_code = str(st.secrets.get("ADMIN_CODE", "ADMIN")).strip().upper()
        if code.upper() == admin_code:
          st.session_state.logged_in = True
          st.session_state.is_admin = True
          st.session_state.user_code = "ADMIN"
          st.session_state.user_name = "مدیر"
          st.rerun()
        else:
          users_df = load_users(sh)
          match = users_df[users_df["code"] == code]
          if not match.empty and bool(match.iloc[0]["active"]):
            st.session_state.logged_in = True
            st.session_state.is_admin = False
            st.session_state.user_code = code
            st.session_state.user_name = match.iloc[0]["name"]
            st.rerun()
          else:
            st.error("کد نامعتبر است یا کاربر غیرفعال شده است.")

  with col2:
    st.caption("کد ورود را از مدیر سیستم دریافت کنید.")

  st.stop()

# ==================== کاربر وارد شده ====================
now = get_tehran_now()
today_str = now.strftime("%Y-%m-%d")
menu_item, day_name = get_today_menu(now)
before_deadline = is_before_deadline(now)

col_header1, col_header2 = st.columns([3, 1])
with col_header1:
  st.markdown(f"**سلام {st.session_state.user_name}** 👋")
with col_header2:
  if st.button("خروج", use_container_width=True):
    for key in list(st.session_state.keys()):
      del st.session_state[key]
    st.rerun()

st.divider()

# ==================== پنل ادمین ====================
if st.session_state.is_admin:
  st.header("🛠️ پنل مدیریت")
  tab1, tab2, tab3 = st.tabs(
      ["📊 سفارش‌های امروز", "👥 مدیریت کاربران", "📈 تاریخچه"]
  )

  with tab1:
    st.subheader(f"سفارش‌های {day_name} ({today_str})")
    if menu_item:
      st.info(f"منوی امروز: **{menu_item}**")
    else:
      st.warning("امروز (جمعه) منو تعریف نشده است.")

    orders_df = load_orders(sh)
    today_orders = (
        orders_df[orders_df["date"] == today_str].copy()
        if not orders_df.empty
        else pd.DataFrame(columns=ORDERS_HEADERS)
    )

    if today_orders.empty:
      st.write("هنوز هیچ سفارشی برای امروز ثبت نشده است.")
    else:
      today_orders = today_orders.sort_values("timestamp").drop_duplicates(
          subset=["code"], keep="last"
      )
      wants_bool = today_orders["wants"].apply(is_yes)
      yes_df = today_orders[wants_bool]
      no_df = today_orders[~wants_bool]

      st.metric("تعداد سفارش (بله)", len(yes_df))

      st.markdown("#### ✅ کسانی که غذا می‌خواهند:")
      if not yes_df.empty:
        st.dataframe(
            yes_df[["name", "code", "timestamp"]].reset_index(drop=True),
            use_container_width=True,
        )
      else:
        st.write("—")

      st.markdown("#### ❌ کسانی که نمی‌خواهند:")
      if not no_df.empty:
        st.dataframe(
            no_df[["name", "code", "timestamp"]].reset_index(drop=True),
            use_container_width=True,
        )
      else:
        st.write("—")

      users_df = load_users(sh)
      active_users = (
          users_df[users_df["active"]]
          if not users_df.empty
          else pd.DataFrame(columns=USERS_HEADERS)
      )
      if not active_users.empty:
        ordered_codes = set(today_orders["code"])
        not_ordered = active_users[~active_users["code"].isin(ordered_codes)]
        if not not_ordered.empty:
          st.markdown("#### ⏳ هنوز اعلام نکرده‌اند:")
          st.dataframe(
              not_ordered[["name", "code"]].reset_index(drop=True),
              use_container_width=True,
          )

  with tab2:
    st.subheader("افزودن کاربر جدید")
    with st.form("add_user_form", clear_on_submit=True):
      new_code = st.text_input("کد کاربر (مثلاً 1001)")
      new_name = st.text_input("نام کامل")
      submitted = st.form_submit_button("افزودن")
      if submitted:
        if new_code.strip() and new_name.strip():
          created = add_user(sh, new_code, new_name)
          if created:
            st.success(f"کاربر «{new_name.strip()}» با کد {new_code.strip()} اضافه شد.")
            st.rerun()
          else:
            st.error("این کد کاربری قبلاً ثبت شده است.")
        else:
          st.error("لطفاً هم کد و هم نام را وارد کنید.")

    st.subheader("لیست کاربران")
    users_df = load_users(sh)
    if not users_df.empty:
      st.dataframe(users_df, use_container_width=True)
    else:
      st.write("هنوز کاربری ثبت نشده است.")

  with tab3:
    st.subheader("تاریخچه سفارش‌ها")
    orders_df = load_orders(sh)
    if not orders_df.empty:
      dates = sorted(orders_df["date"].unique(), reverse=True)
      selected_date = st.selectbox("انتخاب تاریخ", dates)
      filtered = orders_df[orders_df["date"] == selected_date]
      st.dataframe(filtered, use_container_width=True)

      yes_count = int(filtered["wants"].apply(is_yes).sum())
      st.metric(f"تعداد «بله» در {selected_date}", yes_count)
    else:
      st.write("هنوز سفارشی ثبت نشده است.")

# ==================== پنل کاربر عادی ====================
else:
  st.markdown(f"### امروز: **{day_name}**")

  if menu_item is None:
    st.warning("امروز (جمعه) سرویس غذایی نداریم.")
    st.stop()

  st.markdown(
      f"""
    <div class="menu-box">
        <div style="font-size: 0.9em; color: #555;">منوی امروز</div>
        <div class="big-font">{menu_item}</div>
    </div>
    """,
      unsafe_allow_html=True,
  )

  now_time_str = now.strftime("%H:%M")
  if before_deadline:
    remaining = datetime.combine(now.date(), DEADLINE) - datetime.combine(
        now.date(), now.time()
    )
    mins = max(0, int(remaining.total_seconds() // 60))
    st.success(
        f"✅ مهلت ثبت سفارش تا ۱۱:۳۰ باز است (الان {now_time_str} — حدود {mins}"
        " دقیقه مانده)"
    )
  else:
    st.error(
        f"⏰ مهلت ثبت سفارش تمام شده است (الان {now_time_str}). امکان ثبت یا"
        " تغییر وجود ندارد."
    )

  already_ordered = False
  previous_wants = None
  orders_df = load_orders(sh)
  if not orders_df.empty:
    user_today = orders_df[
        (orders_df["date"] == today_str)
        & (orders_df["code"] == str(st.session_state.user_code))
    ]
    if not user_today.empty:
      already_ordered = True
      last_row = user_today.sort_values("timestamp").iloc[-1]
      previous_wants = is_yes(last_row["wants"])

  if already_ordered:
    status_text = (
        "✅ بله، غذا می‌خواهم" if previous_wants else "❌ خیر، نمی‌خواهم"
    )
    st.info(f"آخرین وضعیت ثبت‌شده شما: **{status_text}**")
    if before_deadline:
      st.caption("تا قبل از ۱۱:۳۰ می‌توانید نظر خود را تغییر دهید.")

  if before_deadline:
    st.markdown("#### آیا امروز غذا می‌خواهید؟")
    col_yes, col_no = st.columns(2)

    with col_yes:
      if st.button("✅ بله، می‌خواهم", type="primary", use_container_width=True):
        save_order(
            sh,
            today_str,
            st.session_state.user_code,
            st.session_state.user_name,
            True,
        )
        st.session_state["just_ordered"] = "بله"
        st.rerun()

    with col_no:
      if st.button("❌ خیر، نمی‌خواهم", use_container_width=True):
        save_order(
            sh,
            today_str,
            st.session_state.user_code,
            st.session_state.user_name,
            False,
        )
        st.session_state["just_ordered"] = "خیر"
        st.rerun()

    if st.session_state.get("just_ordered"):
      st.toast(f"وضعیت شما ({st.session_state['just_ordered']}) ثبت شد.")
      del st.session_state["just_ordered"]
  else:
    if not already_ordered:
      st.warning("شما امروز در مهلت مقرر وضعیتی ثبت نکرده‌اید.")

st.divider()
st.caption("سیستم سفارش غذای داخلی • نسخه ۱.۱")
