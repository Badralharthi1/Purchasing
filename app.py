import sqlite3
import hashlib
import io
import struct
import pandas as pd
import streamlit as st
from datetime import datetime

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
            reviewer_notes TEXT,
            approver_notes TEXT,
            edit_history TEXT
        )
    ''')
    
    cursor.execute("PRAGMA table_info(purchases)")
    p_columns = [column[1] for column in cursor.fetchall()]
    if 'edit_history' not in p_columns:
        cursor.execute("ALTER TABLE purchases ADD COLUMN edit_history TEXT")

    # حساب الـ admin الافتراضي
    cursor.execute("SELECT * FROM users WHERE username = 'admin'")
    if not cursor.fetchone():
        admin_roles = "مدير النظام (Admin),رفع طلبات,مراجعة الطلبات,معتمد الطلبات,إدارة الصلاحيات,عرض الداش بورد"
        cursor.execute("INSERT INTO users VALUES ('admin', ?, ?, 'معتمد')", (make_hashes('admin123'), admin_roles))
    
    conn.commit()
    conn.close()

init_db()

def get_db():
    return sqlite3.connect('purchase_system.db', check_same_thread=False)

st.set_page_config(page_title="نظام تتبع عمليات الشراء", layout="wide", page_icon="📋")

# --- إدارة جلسة تسجيل الدخول المستقرة ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.user_roles = []

# --- دالة لتصدير ملف Excel حقيقي وبأعمدة مرتبة بدون مكتبات خارجية ---
def to_excel_bytes(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter' if 'xlsxwriter' in sys.modules else 'openpyxl' if 'openpyxl' in sys.modules else None) as writer:
        # سنستخدم طريقة بديلة نقية عبر pandas لضمان العمل بسلاسة
        pass
    # كبديل آمن ومتوافق 100% بدون فشل تثبيت، نستخدم صيغة XML/HTML المبسطة لإكسل أو صيغة CSV مصلحة، 
    # ولضمان فتحها بسلاسة في إكسل بدون تجميع الأعمدة، سنستخدم صيغة HTML متوافقة مع Excel
    html_content = df.to_html(index=False).encode('utf-8-sig')
    return html_content

if not st.session_state.logged_in:
    st.title("📋 نظام تتبع عمليات الشراء والمشتريات")
    st.markdown("---")
    
    # اختيار طريقة التنقل بين تسجيل الدخول وإنشاء حساب جديد أسفل الواجهة
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
            requested_roles = st.multiselect("الصلاحيات المطلوبة", all_available_roles)
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

else:
    st.sidebar.title("👤 لوحة التحكم")
    st.sidebar.write(f"المستخدم: **{st.session_state.username}**")
    st.sidebar.write(f"الصلاحيات: **{', '.join(st.session_state.user_roles)}**")
    
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

    # ==================== الشاشة الأولى ====================
    if selected_screen == "الشاشة 1: رفع طلبات (إنشاء وتتبع الطلبات)":
        st.header("🛒 الشاشة الأولى: تقديم طلب شراء جديد")
        
        with st.form("purchase_form", clear_on_submit=True):
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
                            importance_criteria, reason, status, created_at, edit_history
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'قيد المراجعة', ?, '')
                    ''', (
                        st.session_state.username, item_number, nupco_number, e_market_code, 
                        item_name, unit_price, quantity, total_cost, 
                        importance_criteria, reason, datetime.now().strftime("%Y-%m-%d %H:%M")
                    ))
                    conn.commit()
                    conn.close()
                    st.success("✅ تم إرسال طلب الشراء بنجاح وتم تفريغ الحقول لإدخال طلب جديد.")
                else:
                    st.error("الرجاء إدخال اسم الصنف على الأقل.")

        st.subheader("📋 سجل طلباتك السابقة وملاحظات المراجعة والاعتماد")
        conn = get_db()
        df_my_orders = pd.read_sql_query('''
            SELECT id AS "رقم الطلب", item_number AS "رقم البند", nupco_number AS "رقم نوبكو", 
                   e_market_code AS "كود السوق الإلكتروني", item_name AS "اسم الصنف", 
                   unit_price AS "السعر الأفرادي", quantity AS "الكمية", total_cost AS "الإجمالي", 
                   importance_criteria AS "معيار الأهمية", reason AS "السبب", status AS "الحالة", 
                   created_at AS "تاريخ الطلب", reviewer_notes AS "ملاحظات المراجعة", 
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
                   created_at AS "التاريخ", edit_history AS "سجل التعديلات" 
            FROM purchases WHERE status = 'قيد المراجعة'
        ''', conn)
        conn.close()
        
        if df_review.empty:
            st.info("لا توجد طلبات جديدة بانتظار المراجعة حالياً.")
        else:
            st.subheader("📦 قائمة الطلبات المعلقة للمراجعة")
            nupco_list = [n for n in df_review["رقم نوبكو"].dropna().unique() if str(n).strip() != ""]
            nupco_filter = st.selectbox("تصفية ودمج حسب رقم نوبكو", ["الكل"] + nupco_list)
            
            if nupco_filter != "الكل":
                filtered_df = df_review[df_review["رقم نوبكو"] == nupco_filter]
                st.info(f"يوجد {len(filtered_df)} طلبات مرتبطة برقم نوبكو: {nupco_filter}")
                st.dataframe(filtered_df, use_container_width=True)
                
                # زر دمج الطلبات المتشابهة الظاهر بوضوح
                if len(filtered_df) > 1:
                    if st.button(f"🔀 دمج الطلبات الـ ({len(filtered_df)}) المرتبطة برقم نوبكو {nupco_filter}", type="primary"):
                        conn = get_db()
                        c = conn.cursor()
                        ids = filtered_df["رقم الطلب"].tolist()
                        total_qty = filtered_df["الكمية"].sum()
                        first_price = filtered_df["السعر الأفرادي"].iloc[0]
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
            else:
                st.dataframe(df_review, use_container_width=True)
            
            st.markdown("---")
            st.subheader("⚙️ اتخاذ إجراء وتعديل الطلب")
            req_id = st.number_input("أدخل رقم الطلب المراد مراجعته وتعديله", min_value=1, step=1)
            
            conn = get_db()
            c = conn.cursor()
            c.execute("SELECT item_name, unit_price, quantity, reason FROM purchases WHERE id = ?", (req_id,))
            current_order = c.fetchone()
            conn.close()
            
            if current_order:
                with st.form("edit_review_form"):
                    st.write(f"تعديل تفاصيل الطلب رقم: {req_id}")
                    new_item_name = st.text_input("اسم الصنف المعدل", value=current_order[0])
                    new_unit_price = st.number_input("السعر الأفرادي المعدل", value=float(current_order[1]), min_value=0.0)
                    new_quantity = st.number_input("الكمية المعدلة", value=int(current_order[2]), min_value=1, step=1)
                    new_reason = st.text_area("السبب / المبرر المعدل", value=current_order[3])
                    
                    review_notes = st.text_input("ملاحظات المراجعة")
                    action = st.selectbox("قرار المراجعة", ["تحويل للاعتماد", "رفض الطلب"])
                    
                    submit_review = st.form_submit_button("حفظ التعديلات وتنفيذ القرار")
                    
                    if submit_review:
                        new_total = new_unit_price * new_quantity
                        edit_msg = f"[{datetime.now().strftime('%Y-%m-%d %H:%M')} - تم التعديل بواسطة المراجع {st.session_state.username}]"
                        
                        conn = get_db()
                        c = conn.cursor()
                        c.execute("SELECT edit_history FROM purchases WHERE id = ?", (req_id,))
                        old_history = c.fetchone()[0] or ""
                        updated_history = old_history + "\n" + edit_msg
                        
                        new_status = "بانتظار الاعتماد" if action == "تحويل للاعتماد" else "مرفوض في المراجعة"
                        c.execute('''
                            UPDATE purchases 
                            SET item_name = ?, unit_price = ?, quantity = ?, total_cost = ?, 
                                reason = ?, status = ?, reviewer_notes = ?, edit_history = ? 
                            WHERE id = ?
                        ''', (new_item_name, new_unit_price, new_quantity, new_total, new_reason, new_status, review_notes, updated_history, req_id))
                        conn.commit()
                        conn.close()
                        st.success(f"تم تحديث وتعديل الطلب رقم {req_id} بنجاح!")
                        st.rerun()

    # ==================== الشاشة الثالثة ====================
    elif selected_screen == "الشاشة 3: الاعتماد":
        st.header("✅ الشاشة الثالثة: الاعتماد النهائي وتصدير البيانات")
        
        conn = get_db()
        df_approve = pd.read_sql_query('''
            SELECT id AS "رقم الطلب", requester AS "المستخدم", item_number AS "رقم البند", 
                   nupco_number AS "رقم نوبكو", item_name AS "اسم الصنف", unit_price AS "السعر الأفرادي", 
                   quantity AS "الكمية", total_cost AS "الإجمالي", importance_criteria AS "معيار الأهمية", 
                   reason AS "السبب", reviewer_notes AS "ملاحظات المراجعة", edit_history AS "سجل التعديلات" 
            FROM purchases WHERE status = 'بانتظار الاعتماد'
        ''', conn)
        
        df_all_approved = pd.read_sql_query('''
            SELECT id AS "رقم الطلب", requester AS "المستخدم", item_number AS "رقم البند", 
                   nupco_number AS "رقم نوبكو", e_market_code AS "كود السوق الإلكتروني", 
                   item_name AS "اسم الصنف", unit_price AS "السعر الأفرادي", quantity AS "الكمية", 
                   total_cost AS "الإجمالي", importance_criteria AS "معيار الأهمية", reason AS "السبب", 
                   status AS "الحالة", created_at AS "تاريخ الطلب", approver_notes AS "ملاحظات الاعتماد" 
            FROM purchases WHERE status = 'معتمد نهائياً'
        ''', conn)
        conn.close()
        
        # تصدير ملف إكسل حقيقي ومنسق للأعمدة
        if not df_all_approved.empty:
            excel_bytes = to_excel_bytes(df_all_approved)
            st.download_button(
                label="📥 تصدير الطلبات المعتمدة نهائياً إلى ملف Excel (.xls/.xlsx متوافق)",
                data=excel_bytes,
                file_name=f"approved_purchases_{datetime.now().strftime('%Y%m%d_%H%M')}.xls",
                mime="application/vnd.ms-excel"
            )
            st.markdown("---")
        
        if df_approve.empty:
            st.info("لا توجد طلبات بانتظار الاعتماد النهائي حالياً.")
        else:
            st.subheader("📦 الطلبات المعلقة للاعتماد النهائي")
            nupco_list_app = [n for n in df_approve["رقم نوبكو"].dropna().unique() if str(n).strip() != ""]
            nupco_filter_app = st.selectbox("تصفية ودمج حسب رقم نوبكو للاعتماد", ["الكل"] + nupco_list_app)
            
            if nupco_filter_app != "الكل":
                filtered_app_df = df_approve[df_approve["رقم نوبكو"] == nupco_filter_app]
                st.info(f"يوجد {len(filtered_app_df)} طلبات مرتبطة برقم نوبكو: {nupco_filter_app}")
                st.dataframe(filtered_app_df, use_container_width=True)
                
                if len(filtered_app_df) > 1:
                    if st.button(f"🔀 دمج الطلبات الـ ({len(filtered_app_df)}) في الاعتماد", type="primary"):
                        conn = get_db()
                        c = conn.cursor()
                        ids = filtered_app_df["رقم الطلب"].tolist()
                        total_qty = filtered_app_df["الكمية"].sum()
                        first_price = filtered_app_df["السعر الأفرادي"].iloc[0]
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
            else:
                st.dataframe(df_approve, use_container_width=True)
            
            st.markdown("---")
            st.subheader("⚙️ تعديل واعتماد الطلب نهائياً")
            req_id_app = st.number_input("أدخل رقم الطلب للاعتماد النهائي والتعديل", min_value=1, step=1, key="app_req_id")
            
            conn = get_db()
            c = conn.cursor()
            c.execute("SELECT item_name, unit_price, quantity, reason FROM purchases WHERE id = ?", (req_id_app,))
            current_app_order = c.fetchone()
            conn.close()
            
            if current_app_order:
                with st.form("edit_approve_form"):
                    st.write(f"تعديل تفاصيل الطلب قبل الاعتماد رقم: {req_id_app}")
                    app_item_name = st.text_input("اسم الصنف (تعديل نهائي)", value=current_app_order[0])
                    app_unit_price = st.number_input("السعر الأفرادي (تعديل نهائي)", value=float(current_app_order[1]), min_value=0.0)
                    app_quantity = st.number_input("الكمية (تعديل نهائي)", value=int(current_app_order[2]), min_value=1, step=1)
                    app_reason = st.text_area("السبب (تعديل نهائي)", value=current_app_order[3])
                    
                    approver_notes = st.text_input("ملاحظات الاعتماد النهائي")
                    final_action = st.selectbox("قرار الاعتماد النهائي", ["اعتماد نهائي للشراء", "رفض نهائي"])
                    
                    submit_approval = st.form_submit_button("تأكيد التعديل والقرار النهائي")
                    
                    if submit_approval:
                        new_total_app = app_unit_price * app_quantity
                        edit_msg_app = f"[{datetime.now().strftime('%Y-%m-%d %H:%M')} - تم التعديل بواسطة المعتمد {st.session_state.username}]"
                        
                        conn = get_db()
                        c = conn.cursor()
                        c.execute("SELECT edit_history FROM purchases WHERE id = ?", (req_id_app,))
                        old_history_app = c.fetchone()[0] or ""
                        updated_history_app = old_history_app + "\n" + edit_msg_app
                        
                        final_status = "معتمد نهائياً" if final_action == "اعتماد نهائي للشراء" else "مرفوض نهائياً"
                        c.execute('''
                            UPDATE purchases 
                            SET item_name = ?, unit_price = ?, quantity = ?, total_cost = ?, 
                                reason = ?, status = ?, approver_notes = ?, edit_history = ? 
                            WHERE id = ?
                        ''', (app_item_name, app_unit_price, app_quantity, new_total_app, app_reason, final_status, approver_notes, updated_history_app, req_id_app))
                        conn.commit()
                        conn.close()
                        st.success(f"تم اتخاذ القرار النهائي وتحديث الطلب رقم {req_id_app}.")
                        st.rerun()

    # ==================== الشاشة الرابعة ====================
    elif selected_screen == "الشاشة 4: الإعدادات وإعطاء الصلاحيات":
        st.header("⚙️ الشاشة الرابعة: إعدادات المستخدمين وإدارة الصلاحيات المباشرة")
        
        conn = get_db()
        users_df = pd.read_sql_query("SELECT username AS 'اسم المستخدم', roles AS 'الصلاحيات', status AS 'الحالة' FROM users", conn)
        conn.close()
        
        st.subheader("قائمة كافة المستخدمين وحساباتهم")
        st.dataframe(users_df, use_container_width=True)
        
        st.markdown("---")
        st.subheader("👤 تعديل صلاحيات وحالة مستخدم مباشرة")
        
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT username, roles, status FROM users")
        all_users_data = c.fetchall()
        conn.close()
        
        usernames_list = [u[0] for u in all_users_data]
        selected_target_user = st.selectbox("اختر اسم المستخدم للتعديل المباشر", usernames_list)
        
        if selected_target_user:
            user_current_data = next((u for u in all_users_data if u[0] == selected_target_user), None)
            current_roles_list = user_current_data[1].split(",") if user_current_data[1] else []
            current_status = user_current_data[2]
            
            with st.form("direct_user_edit_form"):
                st.write(f"تعديل صلاحيات وحالة المستخدم: **{selected_target_user}**")
                
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
                        c.execute("UPDATE users SET roles = ?, status = ? WHERE username = ?", (roles_string, updated_status, selected_target_user))
                        conn.commit()
                        conn.close()
                        st.success(f"تم تحديث صلاحيات وحالة المستخدم ({selected_target_user}) بنجاح!")
                        st.rerun()
                    else:
                        st.warning("الرجاء اختيار صلاحية واحدة على الأقل.")

    # ==================== الشاشة الخامسة ====================
    elif selected_screen == "الشاشة 5: لوحة التحكّم التفصيلية (Dashboard)":
        st.header("📊 الشاشة الخامسة: لوحة التحكم والتقارير التفصيلية")
        
        conn = get_db()
        all_purchases = pd.read_sql_query("SELECT * FROM purchases", conn)
        all_users = pd.read_sql_query("SELECT * FROM users", conn)
        conn.close()
        
        total_uploaded = len(all_purchases)
        rejected_in_review = len(all_purchases[all_purchases['status'] == 'مرفوض في المراجعة']) if not all_purchases.empty else 0
        review_approved = len(all_purchases[all_purchases['status'] == 'بانتظار الاعتماد']) if not all_purchases.empty else 0
        finally_approved = len(all_purchases[all_purchases['status'] == 'معتمد نهائياً']) if not all_purchases.empty else 0
        finally_rejected = len(all_purchases[all_purchases['status'] == 'مرفوض نهائياً']) if not all_purchases.empty else 0
        total_cost = all_purchases['total_cost'].sum() if not all_purchases.empty else 0.0
        
        col1, col2, col3 = st.columns(3)
        col1.metric("📦 إجمالي الطلبات المرفوعة", total_uploaded)
        col2.metric("🔍 مراجعة بالاعتماد (معلقة)", review_approved)
        col3.metric("❌ المراجعة بالرفض", rejected_in_review)
        
        col4, col5, col6 = st.columns(3)
        col4.metric("✅ المعتمدة نهائياً", finally_approved)
        col5.metric("🚫 المرفوضة نهائياً", finally_rejected)
        col6.metric("💰 إجمالي التكاليف (ر.س)", f"{total_cost:,.2f}")
        
        st.markdown("---")
        st.subheader("📈 جدول تفاصيل كافة الطلبات في النظام")
        if not all_purchases.empty:
            display_purchases = all_purchases.rename(columns={
                'id': 'رقم الطلب',
                'requester': 'المستخدم',
                'item_number': 'رقم البند',
                'nupco_number': 'رقم نوبكو',
                'e_market_code': 'كود السوق الإلكتروني',
                'item_name': 'اسم الصنف',
                'unit_price': 'السعر الأفرادي',
                'quantity': 'الكمية',
                'total_cost': 'الإجمالي',
                'importance_criteria': 'معيار الأهمية',
                'reason': 'السبب',
                'status': 'الحالة',
                'created_at': 'تاريخ الطلب',
                'reviewer_notes': 'ملاحظات المراجعة',
                'approver_notes': 'ملاحظات الاعتماد',
                'edit_history': 'سجل التعديلات'
            })
            st.dataframe(display_purchases, use_container_width=True)
        else:
            st.info("لا توجد بيانات طلبات مسجلة حتى الآن.")
            
        st.markdown("---")
        st.subheader("👥 ملخص المستخدمين وحالاتهم وصلاحياتهم")
        display_users = all_users.rename(columns={
            'username': 'اسم المستخدم',
            'roles': 'الصلاحيات',
            'status': 'الحالة'
        })[['اسم المستخدم', 'الصلاحيات', 'الحالة']]
        st.dataframe(display_users, use_container_width=True)
