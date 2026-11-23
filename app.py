
import streamlit as st
import pandas as pd
import hashlib
import hmac
import secrets
from datetime import datetime, time
from zoneinfo import ZoneInfo
import gspread
from google.oauth2.service_account import Credentials
from google.oauth2 import service_account

TEHRAN_TZ = ZoneInfo("Asia/Tehran")
DEADLINE = time(11, 30)
PASSWORD_ITERATIONS = 300000

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


# -------------------------------
# رمزنگاری و بررسی رمز عبور
# -------------------------------

def hash_password(password):
    salt = secrets.token_hex(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PASSWORD_ITERATIONS
    ).hex()

    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt}${password_hash}"


def verify_password(password, stored_hash):
    try:
        algorithm, iterations, salt, expected_hash = stored_hash.split("$")

        if algorithm != "pbkdf2_sha256":
            return False

        actual_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iterations)
        ).hex()

        return hmac.compare_digest(actual_hash, expected_hash)

    except Exception:
        return False


# -------------------------------
# اتصال به گوگل شیت
# -------------------------------

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
        st.error(f"خطای اتصال به گوگل: {e}")
        st.stop()


def get_sheet():
    client = get_gspread_client()
    sheet_name = st.secrets.get("SHEET_NAME", "foodorder")

    try:
        return client.open(sheet_name)
    except gspread.SpreadsheetNotFound:
        st.error(f"فایل {sheet_name} پیدا نشد.")
        st.stop()


def get_or_create_worksheet(sh, title, headers):
    try:
        ws = sh.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=title, rows=1000, cols=10)
        ws.append_row(headers)

    return ws


def ensure_users_headers(sh):
    headers = ["code", "name", "active", "password_hash"]
    ws = get_or_create_worksheet(sh, "Users", headers)

    current = ws.row_values(1)

    for i, header in enumerate(headers):
        if i >= len(current) or not str(current[i]).strip():
            ws.update_cell(1, i + 1, header)

    return ws


def ensure_orders_headers(sh):
    headers = [
        "date", "code", "name",
        "wants", "timestamp", "description"
    ]

    ws = get_or_create_worksheet(sh, "Orders", headers)
    current = ws.row_values(1)

    for i, header in enumerate(headers):
        if i >= len(current) or not str(current[i]).strip():
            ws.update_cell(1, i + 1, header)

    return ws


# -------------------------------
# تاریخ و منوی روز
# -------------------------------

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
    return MENU.get(wd), DAY_NAMES.get(wd, "")


# -------------------------------
# کاربران
# -------------------------------

def load_users(sh):
    ws = ensure_users_headers(sh)
    data = ws.get_all_records()
    df = pd.DataFrame(data)

    if df.empty:
        return pd.DataFrame(
            columns=["code", "name", "active", "password_hash"]
        )

    for column in ["code", "name", "active", "password_hash"]:
        if column not in df.columns:
            df[column] = ""

    df["active"] = (
        df["active"].astype(str).str.lower()
        .isin(["true", "1", "yes", "بله"])
    )

    df["code"] = df["code"].astype(str).str.strip()
    df["name"] = df["name"].astype(str).str.strip()
    df["password_hash"] = df["password_hash"].fillna("").astype(str)

    return df


def add_user(sh, code, name, password):
    ws = ensure_users_headers(sh)
    existing = load_users(sh)

    code = str(code).strip()

    if existing["code"].astype(str).str.strip().eq(code).any():
        return False

    ws.append_row([
        code,
        name.strip(),
        "TRUE",
        hash_password(password)
    ], value_input_option="USER_ENTERED")

    return True


def update_user_password(sh, code, new_password):
    ws = ensure_users_headers(sh)
    all_rows = ws.get_all_records()

    for row_number, row in enumerate(all_rows, start=2):
        if str(row.get("code", "")).strip() == str(code).strip():
            ws.update_cell(
                row_number,
                4,
                hash_password(new_password)
            )
            return True

    return False


# -------------------------------
# سفارش‌ها
# -------------------------------

def load_orders(sh):
    ws = ensure_orders_headers(sh)
    data = ws.get_all_records()
    df = pd.DataFrame(data)

    if df.empty:
        return pd.DataFrame(columns=[
            "date", "code", "name",
            "wants", "timestamp", "description"
        ])

    if "description" not in df.columns:
        df["description"] = ""

    return df


def save_order(sh, date_str, code, name, wants, description):
    ws = ensure_orders_headers(sh)

    now_str = get_tehran_now().strftime("%Y-%m-%d %H:%M:%S")

    ws.append_row([
        date_str,
        code,
        name,
        "بله" if wants else "خیر",
        now_str,
        description.strip()
    ], value_input_option="USER_ENTERED")


# -------------------------------
# تنظیمات صفحه
# -------------------------------

st.set_page_config(
    page_title="سفارش غذای روزانه",
    page_icon="🍚",
    layout="centered"
)

st.title("🍚 سفارش غذای روزانه")

