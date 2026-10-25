import streamlit as st
import pandas as pd
import hashlib
import os
import json
sqlite3 = None
try:
    import sqlite3
except ImportError:
    pass
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

# --- إعداد قاعدة البيانات المحلية SQLite للسرعة الفائقة ---
def init_local_db():
    conn = sqlite3.connect('purchase_local.db', check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT,
            roles TEXT,
            status TEXT,
            hospital TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY,
            requester TEXT,
            hospital TEXT,
            item_number TEXT,
            nupco_number TEXT,
            e_market_code TEXT,
            item_name TEXT,
            unit_price REAL,
            quantity INTEGER,
            total_cost REAL,
            importance_criteria TEXT,
            reason TEXT,
            status TEXT,
            created_at TEXT,
            reviewed_at TEXT,
            approved_at TEXT,
            reviewer_notes TEXT,
            approver_notes TEXT,
            edit_history TEXT
        )
    ''')
    conn.commit()
    
    # التحقق من وجود مستخدم الأدمن الافتراضي
    cursor.execute("SELECT * FROM users WHERE username = 'admin'")
    if not cursor.fetchone():
        admin_pw = make_hashes("admin123")
        admin_roles = "مدير النظام (Admin),رفع طلبات,مراجعة الطلبات,معتمد الطلبات,إدارة الصلاحيات,عرض الداش بورد"
        cursor.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?)", ('admin', admin_pw, admin_roles, 'معتمد', 'مجمع الملك فيصل'))
        conn.commit()
        
    conn.close()

init_local_db()

def get_local_users():
    conn = sqlite3.connect('purchase_local.db', check_same_thread=False)
    df = pd.read_sql("SELECT * FROM users", conn)
    conn.close()
    return df

def get_local_purchases():
    conn = sqlite3.connect('purchase_local.db', check_same_thread=False)
    df = pd.read_sql("SELECT * FROM purchases", conn)
    conn.close()
    if not df.empty and "id" in df.columns:
        df["id"] = pd.to_numeric(df["id"], errors="coerce")
    return df

def save_user_local(username, password, roles, status, hospital):
    conn = sqlite3.connect('purchase_local.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("REPLACE INTO users VALUES (?, ?, ?, ?, ?)", (username, password, roles, status, hospital))
    conn.commit()
    conn.close()

def delete_user_local(username):
    conn = sqlite3.connect('purchase_local.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE username = ?", (username,))
    conn.commit()
    conn.close()

def save_purchase_local(p_data):
    conn = sqlite3.connect('purchase_local.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        REPLACE INTO purchases VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        p_data['id'], p_data['requester'], p_data['hospital'], p_data['item_number'],
        p_data['nupco_number'], p_data['e_market_code'], p_data['item_name'],
        p_data['unit_price'], p_data['quantity'], p_data['total_cost'],
        p_data['importance_criteria'], p_data['reason'], p_data['status'],
        p_data['created_at'], p_data['reviewed_at'], p_data['approved_at'],
        p_data['reviewer_notes'], p_data['approver_notes'], p_data['edit_history']
    ))
    conn.commit()
    conn.close()

def delete_purchase_local(p_id):
    conn = sqlite3.connect('purchase_local.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM purchases WHERE id = ?", (p_id,))
    conn.commit()
    conn.close()

# --- الاتصال السحابي (اختياري عبر زر التحديث أو المزامنة) ---
@st.cache_resource
def get_gsheet_client():
    try:
        raw_json = st.secrets["gcp_json"]
        creds_dict = json.loads(raw_json)
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        return gspread.authorize(creds)
    except Exception:
        return None

def sync_to_google_sheets():
    try:
        client = get_gsheet_client()
        if not client:
            return False
        sh = client.open("Purchase_System_DB")
        
        # مزامنة المستخدمين
        try:
            ws_u = sh.worksheet("users")
        except Exception:
            ws_u = sh.add_worksheet(title="users", rows="1000", cols="10")
        df_u = get_local_users()
        ws_u.clear()
        ws_u.update([df_u.columns.values.tolist()] + df_u.values.tolist())
        
        # مزامنة الطلبات
        try:
            ws_p = sh.worksheet("purchases")
        except Exception:
            ws_p = sh.add_worksheet(title="purchases", rows="1000", cols="25")
        df_p = get_local_purchases()
        ws_p.clear()
        if not df_p.empty:
            ws_p.update([df_p.columns.values.tolist()] + df_p.values.tolist())
        else:
            ws_p.update([[
                "id", "requester", "hospital", "item_number", "nupco_number", "e_market_code",
                "item_name", "unit_price", "quantity", "total_cost", "importance_criteria",
                "reason", "status", "created_at", "reviewed_at", "approved_at",
                "reviewer_notes", "approver_notes", "edit_history"
            ]])
        return True
    except Exception:
        return False

def sync_from_google_sheets():
    try:
        client = get_gsheet_client()
        if not client:
            return False
        sh = client.open("Purchase_System_DB")
        
        # سحب المستخدمين
        try:
            ws_u = sh.worksheet("users")
            recs_u = ws_u.get_all_records()
            if recs_u:
                for r in recs_u:
                    save_user_local(r.get('username'), r.get('password'), r.get('roles'), r.get('status'), r.get('hospital'))
        except Exception:
            pass
            
        # سحب الطلبات
        try:
            ws_p = sh.worksheet("purchases")
            recs_p = ws_p.get_all_records()
            if recs_p:
                for r in recs_p:
                    save_purchase_local(r)
        except Exception:
            pass
        return True
    except Exception:
        return False

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

# ==================== تسجيل الدخول ====================
if not st.session_state.logged_in:
    st.markdown('<div class="main-title">🚀 نظام تتبع عمليات الشراء المباشر</div>', unsafe_allow_html=True)
    st.markdown("---")
    
    auth_mode = st.radio("اختر العملية:", ["تسجيل الدخول", "إنشاء حساب جديد"], horizontal=True)
    st.markdown("---")
    
    if auth_mode == "تسجيل الدخول":
        st.subheader("🔑 تسجيل الدخول للنظام")
        with st.form("login_form"):
            username = st.text_input("اسم المستخدم")
            password = st.text_input("كلمة المرور", type='password')
            if st.form_submit_button("دخول"):
                df_users = get_local_users()
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
            requested_roles = st.multiselect("الصلاحيات المطلوبة", all_available_roles, default=[])
            
            if st.form_submit_button("إرسال طلب التسجيل"):
                if new_user and new_pass and requested_roles and selected_hospital:
                    df_users = get_local_users()
                    if not df_users[df_users["username"] == new_user].empty:
                        st.error("❌ اسم المستخدم مستخدم مسبقاً.")
                    else:
                        roles_str = ",".join(requested_roles)
                        save_user_local(new_user, make_hashes(new_pass), roles_str, "قيد الانتظار", selected_hospital)
                        sync_to_google_sheets()
                        st.success("✅ تم إرسال طلبك بنجاح!")
                else:
                    st.warning("الرجاء تعبئة جميع الحقول واختيار المستشفى والصلاحية.")

# ==================== الواجهة الرئيسية ====================
else:
    st.sidebar.title("👤 لوحة التحكم")
    
    # --- أزرار المزامنة والتحديث السحابي اليدوي ---
    c_sync1, c_sync2 = st.sidebar.columns(2)
    with c_sync1:
        if st.button("📥 سحب من السحابة", use_container_width=True):
            if sync_from_google_sheets():
                st.sidebar.success("تم السحب!")
                st.rerun()
            else:
                st.sidebar.error("فشل الاتصال")
    with c_sync2:
        if st.button("📤 مزامنة للسحابة", use_container_width=True):
            if sync_to_google_sheets():
                st.sidebar.success("تمت المزامنة!")
            else:
                st.sidebar.error("فشل الاتصال")

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
                df_users = get_local_users()
                user_row = df_users[df_users["username"] == st.session_state.username]
                db_pass = user_row.iloc[0]["password"] if not user_row.empty else ""
                
                if not check_hashes(curr_pass, db_pass):
                    st.error("❌ كلمة المرور الحالية غير صحيحة.")
                elif new_pass1 != new_pass2:
                    st.error("❌ كلمة المرور الجديدة وتأكيدها غير متطابقين.")
                elif len(new_pass1) < 4:
                    st.error("❌ كلمة المرور قصيرة جداً.")
                else:
                    u_row = user_row.iloc[0]
                    save_user_local(u_row['username'], make_hashes(new_pass1), u_row['roles'], u_row['status'], u_row['hospital'])
                    sync_to_google_sheets()
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
                df_all_p = get_local_purchases()
                new_id = int(df_all_p["id"].max()) + 1 if not df_all_p.empty and not pd.isna(df_all_p["id"].max()) else 1
                
                new_row = {
                    "id": new_id, "requester": st.session_state.username, "hospital": st.session_state.user_hospital,
                    "item_number": str_item_num, "nupco_number": str_nupco_num, "e_market_code": e_market_code.strip(),
                    "item_name": str_item_name, "unit_price": unit_price, "quantity": quantity, "total_cost": total_cost,
                    "importance_criteria": importance_criteria, "reason": reason, "status": "قيد المراجعة",
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"), "reviewed_at": "", "approved_at": "",
                    "reviewer_notes": "", "approver_notes": "", "edit_history": ""
                }
                save_purchase_local(new_row)
                
                st.session_state.clear_form_flag = True
                st.session_state.reset_fields = True
                st.success("✅ تم حفظ وإرسال طلب الشراء فوراً وبسرعة البرق!")
                st.rerun()

        st.markdown("---")
        st.subheader("📋 سجل طلباتك السابقة")
        df_all_p = get_local_purchases()
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

    # ==================== الشاشة الثانية ====================
    elif selected_screen == "الشاشة 2: المراجعة (مستقلة لكل مستشفى)":
        review_hospital = st.session_state.user_hospital
        if "مدير النظام (Admin)" in st.session_state.user_roles:
            review_hospital = st.selectbox("اختيار مستشفى للمراجعة:", HOSPITALS_LIST, index=HOSPITALS_LIST.index(st.session_state.user_hospital) if st.session_state.user_hospital in HOSPITALS_LIST else 0)

        st.header(f"🔍 الشاشة الثانية: مراجعة الطلبات ({review_hospital})")
        df_all_p = get_local_purchases()
        
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
            nupco_list_filter = [n for n in df_review["nupco_number"].dropna().unique() if str(n).strip() != ""]
            nupco_filter = st.selectbox("تصفية ودمج حسب رقم نوبكو", ["الكل"] + nupco_list_filter)
            
            target_df = df_review
            target_df_view = df_review_view
            if nupco_filter != "الكل":
                target_df = df_review[df_review["nupco_number"] == nupco_filter]
                target_df_view = df_review_view[df_review_view["رقم نوبكو"] == nupco_filter]
                if len(target_df) > 1:
                    if st.button(f"🔀 دمج الطلبات الـ ({len(target_df)}) برقم نوبكو {nupco_filter}", type="primary"):
                        ids = target_df["id"].tolist()
                        total_qty = target_df["quantity"].sum()
                        first_price = target_df["unit_price"].iloc[0]
                        total_cost_merged = total_qty * first_price
                        primary_id = ids[0]
                        
                        df_all_p.loc[df_all_p["id"] == primary_id, "quantity"] = int(total_qty)
                        df_all_p.loc[df_all_p["id"] == primary_id, "total_cost"] = float(total_cost_merged)
                        save_purchase_local(df_all_p[df_all_p["id"] == primary_id].iloc[0].to_dict())
                        
                        for remove_id in ids[1:]:
                            delete_purchase_local(remove_id)
                            
                        st.success("تم الدمج بنجاح وبسرعة فائقة!")
                        st.rerun()

            event = st.dataframe(target_df_view, use_container_width=True, on_select="rerun", selection_mode="single-row")
            selected_rows = event.selection.rows if hasattr(event, "selection") else []
            
            if selected_rows:
                req_id = int(target_df_view.iloc[selected_rows[0]]["رقم الطلب"])
                current_order_row = df_all_p[df_all_p["id"] == req_id]
                if not current_order_row.empty:
                    co = current_order_row.iloc[0]
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
                            
                            updated_row = co.to_dict()
                            updated_row.update({
                                "item_number": str(new_item_number), "nupco_number": str(new_nupco_number),
                                "e_market_code": str(new_e_market_code), "item_name": str(new_item_name),
                                "unit_price": float(new_unit_price), "quantity": int(new_quantity),
                                "total_cost": float(new_total), "importance_criteria": str(new_importance),
                                "reason": str(new_reason), "status": str(new_status),
                                "reviewed_at": str(now_str), "reviewer_notes": str(review_notes)
                            })
                            save_purchase_local(updated_row)
                            st.success("تم الحفظ محلياً فوراً وبدون أي تأخير!")
                            st.rerun()
        else:
            st.info(f"لا توجد طلبات معلقة للمراجعة في ({review_hospital}).")

    # ==================== الشاشة الثالثة (الاعتماد النهائي) ====================
    elif selected_screen == "الشاشة 3: الاعتماد النهائي":
        approve_hospital = st.session_state.user_hospital
        if "مدير النظام (Admin)" in st.session_state.user_roles:
            approve_hospital = st.selectbox("اختيار مستشفى للاعتماد النهائي:", HOSPITALS_LIST, index=HOSPITALS_LIST.index(st.session_state.user_hospital) if st.session_state.user_hospital in HOSPITALS_LIST else 0, key="app_hosp_sb")

        st.header(f"✅ الشاشة الثالثة: الاعتماد النهائي ({approve_hospital})")
        df_all_p = get_local_purchases()
        
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

        df_approve = df_all_p[(df_all_p["status"] == 'بانتظار الاعتماد') & (df_all_p["hospital"] == approve_hospital)] if not df_all_p.empty else pd.DataFrame()
        
        if not df_approve.empty:
            df_approve_view = df_approve.rename(columns={
                "id": "رقم الطلب", "requester": "المستخدم", "hospital": "المستشفى", "item_number": "رقم البند",
                "nupco_number": "رقم نوبكو", "item_name": "اسم الصنف", "total_cost": "الإجمالي", "status": "الحالة", "reviewed_at": "تاريخ المراجعة"
            })
            
            st.subheader("📦 قائمة الطلبات بانتظار الاعتماد النهائي")
            event_app = st.dataframe(df_approve_view, use_container_width=True, on_select="rerun", selection_mode="single-row")
            sel_rows_app = event_app.selection.rows if hasattr(event_app, "selection") else []
            
            if sel_rows_app:
                app_req_id = int(df_approve_view.iloc[sel_rows_app[0]]["رقم الطلب"])
                current_order_row = df_all_p[df_all_p["id"] == app_req_id]
                if not current_order_row.empty:
                    co = current_order_row.iloc[0]
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
                            
                            updated_row = co.to_dict()
                            updated_row.update({
                                "item_number": str(app_item_number), "nupco_number": str(app_nupco_number),
                                "e_market_code": str(app_e_market_code), "item_name": str(app_item_name),
                                "unit_price": float(app_unit_price), "quantity": int(app_quantity),
                                "total_cost": float(app_total), "importance_criteria": str(app_importance),
                                "reason": str(app_reason), "status": str(final_status),
                                "approved_at": str(now_str), "approver_notes": str(approver_notes)
                            })
                            save_purchase_local(updated_row)
                            st.success("تم تنفيذ وحفظ الاعتماد نهائياً وبسرعة فورية!")
                            st.rerun()
        else:
            st.info(f"لا توجد طلبات بانتظار الاعتماد النهائي في ({approve_hospital}).")

    # ==================== الشاشة الرابعة (إدارة الصلاحيات) ====================
    elif selected_screen == "الشاشة 4: إدارة الصلاحيات":
        if "مدير النظام (Admin)" not in st.session_state.user_roles:
            st.error("❌ عذراً، مخصص للأدمن فقط.")
        else:
            st.header("⚙️ الشاشة الرابعة: إدارة المستخدمين والصلاحيات")
            
            tab1, tab2 = st.tabs(["قائمة المستخدمين والحذف", "إضافة مستخدم جديد"])
            
            with tab1:
                df_users = get_local_users()
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
                                    delete_user_local(u_name)
                                    sync_to_google_sheets()
                                    st.success(f"تم حذف المستخدم {u_name}")
                                    st.rerun()
                        st.markdown("---")
                
                st.subheader("👤 تعديل صلاحيات وحالة مستخدم")
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
                            save_user_local(selected_target_user, target_row['password'], ",".join(updated_roles), updated_status, updated_hosp)
                            sync_to_google_sheets()
                            st.success("تم تحديث المستخدم بنجاح!")
                            st.rerun()

            with tab2:
                with st.form("add_new_user_form"):
                    st.subheader("إضافة حساب مستخدم جديد مباشرة")
                    new_u_name = st.text_input("اسم المستخدم الجديد")
                    new_u_pass = st.text_input("كلمة المرور", type="password")
                    new_u_hosp = st.selectbox("المستشفى التابع له", HOSPITALS_LIST)
                    all_roles_options = ["رفع طلبات", "مراجعة الطلبات", "معتمد الطلبات", "إدارة الصلاحيات", "عرض الداش بورد", "مدير النظام (Admin)"]
                    new_u_roles = st.multiselect("الصلاحيات", all_roles_options, default=["رفع طلبات"])
                    
                    if st.form_submit_button("إضافة المستخدم"):
                        if not new_u_name.strip() or not new_u_pass.strip():
                            st.error("الرجاء إدخال اسم المستخدم وكلمة المرور.")
                        else:
                            df_users = get_local_users()
                            if not df_users[df_users["username"] == new_u_name].empty:
                                st.error("اسم المستخدم موجود مسبقاً.")
                            else:
                                save_user_local(new_u_name, make_hashes(new_u_pass), ",".join(new_u_roles), "معتمد", new_u_hosp)
                                sync_to_google_sheets()
                                st.success(f"تمت إضافة المستخدم {new_u_name} واعتماده بنجاح!")
                                st.rerun()

    # ==================== الشاشة الخامسة (Dashboard التفصيلية) ====================
    elif selected_screen == "الشاشة 5: لوحة التحكّم التفصيلية (Dashboard)":
        st.header("📊 الشاشة الخامسة: لوحة المؤشرات والإحصائيات العامة (Dashboard)")
        
        df_all = get_local_purchases()
        users_df = get_local_users()
        
        dash_hosp_filter = st.selectbox("تصفية لوحة التحكم حسب المستشفى:", ["جميع المستشفيات"] + HOSPITALS_LIST)
        if dash_hosp_filter != "جميع المستشفيات" and not df_all.empty:
            df_all = df_all[df_all['hospital'] == dash_hosp_filter]
        
        if not df_all.empty:
            total_orders = len(df_all)
            total_budget = df_all['total_cost'].sum() if 'total_cost' in df_all.columns else 0.0
            pending_review = len(df_all[df_all['status'] == 'قيد المراجعة'])
            pending_approve = len(df_all[df_all['status'] == 'بانتظار الاعتماد'])
            approved_count = len(df_all[df_all['status'] == 'معتمد نهائياً'])
            rejected_count = len(df_all[df_all['status'].str.contains('مرفوض', na=False)])
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("إجمالي الطلبات", total_orders)
            c2.metric("إجمالي التكاليف", f"{total_budget:,.2f} ر.س")
            c3.metric("الطلبات المعلقة", pending_review + pending_approve)
            c4.metric("الطلبات المعتمدة نهائياً", approved_count)
            
            st.markdown("---")
            rc1, rc2, rc3 = st.columns(3)
            rc1.metric("🔍 قيد المراجعة", pending_review)
            rc2.metric("⏳ بانتظار الاعتماد النهائي", pending_approve)
            rc3.metric("🚫 الطلبات المرفوضة", rejected_count)
            
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
            df_app_dash = df_all[df_all['status'] == 'معتمد نهائياً']
            if not df_app_dash.empty:
                st.dataframe(df_app_dash, use_container_width=True)
            else:
                st.info("لا توجد طلبات معتمدة نهائياً حتى الآن.")
        else:
            st.info("لا توجد بيانات مسجلة في النظام بعد.")
        
        st.markdown("---")
        st.subheader("👥 ملخص الحسابات والمستخدمين في النظام")
        st.dataframe(users_df, use_container_width=True)
