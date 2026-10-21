import streamlit as st
import pandas as pd
import hashlib
import os
import json
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- قائمة المستشفيات المعتمدة ---
HOSPITALS_LIST = [
    "مجمع الملك فيصل",
    "مستشفى الملك عبدالعزيز التخصصي",
    "مستشفى الأطفال",
    "مستشفى الصحة النفسية",
    "الإمداد العام"
]

# --- إعداد الصفحة والتصميم الأساسي ---
st.set_page_config(page_title="تتبع عمليات الشراء", layout="wide", page_icon="📋")

st.markdown("""
    <style>
    html, body, [class*="css"] {
        font-size: 1.15rem;
    }
    
    .main-title {
        text-align: center;
        color: #0073e6;
        font-size: 2.2rem;
        font-weight: bold;
        margin-top: 10px;
        margin-bottom: 25px;
    }
    
    div.stButton > button:first-child {
        background-color: #28a745;
        color: white;
        border-radius: 8px;
        font-weight: bold;
        border: none;
    }
    
    div.stButton > button:first-child:hover {
        background-color: #218838;
        color: white;
    }
    
    [data-testid="stMetricValue"] {
        font-size: 1.8rem;
        color: #0A4D68;
    }
    </style>
""", unsafe_allow_html=True)

# --- إعدادات وتشفير كلمات المرور ---
def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    return make_hashes(password) == hashed_text

# --- الربط السحابي مع Google Sheets ---
@st.cache_resource
def get_gsheet_client():
    raw_json = st.secrets["gcp_json"]
    creds_dict = json.loads(raw_json)
    
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client

def get_worksheet(worksheet_name):
    client = get_gsheet_client()
    sh = client.open("Purchase_System_DB")
    try:
        return sh.worksheet(worksheet_name)
    except Exception:
        return sh.add_worksheet(title=worksheet_name, rows="1000", cols="20")

# --- تهيئة وتحديث جداول Google Sheets تلقائياً ---
def init_cloud_db():
    ws_users = get_worksheet("users")
    users_records = ws_users.get_all_records()
    admin_pw_hash = make_hashes("admin123")
    admin_roles = "مدير النظام (Admin),رفع طلبات,مراجعة الطلبات,معتمد الطلبات,إدارة الصلاحيات,عرض الداش بورد"
    
    if not users_records:
        ws_users.update([
            ["username", "password", "roles", "status", "hospital"],
            ["admin", admin_pw_hash, admin_roles, "معتمد", "مجمع الملك فيصل"]
        ])
    else:
        df = pd.DataFrame(users_records)
        if "username" in df.columns and "admin" in df["username"].values:
            cell = ws_users.find("admin")
            if cell:
                ws_users.update_cell(cell.row, 2, admin_pw_hash)
                ws_users.update_cell(cell.row, 3, admin_roles)
                ws_users.update_cell(cell.row, 4, "معتمد")

    ws_purchases = get_worksheet("purchases")
    purchases_records = ws_purchases.get_all_records()
    if not purchases_records:
        ws_purchases.update([
            [
                "id", "requester", "hospital", "item_number", "nupco_number", "e_market_code",
                "item_name", "unit_price", "quantity", "total_cost", "importance_criteria",
                "reason", "status", "created_at", "reviewed_at", "approved_at",
                "reviewer_notes", "approver_notes", "edit_history"
            ]
        ])

init_cloud_db()

# --- جلب بيانات المستخدمين بشكل آمن ومقاوم للأخطاء ---
def get_all_users_df():
    try:
        ws_users = get_worksheet("users")
        records = ws_users.get_all_records()
        if not records:
            admin_pw_hash = make_hashes("admin123")
            admin_roles = "مدير النظام (Admin),رفع طلبات,مراجعة الطلبات,معتمد الطلبات,إدارة الصلاحيات,عرض الداش بورد"
            ws_users.update([
                ["username", "password", "roles", "status", "hospital"],
                ["admin", admin_pw_hash, admin_roles, "معتمد", "مجمع الملك فيصل"]
            ])
            return pd.DataFrame([{
                "username": "admin",
                "password": admin_pw_hash,
                "roles": admin_roles,
                "status": "معتمد",
                "hospital": "مجمع الملك فيصل"
            }])
        
        df = pd.DataFrame(records)
        df.columns = [str(c).strip() for c in df.columns]
        for col in ["username", "password", "roles", "status", "hospital"]:
            if col not in df.columns:
                df[col] = ""
        return df
    except Exception as e:
        st.error(f"خطأ في قراءة ورقة المستخدمين: {e}")
        return pd.DataFrame(columns=["username", "password", "roles", "status", "hospital"])

