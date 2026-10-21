import sqlite3
import hashlib
import os
import pandas as pd
import streamlit as st
from datetime import datetime

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
    
    /* تخصيص لون زر إرسال الطلب ليصبح أخضر مميز */
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

# --- تهيئة وتحديث قاعدة البيانات تلقائياً ---
def init_db():
    conn = sqlite3.connect('purchase_system.db', check_same_thread=False)
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
    
    cursor.execute("PRAGMA table_info(users)")
    columns = [column[1] for column in cursor.fetchall()]
    if 'roles' not in columns:
        if 'role' in columns:
            cursor.execute("ALTER TABLE users RENAME COLUMN role TO roles")
        else:
            cursor.execute("ALTER TABLE users ADD COLUMN roles TEXT")
    if 'hospital' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN hospital TEXT")
            
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    
    cursor.execute("PRAGMA table_info(purchases)")
    p_columns = [column[1] for column in cursor.fetchall()]
    if 'hospital' not in p_columns:
        cursor.execute("ALTER TABLE purchases ADD COLUMN hospital TEXT")
    if 'edit_history' not in p_columns:
        cursor.execute("ALTER TABLE purchases ADD COLUMN edit_history TEXT")
    if 'reviewed_at' not in p_columns:
        cursor.execute("ALTER TABLE purchases ADD COLUMN reviewed_at TEXT")
    if 'approved_at' not in p_columns:
        cursor.execute("ALTER TABLE purchases ADD COLUMN approved_at TEXT")

    cursor.execute("SELECT * FROM users WHERE username = 'admin'")
    if not cursor.fetchone():
        admin_roles = "مدير النظام (Admin),رفع طلبات,مراجعة الطلبات,معتمد الطلبات,إدارة الصلاحيات,عرض الداش بورد"
        cursor.execute("INSERT INTO users VALUES ('admin', ?, ?, 'معتمد', 'مجمع الملك فيصل')", (make_hashes('admin123'), admin_roles))
    
    conn.commit()
    conn.close()

init_db()

def get_db():
    return sqlite3.connect('purchase_system.db', check_same_thread=False)

# --- تحميل ملف الإكسل وتجهيز القوائم المنسدلة مرة واحدة بذاكرة سريعة ---
@st.cache_data
def load_items_catalog():
    file_path = "استهلاك كل قسم على حدا.xlsx"
    if os.path.exists(file_path):
        try:
            df = pd.read_excel(file_path, engine='openpyxl')
            df['رقم نوبكو'] = df['رقم نوبكو'].astype(str).str.strip()
            df['اسم الصنف'] = df['اسم الصنف'].astype(str).str.strip()
            df['رقم البند'] = df['رقم البند'].fillna('').astype(str).str.strip()
            
            items = ["-- اختر أو ابحث --"] + sorted([x for x in df['رقم البند'].unique() if str(x).strip()])
            nupcos = ["-- اختر أو ابحث --"] + sorted([x for x in df['رقم نوبكو'].unique() if str(x).strip()])
            names = ["-- اختر أو ابحث --"] + sorted([x for x in df['اسم الصنف'].unique() if str(x).strip()])
            
            return df, items, nupcos, names
        except Exception:
            return pd.DataFrame(), ["-- اختر أو ابحث --"], ["-- اختر أو ابحث --"], ["-- اختر أو ابحث --"]
    return pd.DataFrame(), ["-- اختر أو ابحث --"], ["-- اختر أو ابحث --"], ["-- اختر أو ابحث --"]

catalog_df, list_items, list_nupco, list_names = load_items_catalog()

# --- إدارة جلسة العمل ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.user_roles = []
    st.session_state.user_hospital = ""

# تهيئة حقول الشاشة الأولى في session_state للتحكم السريع بدون بطء
if 'sb_item_num' not in st.session_state:
    st.session_state.sb_item_num = "-- اختر أو ابحث --"
if 'sb_nupco' not in st.session_state:
    st.session_state.sb_nupco = "-- اختر أو ابحث --"
if 'sb_name' not in st.session_state:
    st.session_state.sb_name = "-- اختر أو ابحث --"
if 'inp_e_market' not in st.session_state:
    st.session_state.inp_e_market = ""
if 'inp_price' not in st.session_state:
    st.session_state.inp_price = 0.0
if 'inp_qty' not in st.session_state:
    st.session_state.inp_qty = 1
if 'inp_reason' not in st.session_state:
    st.session_state.inp_reason = ""

# --- دوال المزامنة فائقة السرعة ---
def sync_selection(source):
    if catalog_df.empty:
        return
    
    if source == "item_num":
        val = st.session_state.sb_item_num
        if val != "-- اختر أو ابحث --":
            m = catalog_df[catalog_df['رقم البند'] == str(val).strip()]
            if not m.empty:
                st.session_state.sb_nupco = str(m.iloc[0]['رقم نوبكو'])
                st.session_state.sb_name = str(m.iloc[0]['اسم الصنف'])

    elif source == "nupco":
        val = st.session_state.sb_nupco
        if val != "-- اختر أو ابحث --":
            m = catalog_df[catalog_df['رقم نوبكو'] == str(val).strip()]
            if not m.empty:
                st.session_state.sb_item_num = str(m.iloc[0]['رقم البند'])
                st.session_state.sb_name = str(m.iloc[0]['اسم الصنف'])

    elif source == "name":
        val = st.session_state.sb_name
        if val != "-- اختر أو ابحث --":
            m = catalog_df[catalog_df['اسم الصنف'] == str(val).strip()]
            if not m.empty:
                st.session_state.sb_item_num = str(m.iloc[0]['رقم البند'])
                st.session_state.sb_nupco = str(m.iloc[0]['رقم نوبكو'])

