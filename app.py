import sys
import subprocess

# تثبيت المكتبات تلقائياً إذا لم تكن موجودة
def install_packages():
    for package in ["streamlit", "pandas"]:
        try:
            __import__(package)
        except ImportError:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])

install_packages()

import sqlite3
import hashlib
import pandas as pd
import streamlit as st
from datetime import datetime

# --- إعدادات وتشفير كلمات المرور ---
def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    return make_hashes(password) == hashed_text

# --- تهيئة قاعدة البيانات ---
def init_db():
    conn = sqlite3.connect('purchase_system.db', check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT,
            role TEXT,
            status TEXT
        )
    ''')
    
    # تحديث جدول طلبات الشراء ليشمل جميع الحقول الجديدة
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
            reviewer_notes TEXT,
            approver_notes TEXT
        )
    ''')
    
    cursor.execute("SELECT * FROM users WHERE username = 'admin'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO users VALUES ('admin', ?, 'مدير النظام (Admin)', 'معتمد')", (make_hashes('admin123'),))
    
    conn.commit()
    conn.close()

init_db()

def get_db():
    return sqlite3.connect('purchase_system.db', check_same_thread=False)

st.set_page_config(page_title="نظام تتبع عمليات الشراء", layout="wide", page_icon="📋")

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.role = ""

if not st.session_state.logged_in:
    st.title("📋 نظام تتبع عمليات الشراء والمشتريات")
    st.markdown("---")
    
    auth_choice = st.sidebar.selectbox("القائمة الرئيسية", ["تسجيل الدخول", "إنشاء حساب جديد"])
    
    if auth_choice == "تسجيل الدخول":
        st.subheader("🔑 تسجيل الدخول للنظام")
        with st.form("login_form"):
            username = st.text_input("اسم المستخدم")
            password = st.text_input("كلمة المرور", type='password')
            submit_login = st.form_submit_button("دخول")
            
            if submit_login:
                conn = get_db()
                c = conn.cursor()
                c.execute("SELECT password, role, status FROM users WHERE username = ?", (username,))
                data = c.fetchone()
                conn.close()
                
                if data and check_hashes(password, data[0]):
                    if data[2] == "معتمد":
                        st.session_state.logged_in = True
                        st.session_state.username = username
                        st.session_state.role = data[1]
                        st.success("تم تسجيل الدخول بنجاح!")
                        st.rerun()
                    else:
                        st.warning("⚠️ حسابك قيد الانتظار ولم يتم اعتماده من قِبل الأدمن بعد.")
                else:
                    st.error("اسم المستخدم أو كلمة المرور غير صحيحة.")
        
        st.info("💡 **بيانات المسؤول الافتراضية:**\n* اسم المستخدم: `admin`\n* كلمة المرور: `admin123`")

    elif auth_choice == "إنشاء حساب جديد":
        st.subheader("📝 طلب تسجيل حساب جديد")
        with st.form("signup_form"):
            new_user = st.text_input("اختر اسم مستخدم")
            new_pass = st.text_input("اختر كلمة المرور", type='password')
            requested_role = st.selectbox("الصلاحية المطلوبة", ["مستخدم طلبات", "مراجعة الطلبات", "معتمد الطلبات"])
            submit_signup = st.form_submit_button("إرسال طلب التسجيل")
            
            if submit_signup:
                if new_user and new_pass:
                    conn = get_db()
                    c = conn.cursor()
                    try:
                        c.execute("INSERT INTO users VALUES (?, ?, ?, 'قيد الانتظار')", 
                                  (new_user, make_hashes(new_pass), requested_role))
                        conn.commit()
                        st.success("✅ تم إرسال طلبك بنجاح! لن تتمكن من الدخول حتى يقوم الأدمن باعتماد الحساب وتفعيله.")
                    except sqlite3.IntegrityError:
                        st.error("❌ اسم المستخدم مستخدم مسبقاً، الرجاء اختيار اسم آخر.")
                    conn.close()
                else:
                    st.warning("الرجاء تعبئة جميع الحقول المطلوبة.")