# --- جلب بيانات الطلبات من Google Sheets ---
def get_all_purchases_df():
    try:
        ws_purchases = get_worksheet("purchases")
        records = ws_purchases.get_all_records()
        if not records:
            return pd.DataFrame(columns=[
                "id", "requester", "hospital", "item_number", "nupco_number", "e_market_code",
                "item_name", "unit_price", "quantity", "total_cost", "importance_criteria",
                "reason", "status", "created_at", "reviewed_at", "approved_at",
                "reviewer_notes", "approver_notes", "edit_history"
            ])
        df = pd.DataFrame(records)
        df.columns = [str(c).strip() for c in df.columns]
        if "id" in df.columns:
            df["id"] = pd.to_numeric(df["id"], errors="coerce")
        return df
    except Exception as e:
        st.error(f"خطأ في جلب الطلبات: {e}")
        return pd.DataFrame()

# --- تحميل ملف الإكسل المرجعي للأصناف ---
@st.cache_data
def load_items_catalog():
    file_path = "استهلاك كل قسم على حدا.xlsx"
    if os.path.exists(file_path):
        try:
            df = pd.read_excel(file_path, engine='openpyxl')
            df['رقم نوبكو'] = df['رقم نوبكو'].astype(str).str.strip()
            df['اسم الصنف'] = df['اسم الصنف'].astype(str).str.strip()
            df['رقم البند'] = df['رقم البند'].fillna('').astype(str).str.strip()
            return df
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()

catalog_df = load_items_catalog()

# --- إدارة جلسة العمل وقيم النماذج ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.user_roles = []
    st.session_state.user_hospital = ""

if 'form_counter' not in st.session_state:
    st.session_state.form_counter = 0

if 'sel_item_num' not in st.session_state:
    st.session_state.sel_item_num = "-- اختر أو ابحث --"
if 'sel_nupco_num' not in st.session_state:
    st.session_state.sel_nupco_num = "-- اختر أو ابحث --"
if 'sel_item_name' not in st.session_state:
    st.session_state.sel_item_name = "-- اختر أو ابحث --"

if 'clear_form_flag' not in st.session_state:
    st.session_state.clear_form_flag = False

def sync_item_num_changed():
    current_key = f"sb_item_num_{st.session_state.form_counter}"
    val = st.session_state.get(current_key, "-- اختر أو ابحث --")
    if val != "-- اختر أو ابحث --" and not catalog_df.empty:
        m = catalog_df[catalog_df['رقم البند'] == str(val).strip()]
        if not m.empty:
            st.session_state.sel_item_num = str(m.iloc[0]['رقم البند'])
            st.session_state.sel_nupco_num = str(m.iloc[0]['رقم نوبكو'])
            st.session_state.sel_item_name = str(m.iloc[0]['اسم الصنف'])
            st.session_state.form_counter += 1

def sync_nupco_changed():
    current_key = f"sb_nupco_{st.session_state.form_counter}"
    val = st.session_state.get(current_key, "-- اختر أو ابحث --")
    if val != "-- اختر أو ابحث --" and not catalog_df.empty:
        m = catalog_df[catalog_df['رقم نوبكو'] == str(val).strip()]
        if not m.empty:
            st.session_state.sel_item_num = str(m.iloc[0]['رقم البند'])
            st.session_state.sel_nupco_num = str(m.iloc[0]['رقم نوبكو'])
            st.session_state.sel_item_name = str(m.iloc[0]['اسم الصنف'])
            st.session_state.form_counter += 1

def sync_name_changed():
    current_key = f"sb_name_{st.session_state.form_counter}"
    val = st.session_state.get(current_key, "-- اختر أو ابحث --")
    if val != "-- اختر أو ابحث --" and not catalog_df.empty:
        m = catalog_df[catalog_df['اسم الصنف'] == str(val).strip()]
        if not m.empty:
            st.session_state.sel_item_num = str(m.iloc[0]['رقم البند'])
            st.session_state.sel_nupco_num = str(m.iloc[0]['رقم نوبكو'])
            st.session_state.sel_item_name = str(m.iloc[0]['اسم الصنف'])
            st.session_state.form_counter += 1

def to_excel_bytes(df):
    html_content = df.to_html(index=False).encode('utf-8-sig')
    return html_content