def reset_first_screen_form():
    st.session_state.sb_item_num = "-- اختر أو ابحث --"
    st.session_state.sb_nupco = "-- اختر أو ابحث --"
    st.session_state.sb_name = "-- اختر أو ابحث --"
    st.session_state.inp_e_market = ""
    st.session_state.inp_price = 0.0
    st.session_state.inp_qty = 1
    st.session_state.inp_reason = ""

def to_excel_bytes(df):
    html_content = df.to_html(index=False).encode('utf-8-sig')
    return html_content

# ==================== واجهة تسجيل الدخول والتسجيل ====================
if not st.session_state.logged_in:
    st.markdown('<div class="main-title">تتبع عمليات الشراء</div>', unsafe_allow_html=True)
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
                conn = get_db()
                c = conn.cursor()
                c.execute("SELECT password, roles, status, hospital FROM users WHERE username = ?", (username,))
                data = c.fetchone()
                conn.close()
                
                if data and check_hashes(password, data[0]):
                    if data[2] == "معتمد":
                        st.session_state.logged_in = True
                        st.session_state.username = username
                        st.session_state.user_roles = data[1].split(",") if data[1] else []
                        st.session_state.user_hospital = data[3] or "مجمع الملك فيصل"
                        st.success("تم تسجيل الدخول بنجاح!")
                        st.rerun()
                    else:
                        st.warning("⚠️ حسابك قيد الانتظار ولم يتم اعتماده بعد.")
                else:
                    st.error("اسم المستخدم أو كلمة المرور غير صحيحة.")

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
                    conn = get_db()
                    c = conn.cursor()
                    try:
                        roles_str = ",".join(requested_roles)
                        c.execute("INSERT INTO users VALUES (?, ?, ?, 'قيد الانتظار', ?)", 
                                  (new_user, make_hashes(new_pass), roles_str, selected_hospital))
                        conn.commit()
                        st.success("✅ تم إرسال طلبك بنجاح! ينتظر اعتماد الأدمن.")
                    except sqlite3.IntegrityError:
                        st.error("❌ اسم المستخدم مستخدم مسبقاً.")
                    conn.close()
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
                conn = get_db()
                c = conn.cursor()
                c.execute("SELECT password FROM users WHERE username = ?", (st.session_state.username,))
                db_pass = c.fetchone()[0]
                
                if not check_hashes(curr_pass, db_pass):
                    st.error("❌ كلمة المرور الحالية غير صحيحة.")
                elif new_pass1 != new_pass2:
                    st.error("❌ كلمة المرور الجديدة وتأكيدها غير متطابقين.")
                elif len(new_pass1) < 4:
                    st.error("❌ يرجى اختيار كلمة مرور أطول.")
                else:
                    c.execute("UPDATE users SET password = ? WHERE username = ?", (make_hashes(new_pass1), st.session_state.username))
                    conn.commit()
                    st.success("✅ تم تغيير كلمة المرور بنجاح!")
                conn.close()

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

    # ==================== الشاشة الأولى (سريعة جداً وخفيفة) ====================
    if selected_screen == "الشاشة 1: رفع طلبات (إنشاء وتتبع الطلبات)":
        st.header(f"🛒 الشاشة الأولى: تقديم طلب شراء جديد ({st.session_state.user_hospital})")

        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.selectbox(
                "1. رقم البند (ابحث أو اختر) *",
                options=list_items,
                key="sb_item_num",
                on_change=sync_selection,
                args=("item_num",)
            )
            
            st.selectbox(
                "2. رقم نوبكو (ابحث أو اختر) *",
                options=list_nupco,
                key="sb_nupco",
                on_change=sync_selection,
                args=("nupco",)
            )
            
            st.text_input("3. كود السوق الالكتروني *", key="inp_e_market")

        with col2:
            st.selectbox(
                "4. اسم الصنف (ابحث أو اختر) *",
                options=list_names,
                key="sb_name",
                on_change=sync_selection,
                args=("name",)
            )
            
            st.number_input("5. السعر الافرادي (ر.س) *", min_value=0.0, step=1.0, key="inp_price")
            st.number_input("6. الكمية المطلوبة *", min_value=1, step=1, key="inp_qty")

        with col3:
            importance_criteria = st.selectbox("7. معيار الأهمية *", ["عالي جداً (حرج)", "عالي", "متوسط", "منخفض"], key="sb_importance")
            st.text_area("8. السبب / المبررات (اختياري)", key="inp_reason")

        total_cost = st.session_state.inp_price * st.session_state.inp_qty
        st.markdown(f"**إجمالي التكلفة المحسوبة:** `{total_cost:,.2f} ر.س`")

        if st.button("إرسال الطلب", use_container_width=True):
            str_item_num = str(st.session_state.sb_item_num).strip() if st.session_state.sb_item_num != "-- اختر أو ابحث --" else ""
            str_nupco_num = str(st.session_state.sb_nupco).strip() if st.session_state.sb_nupco != "-- اختر أو ابحث --" else ""
            str_item_name = str(st.session_state.sb_name).strip() if st.session_state.sb_name != "-- اختر أو ابحث --" else ""
            str_e_market = st.session_state.inp_e_market.strip()
            unit_price = st.session_state.inp_price
            quantity = st.session_state.inp_qty
            reason_text = st.session_state.inp_reason

            if not str_item_num:
                st.error("❌ حقل 'رقم البند' إلزامي.")
            elif not str_nupco_num:
                st.error("❌ حقل 'رقم نوبكو' إلزامي.")
            elif not str_e_market:
                st.error("❌ حقل 'كود السوق الالكتروني' إلزامي.")
            elif not str_item_name:
                st.error("❌ حقل 'اسم الصنف' إلزامي.")
            elif unit_price <= 0:
                st.error("❌ يرجى إدخال 'سعر أفرادي' أعلى من الصفر.")
            elif quantity <= 0:
                st.error("❌ يرجى إدخال 'كمية' أعلى من الصفر.")
            else:
                conn = get_db()
                c = conn.cursor()
                c.execute('''
                    INSERT INTO purchases (
                        requester, hospital, item_number, nupco_number, e_market_code, 
                        item_name, unit_price, quantity, total_cost, 
                        importance_criteria, reason, status, created_at, reviewed_at, approved_at, edit_history
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'قيد المراجعة', ?, '', '', '')
                ''', (
                    st.session_state.username, st.session_state.user_hospital, str_item_num, str_nupco_num, str_e_market, 
                    str_item_name, unit_price, quantity, total_cost, 
                    importance_criteria, reason_text, datetime.now().strftime("%Y-%m-%d %H:%M")
                ))
                conn.commit()
                conn.close()
                
                # تفريغ الخانات فوراً وبسرعة
                reset_first_screen_form()
                
                st.success("✅ تم إرسال طلب الشراء بنجاح ومسح البيانات الحالية لتقديم طلب جديد!")
                st.rerun()

        st.markdown("---")
        st.subheader("📋 سجل طلباتك السابقة")
        conn = get_db()
        df_my_orders = pd.read_sql_query('''
            SELECT id AS "رقم الطلب", hospital AS "المستشفى", item_number AS "رقم البند", nupco_number AS "رقم نوبكو", 
                   e_market_code AS "كود السوق الإلكتروني", item_name AS "اسم الصنف", 
                   unit_price AS "السعر الأفرادي", quantity AS "الكمية", total_cost AS "الإجمالي", 
                   importance_criteria AS "معيار الأهمية", reason AS "السبب", status AS "الحالة", 
                   created_at AS "تاريخ الإنشاء", reviewed_at AS "تاريخ ووقت المراجعة", 
                   approved_at AS "تاريخ ووقت الاعتماد النهائي", reviewer_notes AS "ملاحظات المراجعة", 
                   approver_notes AS "ملاحظات الاعتماد", edit_history AS "سجل التعديلات" 
            FROM purchases WHERE requester = ?
        ''', conn, params=(st.session_state.username,))
        conn.close()
        st.dataframe(df_my_orders, use_container_width=True)

    # ==================== الشاشة الثانية ====================
    elif selected_screen == "الشاشة 2: المراجعة (مستقلة لكل مستشفى)":
        review_hospital = st.session_state.user_hospital
        
        if "مدير النظام (Admin)" in st.session_state.user_roles:
            review_hospital = st.selectbox("اختيار مستشفى للمراجعة (خاص بالأدمن):", HOSPITALS_LIST, index=HOSPITALS_LIST.index(st.session_state.user_hospital) if st.session_state.user_hospital in HOSPITALS_LIST else 0)

        st.header(f"🔍 الشاشة الثانية: مراجعة الطلبات ({review_hospital})")
        
        conn = get_db()
        df_review = pd.read_sql_query('''
            SELECT id AS "رقم الطلب", requester AS "المستخدم", hospital AS "المستشفى", item_number AS "رقم البند", 
                   nupco_number AS "رقم نوبكو", e_market_code AS "كود السوق الإلكتروني", 
                   item_name AS "اسم الصنف", unit_price AS "السعر الأفرادي", quantity AS "الكمية", 
                   total_cost AS "الإجمالي", importance_criteria AS "معيار الأهمية", reason AS "السبب", 
                   created_at AS "تاريخ الإنشاء", edit_history AS "سجل التعديلات" 
            FROM purchases WHERE status = 'قيد المراجعة' AND hospital = ?
        ''', conn, params=(review_hospital,))
        
        df_all_system = pd.read_sql_query('''
            SELECT id AS "رقم الطلب", requester AS "المستخدم", hospital AS "المستشفى", item_number AS "رقم البند", 
                   nupco_number AS "رقم نوبكو", item_name AS "اسم الصنف", 
                   quantity AS "الكمية", total_cost AS "الإجمالي", status AS "الحالة", 
                   created_at AS "تاريخ الإنشاء" 
            FROM purchases WHERE hospital = ?
        ''', conn, params=(review_hospital,))
        conn.close()
        
        if df_review.empty:
            st.info(f"لا توجد طلبات جديدة بانتظار المراجعة لـ ({review_hospital}) حالياً.")
        else:
            st.subheader("📦 قائمة الطلبات المعلقة للمراجعة (انقر على السطر لاختياره)")
            nupco_list_filter = [n for n in df_review["رقم نوبكو"].dropna().unique() if str(n).strip() != ""]
            nupco_filter = st.selectbox("تصفية ودمج حسب رقم نوبكو", ["الكل"] + nupco_list_filter)
            
            target_df = df_review
            if nupco_filter != "الكل":
                target_df = df_review[df_review["رقم نوبكو"] == nupco_filter]
                st.info(f"يوجد {len(target_df)} طلبات مرتبطة برقم نوبكو: {nupco_filter}")
                
                if len(target_df) > 1:
                    if st.button(f"🔀 دمج الطلبات الـ ({len(target_df)}) المرتبطة برقم نوبكو {nupco_filter}", type="primary"):
                        conn = get_db()
                        c = conn.cursor()
                        ids = target_df["رقم الطلب"].tolist()
                        total_qty = target_df["الكمية"].sum()
                        first_price = target_df["السعر الأفرادي"].iloc[0]
                        total_cost_merged = total_qty * first_price
                        merged_ids_str = ", ".join(map(str, ids))
                        
                        primary_id = ids[0]
                        c.execute('''
                            UPDATE purchases 
                            SET quantity = ?, total_cost = ?, 
                                edit_history = COALESCE(edit_history, '') || ?
                            WHERE id = ?
                        ''', (total_qty, total_cost_merged, f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] تم دمج الطلبات ({merged_ids_str})", primary_id))
                        
                        for remove_id in ids[1:]:
                            c.execute("DELETE FROM purchases WHERE id = ?", (remove_id,))
                            
                        conn.commit()
                        conn.close()
                        st.success(f"تم دمج الطلبات بنجاح في الطلب رقم {primary_id}!")
                        st.rerun()

            event = st.dataframe(
                target_df, 
                use_container_width=True,
                on_select="rerun",
                selection_mode="single-row"
            )
            
            selected_rows = event.selection.rows if hasattr(event, "selection") else []
            
            if selected_rows:
                selected_index = selected_rows[0]
                req_id = int(target_df.iloc[selected_index]["رقم الطلب"])
                selected_nupco_val = str(target_df.iloc[selected_index]["رقم نوبكو"])
                
                st.markdown("---")
                st.subheader(f"🔍 السجل التاريخي للطلبات السابقة لرقم نوبكو: `{selected_nupco_val}` في ({review_hospital}) (بدون الطلب الحالي)")
                if not df_all_system.empty and selected_nupco_val.strip() != "":
                    matched_history_df = df_all_system[
                        (df_all_system["رقم نوبكو"] == selected_nupco_val) & 
                        (df_all_system["رقم الطلب"] != req_id)
                    ]
                    if not matched_history_df.empty:
                        st.dataframe(matched_history_df, use_container_width=True)
                    else:
                        st.info("لا توجد طلبات سابقة مطابقة لرقم نوبكو هذا بخلاف الطلب الحالي.")

                conn = get_db()
                c = conn.cursor()
                c.execute("SELECT item_number, nupco_number, e_market_code, item_name, unit_price, quantity, importance_criteria, reason FROM purchases WHERE id = ?", (req_id,))
                current_order = c.fetchone()
                conn.close()
                
                if current_order:
                    st.markdown("---")
                    st.subheader(f"⚙️ اتخاذ إجراء وتعديل الطلب رقم: {req_id}")
                    with st.form("edit_review_form"):
                        c1, c2, c3 = st.columns(3)
                        with c1:
                            new_item_number = st.text_input("رقم البند", value=current_order[0])
                            new_nupco_number = st.text_input("رقم نوبكو", value=current_order[1])
                            new_e_market_code = st.text_input("كود السوق الإلكتروني", value=current_order[2])
                        with c2:
                            new_item_name = st.text_input("اسم الصنف المعدل", value=current_order[3])
                            new_unit_price = st.number_input("السعر الأفرادي المعدل", value=float(current_order[4]), min_value=0.0)
                            new_quantity = st.number_input("الكمية المعدلة", value=int(current_order[5]), min_value=1, step=1)
                        with c3:
                            importance_options = ["عالي جداً (حرج)", "عالي", "متوسط", "منخفض"]
                            curr_importance = current_order[6] if current_order[6] in importance_options else "متوسط"
                            new_importance = st.selectbox("معيار الأهمية", importance_options, index=importance_options.index(curr_importance))
                            new_reason = st.text_area("السبب / المبرر المعدل", value=current_order[7] or "")
                        
                        review_notes = st.text_input("ملاحظات المراجعة")
                        action = st.selectbox("قرار المراجعة", ["تحويل للاعتماد", "رفض الطلب"])
                        
                        submit_review = st.form_submit_button("حفظ التعديلات وتنفيذ القرار")
                        
                        if submit_review:
                            new_total = new_unit_price * new_quantity
                            now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                            
                            conn = get_db()
                            c = conn.cursor()
                            c.execute("SELECT edit_history FROM purchases WHERE id = ?", (req_id,))
                            old_history = c.fetchone()[0] or ""
                            
                            has_changed = (
                                new_item_number != current_order[0] or
                                new_nupco_number != current_order[1] or
                                new_e_market_code != current_order[2] or
                                new_item_name != current_order[3] or
                                new_unit_price != float(current_order[4]) or
                                new_quantity != int(current_order[5]) or
                                new_importance != current_order[6] or
                                new_reason != (current_order[7] or "")
                            )
                            
                            if has_changed:
                                edit_msg = f"[{now_str} - تم التعديل بواسطة المراجع {st.session_state.username}]"
                                updated_history = (old_history + "\n" + edit_msg).strip()
                            else:
                                updated_history = old_history
                            
                            new_status = "بانتظار الاعتماد" if action == "تحويل للاعتماد" else "مرفوض في المراجعة"
                            c.execute('''
                                UPDATE purchases 
                                SET item_number = ?, nupco_number = ?, e_market_code = ?, item_name = ?, 
                                    unit_price = ?, quantity = ?, total_cost = ?, importance_criteria = ?, 
                                    reason = ?, status = ?, reviewed_at = ?, reviewer_notes = ?, edit_history = ? 
                                WHERE id = ?
                            ''', (new_item_number, new_nupco_number, new_e_market_code, new_item_name, 
                                  new_unit_price, new_quantity, new_total, new_importance, 
                                  new_reason, new_status, now_str, review_notes, updated_history, req_id))
                            conn.commit()
                            conn.close()
                            st.success(f"تم تحديث وتعديل وتسجيل وقت مراجعة الطلب رقم {req_id} بنجاح!")
                            st.rerun()

    # ==================== الشاشة الثالثة (الاعتماد النهائي) ====================
    elif selected_screen == "الشاشة 3: الاعتماد النهائي":
        st.header("✅ الشاشة الثالثة: الاعتماد النهائي")
        
        conn = get_db()
        df_approve = pd.read_sql_query('''
            SELECT id AS "رقم الطلب", requester AS "المستخدم", hospital AS "المستشفى", item_number AS "رقم البند", 
                   nupco_number AS "رقم نوبكو", e_market_code AS "كود السوق الإلكتروني", item_name AS "اسم الصنف", unit_price AS "السعر الأفرادي", 
                   quantity AS "الكمية", total_cost AS "الإجمالي", importance_criteria AS "معيار الأهمية", 
                   reason AS "السبب", reviewed_at AS "تاريخ ووقت المراجعة", reviewer_notes AS "ملاحظات المراجعة", edit_history AS "سجل التعديلات" 
            FROM purchases WHERE status = 'بانتظار الاعتماد'
        ''', conn)
        
        df_all_approved = pd.read_sql_query('''
            SELECT id AS "رقم الطلب", requester AS "المستخدم", hospital AS "المستشفى", item_number AS "رقم البند", 
                   nupco_number AS "رقم نوبكو", e_market_code AS "كود السوق الإلكتروني", 
                   item_name AS "اسم الصنف", unit_price AS "السعر الأفرادي", quantity AS "الكمية", 
                   total_cost AS "الإجمالي", importance_criteria AS "معيار الأهمية", reason AS "السبب", 
                   status AS "الحالة", created_at AS "تاريخ الإنشاء", reviewed_at AS "تاريخ المراجعة", 
                   approved_at AS "تاريخ الاعتماد النهائي", approver_notes AS "ملاحظات الاعتماد" 
            FROM purchases WHERE status = 'معتمد نهائياً'
        ''', conn)
        
        df_all_system_app = pd.read_sql_query('''
            SELECT id AS "رقم الطلب", requester AS "المستخدم", hospital AS "المستشفى", item_number AS "رقم البند", 
                   nupco_number AS "رقم نوبكو", item_name AS "اسم الصنف", 
                   quantity AS "الكمية", total_cost AS "الإجمالي", status AS "الحالة", 
                   created_at AS "تاريخ الإنشاء" 
            FROM purchases
        ''', conn)
        conn.close()
        
        if not df_all_approved.empty:
            excel_bytes = to_excel_bytes(df_all_approved)
            st.download_button(
                label="📥 تصدير الطلبات المعتمدة نهائياً إلى ملف Excel متوافق (.xls)",
                data=excel_bytes,
                file_name=f"approved_purchases_all_{datetime.now().strftime('%Y%m%d_%H%M')}.xls",
                mime="application/vnd.ms-excel"
            )
            st.markdown("---")
        
        if df_approve.empty:
            st.info("لا توجد طلبات بانتظار الاعتماد النهائي حالياً.")
        else:
            filter_col1, filter_col2 = st.columns(2)
            with filter_col1:
                hosp_app_filter = st.selectbox("تصفية حسب المستشفى للاعتماد", ["جميع المستشفيات"] + HOSPITALS_LIST)
            
            target_app_df = df_approve
            if hosp_app_filter != "جميع المستشفيات":
                target_app_df = target_app_df[target_app_df["المستشفى"] == hosp_app_filter]

            with filter_col2:
                nupco_list_app = [n for n in target_app_df["رقم نوبكو"].dropna().unique() if str(n).strip() != ""]
                nupco_filter_app = st.selectbox("تصفية ودمج حسب رقم نوبكو للاعتماد", ["الكل"] + nupco_list_app)
            
            if nupco_filter_app != "الكل":
                target_app_df = target_app_df[target_app_df["رقم نوبكو"] == nupco_filter_app]
                st.info(f"يوجد {len(target_app_df)} طلبات مرتبطة برقم نوبكو: {nupco_filter_app}")
                
                if len(target_app_df) > 1:
                    if st.button(f"🔀 دمج الطلبات الـ ({len(target_app_df)}) في الاعتماد", type="primary"):
                        conn = get_db()
                        c = conn.cursor()
                        ids = target_app_df["رقم الطلب"].tolist()
                        total_qty = target_app_df["الكمية"].sum()
                        first_price = target_app_df["السعر الأفرادي"].iloc[0]
                        total_cost_merged = total_qty * first_price
                        merged_ids_str = ", ".join(map(str, ids))
                        
                        primary_id = ids[0]
                        c.execute('''
                            UPDATE purchases 
                            SET quantity = ?, total_cost = ?, 
                                edit_history = COALESCE(edit_history, '') || ?
                            WHERE id = ?
                        ''', (total_qty, total_cost_merged, f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] تم دمج الطلبات ({merged_ids_str})", primary_id))
                        
                        for remove_id in ids[1:]:
                            c.execute("DELETE FROM purchases WHERE id = ?", (remove_id,))
                            
                        conn.commit()
                        conn.close()
                        st.success(f"تم دمج الطلبات بنجاح في الطلب رقم {primary_id}!")
                        st.rerun()

            event_app = st.dataframe(
                target_app_df, 
                use_container_width=True,
                on_select="rerun",
                selection_mode="single-row"
            )
            
            selected_app_rows = event_app.selection.rows if hasattr(event_app, "selection") else []
            
            if selected_app_rows:
                selected_app_index = selected_app_rows[0]
                req_id_app = int(target_app_df.iloc[selected_app_index]["رقم الطلب"])
                selected_nupco_app_val = str(target_app_df.iloc[selected_app_index]["رقم نوبكو"])
                
                st.markdown("---")
                st.subheader(f"🔍 السجل التاريخي للطلبات السابقة لرقم نوبكو: `{selected_nupco_app_val}` (بدون الطلب الحالي)")
                if not df_all_system_app.empty and selected_nupco_app_val.strip() != "":
                    matched_history_app_df = df_all_system_app[
                        (df_all_system_app["رقم نوبكو"] == selected_nupco_app_val) & 
                        (df_all_system_app["رقم الطلب"] != req_id_app)
                    ]
                    if not matched_history_app_df.empty:
                        st.dataframe(matched_history_app_df, use_container_width=True)
                    else:
                        st.info("لا توجد طلبات سابقة مطابقة لرقم نوبكو هذا بخلاف الطلب الحالي.")

                conn = get_db()
                c = conn.cursor()
                c.execute("SELECT item_number, nupco_number, e_market_code, item_name, unit_price, quantity, importance_criteria, reason FROM purchases WHERE id = ?", (req_id_app,))
                current_app_order = c.fetchone()
                conn.close()
                
                if current_app_order:
                    st.markdown("---")
                    st.subheader(f"⚙️ تعديل واعتماد الطلب نهائياً رقم: {req_id_app}")
                    with st.form("edit_approve_form"):
                        c1, c2, c3 = st.columns(3)
                        with c1:
                            app_item_number = st.text_input("رقم البند", value=current_app_order[0])
                            app_nupco_number = st.text_input("رقم نوبكو", value=current_app_order[1])
                            app_e_market_code = st.text_input("كود السوق الإلكتروني", value=current_app_order[2])
                        with c2:
                            app_item_name = st.text_input("اسم الصنف (تعديل نهائي)", value=current_app_order[3])
                            app_unit_price = st.number_input("السعر الأفرادي (تعديل نهائي)", value=float(current_app_order[4]), min_value=0.0)
                            app_quantity = st.number_input("الكمية (تعديل نهائي)", value=int(current_app_order[5]), min_value=1, step=1)
                        with c3:
                            importance_options = ["عالي جداً (حرج)", "عالي", "متوسط", "منخفض"]
                            curr_importance = current_app_order[6] if current_app_order[6] in importance_options else "متوسط"
                            app_importance = st.selectbox("معيار الأهمية", importance_options, index=importance_options.index(curr_importance))
                            app_reason = st.text_area("السبب (تعديل نهائي)", value=current_app_order[7] or "")
                        
                        approver_notes = st.text_input("ملاحظات الاعتماد النهائي")
                        final_action = st.selectbox("قرار الاعتماد النهائي", ["اعتماد نهائي للشراء", "رفض نهائي"])
                        
                        submit_approval = st.form_submit_button("تأكيد التعديل والقرار النهائي")
                        
                        if submit_approval:
                            new_total_app = app_unit_price * app_quantity
                            now_str_app = datetime.now().strftime("%Y-%m-%d %H:%M")
                            
                            conn = get_db()
                            c = conn.cursor()
                            c.execute("SELECT edit_history FROM purchases WHERE id = ?", (req_id_app,))
                            old_history_app = c.fetchone()[0] or ""
                            
                            has_changed_app = (
                                app_item_number != current_app_order[0] or
                                app_nupco_number != current_app_order[1] or
                                app_e_market_code != current_app_order[2] or
                                app_item_name != current_app_order[3] or
                                app_unit_price != float(current_app_order[4]) or
                                app_quantity != int(current_app_order[5]) or
                                app_importance != current_app_order[6] or
                                app_reason != (current_app_order[7] or "")
                            )
                            
                            if has_changed_app:
                                edit_msg_app = f"[{now_str_app} - تم التعديل بواسطة المعتمد {st.session_state.username}]"
                                updated_history_app = (old_history_app + "\n" + edit_msg_app).strip()
                            else:
                                updated_history_app = old_history_app
                            
                            final_status = "معتمد نهائياً" if final_action == "اعتماد نهائي للشراء" else "مرفوض نهائياً"
                            c.execute('''
                                UPDATE purchases 
                                SET item_number = ?, nupco_number = ?, e_market_code = ?, item_name = ?, 
                                    unit_price = ?, quantity = ?, total_cost = ?, importance_criteria = ?, 
                                    reason = ?, status = ?, approved_at = ?, approver_notes = ?, edit_history = ? 
                                WHERE id = ?
                            ''', (app_item_number, app_nupco_number, app_e_market_code, app_item_name, 
                                  app_unit_price, app_quantity, new_total_app, app_importance, 
                                  app_reason, final_status, now_str_app, approver_notes, updated_history_app, req_id_app))
                            conn.commit()
                            conn.close()
                            st.success(f"تم اتخاذ القرار النهائي وتسجيل وقت الاعتماد للطلب رقم {req_id_app}.")
                            st.rerun()

    # ==================== الشاشة الرابعة (إدارة الصلاحيات) ====================
    elif selected_screen == "الشاشة 4: إدارة الصلاحيات":
        st.header("⚙️ الشاشة الرابعة: إدارة الصلاحيات")
        
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT username, roles, status, hospital FROM users")
        all_users_data = c.fetchall()
        conn.close()
        
        st.subheader("📋 جدول المستخدمين الحاليين")
        
        if all_users_data:
            header_col1, header_col2, header_col3, header_col4, header_col5 = st.columns([2, 2, 3, 2, 1])
            header_col1.markdown("**اسم المستخدم**")
            header_col2.markdown("**المستشفى**")
            header_col3.markdown("**الصلاحيات**")
            header_col4.markdown("**الحالة**")
            header_col5.markdown("**حذف**")
            st.markdown("---")
            
            for u in all_users_data:
                u_name = u[0]
                u_roles = u[1]
                u_status = u[2]
                u_hosp = u[3] or "مجمع الملك فيصل"
                
                row_col1, row_col2, row_col3, row_col4, row_col5 = st.columns([2, 2, 3, 2, 1])
                row_col1.write(u_name)
                row_col2.write(u_hosp)
                row_col3.write(u_roles)
                row_col4.write(u_status)
                
                with row_col5:
                    if st.button("🗑️", key=f"table_del_{u_name}", type="secondary"):
                        if u_name == "admin":
                            st.error("❌ لا يمكن حذف حساب المدير الأساسي (admin).")
                        elif u_name == st.session_state.username:
                            st.error("❌ لا يمكنك حذف حسابك الحالي.")
                        else:
                            conn = get_db()
                            c = conn.cursor()
                            c.execute("DELETE FROM users WHERE username = ?", (u_name,))
                            conn.commit()
                            conn.close()
                            st.success(f"✅ تم حذف المستخدم ({u_name}) بنجاح!")
                            st.rerun()
                st.markdown("---")
        else:
            st.info("لا توجد حسابات مستخدمين مسجلة.")
        
        st.subheader("👤 إدارة صلاحيات المستخدمين")
        
        usernames_list = [u[0] for u in all_users_data]
        selected_target_user = st.selectbox("اختر اسم المستخدم للتعديل المباشر", usernames_list)
        
        if selected_target_user:
            user_current_data = next((u for u in all_users_data if u[0] == selected_target_user), None)
            current_roles_list = user_current_data[1].split(",") if user_current_data[1] else []
            current_status = user_current_data[2]
            current_hosp = user_current_data[3] or "مجمع الملك فيصل"
            
            with st.form("direct_user_edit_form"):
                st.write(f"تعديل صلاحيات وحالة المستخدم: **{selected_target_user}**")
                
                updated_hosp = st.selectbox("تعديل المستشفى التابع له", HOSPITALS_LIST, index=HOSPITALS_LIST.index(current_hosp) if current_hosp in HOSPITALS_LIST else 0)
                
                all_roles_options = ["رفع طلبات", "مراجعة الطلبات", "معتمد الطلبات", "إدارة الصلاحيات", "عرض الداش بورد", "مدير النظام (Admin)"]
                updated_roles = st.multiselect(
                    "تعديل الصلاحيات (تعدد الصلاحيات)", 
                    all_roles_options,
                    default=[r for r in current_roles_list if r in all_roles_options]
                )
                
                status_options = ["معتمد", "قيد الانتظار", "موقوف"]
                status_index = status_options.index(current_status) if current_status in status_options else 0
                updated_status = st.selectbox("حالة الحساب", status_options, index=status_index)
                
                submit_user_edit = st.form_submit_button("حفظ التعديلات فوراً")
                
                if submit_user_edit:
                    if updated_roles:
                        roles_string = ",".join(updated_roles)
                        conn = get_db()
                        c = conn.cursor()
                        c.execute("UPDATE users SET roles = ?, status = ?, hospital = ? WHERE username = ?", (roles_string, updated_status, updated_hosp, selected_target_user))
                        conn.commit()
                        conn.close()
                        st.success(f"تم تحديث صلاحيات ومستشفى المستخدم ({selected_target_user}) بنجاح!")
                        st.rerun()
                    else:
                        st.warning("الرجاء اختيار صلاحية واحدة على الأقل.")

    # ==================== الشاشة الخامسة (لوحة التحكم والتقارير) ====================
    elif selected_screen == "الشاشة 5: لوحة التحكّم التفصيلية (Dashboard)":
        st.header("📊 الشاشة الخامسة: لوحة التحكم والتقارير التفصيلية")
        
        conn = get_db()
        df_all = pd.read_sql_query('''
            SELECT id AS "رقم الطلب", requester AS "المستخدم", hospital AS "المستشفى", item_number AS "رقم البند", 
                   nupco_number AS "رقم نوبكو", e_market_code AS "كود السوق الإلكتروني", item_name AS "اسم الصنف", 
                   unit_price AS "السعر الأفرادي", quantity AS "الكمية", total_cost AS "الإجمالي", 
                   importance_criteria AS "معيار الأهمية", reason AS "السبب", status AS "الحالة", 
                   created_at AS "تاريخ الإنشاء", reviewed_at AS "تاريخ المراجعة", 
                   approved_at AS "تاريخ الاعتماد النهائي", reviewer_notes AS "ملاحظات المراجعة", 
                   approver_notes AS "ملاحظات الاعتماد", edit_history AS "سجل التعديلات" 
            FROM purchases
        ''', conn)
        
        users_df = pd.read_sql_query('''
            SELECT username AS "اسم المستخدم", hospital AS "المستشفى", roles AS "الصلاحيات", status AS "الحالة" 
            FROM users
        ''', conn)
        conn.close()
        
        dash_hosp_filter = st.selectbox("تصفية لوحة التحكم حسب المستشفى:", ["جميع المستشفيات"] + HOSPITALS_LIST)
        
        if dash_hosp_filter != "جميع المستشفيات" and not df_all.empty:
            df_all = df_all[df_all['المستشفى'] == dash_hosp_filter]
        
        df_review_pending = df_all[df_all['الحالة'] == 'قيد المراجعة'] if not df_all.empty else pd.DataFrame()
        df_review_approved = df_all[(df_all['الحالة'] == 'بانتظار الاعتماد') | (df_all['الحالة'] == 'معتمد نهائياً') | (df_all['الحالة'] == 'مرفوض نهائياً')] if not df_all.empty else pd.DataFrame()
        df_review_rejected = df_all[df_all['الحالة'] == 'مرفوض في المراجعة'] if not df_all.empty else pd.DataFrame()
        
        df_final_approved = df_all[df_all['الحالة'] == 'معتمد نهائياً'] if not df_all.empty else pd.DataFrame()
        df_final_rejected = df_all[df_all['الحالة'] == 'مرفوض نهائياً'] if not df_all.empty else pd.DataFrame()
        
        st.subheader("📌 إحصائيات مرحلة المراجعة")
        rc1, rc2, rc3 = st.columns(3)
        rc1.metric("🔍 طلبات قيد المراجعة (معلقة)", len(df_review_pending))
        rc2.metric("✅ طلبات معتمدة بالمراجعة (تم تحويلها)", len(df_review_approved))
        rc3.metric("❌ طلبات مرفوضة في المراجعة", len(df_review_rejected))
        
        st.markdown("---")
        
        st.subheader("📌 إحصائيات مرحلة الاعتماد النهائي")
        fc1, fc2, fc3 = st.columns(3)
        fc1.metric("⏳ طلبات بانتظار الاعتماد النهائي", len(df_all[df_all['الحالة'] == 'بانتظار الاعتماد']) if not df_all.empty else 0)
        fc2.metric("✅ طلبات معتمدة نهائياً", len(df_final_approved))
        fc3.metric("🚫 طلبات مرفوضة نهائياً", len(df_final_rejected))
        
        st.markdown("---")
        
        st.subheader("🔍 تفاصيل مرحلة: قيد المراجعة (المعلقة)")
        if not df_review_pending.empty:
            st.dataframe(df_review_pending, use_container_width=True)
        else:
            st.info("لا توجد طلبات معلقة قيد المراجعة.")
            
        st.markdown("---")
        
        st.subheader("⏳ تفاصيل مرحلة: بانتظار الاعتماد النهائي")
        df_wait = df_all[df_all['الحالة'] == 'بانتظار الاعتماد'] if not df_all.empty else pd.DataFrame()
        if not df_wait.empty:
            st.dataframe(df_wait, use_container_width=True)
        else:
            st.info("لا توجد طلبات بانتظار الاعتماد النهائي حالياً.")
            
        st.markdown("---")
        
        st.subheader("✅ تفاصيل مرحلة: الطلبات المعتمدة نهائياً")
        if not df_final_approved.empty:
            total_approved_cost = df_final_approved['الإجمالي'].sum()
            st.metric("💰 إجمالي تكلفة الطلبات المعتمدة نهائياً", f"{total_approved_cost:,.2f} ر.س")
            st.dataframe(df_final_approved, use_container_width=True)
        else:
            st.info("لا توجد طلبات معتمدة نهائياً حتى الآن.")
            
        st.markdown("---")
        
        st.subheader("👥 ملخص الحسابات والمستخدمين في النظام")
        st.dataframe(users_df, use_container_width=True)
