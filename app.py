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
st.set_page_config(page_title="نظام تتبع عمليات الشراء المباشر", layout="wide", page_icon="🚀")

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

# --- الاتصال السحابي ---
@st.cache_resource
def get_gsheet_client():
    raw_json = st.secrets["gcp_json"]
    creds_dict = json.loads(raw_json)
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

def get_worksheet(worksheet_name):
    client = get_gsheet_client()
    sh = client.open("Purchase_System_DB")
    try:
        return sh.worksheet(worksheet_name)
    except Exception:
        return sh.add_worksheet(title=worksheet_name, rows="1000", cols="20")

# --- إدارة الذاكرة المحلية المؤقتة لضمان التحديث الفوري والربط السحابي ---
def load_data_to_session():
    try:
        ws_users = get_worksheet("users")
        recs = ws_users.get_all_records()
        if not recs:
            admin_pw = make_hashes("admin123")
            admin_roles = "مدير النظام (Admin),رفع طلبات,مراجعة الطلبات,معتمد الطلبات,إدارة الصلاحيات,عرض الداش بورد,اعتماد لجنة الشراء الطارئ"
            ws_users.update([
                ["username", "password", "roles", "status", "hospital"],
                ["admin", admin_pw, admin_roles, "معتمد", "مجمع الملك فيصل"]
            ])
            st.session_state.db_users = pd.DataFrame([{
                "username": "admin", "password": admin_pw, "roles": admin_roles, "status": "معتمد", "hospital": "مجمع الملك فيصل"
            }])
        else:
            df_u = pd.DataFrame(recs)
            df_u.columns = [str(c).strip() for c in df_u.columns]
            st.session_state.db_users = df_u
    except Exception:
        if 'db_users' not in st.session_state:
            st.session_state.db_users = pd.DataFrame(columns=["username", "password", "roles", "status", "hospital"])

    try:
        ws_p = get_worksheet("purchases")
        recs_p = ws_p.get_all_records()
        if not recs_p:
            ws_p.update([[
                "id", "requester", "hospital", "item_number", "nupco_number", "e_market_code",
                "item_name", "unit_price", "quantity", "total_cost", "importance_criteria",
                "reason", "status", "created_at", "reviewed_at", "approved_at",
                "reviewer_notes", "approver_notes", "edit_history"
            ]])
            st.session_state.db_purchases = pd.DataFrame(columns=[
                "id", "requester", "hospital", "item_number", "nupco_number", "e_market_code",
                "item_name", "unit_price", "quantity", "total_cost", "importance_criteria",
                "reason", "status", "created_at", "reviewed_at", "approved_at",
                "reviewer_notes", "approver_notes", "edit_history"
            ])
        else:
            df_p = pd.DataFrame(recs_p)
            df_p.columns = [str(c).strip() for c in df_p.columns]
            if "id" in df_p.columns:
                df_p["id"] = pd.to_numeric(df_p["id"], errors="coerce")
            if "unit_price" in df_p.columns:
                df_p["unit_price"] = pd.to_numeric(df_p["unit_price"], errors="coerce").fillna(0.0)
            if "quantity" in df_p.columns:
                df_p["quantity"] = pd.to_numeric(df_p["quantity"], errors="coerce").fillna(1).astype(int)
            if "total_cost" in df_p.columns:
                df_p["total_cost"] = pd.to_numeric(df_p["total_cost"], errors="coerce").fillna(0.0)
            st.session_state.db_purchases = df_p
    except Exception:
        if 'db_purchases' not in st.session_state:
            st.session_state.db_purchases = pd.DataFrame()

if 'db_purchases' not in st.session_state:
    load_data_to_session()

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

# --- إدارة الجلسة ونماذج الإدخال ---
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
    return df.to_html(index=False).encode('utf-8-sig')

# --- دوال تلوين الصفوف بناءً على أيام التأخير للشاشات ---
def highlight_delay_standard(row):
    try:
        created = pd.to_datetime(row.get('تاريخ الإنشاء') or row.get('created_at'), errors='coerce')
        if pd.isna(created):
            return [''] * len(row)
        days_diff = (datetime.now() - created).days
        if days_diff >= 3:
            return ['background-color: #ffcccc; color: #990000; font-weight: bold;'] * len(row) # أحمر
        elif days_diff == 1:
            return ['background-color: #fff3cd; color: #856404; font-weight: bold;'] * len(row) # أصفر
    except Exception:
        pass
    return [''] * len(row)

def highlight_delay_screen4(row):
    try:
        created = pd.to_datetime(row.get('تاريخ الإنشاء') or row.get('created_at'), errors='coerce')
        if pd.isna(created):
            return [''] * len(row)
        days_diff = (datetime.now() - created).days
        if days_diff > 10:
            return ['background-color: #ffcccc; color: #990000; font-weight: bold;'] * len(row) # أحمر (أكثر من 10 أيام)
        elif 7 <= days_diff <= 10:
            return ['background-color: #fff3cd; color: #856404; font-weight: bold;'] * len(row) # أصفر (من 7-10 أيام)
    except Exception:
        pass
    return [''] * len(row)