# ==================== واجهة تسجيل الدخول والتسجيل ====================
if not st.session_state.logged_in:
    st.markdown('<div class="main-title">تتبع عمليات الشراء (سحابي - Google Sheets)</div>', unsafe_allow_html=True)
    st.markdown("---")
    
    auth_mode = st.radio("اختر العملية:", ["تسجيل الدخول", "إنشاء حساب جديد"], horizontal=True)
    st.markdown("---")
    
    if auth_mode == "تسجيل الدخول":
        st.subheader("🔑 تسجيل الدخول للنظام")
        with st.form("login_form"):
            username = st.text_input("اسم المستخدم")
            password = st.text_input("كلمة المرور", type='password')
            submit_login = st.form_submit_button("دخول")
            
            if submit_login:
                df_users = get_all_users_df()
                user_row = df_users[df_users["username"] == username]
                
                if not user_row.empty:
                    stored_pass = user_row.iloc[0]["password"]
                    roles_val = user_row.iloc[0]["roles"]
                    status_val = user_row.iloc[0]["status"]
                    hosp_val = user_row.iloc[0]["hospital"]
                    
                    if check_hashes(password, stored_pass):
                        if status_val == "معتمد":
                            st.session_state.logged_in = True
                            st.session_state.username = username
                            st.session_state.user_roles = roles_val.split(",") if roles_val else []
                            st.session_state.user_hospital = hosp_val or "مجمع الملك فيصل"
                            st.success("تم تسجيل الدخول بنجاح!")
                            st.rerun()
                        else:
                            st.warning("⚠️ حسابك قيد الانتظار أو موقوف ولم يتم اعتماده بعد.")
                    else:
                        st.error("كلمة المرور غير صحيحة.")
                else:
                    st.error("اسم المستخدم غير موجود.")

    elif auth_mode == "إنشاء حساب جديد":
        st.subheader("📝 طلب تسجيل حساب جديد")
        with st.form("signup_form"):
            new_user = st.text_input("اختر اسم مستخدم")
            new_pass = st.text_input("اختر كلمة المرور", type='password')
            selected_hospital = st.selectbox("اختر المستشفى التابع له *", HOSPITALS_LIST)
            all_available_roles = ["رفع طلبات", "مراجعة الطلبات", "معتمد الطلبات", "إدارة الصلاحيات", "عرض الداش بورد"]
            requested_roles = st.multiselect("الصلاحيات المطلوبة (اختر ما تحتاجه)", all_available_roles, default=[])
            submit_signup = st.form_submit_button("إرسال طلب التسجيل")
            
            if submit_signup:
                if new_user and new_pass and requested_roles and selected_hospital:
                    df_users = get_all_users_df()
                    if not df_users[df_users["username"] == new_user].empty:
                        st.error("❌ اسم المستخدم مستخدم مسبقاً.")
                    else:
                        ws_users = get_worksheet("users")
                        roles_str = ",".join(requested_roles)
                        ws_users.append_row([new_user, make_hashes(new_pass), roles_str, "قيد الانتظار", selected_hospital])
                        st.success("✅ تم إرسال طلبك بنجاح! ينتظر اعتماد الأدمن.")
                else:
                    st.warning("الرجاء تعبئة جميع الحقول واختيار المستشفى وصلاحية واحدة على الأقل.")