else:
    st.sidebar.title("👤 لوحة التحكم")
    st.sidebar.write(f"المستخدم: **{st.session_state.username}**")
    st.sidebar.write(f"الدور: **{st.session_state.role}**")
    
    if st.sidebar.button("تسجيل الخروج"):
        st.session_state.logged_in = False
        st.rerun()

    st.sidebar.markdown("---")
    
    screens = ["الشاشة 1: المستخدم الأول (إنشاء وتتبع الطلبات)"]
    role = st.session_state.role
    
    if role in ["مراجعة الطلبات", "مدير النظام (Admin)"]:
        screens.append("الشاشة 2: المراجعة")
    if role in ["معتمد الطلبات", "مدير النظام (Admin)"]:
        screens.append("الشاشة 3: الاعتماد")
    if role == "مدير النظام (Admin)":
        screens.append("الشاشة 4: الإعدادات وإعطاء الصلاحيات")
        screens.append("الشاشة 5: لوحة التحكّم التفصيلية (Dashboard)")

    selected_screen = st.sidebar.radio("التنقل بين الشاشات:", screens)
    st.sidebar.markdown("---")

    # ==================== الشاشة الأولى ====================
    if selected_screen == "الشاشة 1: المستخدم الأول (إنشاء وتتبع الطلبات)":
        st.header("🛒 الشاشة الأولى: تقديم طلب شراء جديد")
        with st.form("purchase_form"):
            col1, col2, col3 = st.columns(3)
            with col1:
                item_number = st.text_input("1. رقم البند")
                nupco_number = st.text_input("2. رقم نوبكو")
                e_market_code = st.text_input("3. كود السوق الالكتروني للبنود التخصصية")
            with col2:
                item_name = st.text_input("4. اسم الصنف")
                unit_price = st.number_input("5. السعر الافرادي (ر.س)", min_value=0.0, step=1.0)
                quantity = st.number_input("6. الكمية المطلوبة", min_value=1, step=1)
            with col3:
                importance_criteria = st.selectbox("7. معيار الأهمية", ["عالي جداً (حرج)", "عالي", "متوسط", "منخفض"])
                reason = st.text_area("8. السبب / المبررات")
            
            # حساب إجمالي التكلفة تلقائياً
            total_cost = unit_price * quantity
            st.markdown(f"**إجمالي التكلفة المحسوبة:** `{total_cost:,.2f} ر.س`")
            
            submit_order = st.form_submit_button("إرسال الطلب")
            if submit_order:
                if item_name:
                    conn = get_db()
                    c = conn.cursor()
                    c.execute('''
                        INSERT INTO purchases (
                            requester, item_number, nupco_number, e_market_code, 
                            item_name, unit_price, quantity, total_cost, 
                            importance_criteria, reason, status, created_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'قيد المراجعة', ?)
                    ''', (
                        st.session_state.username, item_number, nupco_number, e_market_code, 
                        item_name, unit_price, quantity, total_cost, 
                        importance_criteria, reason, datetime.now().strftime("%Y-%m-%d %H:%M")
                    ))
                    conn.commit()
                    conn.close()
                    st.success("تم إرسال طلب الشراء بنجاح وهو الآن قيد المراجعة.")
                else:
                    st.error("الرجاء إدخال اسم الصنف على الأقل.")

        st.subheader("📋 سجل طلباتك السابقة وملاحظات المراجعة والاعتماد")
        conn = get_db()
        df_my_orders = pd.read_sql_query('''
            SELECT id AS "رقم الطلب", item_number AS "رقم البند", nupco_number AS "رقم نوبكو", 
                   e_market_code AS "كود السوق الإلكتروني", item_name AS "اسم الصنف", 
                   unit_price AS "السعر الأفرادي", quantity AS "الكمية", total_cost AS "الإجمالي", 
                   importance_criteria AS "معيار الأهمية", reason AS "السبب", status AS "الحالة", 
                   created_at AS "تاريخ الطلب", reviewer_notes AS "ملاحظات المراجعة", approver_notes AS "ملاحظات الاعتماد" 
            FROM purchases WHERE requester = ?
        ''', conn, params=(st.session_state.username,))
        conn.close()
        st.dataframe(df_my_orders, use_container_width=True)

    # ==================== الشاشة الثانية ====================
    elif selected_screen == "الشاشة 2: المراجعة":
        st.header("🔍 الشاشة الثانية: مراجعة الطلبات")
        conn = get_db()
        df_review = pd.read_sql_query('''
            SELECT id AS "رقم الطلب", requester AS "المستخدم", item_number AS "رقم البند", 
                   nupco_number AS "رقم نوبكو", e_market_code AS "كود السوق الإلكتروني", 
                   item_name AS "اسم الصنف", unit_price AS "السعر الأفرادي", quantity AS "الكمية", 
                   total_cost AS "الإجمالي", importance_criteria AS "معيار الأهمية", reason AS "السبب", 
                   created_at AS "التاريخ" 
            FROM purchases WHERE status = 'قيد المراجعة'
        ''', conn)
        conn.close()
        
        if df_review.empty:
            st.info("لا توجد طلبات جديدة بانتظار المراجعة حالياً.")
        else:
            st.dataframe(df_review, use_container_width=True)
            st.markdown("---")
            req_id = st.number_input("أدخل رقم الطلب (رقم الطلب) المراد اتخاذ إجراء بشأنه", min_value=1, step=1)
            review_notes = st.text_input("ملاحظات المراجعة")
            action = st.selectbox("قرار المراجعة", ["تحويل للاعتماد", "رفض الطلب"])
            
            if st.button("تنفيذ قرار المراجعة"):
                conn = get_db()
                c = conn.cursor()
                new_status = "بانتظار الاعتماد" if action == "تحويل للاعتماد" else "مرفوض في المراجعة"
                c.execute("UPDATE purchases SET status = ?, reviewer_notes = ? WHERE id = ?", (new_status, review_notes, req_id))
                conn.commit()
                conn.close()
                st.success(f"تم تحديث حالة الطلب رقم {req_id} بنجاح.")
                st.rerun()

    # ==================== الشاشة الثالثة ====================
    elif selected_screen == "الشاشة 3: الاعتماد":
        st.header("✅ الشاشة الثالثة: اعتماد الطلبات النهائي")
        conn = get_db()
        df_approve = pd.read_sql_query('''
            SELECT id AS "رقم الطلب", requester AS "المستخدم", item_number AS "رقم البند", 
                   nupco_number AS "رقم نوبكو", item_name AS "اسم الصنف", unit_price AS "السعر الأفرادي", 
                   quantity AS "الكمية", total_cost AS "الإجمالي", importance_criteria AS "معيار الأهمية", 
                   reason AS "السبب", reviewer_notes AS "ملاحظات المراجعة" 
            FROM purchases WHERE status = 'بانتظار الاعتماد'
        ''', conn)
        conn.close()
        
        if df_approve.empty:
            st.info("لا توجد طلبات بانتظار الاعتماد النهائي حالياً.")
        else:
            st.dataframe(df_approve, use_container_width=True)
            st.markdown("---")
            req_id = st.number_input("أدخل رقم الطلب (رقم الطلب) للاعتماد النهائي", min_value=1, step=1)
            approver_notes = st.text_input("ملاحظات الاعتماد")
            final_action = st.selectbox("قرار الاعتماد النهائي", ["اعتماد نهائي للشراء", "رفض نهائي"])
            
            if st.button("تأكيد القرار النهائي"):
                conn = get_db()
                c = conn.cursor()
                final_status = "معتمد نهائياً" if final_action == "اعتماد نهائي للشراء" else "مرفوض نهائياً"
                c.execute("UPDATE purchases SET status = ?, approver_notes = ? WHERE id = ?", (final_status, approver_notes, req_id))
                conn.commit()
                conn.close()
                st.success(f"تم اتخاذ القرار النهائي للطلب رقم {req_id}.")
                st.rerun()

    # ==================== الشاشة الرابعة ====================
    elif selected_screen == "الشاشة 4: الإعدادات وإعطاء الصلاحيات":
        st.header("⚙️ الشاشة الرابعة: إعدادات المستخدمين وإدارة الصلاحيات")
        
        conn = get_db()
        users_df = pd.read_sql_query("SELECT username AS 'اسم المستخدم', role AS 'الصلاحية', status AS 'الحالة' FROM users", conn)
        conn.close()
        
        st.subheader("قائمة كافة المستخدمين وحساباتهم المعلقة أو المعتمدة")
        st.dataframe(users_df, use_container_width=True)
        
        st.markdown("---")
        st.subheader("تفعيل حساب أو تعديل صلاحية مستخدم")
        
        with st.form("admin_settings_form"):
            target_user = st.text_input("اكتب اسم المستخدم المراد تعديله بدقة")
            new_status = st.selectbox("تغيير حالة الحساب", ["معتمد", "قيد الانتظار", "موقوف"])
            new_role = st.selectbox("تغيير الدور والصلاحية", ["مستخدم طلبات", "مراجعة الطلبات", "معتمد الطلبات", "مدير النظام (Admin)"])
            submit_changes = st.form_submit_button("حفظ وتحديث الصلاحيات")
            
            if submit_changes:
                if target_user:
                    conn = get_db()
                    c = conn.cursor()
                    c.execute("UPDATE users SET status = ?, role = ? WHERE username = ?", (new_status, new_role, target_user))
                    conn.commit()
                    conn.close()
                    st.success(f"تم تحديث بيانات وحالة المستخدم ({target_user}) بنجاح!")
                    st.rerun()
                else:
                    st.warning("الرجاء كتابة اسم المستخدم المراد تعديله.")

    # ==================== الشاشة الخامسة ====================
    elif selected_screen == "الشاشة 5: لوحة التحكّم التفصيلية (Dashboard)":
        st.header("📊 الشاشة الخامسة: لوحة التحكم والتقارير التفصيلية")
        
        conn = get_db()
        all_purchases = pd.read_sql_query("SELECT * FROM purchases", conn)
        all_users = pd.read_sql_query("SELECT * FROM users", conn)
        conn.close()
        
        total_orders = len(all_purchases)
        total_users = len(all_users)
        approved_orders = len(all_purchases[all_purchases['status'] == 'معتمد نهائياً']) if not all_purchases.empty else 0
        pending_orders = len(all_purchases[all_purchases['status'].isin(['قيد المراجعة', 'بانتظار الاعتماد'])]) if not all_purchases.empty else 0
        total_cost = all_purchases['total_cost'].sum() if not all_purchases.empty else 0.0
        
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("إجمالي الطلبات", total_orders)
        col2.metric("الطلبات المعتمدة", approved_orders)
        col3.metric("الطلبات المعلقة", pending_orders)
        col4.metric("إجمالي المستخدمين", total_users)
        col5.metric("إجمالي التكاليف (ر.س)", f"{total_cost:,.2f}")
        
        st.markdown("---")
        st.subheader("📈 تفاصيل كافة الطلبات في النظام")
        if not all_purchases.empty:
            st.dataframe(all_purchases, use_container_width=True)
        else:
            st.info("لا توجد بيانات طلبات مسجلة حتى الآن.")
            
        st.markdown("---")
        st.subheader("👥 ملخص المستخدمين وحالاتهم")
        st.dataframe(all_users, use_container_width=True)