# ==================== تسجيل الدخول والاستعادة بموافقة الأدمن ====================
if not st.session_state.logged_in:
    st.markdown('<div class="main-title">🚀 نظام تتبع عمليات الشراء المباشر</div>', unsafe_allow_html=True)
    st.markdown("---")
    
    auth_mode = st.radio("اختر العملية:", ["تسجيل الدخول", "إنشاء حساب جديد", "نسيت كلمة المرور؟"], horizontal=True)
    st.markdown("---")
    
    if auth_mode == "تسجيل الدخول":
        st.subheader("🔑 تسجيل الدخول للنظام")
        with st.form("login_form"):
            username = st.text_input("اسم المستخدم")
            password = st.text_input("كلمة المرور", type='password')
            if st.form_submit_button("دخول"):
                df_users = st.session_state.db_users
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
                        elif status_val == "قيد إعادة تعيين كلمة المرور":
                            st.warning("⏳ طلب تغيير كلمة المرور قيد الانتظار لموافقة مدير النظام (الأدمن).")
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
            all_available_roles = ["رفع طلبات", "مراجعة الطلبات", "معتمد الطلبات", "اعتماد لجنة الشراء الطارئ", "إدارة الصلاحيات", "عرض الداش بورد"]
            requested_roles = st.multiselect("الصلاحيات المطلوبة", all_available_roles, default=[])
            
            if st.form_submit_button("إرسال طلب التسجيل"):
                if new_user and new_pass and requested_roles and selected_hospital:
                    df_users = st.session_state.db_users
                    if not df_users[df_users["username"] == new_user].empty:
                        st.error("❌ اسم المستخدم مستخدم مسبقاً.")
                    else:
                        ws_users = get_worksheet("users")
                        ws_users.append_row([new_user, make_hashes(new_pass), ",".join(requested_roles), "قيد الانتظار", selected_hospital])
                        load_data_to_session()
                        st.success("✅ تم إرسال طلبك بنجاح!")
                else:
                    st.warning("الرجاء تعبئة جميع الحقول واختيار المستشفى والصلاحية.")

    elif auth_mode == "نسيت كلمة المرور؟":
        st.subheader("🔄 طلب إعادة تعيين كلمة المرور (يتطلب موافقة الأدمن)")
        with st.form("forgot_password_form"):
            f_user = st.text_input("اسم المستخدم")
            f_hosp = st.selectbox("المستشفى التابع له", HOSPITALS_LIST)
            f_new_pass1 = st.text_input("كلمة المرور الجديدة", type="password")
            f_new_pass2 = st.text_input("تأكيد كلمة المرور الجديدة", type="password")
            
            if st.form_submit_button("إرسال طلب تغيير كلمة المرور للأدمن"):
                df_users = st.session_state.db_users
                user_match = df_users[(df_users["username"] == f_user) & (df_users["hospital"] == f_hosp)]
                
                if user_match.empty:
                    st.error("❌ اسم المستخدم أو المستشفى غير مطابق للبيانات المسجلة.")
                elif f_new_pass1 != f_new_pass2:
                    st.error("❌ كلمة المرور الجديدة وتأكيدها غير متطابقين.")
                elif len(f_new_pass1) < 4:
                    st.error("❌ كلمة المرور قصيرة جداً.")
                else:
                    ws_users = get_worksheet("users")
                    cell = ws_users.find(f_user)
                    if cell:
                        ws_users.update_cell(cell.row, 2, make_hashes(f_new_pass1))
                        ws_users.update_cell(cell.row, 4, "قيد إعادة تعيين كلمة المرور")
                        load_data_to_session()
                        st.success("✅ تم إرسال طلب إعادة تعيين كلمة المرور بنجاح! يرجى التواصل مع مدير النظام (الأدمن) للموافقة واعتماد الطلب.")