# ==================== الواجهة الرئيسية بعد تسجيل الدخول ====================
else:
    st.sidebar.title("👤 لوحة التحكم")
    st.sidebar.write(f"المستخدم: **{st.session_state.username}**")
    st.sidebar.write(f"المستشفى: **{st.session_state.user_hospital}**")
    st.sidebar.write(f"الصلاحيات: **{', '.join(st.session_state.user_roles)}**")
    
    with st.sidebar.expander("🔒 تغيير كلمة المرور"):
        with st.form("change_password_form"):
            curr_pass = st.text_input("كلمة المرور الحالية", type="password")
            new_pass1 = st.text_input("كلمة المرور الجديدة", type="password")
            new_pass2 = st.text_input("تأكيد كلمة المرور الجديدة", type="password")
            submit_pass_change = st.form_submit_button("حفظ كلمة المرور الجديدة")
            
            if submit_pass_change:
                df_users = get_all_users_df()
                user_row = df_users[df_users["username"] == st.session_state.username]
                db_pass = user_row.iloc[0]["password"] if not user_row.empty else ""
                
                if not check_hashes(curr_pass, db_pass):
                    st.error("❌ كلمة المرور الحالية غير صحيحة.")
                elif new_pass1 != new_pass2:
                    st.error("❌ كلمة المرور الجديدة وتأكيدها غير متطابقين.")
                elif len(new_pass1) < 4:
                    st.error("❌ يرجى اختيار كلمة مرور أطول.")
                else:
                    ws_users = get_worksheet("users")
                    cell = ws_users.find(st.session_state.username)
                    if cell:
                        ws_users.update_cell(cell.row, 2, make_hashes(new_pass1))
                        st.success("✅ تم تغيير كلمة المرور بنجاح!")

    if st.sidebar.button("تسجيل الخروج"):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.session_state.user_roles = []
        st.session_state.user_hospital = ""
        st.rerun()

    st.sidebar.markdown("---")
    
    screens = []
    roles = st.session_state.user_roles
    
    if "رفع طلبات" in roles or "مدير النظام (Admin)" in roles:
        screens.append("الشاشة 1: رفع طلبات (إنشاء وتتبع الطلبات)")
    if "مراجعة الطلبات" in roles or "مدير النظام (Admin)" in roles:
        screens.append("الشاشة 2: المراجعة (مستقلة لكل مستشفى)")
    if "معتمد الطلبات" in roles or "مدير النظام (Admin)" in roles:
        screens.append("الشاشة 3: الاعتماد النهائي")
    if "إدارة الصلاحيات" in roles or "مدير النظام (Admin)" in roles:
        screens.append("الشاشة 4: إدارة الصلاحيات")
    if "عرض الداش بورد" in roles or "مدير النظام (Admin)" in roles:
        screens.append("الشاشة 5: لوحة التحكّم التفصيلية (Dashboard)")

    if not screens:
        st.warning("⚠️ لا توجد لديك أي صلاحيات مفعلة حالياً. الرجاء مراجعة مدير النظام.")
        st.stop()

    selected_screen = st.sidebar.radio("التنقل بين الشاشات:", screens)
    st.sidebar.markdown("---")

    st.markdown('<div class="main-title">تتبع عمليات الشراء</div>', unsafe_allow_html=True)

    # ==================== الشاشة الأولى ====================
    if selected_screen == "الشاشة 1: رفع طلبات (إنشاء وتتبع الطلبات)":
        st.header(f"🛒 الشاشة الأولى: تقديم طلب شراء جديد ({st.session_state.user_hospital})")
        
        list_items = ["-- اختر أو ابحث --"] + (sorted([str(n) for n in catalog_df['رقم البند'].unique() if str(n).strip() != ""]) if not catalog_df.empty else [])
        list_nupco = ["-- اختر أو ابحث --"] + (sorted([str(n) for n in catalog_df['رقم نوبكو'].unique() if str(n).strip() != ""]) if not catalog_df.empty else [])
        list_names = ["-- اختر أو ابحث --"] + (sorted([str(n) for n in catalog_df['اسم الصنف'].unique() if str(n).strip() != ""]) if not catalog_df.empty else [])

        if st.session_state.get('clear_form_flag', False):
            st.session_state.sel_item_num = "-- اختر أو ابحث --"
            st.session_state.sel_nupco_num = "-- اختر أو ابحث --"
            st.session_state.sel_item_name = "-- اختر أو ابحث --"
            st.session_state.form_counter += 1
            st.session_state.clear_form_flag = False

        idx_item = list_items.index(st.session_state.sel_item_num) if st.session_state.sel_item_num in list_items else 0
        idx_nupco = list_nupco.index(st.session_state.sel_nupco_num) if st.session_state.sel_nupco_num in list_nupco else 0
        idx_name = list_names.index(st.session_state.sel_item_name) if st.session_state.sel_item_name in list_names else 0

        cnt = st.session_state.form_counter

        def_e_market = "" if not st.session_state.get('reset_fields', False) else ""
        def_price = 0.0 if not st.session_state.get('reset_fields', False) else 0.0
        def_qty = 1 if not st.session_state.get('reset_fields', False) else 1
        def_reason = "" if not st.session_state.get('reset_fields', False) else ""
        
        if st.session_state.get('reset_fields', False):
            st.session_state.reset_fields = False

        col1, col2, col3 = st.columns(3)
        
        with col1:
            item_num_val = st.selectbox(
                "1. رقم البند (ابحث أو اختر) *",
                options=list_items,
                index=idx_item,
                key=f"sb_item_num_{cnt}",
                on_change=sync_item_num_changed
            )
            
            nupco_num_val = st.selectbox(
                "2. رقم نوبكو (ابحث أو اختر) *",
                options=list_nupco,
                index=idx_nupco,
                key=f"sb_nupco_{cnt}",
                on_change=sync_nupco_changed
            )
            
            e_market_code = st.text_input("3. كود السوق الالكتروني *", value=def_e_market, key=f"input_e_market_{cnt}")

        with col2:
            item_name_val = st.selectbox(
                "4. اسم الصنف (ابحث أو اختر) *",
                options=list_names,
                index=idx_name,
                key=f"sb_name_{cnt}",
                on_change=sync_name_changed
            )
            
            unit_price = st.number_input("5. السعر الافرادي (ر.س) *", min_value=0.0, step=1.0, value=def_price, key=f"input_unit_price_{cnt}")
            quantity = st.number_input("6. الكمية المطلوبة *", min_value=1, step=1, value=def_qty, key=f"input_quantity_{cnt}")

        with col3:
            importance_criteria = st.selectbox("7. معيار الأهمية *", ["عالي جداً (حرج)", "عالي", "متوسط", "منخفض"], key=f"sb_importance_{cnt}")
            reason = st.text_area("8. السبب / المبررات (اختياري)", value=def_reason, key=f"input_reason_{cnt}")

        total_cost = unit_price * quantity
        st.markdown(f"**إجمالي التكلفة المحسوبة:** `{total_cost:,.2f} ر.س`")

        if st.button("إرسال الطلب", use_container_width=True):
            str_item_num = str(item_num_val).strip() if item_num_val != "-- اختر أو ابحث --" else ""
            str_nupco_num = str(nupco_num_val).strip() if nupco_num_val != "-- اختر أو ابحث --" else ""
            str_item_name = str(item_name_val).strip() if item_name_val != "-- اختر أو ابحث --" else ""

            if not str_item_num:
                st.error("❌ حقل 'رقم البند' إلزامي.")
            elif not str_nupco_num:
                st.error("❌ حقل 'رقم نوبكو' إلزامي.")
            elif not e_market_code.strip():
                st.error("❌ حقل 'كود السوق الالكتروني' إلزامي.")
            elif not str_item_name:
                st.error("❌ حقل 'اسم الصنف' إلزامي.")
            elif unit_price <= 0:
                st.error("❌ يرجى إدخال 'سعر أفرادي' أعلى من الصفر.")
            elif quantity <= 0:
                st.error("❌ يرجى إدخال 'كمية' أعلى من الصفر.")
            else:
                df_all_p = get_all_purchases_df()
                new_id = int(df_all_p["id"].max()) + 1 if not df_all_p.empty and not pd.isna(df_all_p["id"].max()) else 1
                
                ws_purchases = get_worksheet("purchases")
                ws_purchases.append_row([
                    new_id, st.session_state.username, st.session_state.user_hospital,
                    str_item_num, str_nupco_num, e_market_code.strip(), str_item_name,
                    unit_price, quantity, total_cost, importance_criteria, reason,
                    "قيد المراجعة", datetime.now().strftime("%Y-%m-%d %H:%M"), "", "", "", "", ""
                ])
                
                st.session_state.clear_form_flag = True
                st.session_state.reset_fields = True
                st.success("✅ تم إرسال طلب الشراء بنجاح سحابياً ومسح البيانات الحالية لتقديم طلب جديد!")
                st.rerun()

        st.markdown("---")
        st.subheader("📋 سجل طلباتك السابقة")
        df_all_p = get_all_purchases_df()
        df_my_orders = df_all_p[df_all_p["requester"] == st.session_state.username] if not df_all_p.empty else pd.DataFrame()
        
        if not df_my_orders.empty:
            df_my_orders = df_my_orders.rename(columns={
                "id": "رقم الطلب", "hospital": "المستشفى", "item_number": "رقم البند",
                "nupco_number": "رقم نوبكو", "e_market_code": "كود السوق الإلكتروني",
                "item_name": "اسم الصنف", "unit_price": "السعر الأفرادي", "quantity": "الكمية",
                "total_cost": "الإجمالي", "importance_criteria": "معيار الأهمية", "reason": "السبب",
                "status": "الحالة", "created_at": "تاريخ الإنشاء", "reviewed_at": "تاريخ ووقت المراجعة",
                "approved_at": "تاريخ ووقت الاعتماد النهائي", "reviewer_notes": "ملاحظات المراجعة",
                "approver_notes": "ملاحظات الاعتماد", "edit_history": "سجل التعديلات"
            })
        st.dataframe(df_my_orders, use_container_width=True)

    # ==================== الشاشة الثانية ====================
    elif selected_screen == "الشاشة 2: المراجعة (مستقلة لكل مستشفى)":
        review_hospital = st.session_state.user_hospital
        
        if "مدير النظام (Admin)" in st.session_state.user_roles:
            review_hospital = st.selectbox("اختيار مستشفى للمراجعة (خاص بالأدمن):", HOSPITALS_LIST, index=HOSPITALS_LIST.index(st.session_state.user_hospital) if st.session_state.user_hospital in HOSPITALS_LIST else 0)

        st.header(f"🔍 الشاشة الثانية: مراجعة الطلبات ({review_hospital})")
        
        df_all_p = get_all_purchases_df()
        if not df_all_p.empty:
            df_review = df_all_p[(df_all_p["status"] == 'قيد المراجعة') & (df_all_p["hospital"] == review_hospital)]
            df_all_system = df_all_p[df_all_p["hospital"] == review_hospital]
        else:
            df_review = pd.DataFrame()
            df_all_system = pd.DataFrame()
        
        if not df_review.empty:
            df_review = df_review.rename(columns={
                "id": "رقم الطلب", "requester": "المستخدم", "hospital": "المستشفى", "item_number": "رقم البند",
                "nupco_number": "رقم نوبكو", "e_market_code": "كود السوق الإلكتروني", "item_name": "اسم الصنف",
                "unit_price": "السعر الأفرادي", "quantity": "الكمية", "total_cost": "الإجمالي",
                "importance_criteria": "معيار الأهمية", "reason": "السبب", "created_at": "تاريخ الإنشاء", "edit_history": "سجل التعديلات"
            })
        
        if not df_review.empty:
            st.subheader("📦 قائمة الطلبات المعلقة للمراجعة (انقر على السطر لاختياره)")
            nupco_list_filter = [n for n in df_review["رقم نوبكو"].dropna().unique() if str(n).strip() != ""]
            nupco_filter = st.selectbox("تصفية ودمج حسب رقم نوبكو", ["الكل"] + nupco_list_filter)
            
            target_df = df_review
            if nupco_filter != "الكل":
                target_df = df_review[df_review["رقم نوبكو"] == nupco_filter]
                st.info(f"يوجد {len(target_df)} طلبات مرتبطة برقم نوبكو: {nupco_filter}")
                
                if len(target_df) > 1:
                    if st.button(f"🔀 دمج الطلبات الـ ({len(target_df)}) المرتبطة برقم نوبكو {nupco_filter}", type="primary"):
                        ws_p = get_worksheet("purchases")
                        all_rows = ws_p.get_all_records()
                        
                        ids = target_df["رقم الطلب"].tolist()
                        total_qty = target_df["الكمية"].sum()
                        first_price = target_df["السعر الأفرادي"].iloc[0]
                        total_cost_merged = total_qty * first_price
                        primary_id = ids[0]
                        
                        for idx, row in enumerate(all_rows, start=2):
                            if row.get("id") == primary_id:
                                ws_p.update_cell(idx, 9, int(total_qty))
                                ws_p.update_cell(idx, 10, float(total_cost_merged))
                                break
                        
                        for remove_id in ids[1:]:
                            for idx, row in enumerate(all_rows, start=2):
                                if row.get("id") == remove_id:
                                    ws_p.delete_rows(idx)
                                    break
                        
                        st.success("تم دمج الطلبات بنجاح في Google Sheets!")
                        st.rerun()

            event = st.dataframe(target_df, use_container_width=True, on_select="rerun", selection_mode="single-row")
            selected_rows = event.selection.rows if hasattr(event, "selection") else []
            
            if selected_rows:
                selected_index = selected_rows[0]
                req_id = int(target_df.iloc[selected_index]["رقم الطلب"])
                selected_nupco_val = str(target_df.iloc[selected_index]["رقم نوبكو"])
                
                st.markdown("---")
                st.subheader(f"🔍 السجل التاريخي لرقم نوبكو: `{selected_nupco_val}`")
                if not df_all_system.empty:
                    matched_history_df = df_all_system[(df_all_system["nupco_number"] == selected_nupco_val) & (df_all_system["id"] != req_id)]
                    if not matched_history_df.empty:
                        st.dataframe(matched_history_df, use_container_width=True)
                    else:
                        st.info("لا توجد طلبات سابقة مطابقة.")

                current_order_row = df_all_p[df_all_p["id"] == req_id]
                if not current_order_row.empty:
                    co = current_order_row.iloc[0]
                    st.markdown("---")
                    st.subheader(f"⚙️ اتخاذ إجراء وتعديل الطلب رقم: {req_id}")
                    with st.form("edit_review_form"):
                        c1, c2, c3 = st.columns(3)
                        with c1:
                            new_item_number = st.text_input("رقم البند", value=str(co["item_number"]))
                            new_nupco_number = st.text_input("رقم نوبكو", value=str(co["nupco_number"]))
                            new_e_market_code = st.text_input("كود السوق الإلكتروني", value=str(co["e_market_code"]))
                        with c2:
                            new_item_name = st.text_input("اسم الصنف المعدل", value=str(co["item_name"]))
                            new_unit_price = st.number_input("السعر الأفرادي المعدل", value=float(co["unit_price"]), min_value=0.0)
                            new_quantity = st.number_input("الكمية المعدلة", value=int(co["quantity"]), min_value=1, step=1)
                        with c3:
                            importance_options = ["عالي جداً (حرج)", "عالي", "متوسط", "منخفض"]
                            curr_importance = co["importance_criteria"] if co["importance_criteria"] in importance_options else "متوسط"
                            new_importance = st.selectbox("معيار الأهمية", importance_options, index=importance_options.index(curr_importance))
                            new_reason = st.text_area("السبب / المبرر المعدل", value=str(co["reason"] or ""))
                        
                        review_notes = st.text_input("ملاحظات المراجعة")
                        action = st.selectbox("قرار المراجعة", ["تحويل للاعتماد", "رفض الطلب"])
                        
                        submit_review = st.form_submit_button("حفظ التعديلات وتنفيذ القرار")
                        
                        if submit_review:
                            new_total = new_unit_price * new_quantity
                            now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                            new_status = "بانتظار الاعتماد" if action == "تحويل للاعتماد" else "مرفوض في المراجعة"
                            
                            ws_p = get_worksheet("purchases")
                            all_rows = ws_p.get_all_records()
                            for idx, row in enumerate(all_rows, start=2):
                                if row.get("id") == req_id:
                                    ws_p.update_cell(idx, 4, str(new_item_number))
                                    ws_p.update_cell(idx, 5, str(new_nupco_number))
                                    ws_p.update_cell(idx, 6, str(new_e_market_code))
                                    ws_p.update_cell(idx, 7, str(new_item_name))
                                    ws_p.update_cell(idx, 8, float(new_unit_price))
                                    ws_p.update_cell(idx, 9, int(new_quantity))
                                    ws_p.update_cell(idx, 10, float(new_total))
                                    ws_p.update_cell(idx, 11, str(new_importance))
                                    ws_p.update_cell(idx, 12, str(new_reason))
                                    ws_p.update_cell(idx, 13, str(new_status))
                                    ws_p.update_cell(idx, 15, str(now_str))
                                    ws_p.update_cell(idx, 17, str(review_notes))
                                    break
                            
                            st.success(f"تم تحديث الطلب رقم {req_id} بنجاح سحابياً!")
                            st.rerun()
        else:
            st.info(f"لا توجد طلبات جديدة بانتظار المراجعة لـ ({review_hospital}) حالياً.")

    # ==================== الشاشة الثالثة (الاعتماد النهائي) ====================
    elif selected_screen == "الشاشة 3: الاعتماد النهائي":
        st.header("✅ الشاشة الثالثة: الاعتماد النهائي")
        
        df_all_p = get_all_purchases_df()
        df_approve = df_all_p[df_all_p["status"] == 'بانتظار الاعتماد'] if not df_all_p.empty else pd.DataFrame()
        df_all_approved = df_all_p[df_all_p["status"] == 'معتمد نهائياً'] if not df_all_p.empty else pd.DataFrame()
        
        if not df_all_approved.empty:
            df_app_view = df_all_approved.rename(columns={
                "id": "رقم الطلب", "requester": "المستخدم", "hospital": "المستشفى", "item_number": "رقم البند",
                "nupco_number": "رقم نوبكو", "e_market_code": "كود السوق الإلكتروني", "item_name": "اسم الصنف",
                "unit_price": "السعر الأفرادي", "quantity": "الكمية", "total_cost": "الإجمالي",
                "importance_criteria": "معيار الأهمية", "reason": "السبب", "status": "الحالة",
                "created_at": "تاريخ الإنشاء", "reviewed_at": "تاريخ المراجعة", "approved_at": "تاريخ الاعتماد النهائي",
                "approver_notes": "ملاحظات الاعتماد"
            })
            excel_bytes = to_excel_bytes(df_app_view)
            st.download_button(
                label="📥 تصدير الطلبات المعتمدة نهائياً إلى ملف Excel (.xls)",
                data=excel_bytes,
                file_name=f"approved_purchases_{datetime.now().strftime('%Y%m%d_%H%M')}.xls",
                mime="application/vnd.ms-excel"
            )
            st.markdown("---")
        
        if df_approve.empty:
            st.info("لا توجد طلبات بانتظار الاعتماد النهائي حالياً.")
        else:
            df_approve_view = df_approve.rename(columns={
                "id": "رقم الطلب", "requester": "المستخدم", "hospital": "المستشفى", "item_number": "رقم البند",
                "nupco_number": "رقم نوبكو", "e_market_code": "كود السوق الإلكتروني", "item_name": "اسم الصنف",
                "unit_price": "السعر الأفرادي", "quantity": "الكمية", "total_cost": "الإجمالي",
                "importance_criteria": "معيار الأهمية", "reason": "السبب", "reviewed_at": "تاريخ ووقت المراجعة",
                "reviewer_notes": "ملاحظات المراجعة", "edit_history": "سجل التعديلات"
            })
            
            event_app = st.dataframe(df_approve_view, use_container_width=True, on_select="rerun", selection_mode="single-row")
            sel_rows_app = event_app.selection.rows if hasattr(event_app, "selection") else []
            
            if sel_rows_app:
                app_idx = sel_rows_app[0]
                app_req_id = int(df_approve_view.iloc[app_idx]["رقم الطلب"])
                
                st.markdown("---")
                st.subheader(f"⚖️ اتخاذ القرار النهائي للطلب رقم: {app_req_id}")
                with st.form("approval_action_form"):
                    approver_notes = st.text_input("ملاحظات المعتمد")
                    app_action = st.selectbox("قرار الاعتماد", ["اعتماد الطلب نهائياً", "رفض الطلب نهائياً"])
                    submit_app = st.form_submit_button("تنفيذ واعتماد القرار")
                    
                    if submit_app:
                        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                        final_status = "معتمد نهائياً" if app_action == "اعتماد الطلب نهائياً" else "مرفوض نهائياً"
                        
                        ws_p = get_worksheet("purchases")
                        all_rows = ws_p.get_all_records()
                        for idx, row in enumerate(all_rows, start=2):
                            if row.get("id") == app_req_id:
                                ws_p.update_cell(idx, 13, str(final_status))
                                ws_p.update_cell(idx, 16, str(now_str))
                                ws_p.update_cell(idx, 18, str(approver_notes))
                                break
                        
                        st.success(f"تم تسجيل القرار النهائي للطلب رقم {app_req_id} بنجاح!")
                        st.rerun()

    # ==================== الشاشة الرابعة (إدارة الصلاحيات) ====================
    elif selected_screen == "الشاشة 4: إدارة الصلاحيات":
        if "مدير النظام (Admin)" not in st.session_state.user_roles:
            st.error("❌ عذراً، هذه الشاشة مخصصة لمدير النظام فقط.")
        else:
            st.header("⚙️ الشاشة الرابعة: إدارة الصلاحيات والمستخدمين")
            
            df_users = get_all_users_df()
            st.subheader("📋 جدول المستخدمين الحاليين")
            
            if not df_users.empty:
                for idx, row in df_users.iterrows():
                    u_name = row["username"]
                    u_hosp = row["hospital"] or "مجمع الملك فيصل"
                    u_roles = row["roles"]
                    u_status = row["status"]
                    
                    col1, col2, col3, col4, col5 = st.columns([2, 2, 3, 2, 1])
                    col1.write(u_name)
                    col2.write(u_hosp)
                    col3.write(u_roles)
                    col4.write(u_status)
                    
                    with col5:
                        if st.button("🗑️", key=f"del_u_{u_name}"):
                            if u_name == "admin":
                                st.error("لا يمكن حذف المدير الأساسي.")
                            elif u_name == st.session_state.username:
                                st.error("لا يمكنك حذف حسابك.")
                            else:
                                ws_u = get_worksheet("users")
                                cell = ws_u.find(u_name)
                                if cell:
                                    ws_u.delete_rows(cell.row)
                                    st.success(f"تم حذف {u_name}")
                                    st.rerun()
                    st.markdown("---")
            
            st.subheader("👤 تعديل صلاحيات المستخدمين")
            if not df_users.empty:
                usernames_list = df_users["username"].tolist()
                selected_target_user = st.selectbox("اختر مستخدم للتعديل", usernames_list)
                
                target_row = df_users[df_users["username"] == selected_target_user].iloc[0]
                curr_roles = target_row["roles"].split(",") if target_row["roles"] else []
                curr_status = target_row["status"]
                curr_hosp = target_row["hospital"] if target_row["hospital"] in HOSPITALS_LIST else HOSPITALS_LIST[0]
                
                with st.form("direct_user_edit_form"):
                    updated_hosp = st.selectbox("المستشفى التابع له", HOSPITALS_LIST, index=HOSPITALS_LIST.index(curr_hosp))
                    all_roles_options = ["رفع طلبات", "مراجعة الطلبات", "معتمد الطلبات", "إدارة الصلاحيات", "عرض الداش بورد", "مدير النظام (Admin)"]
                    updated_roles = st.multiselect("الصلاحيات الممنوحة", all_roles_options, default=[r for r in curr_roles if r in all_roles_options])
                    status_options = ["معتمد", "قيد الانتظار", "موقوف"]
                    updated_status = st.selectbox("حالة الحساب", status_options, index=status_options.index(curr_status) if curr_status in status_options else 0)
                    
                    if st.form_submit_button("حفظ التعديلات"):
                        ws_u = get_worksheet("users")
                        cell = ws_u.find(selected_target_user)
                        if cell:
                            ws_u.update_cell(cell.row, 3, ",".join(updated_roles))
                            ws_u.update_cell(cell.row, 4, str(updated_status))
                            ws_u.update_cell(cell.row, 5, str(updated_hosp))
                            st.success("تم التعديل بنجاح!")
                            st.rerun()

    # ==================== الشاشة الخامسة (Dashboard) ====================
    elif selected_screen == "الشاشة 5: لوحة التحكّم التفصيلية (Dashboard)":
        st.header("📊 الشاشة الخامسة: لوحة المؤشرات والإحصائيات العامة (Dashboard)")
        
        df_all = get_all_purchases_df()
        users_df = get_all_users_df()
        
        dash_hosp_filter = st.selectbox("تصفية لوحة التحكم حسب المستشفى:", ["جميع المستشفيات"] + HOSPITALS_LIST)
        if dash_hosp_filter != "جميع المستشفيات" and not df_all.empty:
            df_all = df_all[df_all['hospital'] == dash_hosp_filter]
        
        if not df_all.empty:
            total_orders = len(df_all)
            total_budget = df_all['total_cost'].sum() if 'total_cost' in df_all.columns else 0.0
            pending_count = len(df_all[df_all['status'].isin(['قيد المراجعة', 'بانتظار الاعتماد'])])
            approved_count = len(df_all[df_all['status'] == 'معتمد نهائياً'])
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("إجمالي الطلبات", total_orders)
            c2.metric("إجمالي التكاليف", f"{total_budget:,.2f} ر.س")
            c3.metric("الطلبات المعلقة", pending_count)
            c4.metric("الطلبات المعتمدة نهائياً", approved_count)
            
            st.markdown("---")
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                st.subheader("🏥 توزيع الطلبات حسب المستشفى")
                if 'hospital' in df_all.columns:
                    st.bar_chart(df_all['hospital'].value_counts())
            with col_d2:
                st.subheader("📌 تباين حالات الطلبات")
                if 'status' in df_all.columns:
                    st.bar_chart(df_all['status'].value_counts())
        else:
            st.info("لا توجد بيانات مسجلة بعد.")
        
        st.markdown("---")
        st.subheader("👥 ملخص الحسابات والمستخدمين")
        st.dataframe(users_df, use_container_width=True)