try:
    sh = get_sheet()
    st.success("اتصال به گوگل شیت برقرار شد")
except Exception as e:
    st.error(f"خطای اتصال به شیت: {e}")
    sh = None


# -------------------------------
# وضعیت ورود
# -------------------------------

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_code = None
    st.session_state.user_name = None
    st.session_state.is_admin = False


# -------------------------------
# صفحه ورود با رمز
# -------------------------------

if not st.session_state.logged_in:

    st.markdown("### 🔐 ورود به حساب کاربری")

    login_code = st.text_input(
        "نام کاربری یا کد اختصاصی",
        placeholder="کد اختصاصی خود را وارد کنید"
    )

    login_password = st.text_input(
        "رمز عبور",
        type="password"
    )

    if st.button("ورود", type="primary", use_container_width=True):

        if not login_code.strip() or not login_password:
            st.error("نام کاربری و رمز عبور را وارد کنید")

        else:
            code = login_code.strip()

            admin_username = str(
                st.secrets.get("ADMIN_USERNAME", "ADMIN")
            ).strip()

            admin_password = str(
                st.secrets.get("ADMIN_PASSWORD", "")
            )

            if code == admin_username:

                if not admin_password:
                    st.error(
                        "رمز مدیر در تنظیمات Secrets تعریف نشده است."
                    )

                elif hmac.compare_digest(
                    login_password, admin_password
                ):
                    st.session_state.logged_in = True
                    st.session_state.is_admin = True
                    st.session_state.user_code = "ADMIN"
                    st.session_state.user_name = "مدیر"
                    st.rerun()

                else:
                    st.error("نام کاربری یا رمز عبور اشتباه است")

            elif sh is not None:

                users_df = load_users(sh)

                match = users_df[
                    (users_df["code"] == code)
                    & (users_df["active"] == True)
                ]

                if match.empty:
                    st.error("نام کاربری یا رمز عبور اشتباه است")

                else:
                    user = match.iloc[0]
                    saved_hash = str(user["password_hash"]).strip()

                    if not saved_hash:
                        st.error(
                            "برای حساب شما هنوز رمزی تعیین نشده است. "
                            "از مدیر بخواهید برایتان رمز تعریف کند."
                        )

                    elif verify_password(login_password, saved_hash):
                        st.session_state.logged_in = True
                        st.session_state.is_admin = False
                        st.session_state.user_code = code
                        st.session_state.user_name = user["name"]
                        st.rerun()

                    else:
                        st.error("نام کاربری یا رمز عبور اشتباه است")

            else:
                st.error("اتصال به شیت برقرار نیست")

    st.stop()


# -------------------------------
# اطلاعات روز
# -------------------------------

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


# -------------------------------
# پنل مدیریت
# -------------------------------