# ==================== الواجهة الرئيسية ====================
else:
    st.sidebar.title("👤 لوحة التحكم")
    
    if st.sidebar.button("🔄 تحديث البيانات من السحابة", use_container_width=True):
        load_data_to_session()
        st.sidebar.success("تم تحديث البيانات بنجاح!")
        st.rerun()
        
    st.sidebar.markdown("---")
    st.sidebar.write(f"المستخدم: **{st.session_state.username}**")
    st.sidebar.write(f"المستشفى: **{st.session_state.user_hospital}**")
    st.sidebar.write(f"الصلاحيات: **{', '.join(st.session_state.user_roles)}**")
    
    with st.sidebar.expander("🔒 تغيير كلمة المرور"):
        with st.form("change_password_form"):
            curr_pass = st.text_input("كلمة المرور الحالية", type="password")
            new_pass1 = st.text_input("كلمة المرور الجديدة", type="password")
            new_pass2 = st.text_input("تأكيد كلمة المرور الجديدة", type="password")
            if st.form_submit_button("حفظ كلمة المرور"):
                df_users = st.session_state.db_users
                user_row = df_users[df_users["username"] == st.session_state.username]
                db_pass = user_row.iloc[0]["password"] if not user_row.empty else ""
                
                if not check_hashes(curr_pass, db_pass):
                    st.error("❌ كلمة المرور الحالية غير صحيحة.")
                elif new_pass1 != new_pass2:
                    st.error("❌ كلمة المرور الجديدة وتأكيدها غير متطابقين.")
                elif len(new_pass1) < 4:
                    st.error("❌ كلمة المرور قصيرة جداً.")
                else:
                    ws_users = get_worksheet("users")
                    cell = ws_users.find(st.session_state.username)
                    if cell:
                        ws_users.update_cell(cell.row, 2, make_hashes(new_pass1))
                        load_data_to_session()
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
        screens.append("الشاشة 2: إدارة التخطيط بالمستشفى")
    if "معتمد الطلبات" in roles or "مدير النظام (Admin)" in roles:
        screens.append("الشاشة 3: إدارة التخطيط بالإمداد")
    if "اعتماد لجنة الشراء الطارئ" in roles or "مدير النظام (Admin)" in roles:
        screens.append("الشاشة 4: اعتماد لجنة الشراء الطارئ")
    if "إدارة الصلاحيات" in roles or "مدير النظام (Admin)" in roles:
        screens.append("الشاشة 5: إدارة الصلاحيات")
    if "عرض الداش بورد" in roles or "مدير النظام (Admin)" in roles:
        screens.append("الشاشة 6: لوحة التحكّم التفصيلية (Dashboard)")

    if not screens:
        st.warning("⚠️ لا توجد صلاحيات مفعلة حالياً.")
        st.stop()

    selected_screen = st.sidebar.radio("التنقل بين الشاشات:", screens)
    st.sidebar.markdown("---")

    st.markdown('<div class="main-title">🚀 نظام تتبع عمليات الشراء المباشر</div>', unsafe_allow_html=True)

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
            item_num_val = st.selectbox("1. رقم البند *", options=list_items, index=idx_item, key=f"sb_item_num_{cnt}", on_change=sync_item_num_changed)
            nupco_num_val = st.selectbox("2. رقم نوبكو *", options=list_nupco, index=idx_nupco, key=f"sb_nupco_{cnt}", on_change=sync_nupco_changed)
            e_market_code = st.text_input("3. كود السوق الالكتروني *", value=def_e_market, key=f"input_e_market_{cnt}")

        with col2:
            item_name_val = st.selectbox("4. اسم الصنف *", options=list_names, index=idx_name, key=f"sb_name_{cnt}", on_change=sync_name_changed)
            unit_price = st.number_input("5. السعر الافرادي *", min_value=0.0, step=1.0, value=def_price, key=f"input_unit_price_{cnt}")
            quantity = st.number_input("6. الكمية المطلوبة *", min_value=1, step=1, value=def_qty, key=f"input_quantity_{cnt}")

        with col3:
            importance_criteria = st.selectbox("7. معيار الأهمية *", ["عالي جداً (حرج)", "عالي", "متوسط", "منخفض"], key=f"sb_importance_{cnt}")
            reason = st.text_area("8. السبب / المبررات", value=def_reason, key=f"input_reason_{cnt}")

        total_cost = unit_price * quantity
        st.markdown(f"**إجمالي التكلفة المحسوبة:** `{total_cost:,.2f} ر.س`")

        if st.button("إرسال الطلب", use_container_width=True):
            str_item_num = str(item_num_val).strip() if item_num_val != "-- اختر أو ابحث --" else ""
            str_nupco_num = str(nupco_num_val).strip() if nupco_num_val != "-- اختر أو ابحث --" else ""
            str_item_name = str(item_name_val).strip() if item_name_val != "-- اختر أو ابحث --" else ""

            if not str_item_num or not str_nupco_num or not e_market_code.strip() or not str_item_name or unit_price <= 0 or quantity <= 0:
                st.error("❌ يرجى تعبئة كافة الحقول الإلزامية بصورة صحيحة.")
            else:
                df_all_p = st.session_state.db_purchases
                new_id = int(df_all_p["id"].max()) + 1 if not df_all_p.empty and not pd.isna(df_all_p["id"].max()) else 1
                
                new_row = {
                    "id": new_id, "requester": st.session_state.username, "hospital": st.session_state.user_hospital,
                    "item_number": str_item_num, "nupco_number": str_nupco_num, "e_market_code": e_market_code.strip(),
                    "item_name": str_item_name, "unit_price": unit_price, "quantity": quantity, "total_cost": total_cost,
                    "importance_criteria": importance_criteria, "reason": reason, "status": "قيد المراجعة",
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"), "reviewed_at": "", "approved_at": "",
                    "reviewer_notes": "", "approver_notes": "", "edit_history": ""
                }
                
                ws_purchases = get_worksheet("purchases")
                ws_purchases.append_row(list(new_row.values()))
                load_data_to_session()
                
                st.session_state.clear_form_flag = True
                st.session_state.reset_fields = True
                st.success("✅ تم إرسال طلب الشراء بنجاح وظهر في الشاشات التالية فورا!")
                st.rerun()

        st.markdown("---")
        st.subheader("📋 سجل طلباتك السابقة")
        df_all_p = st.session_state.db_purchases
        df_my_orders = df_all_p[df_all_p["requester"] == st.session_state.username] if not df_all_p.empty else pd.DataFrame()
        if not df_my_orders.empty:
            df_my_orders = df_my_orders.rename(columns={
                "id": "رقم الطلب", "hospital": "المستشفى", "item_number": "رقم البند",
                "nupco_number": "رقم نوبكو", "e_market_code": "كود السوق",
                "item_name": "اسم الصنف", "unit_price": "السعر الأفرادي", "quantity": "الكمية",
                "total_cost": "الإجمالي", "importance_criteria": "الأهمية", "reason": "السبب",
                "status": "الحالة", "created_at": "تاريخ الإنشاء"
            })
        st.dataframe(df_my_orders, use_container_width=True)

    # ==================== الشاشة الثانية (إدارة التخطيط بالمستشفى) ====================
    elif selected_screen == "الشاشة 2: إدارة التخطيط بالمستشفى":
        review_hospital = st.session_state.user_hospital
        if "مدير النظام (Admin)" in st.session_state.user_roles:
            review_hospital = st.selectbox("اختيار مستشفى للمراجعة:", HOSPITALS_LIST, index=HOSPITALS_LIST.index(st.session_state.user_hospital) if st.session_state.user_hospital in HOSPITALS_LIST else 0)

        st.header(f"🔍 الشاشة الثانية: إدارة التخطيط بالمستشفى ({review_hospital})")
        df_all_p = st.session_state.db_purchases
        
        if not df_all_p.empty:
            df_review = df_all_p[(df_all_p["status"] == 'قيد المراجعة') & (df_all_p["hospital"] == review_hospital)]
        else:
            df_review = pd.DataFrame()
        
        if not df_review.empty:
            df_review_view = df_review.rename(columns={
                "id": "رقم الطلب", "requester": "المستخدم", "hospital": "المستشفى", "item_number": "رقم البند",
                "nupco_number": "رقم نوبكو", "e_market_code": "كود السوق", "item_name": "اسم الصنف",
                "unit_price": "السعر الأفرادي", "quantity": "الكمية", "total_cost": "الإجمالي",
                "importance_criteria": "الأهمية", "reason": "السبب", "created_at": "تاريخ الإنشاء"
            })
            
            st.subheader("📦 قائمة الطلبات المعلقة للمراجعة")
            st.markdown("⚠️ **مفتاح التلوين:** <span style='background-color: #fff3cd; color: #856404; padding: 2px 6px; border-radius: 4px;'>متأخر يوم (أصفر)</span> | <span style='background-color: #ffcccc; color: #990000; padding: 2px 6px; border-radius: 4px;'>متأخر 3 أيام فأكثر (أحمر)</span>", unsafe_allow_html=True)
            
            nupco_list_filter = [n for n in df_review["nupco_number"].dropna().unique() if str(n).strip() != ""]
            nupco_filter = st.selectbox("تصفية ودمج حسب رقم نوبكو", ["الكل"] + nupco_list_filter)
            
            target_df = df_review
            target_df_view = df_review_view
            if nupco_filter != "الكل":
                target_df = df_review[df_review["nupco_number"] == nupco_filter]
                target_df_view = df_review_view[df_review_view["رقم نوبكو"] == nupco_filter]
                if len(target_df) > 1:
                    if st.button(f"🔀 دمج الطلبات الـ ({len(target_df)}) برقم نوبكو {nupco_filter}", type="primary"):
                        ws_p = get_worksheet("purchases")
                        all_rows = ws_p.get_all_records()
                        ids = target_df["id"].tolist()
                        total_qty = target_df["quantity"].sum()
                        first_price = target_df["unit_price"].iloc[0]
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
                        load_data_to_session()
                        st.success("تم الدمج بنجاح!")
                        st.rerun()

            styled_review_df = target_df_view.style.apply(highlight_delay_standard, axis=1)
            event = st.dataframe(styled_review_df, use_container_width=True, on_select="rerun", selection_mode="single-row")
            selected_rows = event.selection.rows if hasattr(event, "selection") else []
            
            if selected_rows:
                req_id = int(target_df_view.iloc[selected_rows[0]]["رقم الطلب"])
                current_order_row = df_all_p[df_all_p["id"] == req_id]
                if not current_order_row.empty:
                    co = current_order_row.iloc[0]
                    
                    sel_item_num = str(co["item_number"]).strip()
                    sel_nupco = str(co["nupco_number"]).strip()
                    sel_name = str(co["item_name"]).strip()
                    
                    if not df_all_p.empty:
                        similar_orders = df_all_p[
                            (
                                ((df_all_p["item_number"] == sel_item_num) & (sel_item_num != "")) |
                                ((df_all_p["nupco_number"] == sel_nupco) & (sel_nupco != "")) |
                                ((df_all_p["item_name"] == sel_name) & (sel_name != ""))
                            ) & 
                            (df_all_p["id"] != req_id)
                        ]
                    else:
                        similar_orders = pd.DataFrame()
                    
                    if not similar_orders.empty:
                        st.markdown("---")
                        st.info(f"📌 **سجل الطلبات المشابهة السابقة (المعتمدة، المرفوضة، والمنتظرة) للصنف الحالي:**")
                        sim_view = similar_orders.rename(columns={"id": "رقم الطلب", "hospital": "المستشفى", "item_number": "رقم البند", "nupco_number": "رقم نوبكو", "item_name": "اسم الصنف", "quantity": "الكمية", "total_cost": "الإجمالي", "status": "الحالة", "created_at": "تاريخ الإنشاء"})
                        st.dataframe(sim_view[["رقم الطلب", "المستشفى", "رقم البند", "رقم نوبكو", "اسم الصنف", "الكمية", "الإجمالي", "الحالة", "تاريخ الإنشاء"]], use_container_width=True)
                    
                    st.markdown("---")
                    st.subheader(f"⚙️ تعديل الطلب رقم: {req_id}")
                    with st.form("edit_review_form"):
                        c1, c2, c3 = st.columns(3)
                        with c1:
                            new_item_number = st.text_input("رقم البند", value=str(co["item_number"]))
                            new_nupco_number = st.text_input("رقم نوبكو", value=str(co["nupco_number"]))
                            new_e_market_code = st.text_input("كود السوق", value=str(co["e_market_code"]))
                        with c2:
                            new_item_name = st.text_input("اسم الصنف", value=str(co["item_name"]))
                            new_unit_price = st.number_input("السعر الأفرادي", value=float(co["unit_price"]), min_value=0.0)
                            new_quantity = st.number_input("الكمية", value=int(co["quantity"]), min_value=1, step=1)
                        with c3:
                            new_importance = st.selectbox("معيار الأهمية", ["عالي جداً (حرج)", "عالي", "متوسط", "منخفض"])
                            new_reason = st.text_area("السبب", value=str(co["reason"] or ""))
                        
                        review_notes = st.text_input("ملاحظات المراجعة")
                        action = st.selectbox("قرار المراجعة", ["تحويل للاعتماد", "رفض الطلب"])
                        
                        if st.form_submit_button("حفظ التعديلات وتنفيذ القرار"):
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
                            load_data_to_session()
                            st.success("تم التحديث بنجاح!")
                            st.rerun()
        else:
            st.info(f"لا توجد طلبات معلقة للمراجعة في ({review_hospital}).")

    # ==================== الشاشة الثالثة (إدارة التخطيط بالإمداد) ====================
    elif selected_screen == "الشاشة 3: إدارة التخطيط بالإمداد":
        app_hospital_selection = ["جميع المستشفيات"] + HOSPITALS_LIST
        selected_app_filter = st.selectbox("اختيار المستشفى للإعتماد:", app_hospital_selection, index=0, key="app_hosp_sb")

        st.header(f"✅ الشاشة الثالثة: إدارة التخطيط بالإمداد ({selected_app_filter})")
        df_all_p = st.session_state.db_purchases
        
        df_all_approved = df_all_p[df_all_p["status"] == 'معتمد نهائياً'] if not df_all_p.empty else pd.DataFrame()
        if not df_all_approved.empty:
            excel_bytes = to_excel_bytes(df_all_approved)
            st.download_button(
                label="📥 تصدير جميع الطلبات المعتمدة نهائياً إلى ملف Excel (.xls)",
                data=excel_bytes,
                file_name=f"approved_purchases_{datetime.now().strftime('%Y%m%d_%H%M')}.xls",
                mime="application/vnd.ms-excel"
            )
            st.markdown("---")

        if not df_all_p.empty:
            df_approve = df_all_p[df_all_p["status"] == 'بانتظار الاعتماد']
            if selected_app_filter != "جميع المستشفيات":
                df_approve = df_approve[df_approve["hospital"] == selected_app_filter]
        else:
            df_approve = pd.DataFrame()
        
        if not df_approve.empty:
            df_approve_view = df_approve.rename(columns={
                "id": "رقم الطلب", "requester": "المستخدم", "hospital": "المستشفى", "item_number": "رقم البند",
                "nupco_number": "رقم نوبكو", "item_name": "اسم الصنف", "total_cost": "الإجمالي", "status": "الحالة", "created_at": "تاريخ الإنشاء"
            })
            
            st.subheader("📦 قائمة الطلبات بانتظار الاعتماد النهائي")
            st.markdown("⚠️ **مفتاح التلوين:** <span style='background-color: #fff3cd; color: #856404; padding: 2px 6px; border-radius: 4px;'>متأخر يوم (أصفر)</span> | <span style='background-color: #ffcccc; color: #990000; padding: 2px 6px; border-radius: 4px;'>متأخر 3 أيام فأكثر (أحمر)</span>", unsafe_allow_html=True)
            
            styled_app_df = df_approve_view.style.apply(highlight_delay_standard, axis=1)
            event_app = st.dataframe(styled_app_df, use_container_width=True, on_select="rerun", selection_mode="single-row")
            sel_rows_app = event_app.selection.rows if hasattr(event_app, "selection") else []
            
            if sel_rows_app:
                app_req_id = int(df_approve_view.iloc[sel_rows_app[0]]["رقم الطلب"])
                current_order_row = df_all_p[df_all_p["id"] == app_req_id]
                if not current_order_row.empty:
                    co = current_order_row.iloc[0]
                    
                    sel_item_num = str(co["item_number"]).strip()
                    sel_nupco = str(co["nupco_number"]).strip()
                    sel_name = str(co["item_name"]).strip()
                    
                    if not df_all_p.empty:
                        similar_orders = df_all_p[
                            (
                                ((df_all_p["item_number"] == sel_item_num) & (sel_item_num != "")) |
                                ((df_all_p["nupco_number"] == sel_nupco) & (sel_nupco != "")) |
                                ((df_all_p["item_name"] == sel_name) & (sel_name != ""))
                            ) & 
                            (df_all_p["id"] != app_req_id)
                        ]
                    else:
                        similar_orders = pd.DataFrame()
                    
                    if not similar_orders.empty:
                        st.markdown("---")
                        st.info(f"📌 **سجل الطلبات المشابهة السابقة (المعتمدة، المرفوضة، والمنتظرة) للصنف الحالي:**")
                        sim_view = similar_orders.rename(columns={"id": "رقم الطلب", "hospital": "المستشفى", "item_number": "رقم البند", "nupco_number": "رقم نوبكو", "item_name": "اسم الصنف", "quantity": "الكمية", "total_cost": "الإجمالي", "status": "الحالة", "created_at": "تاريخ الإنشاء"})
                        st.dataframe(sim_view[["رقم الطلب", "المستشفى", "رقم البند", "رقم نوبكو", "اسم الصنف", "الكمية", "الإجمالي", "الحالة", "تاريخ الإنشاء"]], use_container_width=True)
                    
                    st.markdown("---")
                    st.subheader(f"⚖️ تعديل الطلب واتخاذ القرار النهائي رقم: {app_req_id}")
                    with st.form("approval_action_form"):
                        c1, c2, c3 = st.columns(3)
                        with c1:
                            app_item_number = st.text_input("رقم البند", value=str(co["item_number"]))
                            app_nupco_number = st.text_input("رقم نوبكو", value=str(co["nupco_number"]))
                            app_e_market_code = st.text_input("كود السوق", value=str(co["e_market_code"]))
                        with c2:
                            app_item_name = st.text_input("اسم الصنف", value=str(co["item_name"]))
                            app_unit_price = st.number_input("السعر الأفرادي", value=float(co["unit_price"]), min_value=0.0)
                            app_quantity = st.number_input("الكمية", value=int(co["quantity"]), min_value=1, step=1)
                        with c3:
                            app_importance = st.selectbox("معيار الأهمية", ["عالي جداً (حرج)", "عالي", "متوسط", "منخفض"])
                            app_reason = st.text_area("السبب", value=str(co["reason"] or ""))
                        
                        approver_notes = st.text_input("ملاحظات المعتمد")
                        app_action = st.selectbox("قرار الاعتماد", ["اعتماد الطلب نهائياً", "رفض الطلب نهائياً"])
                        
                        if st.form_submit_button("حفظ التعديلات وتنفيذ القرار النهائي"):
                            app_total = app_unit_price * app_quantity
                            now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                            final_status = "معتمد نهائياً" if app_action == "اعتماد الطلب نهائياً" else "مرفوض نهائياً"
                            
                            ws_p = get_worksheet("purchases")
                            all_rows = ws_p.get_all_records()
                            for idx, row in enumerate(all_rows, start=2):
                                if row.get("id") == app_req_id:
                                    ws_p.update_cell(idx, 4, str(app_item_number))
                                    ws_p.update_cell(idx, 5, str(app_nupco_number))
                                    ws_p.update_cell(idx, 6, str(app_e_market_code))
                                    ws_p.update_cell(idx, 7, str(app_item_name))
                                    ws_p.update_cell(idx, 8, float(app_unit_price))
                                    ws_p.update_cell(idx, 9, int(app_quantity))
                                    ws_p.update_cell(idx, 10, float(app_total))
                                    ws_p.update_cell(idx, 11, str(app_importance))
                                    ws_p.update_cell(idx, 12, str(app_reason))
                                    ws_p.update_cell(idx, 13, str(final_status))
                                    ws_p.update_cell(idx, 16, str(now_str))
                                    ws_p.update_cell(idx, 18, str(approver_notes))
                                    break
                            load_data_to_session()
                            st.success("تم تحديث الطلب واعتماد القرار النهائي بنجاح!")
                            st.rerun()
        else:
            st.info(f"لا توجد طلبات بانتظار الاعتماد النهائي في ({selected_app_filter}).")

    # ==================== الشاشة الرابعة (اعتماد لجنة الشراء الطارئ) ====================
    elif selected_screen == "الشاشة 4: اعتماد لجنة الشراء الطارئ":
        emg_hospital_selection = ["جميع المستشفيات"] + HOSPITALS_LIST
        selected_emg_filter = st.selectbox("اختيار المستشفى للجنة الشراء الطارئ:", emg_hospital_selection, index=0, key="emg_hosp_sb")

        st.header(f"🚨 الشاشة الرابعة: اعتماد لجنة الشراء الطارئ ({selected_emg_filter})")
        df_all_p = st.session_state.db_purchases
        
        if not df_all_p.empty:
            df_emergency = df_all_p[(df_all_p["importance_criteria"] == 'عالي جداً (حرج)') & (df_all_p["status"] == 'بانتظار الاعتماد')]
            if selected_emg_filter != "جميع المستشفيات":
                df_emergency = df_emergency[df_emergency["hospital"] == selected_emg_filter]
        else:
            df_emergency = pd.DataFrame()

        if not df_emergency.empty:
            excel_bytes_emg = to_excel_bytes(df_emergency)
            st.download_button(
                label="📥 تصدير قائمة طلبات الطوارئ الحالية إلى ملف Excel (.xls)",
                data=excel_bytes_emg,
                file_name=f"emergency_current_purchases_{datetime.now().strftime('%Y%m%d_%H%M')}.xls",
                mime="application/vnd.ms-excel"
            )
            st.markdown("---")
        
        if not df_emergency.empty:
            df_emg_view = df_emergency.rename(columns={
                "id": "رقم الطلب", "requester": "المستخدم", "hospital": "المستشفى", "item_number": "رقم البند",
                "nupco_number": "رقم نوبكو", "item_name": "اسم الصنف", "total_cost": "الإجمالي", "status": "الحالة", "reason": "السبب", "created_at": "تاريخ الإنشاء"
            })
            
            st.subheader("📦 قائمة طلبات الشراء الطارئة (الحرجة جداً)")
            st.markdown("⚠️ **مفتاح التلوين (الشاشة 4):** <span style='background-color: #fff3cd; color: #856404; padding: 2px 6px; border-radius: 4px;'>متأخر من 7-10 أيام (أصفر)</span> | <span style='background-color: #ffcccc; color: #990000; padding: 2px 6px; border-radius: 4px;'>متأخر أكثر من 10 أيام (أحمر)</span>", unsafe_allow_html=True)
            
            styled_emg_df = df_emg_view.style.apply(highlight_delay_screen4, axis=1)
            event_emg = st.dataframe(styled_emg_df, use_container_width=True, on_select="rerun", selection_mode="single-row")
            sel_rows_emg = event_emg.selection.rows if hasattr(event_emg, "selection") else []
            
            if sel_rows_emg:
                emg_req_id = int(df_emg_view.iloc[sel_rows_emg[0]]["رقم الطلب"])
                current_emg_row = df_all_p[df_all_p["id"] == emg_req_id]
                if not current_emg_row.empty:
                    co_emg = current_emg_row.iloc[0]
                    
                    sel_item_num = str(co_emg["item_number"]).strip()
                    sel_nupco = str(co_emg["nupco_number"]).strip()
                    sel_name = str(co_emg["item_name"]).strip()
                    
                    if not df_all_p.empty:
                        similar_orders = df_all_p[
                            (
                                ((df_all_p["item_number"] == sel_item_num) & (sel_item_num != "")) |
                                ((df_all_p["nupco_number"] == sel_nupco) & (sel_nupco != "")) |
                                ((df_all_p["item_name"] == sel_name) & (sel_name != ""))
                            ) & 
                            (df_all_p["id"] != emg_req_id)
                        ]
                    else:
                        similar_orders = pd.DataFrame()

                    if not similar_orders.empty:
                        st.markdown("---")
                        st.info(f"📌 **سجل الطلبات المشابهة السابقة (المعتمدة، المرفوضة، والمنتظرة) للصنف الحالي:**")
                        sim_view = similar_orders.rename(columns={"id": "رقم الطلب", "hospital": "المستشفى", "item_number": "رقم البند", "nupco_number": "رقم نوبكو", "item_name": "اسم الصنف", "quantity": "الكمية", "total_cost": "الإجمالي", "status": "الحالة", "created_at": "تاريخ الإنشاء"})
                        st.dataframe(sim_view[["رقم الطلب", "المستشفى", "رقم البند", "رقم نوبكو", "اسم الصنف", "الكمية", "الإجمالي", "الحالة", "تاريخ الإنشاء"]], use_container_width=True)

                    st.markdown("---")
                    st.subheader(f"⚖️ تعديل ومعالجة طلب الطوارئ رقم: {emg_req_id}")
                    with st.form("emergency_action_form"):
                        c1, c2, c3 = st.columns(3)
                        with c1:
                            emg_item_number = st.text_input("رقم البند", value=str(co_emg["item_number"]), key="emg_in")
                            emg_nupco_number = st.text_input("رقم نوبكو", value=str(co_emg["nupco_number"]), key="emg_nu")
                            emg_e_market_code = st.text_input("كود السوق", value=str(co_emg["e_market_code"]), key="emg_em")
                        with c2:
                            emg_item_name = st.text_input("اسم الصنف", value=str(co_emg["item_name"]), key="emg_na")
                            emg_unit_price = st.number_input("السعر الأفرادي", value=float(co_emg["unit_price"]), min_value=0.0, key="emg_pr")
                            emg_quantity = st.number_input("الكمية", value=int(co_emg["quantity"]), min_value=1, step=1, key="emg_qu")
                        with c3:
                            emg_importance = st.selectbox("معيار الأهمية", ["عالي جداً (حرج)", "عالي", "متوسط", "منخفض"], index=0, key="emg_im")
                            emg_reason = st.text_area("السبب / المبرر", value=str(co_emg["reason"] or ""), key="emg_re")
                        
                        emg_notes = st.text_input("ملاحظات لجنة الشراء الطارئ", key="emg_no")
                        emg_action = st.selectbox("قرار اللجنة الطارئة", ["اعتماد طوارئ نهائياً", "رفض طلب الطوارئ"], key="emg_ac")
                        
                        if st.form_submit_button("حفظ وتنفيذ قرار لجنة الطوارئ"):
                            emg_total = emg_unit_price * emg_quantity
                            now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                            emg_final_status = "معتمد طوارئ نهائياً" if emg_action == "اعتماد طوارئ نهائياً" else "مرفوض في الطوارئ"
                            
                            ws_p = get_worksheet("purchases")
                            all_rows = ws_p.get_all_records()
                            for idx, row in enumerate(all_rows, start=2):
                                if row.get("id") == emg_req_id:
                                    ws_p.update_cell(idx, 4, str(emg_item_number))
                                    ws_p.update_cell(idx, 5, str(emg_nupco_number))
                                    ws_p.update_cell(idx, 6, str(emg_e_market_code))
                                    ws_p.update_cell(idx, 7, str(emg_item_name))
                                    ws_p.update_cell(idx, 8, float(emg_unit_price))
                                    ws_p.update_cell(idx, 9, int(emg_quantity))
                                    ws_p.update_cell(idx, 10, float(emg_total))
                                    ws_p.update_cell(idx, 11, str(emg_importance))
                                    ws_p.update_cell(idx, 12, str(emg_reason))
                                    ws_p.update_cell(idx, 13, str(emg_final_status))
                                    ws_p.update_cell(idx, 16, str(now_str))
                                    ws_p.update_cell(idx, 18, str(emg_notes))
                                    break
                            load_data_to_session()
                            st.success("✅ تم اعتماد وتحديث طلب الشراء الطارئ بنجاح!")
                            st.rerun()
        else:
            st.info(f"لا توجد طلبات طارئة حرجة بانتظار الاعتماد في ({selected_emg_filter}).")

    # ==================== الشاشة الخامسة (إدارة الصلاحيات) ====================
    elif selected_screen == "الشاشة 5: إدارة الصلاحيات":
        if "مدير النظام (Admin)" not in st.session_state.user_roles:
            st.error("❌ عذراً، مخصص للأدمن فقط.")
        else:
            st.header("⚙️ الشاشة الخامسة: إدارة المستخدمين والصلاحيات")
            
            tab1, tab2 = st.tabs(["قائمة المستخدمين والحذف", "إضافة مستخدم جديد"])
            
            with tab1:
                df_users = st.session_state.db_users
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
                                    st.error("لا يمكنك حذف حسابك الحالي.")
                                else:
                                    ws_u = get_worksheet("users")
                                    cell = ws_u.find(u_name)
                                    if cell:
                                        ws_u.delete_rows(cell.row)
                                        load_data_to_session()
                                        st.success(f"تم حذف المستخدم {u_name}")
                                        st.rerun()
                        st.markdown("---")
                
                st.subheader("👤 تعديل صلاحيات وحالة مستخدم (الموافقة على الحسابات وكلمات المرور)")
                if not df_users.empty:
                    usernames_list = df_users["username"].tolist()
                    selected_target_user = st.selectbox("اختر مستخدم للتعديل", usernames_list)
                    
                    target_row = df_users[df_users["username"] == selected_target_user].iloc[0]
                    curr_roles = target_row["roles"].split(",") if target_row["roles"] else []
                    curr_status = target_row["status"]
                    curr_hosp = target_row["hospital"] if target_row["hospital"] in HOSPITALS_LIST else HOSPITALS_LIST[0]
                    
                    with st.form("direct_user_edit_form"):
                        updated_hosp = st.selectbox("المستشفى التابع له", HOSPITALS_LIST, index=HOSPITALS_LIST.index(curr_hosp))
                        all_roles_options = ["رفع طلبات", "مراجعة الطلبات", "معتمد الطلبات", "اعتماد لجنة الشراء الطارئ", "إدارة الصلاحيات", "عرض الداش بورد", "مدير النظام (Admin)"]
                        updated_roles = st.multiselect("الصلاحيات الممنوحة", all_roles_options, default=[r for r in curr_roles if r in all_roles_options])
                        status_options = ["معتمد", "قيد الانتظار", "قيد إعادة تعيين كلمة المرور", "موقوف"]
                        updated_status = st.selectbox("حالة الحساب (اختر معتمد للموافقة)", status_options, index=status_options.index(curr_status) if curr_status in status_options else 0)
                        
                        if st.form_submit_button("حفظ التعديلات والموافقة"):
                            ws_u = get_worksheet("users")
                            cell = ws_u.find(selected_target_user)
                            if cell:
                                ws_u.update_cell(cell.row, 3, ",".join(updated_roles))
                                ws_u.update_cell(cell.row, 4, str(updated_status))
                                ws_u.update_cell(cell.row, 5, str(updated_hosp))
                                load_data_to_session()
                                st.success("تم تحديث المستخدم والموافقة عليه بنجاح!")
                                st.rerun()

            with tab2:
                with st.form("add_new_user_form"):
                    st.subheader("إضافة حساب مستخدم جديد مباشرة")
                    new_u_name = st.text_input("اسم المستخدم الجديد")
                    new_u_pass = st.text_input("كلمة المرور", type="password")
                    new_u_hosp = st.selectbox("المستشفى التابع له", HOSPITALS_LIST)
                    all_roles_options = ["رفع طلبات", "مراجعة الطلبات", "معتمد الطلبات", "اعتماد لجنة الشراء الطارئ", "إدارة الصلاحيات", "عرض الداش بورد", "مدير النظام (Admin)"]
                    new_u_roles = st.multiselect("الصلاحيات", all_roles_options, default=["رفع طلبات"])
                    
                    if st.form_submit_button("إضافة المستخدم"):
                        if not new_u_name.strip() or not new_u_pass.strip():
                            st.error("الرجاء إدخال اسم المستخدم وكلمة المرور.")
                        else:
                            df_users = st.session_state.db_users
                            if not df_users[df_users["username"] == new_u_name].empty:
                                st.error("اسم المستخدم موجود مسبقاً.")
                            else:
                                ws_u = get_worksheet("users")
                                ws_u.append_row([new_u_name, make_hashes(new_u_pass), ",".join(new_u_roles), "معتمد", new_u_hosp])
                                load_data_to_session()
                                st.success(f"تمت إضافة المستخدم {new_u_name} واعتماده بنجاح!")
                                st.rerun()

    # ==================== الشاشة السادسة (Dashboard التفصيلية) ====================
    elif selected_screen == "الشاشة 6: لوحة التحكّم التفصيلية (Dashboard)":
        st.header("📊 الشاشة السادسة: لوحة المؤشرات والإحصائيات العامة (Dashboard)")
        
        df_all = st.session_state.db_purchases
        users_df = st.session_state.db_users
        
        dash_hosp_filter = st.selectbox("تصفية لوحة التحكم حسب المستشفى:", ["جميع المستشفيات"] + HOSPITALS_LIST)
        if dash_hosp_filter != "جميع المستشفيات" and not df_all.empty:
            df_all = df_all[df_all['hospital'] == dash_hosp_filter]
        
        if not df_all.empty:
            total_orders = len(df_all)
            total_budget = df_all['total_cost'].sum() if 'total_cost' in df_all.columns else 0.0
            pending_review = len(df_all[df_all['status'] == 'قيد المراجعة'])
            pending_approve = len(df_all[df_all['status'] == 'بانتظار الاعتماد'])
            approved_count = len(df_all[df_all['status'].str.contains('معتمد', na=False)])
            rejected_count = len(df_all[df_all['status'].str.contains('مرفوض', na=False)])
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("إجمالي الطلبات", total_orders)
            c2.metric("إجمالي التكاليف", f"{total_budget:,.2f} ر.س")
            c3.metric("الطلبات المعلقة", pending_review + pending_approve)
            c4.metric("إجمالي المعتمدة", approved_count)
            
            st.markdown("---")
            rc1, rc2, rc3 = st.columns(3)
            rc1.metric("🔍 قيد المراجعة", pending_review)
            rc2.metric("⏳ بانتظار الاعتماد", pending_approve)
            rc3.metric("🚫 الطلبات المرفوضة", rejected_count)
            
            # --- حساب معدل التأخير لكل شاشة (بالأيام) ---
            st.markdown("---")
            st.subheader("⏱️ مؤشرات معدل التأخير في اعتماد الطلبات لكل شاشة")
            
            df_screen2_pending = df_all[df_all['status'] == 'قيد المراجعة']
            avg_delay_s2 = 0.0
            if not df_screen2_pending.empty:
                dates_s2 = pd.to_datetime(df_screen2_pending['created_at'], errors='coerce')
                delays_s2 = (datetime.now() - dates_s2).dt.total_seconds() / 86400
                avg_delay_s2 = delays_s2.mean() if not delays_s2.empty else 0.0

            df_screen3_pending = df_all[df_all['status'] == 'بانتظار الاعتماد']
            avg_delay_s3_4 = 0.0
            if not df_screen3_pending.empty:
                ref_dates = df_screen3_pending['reviewed_at'].apply(lambda x: x if str(x).strip() != "" else None).fillna(df_screen3_pending['created_at'])
                dates_s3 = pd.to_datetime(ref_dates, errors='coerce')
                delays_s3 = (datetime.now() - dates_s3).dt.total_seconds() / 86400
                avg_delay_s3_4 = delays_s3.mean() if not delays_s3.empty else 0.0

            dc1, dc2, dc3 = st.columns(3)
            dc1.metric("معدل تأخير الشاشة 2 (مراجعة المستشفى)", f"{avg_delay_s2:.1f} يوم")
            dc2.metric("معدل تأخير الشاشة 3 (اعتماد الإمداد)", f"{avg_delay_s3_4:.1f} يوم")
            dc3.metric("معدل تأخير الشاشة 4 (لجنة الطوارئ)", f"{avg_delay_s3_4:.1f} يوم")
            
            st.markdown("---")
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                st.subheader("🏥 توزيع الطلبات حسب المستشفى")
                if 'hospital' in df_all.columns:
                    st.bar_chart(df_all['hospital'].value_counts())
            with col_d2:
                st.subheader("📌 تباين حالات الطلبات في النظام")
                if 'status' in df_all.columns:
                    st.bar_chart(df_all['status'].value_counts())
            
            st.markdown("---")
            st.subheader("📋 تفاصيل الطلبات المعتمدة نهائياً")
            df_app_dash = df_all[df_all['status'].str.contains('معتمد', na=False)]
            if not df_app_dash.empty:
                st.dataframe(df_app_dash, use_container_width=True)
            else:
                st.info("لا توجد طلبات معتمدة نهائياً حتى الآن.")
        else:
            st.info("لا توجد بيانات مسجلة في النظام بعد.")
        
        st.markdown("---")
        st.subheader("👥 ملخص الحسابات والمستخدمين في النظام")
        st.dataframe(users_df, use_container_width=True)
