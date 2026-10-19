import sqlite3
import hashlib
import os
import pandas as pd
import streamlit as st
from datetime import datetime

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
    
    .stButton>button {
        border-radius: 8px;
        font-weight: bold;
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
            status TEXT
        )
    ''')
    
    cursor.execute("PRAGMA table_info(users)")
    columns = [column[1] for column in cursor.fetchall()]
    if 'roles' not in columns:
        if 'role' in columns:
            cursor.execute("ALTER TABLE users RENAME COLUMN role TO roles")
        else:
            cursor.execute("ALTER TABLE users ADD COLUMN roles TEXT")
            
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            requester TEXT,
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
    if 'edit_history' not in p_columns:
        cursor.execute("ALTER TABLE purchases ADD COLUMN edit_history TEXT")
    if 'reviewed_at' not in p_columns:
        cursor.execute("ALTER TABLE purchases ADD COLUMN reviewed_at TEXT")
    if 'approved_at' not in p_columns:
        cursor.execute("ALTER TABLE purchases ADD COLUMN approved_at TEXT")

    cursor.execute("SELECT * FROM users WHERE username = 'admin'")
    if not cursor.fetchone():
        admin_roles = "مدير النظام (Admin),رفع طلبات,مراجعة الطلبات,معتمد الطلبات,إدارة الصلاحيات,عرض الداش بورد"
        cursor.execute("INSERT INTO users VALUES ('admin', ?, ?, 'معتمد')", (make_hashes('admin123'), admin_roles))
    
    conn.commit()
    conn.close()

init_db()

def get_db():
    return sqlite3.connect('purchase_system.db', check_same_thread=False)

# --- تحميل ملف الإكسل المرجعي وسحب البيانات ---
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

# --- إدارة جلسة العمل وقيم حقول النموذج ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.user_roles = []

# تهيئة القيم للبحث المنفصل لكل خانة
if 'sel_item_name' not in st.session_state:
    st.session_state.sel_item_name = "-- اختر اسم الصنف --"
if 'sel_nupco' not in st.session_state:
    st.session_state.sel_nupco = "-- اختر رقم نوبكو --"
if 'sel_item_num' not in st.session_state:
    st.session_state.sel_item_num = "-- اختر رقم البند --"

if 'input_e_market' not in st.session_state:
    st.session_state.input_e_market = ""
if 'input_unit_price' not in st.session_state:
    st.session_state.input_unit_price = 0.0
if 'input_quantity' not in st.session_state:
    st.session_state.input_quantity = 1
if 'input_reason' not in st.session_state:
    st.session_state.input_reason = ""

# --- دوال الربط التلقائي لكل خانة منفصلة ---
def on_change_name():
    val = st.session_state.sel_item_name
    if val != "-- اختر اسم الصنف --" and not catalog_df.empty:
        row = catalog_df[catalog_df['اسم الصنف'] == val].iloc[0]
        st.session_state.sel_nupco = str(row['رقم نوبكو'])
        st.session_state.sel_item_num = str(row['رقم البند'])

def on_change_nupco():
    val = st.session_state.sel_nupco
    if val != "-- اختر رقم نوبكو --" and not catalog_df.empty:
        row = catalog_df[catalog_df['رقم نوبكو'] == val].iloc[0]
        st.session_state.sel_item_name = str(row['اسم الصنف'])
        st.session_state.sel_item_num = str(row['رقم البند'])

def on_change_item_num():
    val = st.session_state.sel_item_num
    if val != "-- اختر رقم البند --" and not catalog_df.empty:
        row = catalog_df[catalog_df['رقم البند'] == val].iloc[0]
        st.session_state.sel_item_name = str(row['اسم الصنف'])
        st.session_state.sel_nupco = str(row['رقم نوبكو'])

# --- دالة تصدير إكسل آمنة ---
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
                c.execute("SELECT password, roles, status FROM users WHERE username = ?", (username,))
                data = c.fetchone()
                conn.close()
                
                if data and check_hashes(password, data[0]):
                    if data[2] == "معتمد":
                        st.session_state.logged_in = True
                        st.session_state.username = username
                        st.session_state.user_roles = data[1].split(",") if data[1] else []
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
            all_available_roles = ["رفع طلبات", "مراجعة الطلبات", "معتمد الطلبات", "إدارة الصلاحيات", "عرض الداش بورد"]
            requested_roles = st.multiselect("الصلاحيات المطلوبة (اختر ما تحتاجه)", all_available_roles, default=[])
            submit_signup = st.form_submit_button("إرسال طلب التسجيل")
            
            if submit_signup:
                if new_user and new_pass and requested_roles:
                    conn = get_db()
                    c = conn.cursor()
                    try:
                        roles_str = ",".join(requested_roles)
                        c.execute("INSERT INTO users VALUES (?, ?, ?, 'قيد الانتظار')", 
                                  (new_user, make_hashes(new_pass), roles_str))
                        conn.commit()
                        st.success("✅ تم إرسال طلبك بنجاح! ينتظر اعتماد الأدمن.")
                    except sqlite3.IntegrityError:
                        st.error("❌ اسم المستخدم مستخدم مسبقاً.")
                    conn.close()
                else:
                    st.warning("الرجاء تعبئة جميع الحقول واختيار صلاحية واحدة على الأقل.")

# ==================== الواجهة الرئيسية بعد تسجيل الدخول ====================
else:
    st.sidebar.title("👤 لوحة التحكم")
    st.sidebar.write(f"المستخدم: **{st.session_state.username}**")
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
        st.rerun()

    st.sidebar.markdown("---")
    
    screens = []
    roles = st.session_state.user_roles
    
    if "رفع طلبات" in roles or "مدير النظام (Admin)" in roles:
        screens.append("الشاشة 1: رفع طلبات (إنشاء وتتبع الطلبات)")
    if "مراجعة الطلبات" in roles or "مدير النظام (Admin)" in roles:
        screens.append("الشاشة 2: المراجعة")
    if "معتمد الطلبات" in roles or "مدير النظام (Admin)" in roles:
        screens.append("الشاشة 3: الاعتماد")
    if "إدارة الصلاحيات" in roles or "مدير النظام (Admin)" in roles:
        screens.append("الشاشة 4: الإعدادات وإعطاء الصلاحيات")
    if "عرض الداش بورد" in roles or "مدير النظام (Admin)" in roles:
        screens.append("الشاشة 5: لوحة التحكّم التفصيلية (Dashboard)")

    if not screens:
        st.warning("⚠️ لا توجد لديك أي صلاحيات مفعلة حالياً. الرجاء مراجعة مدير النظام.")
        st.stop()

    selected_screen = st.sidebar.radio("التنقل بين الشاشات:", screens)
    st.sidebar.markdown("---")

    st.markdown('<div class="main-title">تتبع عمليات الشراء</div>', unsafe_allow_html=True)

    # ==================== الشاشة الأولى (البحث المنفصل والتفريغ بعد الإرسال) ====================
    if selected_screen == "الشاشة 1: رفع طلبات (إنشاء وتتبع الطلبات)":
        st.header("🛒 الشاشة الأولى: تقديم طلب شراء جديد")
        
        # تحضير القوائم المنفصلة
        names_list = ["-- اختر اسم الصنف --"]
        nupco_list = ["-- اختر رقم نوبكو --"]
        items_list = ["-- اختر رقم البند --"]

        if not catalog_df.empty:
            names_list += sorted([n for n in catalog_df['اسم الصنف'].unique() if n])
            nupco_list += sorted([n for n in catalog_df['رقم نوبكو'].unique() if n])
            items_list += sorted([n for n in catalog_df['رقم البند'].unique() if n])

        col1, col2, col3 = st.columns(3)
        
        with col1:
            # 1. البحث والتعيين المباشر برقم البند
            idx_item = items_list.index(st.session_state.sel_item_num) if st.session_state.sel_item_num in items_list else 0
            selected_item_num = st.selectbox(
                "1. رقم البند *",
                items_list,
                index=idx_item,
                key="sel_item_num",
                on_change=on_change_item_num
            )
            
            # 2. البحث والتعيين المباشر برقم نوبكو
            idx_nupco = nupco_list.index(st.session_state.sel_nupco) if st.session_state.sel_nupco in nupco_list else 0
            selected_nupco = st.selectbox(
                "2. رقم نوبكو *",
                nupco_list,
                index=idx_nupco,
                key="sel_nupco",
                on_change=on_change_nupco
            )
            
            e_market_code = st.text_input("3. كود السوق الالكتروني *", value=st.session_state.input_e_market, key="k_e_market")

        with col2:
            # 4. البحث والتعيين المباشر باسم الصنف
            idx_name = names_list.index(st.session_state.sel_item_name) if st.session_state.sel_item_name in names_list else 0
            selected_item_name = st.selectbox(
                "4. اسم الصنف *",
                names_list,
                index=idx_name,
                key="sel_item_name",
                on_change=on_change_name
            )
            
            unit_price = st.number_input("5. السعر الافرادي (ر.س) *", min_value=0.0, step=1.0, value=st.session_state.input_unit_price, key="k_unit_price")
            quantity = st.number_input("6. الكمية المطلوبة *", min_value=1, step=1, value=st.session_state.input_quantity, key="k_quantity")

        with col3:
            importance_criteria = st.selectbox("7. معيار الأهمية *", ["عالي جداً (حرج)", "عالي", "متوسط", "منخفض"])
            reason = st.text_area("8. السبب / المبررات (اختياري)", value=st.session_state.input_reason, key="k_reason")

        total_cost = unit_price * quantity
        st.markdown(f"**إجمالي التكلفة المحسوبة:** `{total_cost:,.2f} ر.س`")

        if st.button("إرسال الطلب", use_container_width=True):
            fin_item_num = "" if selected_item_num == "-- اختر رقم البند --" else selected_item_num
            fin_nupco_num = "" if selected_nupco == "-- اختر رقم نوبكو --" else selected_nupco
            fin_item_name = "" if selected_item_name == "-- اختر اسم الصنف --" else selected_item_name

            if not fin_item_num.strip():
                st.error("❌ حقل 'رقم البند' إلزامي.")
            elif not fin_nupco_num.strip():
                st.error("❌ حقل 'رقم نوبكو' إلزامي.")
            elif not e_market_code.strip():
                st.error("❌ حقل 'كود السوق الالكتروني' إلزامي.")
            elif not fin_item_name.strip():
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
                        requester, item_number, nupco_number, e_market_code, 
                        item_name, unit_price, quantity, total_cost, 
                        importance_criteria, reason, status, created_at, reviewed_at, approved_at, edit_history
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'قيد المراجعة', ?, '', '', '')
                ''', (
                    st.session_state.username, fin_item_num, fin_nupco_num, e_market_code, 
                    fin_item_name, unit_price, quantity, total_cost, 
                    importance_criteria, reason, datetime.now().strftime("%Y-%m-%d %H:%M")
                ))
                conn.commit()
                conn.close()
                
                # تفريغ جميع الخانات بالكامل بعد الإرسال
                st.session_state.sel_item_name = "-- اختر اسم الصنف --"
                st.session_state.sel_nupco = "-- اختر رقم نوبكو --"
                st.session_state.sel_item_num = "-- اختر رقم البند --"
                st.session_state.input_e_market = ""
                st.session_state.input_unit_price = 0.0
                st.session_state.input_quantity = 1
                st.session_state.input_reason = ""
                
                st.success("✅ تم إرسال طلب الشراء بنجاح وتفريغ الخانات لتقديم طلب جديد!")
                st.rerun()

        st.markdown("---")
        st.subheader("📋 سجل طلباتك السابقة ومواعيد الاعتماد")
        conn = get_db()
        df_my_orders = pd.read_sql_query('''
            SELECT id AS "رقم الطلب", item_number AS "رقم البند", nupco_number AS "رقم نوبكو", 
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
    elif selected_screen == "الشاشة 2: المراجعة":
        st.header("🔍 الشاشة الثانية: مراجعة الطلبات وتعديلها أو دمجها")
        
        conn = get_db()
        df_review = pd.read_sql_query('''
            SELECT id AS "رقم الطلب", requester AS "المستخدم", item_number AS "رقم البند", 
                   nupco_number AS "رقم نوبكو", e_market_code AS "كود السوق الإلكتروني", 
                   item_name AS "اسم الصنف", unit_price AS "السعر الأفرادي", quantity AS "الكمية", 
                   total_cost AS "الإجمالي", importance_criteria AS "معيار الأهمية", reason AS "السبب", 
                   created_at AS "تاريخ الإنشاء", edit_history AS "سجل التعديلات" 
            FROM purchases WHERE status = 'قيد المراجعة'
        ''', conn)
        conn.close()
        
        if df_review.empty:
            st.info("لا توجد طلبات جديدة بانتظار المراجعة حالياً.")
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

    # ==================== الشاشة الثالثة ====================
    elif selected_screen == "الشاشة 3: الاعتماد":
        st.header("✅ الشاشة الثالثة: الاعتماد النهائي وتصدير البيانات")
        
        conn = get_db()
        df_approve = pd.read_sql_query('''
            SELECT id AS "رقم الطلب", requester AS "المستخدم", item_number AS "رقم البند", 
                   nupco_number AS "رقم نوبكو", e_market_code AS "كود السوق الإلكتروني", item_name AS "اسم الصنف", unit_price AS "السعر الأفرادي", 
                   quantity AS "الكمية", total_cost AS "الإجمالي", importance_criteria AS "معيار الأهمية", 
                   reason AS "السبب", reviewed_at AS "تاريخ ووقت المراجعة", reviewer_notes AS "ملاحظات المراجعة", edit_history AS "سجل التعديلات" 
            FROM purchases WHERE status = 'بانتظار الاعتماد'
        ''', conn)
        
        df_all_approved = pd.read_sql_query('''
            SELECT id AS "رقم الطلب", requester AS "المستخدم", item_number AS "رقم البند", 
                   nupco_number AS "رقم نوبكو", e_market_code AS "كود السوق الإلكتروني", 
                   item_name AS "اسم الصنف", unit_price AS "السعر الأفرادي", quantity AS "الكمية", 
                   total_cost AS "الإجمالي", importance_criteria AS "معيار الأهمية", reason AS "السبب", 
                   status AS "الحالة", created_at AS "تاريخ الإنشاء", reviewed_at AS "تاريخ المراجعة", 
                   approved_at AS "تاريخ الاعتماد النهائي", approver_notes AS "ملاحظات الاعتماد" 
            FROM purchases WHERE status = 'معتمد نهائياً'
        ''', conn)
        conn.close()
        
        if not df_all_approved.empty:
            excel_bytes = to_excel_bytes(df_all_approved)
            st.download_button(
                label="📥 تصدير الطلبات المعتمدة نهائياً إلى ملف Excel متوافق (.xls)",
                data=excel_bytes,
                file_name=f"approved_purchases_{datetime.now().strftime('%Y%m%d_%H%M')}.xls",
                mime="application/vnd.ms-excel"
            )
            st.markdown("---")
        
        if df_approve.empty:
            st.info("لا توجد طلبات بانتظار الاعتماد النهائي حالياً.")
        else:
            st.subheader("📦 الطلبات المعلقة للاعتماد النهائي (انقر على السطر لاختياره)")
            nupco_list_app = [n for n in df_approve["رقم نوبكو"].dropna().unique() if str(n).strip() != ""]
            nupco_filter_app = st.selectbox("تصفية ودمج حسب رقم نوبكو للاعتماد", ["الكل"] + nupco_list_app)
            
            target_app_df = df_approve
            if nupco_filter_app != "الكل":
                target_app_df = df_approve[df_approve["رقم نوبكو"] == nupco_filter_app]
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