if st.session_state.is_admin:

    st.header("🛠️ پنل مدیریت")

    tab1, tab2, tab3 = st.tabs([
        "سفارش‌های امروز",
        "مدیریت کاربران",
        "تاریخچه"
    ])

    with tab1:

        st.subheader(f"سفارش‌های {day_name}")

        if menu_item:
            st.info(f"منوی امروز: **{menu_item}**")

        if sh is not None:

            orders_df = load_orders(sh)

            today_orders = (
                orders_df[orders_df["date"] == today_str]
                if not orders_df.empty
                else pd.DataFrame()
            )

            if today_orders.empty:
                st.write("هنوز سفارشی ثبت نشده.")

            else:
                today_orders = (
                    today_orders.sort_values("timestamp")
                    .drop_duplicates(subset=["code"], keep="last")
                )

                yes_df = today_orders[
                    today_orders["wants"].isin(
                        ["بله", True, "TRUE", "yes", 1]
                    )
                ]

                no_df = today_orders[
                    today_orders["wants"].isin(
                        ["خیر", False, "FALSE", "no", 0]
                    )
                ]

                col1, col2, col3 = st.columns(3)
                col1.metric("تعداد بله", len(yes_df))
                col2.metric("تعداد خیر", len(no_df))
                col3.metric("کل پاسخ‌ها", len(today_orders))

                st.markdown("### 📋 پاسخ و توضیحات کاربران")

                st.dataframe(
                    today_orders[
                        ["name", "code", "wants",
                         "description", "timestamp"]
                    ].rename(columns={
                        "name": "نام",
                        "code": "کد",
                        "wants": "پاسخ",
                        "description": "توضیحات",
                        "timestamp": "زمان ثبت"
                    }),
                    use_container_width=True,
                    hide_index=True
                )

    with tab2:

        st.subheader("مدیریت کاربران")

        st.markdown("#### افزودن کاربر جدید")

        with st.form("add_user_form"):

            new_code = st.text_input("کد یا نام کاربری جدید")
            new_name = st.text_input("نام کاربر")
            new_password = st.text_input(
                "رمز عبور کاربر",
                type="password"
            )
            confirm_password = st.text_input(
                "تکرار رمز عبور",
                type="password"
            )

            add_submitted = st.form_submit_button("افزودن کاربر")

            if add_submitted:

                if not new_code.strip() or not new_name.strip():
                    st.error("کد و نام کاربر را وارد کنید")

                elif len(new_password) < 8:
                    st.error("رمز عبور باید حداقل ۸ کاراکتر باشد")

                elif new_password != confirm_password:
                    st.error("رمز عبور و تکرار آن یکسان نیستند")

                elif sh is not None:

                    try:
                        if add_user(
                            sh, new_code, new_name, new_password
                        ):
                            st.success("کاربر با موفقیت اضافه شد")
                            st.rerun()
                        else:
                            st.error("این کد کاربری قبلاً ثبت شده است")

                    except Exception as e:
                        st.error(f"خطا در افزودن کاربر: {e}")

        st.divider()

        st.markdown("#### تغییر یا تعیین رمز کاربران")

        if sh is not None:

            users_df = load_users(sh)

            if users_df.empty:
                st.info("هنوز کاربری ثبت نشده است")

            else:

                user_options = {
                    f"{row['name']} - {row['code']}": row["code"]
                    for _, row in users_df.iterrows()
                }

                selected_label = st.selectbox(
                    "انتخاب کاربر",
                    list(user_options.keys())
                )

                selected_code = user_options[selected_label]

                with st.form("change_password_form"):

                    reset_password = st.text_input(
                        "رمز جدید",
                        type="password"
                    )

                    reset_confirm = st.text_input(
                        "تکرار رمز جدید",
                        type="password"
                    )

                    reset_submitted = st.form_submit_button(
                        "ثبت رمز جدید"
                    )

                    if reset_submitted:

                        if len(reset_password) < 8:
                            st.error(
                                "رمز عبور باید حداقل ۸ کاراکتر باشد"
                            )

                        elif reset_password != reset_confirm:
                            st.error("دو رمز واردشده یکسان نیستند")

                        else:
                            try:
                                if update_user_password(
                                    sh, selected_code, reset_password
                                ):
                                    st.success(
                                        "رمز کاربر با موفقیت تغییر کرد"
                                    )
                                else:
                                    st.error("کاربر پیدا نشد")

                            except Exception as e:
                                st.error(f"خطا در تغییر رمز: {e}")

            st.divider()
            st.markdown("#### فهرست کاربران")

            if not users_df.empty:
                st.dataframe(
                    users_df[["code", "name", "active"]].rename(
                        columns={
                            "code": "کد کاربر",
                            "name": "نام",
                            "active": "فعال"
                        }
                    ),
                    use_container_width=True,
                    hide_index=True
                )

    with tab3:

        st.subheader("تاریخچه سفارش‌ها")

        if sh is not None:

            orders_df = load_orders(sh)

            if not orders_df.empty:

                st.dataframe(
                    orders_df.rename(columns={
                        "date": "تاریخ",
                        "code": "کد",
                        "name": "نام",
                        "wants": "پاسخ",
                        "timestamp": "زمان ثبت",
                        "description": "توضیحات"
                    }),
                    use_container_width=True,
                    hide_index=True
                )


# -------------------------------
# صفحه کاربران
# -------------------------------

else:

    st.markdown(f"### امروز: **{day_name}**")

    if menu_item is None:
        st.warning("امروز سرویس نداریم.")
        st.stop()

    st.markdown(f"### منوی امروز: **{menu_item}**")

    if before_deadline:

        st.success("مهلت ثبت سفارش باز است (تا ۱۱:۳۰)")

        st.markdown("### 📝 توضیحات و درخواست‌های خاص")

        description = st.text_area(
            "اگر توضیحی دارید اینجا بنویسید (اختیاری)",
            placeholder="مثلاً لطفاً برنج کمتر باشد...",
            max_chars=500,
            key="order_description"
        )

        st.caption(
            "توضیحات شما همراه پاسخ بله یا خیر ثبت می‌شود."
        )

        col1, col2 = st.columns(2)

        with col1:

            if st.button("بله، می‌خواهم", type="primary"):

                try:
                    if sh is not None:
                        save_order(
                            sh,
                            today_str,
                            st.session_state.user_code,
                            st.session_state.user_name,
                            True,
                            description
                        )

                        st.success("✅ سفارش شما با موفقیت ثبت شد")
                        st.balloons()

                    else:
                        st.error("اتصال به شیت برقرار نیست")

                except Exception as e:
                    st.error(f"خطا در ثبت سفارش: {e}")

        with col2:

            if st.button("خیر، نمی‌خواهم"):

                try:
                    if sh is not None:
                        save_order(
                            sh,
                            today_str,
                            st.session_state.user_code,
                            st.session_state.user_name,
                            False,
                            description
                        )

                        st.success("✅ پاسخ شما با موفقیت ثبت شد")

                    else:
                        st.error("اتصال به شیت برقرار نیست")

                except Exception as e:
                    st.error(f"خطا در ثبت پاسخ: {e}")

    else:
        st.error("مهلت ثبت سفارش تمام شده است.")
