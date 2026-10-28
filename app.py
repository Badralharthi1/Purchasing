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
    /* تصميم موحد لكافة الأزرار بشكل ثلاثي الأبعاد (3D Buttons) */
    div.stButton > button:first-child, div.stFormSubmitButton > button:first-child {
        background: linear-gradient(135deg, #28a745 0%, #218838 100%);
        color: white;
        border-radius: 10px;
        font-weight: bold;
        border: none;
        border-bottom: 4px solid #1e7e34;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.2);
        transition: all 0.1s ease;
        width: 100%;
    }
    div.stButton > button:first-child:hover, div.stFormSubmitButton > button:first-child:hover {
        background: linear-gradient(135deg, #218838 0%, #1e7e34 100%);
        box-shadow: 0 6px 8px rgba(0, 0, 0, 0.25);
        transform: translateY(-1px);
    }
    div.stButton > button:first-child:active, div.stFormSubmitButton > button:first-child:active {
        transform: translateY(2px);
        border-bottom: 2px solid #1e7e34;
        box-shadow: 0 2px 3px rgba(0, 0, 0, 0.2);
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

# --- إدارة الذاكرة المحلية المؤقتة ---
def load_data_to_session():
    try:
        ws_users = get_worksheet("users")
        recs = ws_users.get_all_records()
        if not recs:
            admin_pw = make_hashes("admin123")
            admin_roles = "مدير النظام (Admin),رفع طلبات,مراجعة الطلبات,معتمد الطلبات,إدارة الصلاحيات,عرض الداش بورد,اعتماد لجنة الشراء الطارئ,البحث الشامل,الشكاوى والاقتراحات"
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
                df_p["id"] = pd.to_numeric(df_p["id"], errors="coerce").fillna(0).astype(int)
            if "unit_price" in df_p.columns:
                df_p["unit_price"] = pd.to_numeric(df_p["unit_price"], errors="coerce").fillna(0.0)
            else:
                df_p["unit_price"] = 0.0
                
            if "quantity" in df_p.columns:
                df_p["quantity"] = pd.to_numeric(df_p["quantity"], errors="coerce").fillna(1).astype(int)
            else:
                df_p["quantity"] = 1
                
            if "total_cost" in df_p.columns:
                df_p["total_cost"] = pd.to_numeric(df_p["total_cost"], errors="coerce").fillna(0.0)
            else:
                df_p["total_cost"] = df_p["unit_price"] * df_p["quantity"]
                
            st.session_state.db_purchases = df_p
    except Exception:
        if 'db_purchases' not in st.session_state:
            st.session_state.db_purchases = pd.DataFrame()

    try:
        ws_c = get_worksheet("complaints")
        recs_c = ws_c.get_all_records()
        if not recs_c:
            ws_c.update([["id", "username", "hospital", "type", "content", "created_at", "status", "admin_reply"]])
            st.session_state.db_complaints = pd.DataFrame(columns=["id", "username", "hospital", "type", "content", "created_at", "status", "admin_reply"])
        else:
            df_c = pd.DataFrame(recs_c)
            df_c.columns = [str(c).strip() for c in df_c.columns]
            if "id" in df_c.columns:
                df_c["id"] = pd.to_numeric(df_c["id"], errors="coerce").fillna(0).astype(int)
            st.session_state.db_complaints = df_c
    except Exception:
        if 'db_complaints' not in st.session_state:
            st.session_state.db_complaints = pd.DataFrame(columns=["id", "username", "hospital", "type", "content", "created_at", "status", "admin_reply"])

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

if 'selected_item_num' not in st.session_state:
    st.session_state.selected_item_num = ""
if 'selected_nupco' not in st.session_state:
    st.session_state.selected_nupco = ""
if 'selected_name' not in st.session_state:
    st.session_state.selected_name = ""

def to_excel_bytes(df):
    return df.to_html(index=False).encode('utf-8-sig')

def safe_display_df(df):
    if df.empty:
        return df
    safe_df = df.copy()
    for col in safe_df.columns:
        if col not in ["رقم الطلب", "السعر الأفرادي", "الكمية", "الإجمالي", "الرقم"]:
            safe_df[col] = safe_df[col].astype(str).replace('nan', '')
    return safe_df

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
            all_available_roles = ["رفع طلبات", "مراجعة الطلبات", "معتمد الطلبات", "اعتماد لجنة الشراء الطارئ", "إدارة الصلاحيات", "عرض الداش بورد", "البحث الشامل", "الشكاوى والاقتراحات"]
            requested_roles = st.multiselect("الصلاحيات المطلوبة", all_available_roles, default=[])
            
            if st.form_submit_button("إرسال طلب التسجيل"):
                if new_user and new_pass and requested_roles and selected_hospital:
                    df_users = st.session_state.db_users
                    if not df_users[df_users["username"] == new_user].empty:
                        st.error("❌ اسم المستخدم مستخدم مسبقاً.")
                    else:
                        ws_users = get_worksheet("users")
                        ws_users.append_row([new_user, make_hashes(new_pass), ",".join(requested_roles), "قيد الانتظار", selected_hospital])
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
                        st.success("✅ تم إرسال طلب إعادة تعيين كلمة المرور بنجاح!")

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
    if "البحث الشامل" in roles or "مدير النظام (Admin)" in roles:
        screens.append("الشاشة 7: البحث الشامل في كافة الطلبات")
    if "الشكاوى والاقتراحات" in roles or "مدير النظام (Admin)" in roles:
        screens.append("الشاشة 8: الشكاوى والاقتراحات")

    if not screens:
        st.warning("⚠️ لا توجد صلاحيات مفعلة حالياً.")
        st.stop()

    selected_screen = st.sidebar.radio("التنقل بين الشاشات:", screens)
    st.sidebar.markdown("---")

    st.markdown('<div class="main-title">🚀 نظام تتبع عمليات الشراء المباشر</div>', unsafe_allow_html=True)

    # ==================== الشاشة الأولى ====================
    if selected_screen == "الشاشة 1: رفع طلبات (إنشاء وتتبع الطلبات)":
        st.header(f"🛒 الشاشة الأولى: تقديم طلب شراء جديد ({st.session_state.user_hospital})")
        
        st.subheader("🔍 البحث السريع في دليل الأصناف للإدراج الفوري")
        search_query = st.text_input("أدخل جزءاً من (رقم البند، رقم نوبكو، أو اسم الصنف) ثم اضغط بحث:")
        
        if search_query.strip() and not catalog_df.empty:
            q = search_query.strip().lower()
            filtered_cat = catalog_df[
                catalog_df['رقم البند'].str.lower().str.contains(q, na=False) |
                catalog_df['رقم نوبكو'].str.lower().str.contains(q, na=False) |
                catalog_df['اسم الصنف'].str.lower().str.contains(q, na=False)
            ].head(15)
            
            if not filtered_cat.empty:
                options_list = [f"{r['رقم البند']} | {r['رقم نوبكو']} | {r['اسم الصنف']}" for _, r in filtered_cat.iterrows()]
                chosen_option = st.selectbox("اختر الصنف المطابق من النتائج:", options_list)
                
                if st.button("📥 إدراج البيانات في النموذج"):
                    parts = [p.strip() for p in chosen_option.split("|")]
                    if len(parts) >= 3:
                        st.session_state.selected_item_num = parts[0]
                        st.session_state.selected_nupco = parts[1]
                        st.session_state.selected_name = parts[2]
                        st.success("✅ تم إدراج بيانات الصنف بنجاح في النموذج أدناه!")
                        st.rerun()
            else:
                st.info("لا توجد نتائج مطابقة لبحثك في الدليل.")

        st.markdown("---")
        
        # نموذج تقديم الطلب مع تفريغ الحقول وسرعة عالية في الإرسال
        with st.form("purchase_request_form", clear_on_submit=True):
            col1, col2, col3 = st.columns(3)
            with col1:
                item_number_input = st.text_input("1. رقم البند *", value=st.session_state.selected_item_num)
                nupco_number_input = st.text_input("2. رقم نوبكو *", value=st.session_state.selected_nupco)
                e_market_code = st.text_input("3. كود السوق الالكتروني *")

            with col2:
                item_name_input = st.text_input("4. اسم الصنف *", value=st.session_state.selected_name)
                unit_price = st.number_input("5. السعر الأفرادي *", min_value=0.0, step=1.0, value=0.0)
                quantity = st.number_input("6. الكمية المطلوبة *", min_value=1, step=1, value=1)

            with col3:
                importance_criteria = st.selectbox("7. معيار الأهمية *", ["عالي جداً (حرج)", "عالي", "متوسط", "منخفض"])
                reason = st.text_area("8. السبب / المبررات")

            submitted = st.form_submit_button("إرسال الطلب")
            if submitted:
                if not item_number_input.strip() or not nupco_number_input.strip() or not e_market_code.strip() or not item_name_input.strip() or unit_price <= 0 or quantity <= 0:
                    st.error("❌ يرجى تعبئة كافة الحقول الإلزامية بصورة صحيحة (السعر والكمية يجب أن تكون أكبر من صفر).")
                else:
                    df_all_p = st.session_state.db_purchases
                    new_id = int(df_all_p["id"].max()) + 1 if not df_all_p.empty and not pd.isna(df_all_p["id"].max()) else 1
                    
                    new_row = {
                        "id": new_id, "requester": st.session_state.username, "hospital": st.session_state.user_hospital,
                        "item_number": item_number_input.strip(), "nupco_number": nupco_number_input.strip(), "e_market_code": e_market_code.strip(),
                        "item_name": item_name_input.strip(), "unit_price": float(unit_price), "quantity": int(quantity), "total_cost": float(unit_price * quantity),
                        "importance_criteria": importance_criteria, "reason": reason, "status": "التخطيط بالمستشفى",
                        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"), "reviewed_at": "", "approved_at": "",
                        "reviewer_notes": "", "approver_notes": "", "edit_history": ""
                    }
                    
                    ws_purchases = get_worksheet("purchases")
                    ws_purchases.append_row(list(new_row.values()))
                    
                    st.session_state.db_purchases = pd.concat([st.session_state.db_purchases, pd.DataFrame([new_row])], ignore_index=True)
                    
                    st.session_state.selected_item_num = ""
                    st.session_state.selected_nupco = ""
                    st.session_state.selected_name = ""
                    
                    st.success("✅ تم إرسال طلب الشراء وتفريغ كافة الحقول بنجاح!")

        st.markdown("---")
        st.subheader("📋 سجل طلباتك السابقة")
        df_all_p = st.session_state.db_purchases
        df_my_orders = df_all_p[df_all_p["requester"] == st.session_state.username] if not df_all_p.empty else pd.DataFrame()
        if not df_my_orders.empty:
            df_my_orders["unit_price"] = pd.to_numeric(df_my_orders["unit_price"], errors="coerce").fillna(0.0)
            df_my_orders["total_cost"] = pd.to_numeric(df_my_orders["total_cost"], errors="coerce").fillna(0.0)
            df_my_orders = df_my_orders.rename(columns={
                "id": "رقم الطلب", "hospital": "المستشفى", "item_number": "رقم البند",
                "nupco_number": "رقم نوبكو", "e_market_code": "كود السوق",
                "item_name": "اسم الصنف", "unit_price": "السعر الأفرادي", "quantity": "الكمية",
                "total_cost": "الإجمالي", "importance_criteria": "الأهمية", "reason": "السبب",
                "status": "الحالة", "created_at": "تاريخ الإنشاء"
            })
        st.dataframe(safe_display_df(df_my_orders), use_container_width=True)

    # ==================== الشاشة الثانية (إدارة التخطيط بالمستشفى) ====================
    elif selected_screen == "الشاشة 2: إدارة التخطيط بالمستشفى":
        review_hospital = st.session_state.user_hospital
        if "مدير النظام (Admin)" in st.session_state.user_roles:
            review_hospital = st.selectbox("اختيار مستشفى للمراجعة:", HOSPITALS_LIST, index=HOSPITALS_LIST.index(st.session_state.user_hospital) if st.session_state.user_hospital in HOSPITALS_LIST else 0)

        st.header(f"🔍 الشاشة الثانية: إدارة التخطيط بالمستشفى ({review_hospital})")
        df_all_p = st.session_state.db_purchases
        
        if not df_all_p.empty:
            df_all_p["unit_price"] = pd.to_numeric(df_all_p["unit_price"], errors="coerce").fillna(0.0)
            df_all_p["total_cost"] = pd.to_numeric(df_all_p["total_cost"], errors="coerce").fillna(0.0)
            df_review = df_all_p[(df_all_p["status"] == 'التخطيط بالمستشفى') & (df_all_p["hospital"] == review_hospital)]
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
            st.markdown("⚠️ **مفتاح تلوين التأخير:** <span style='background-color: #fff3cd; color: #856404; padding: 2px 6px; border-radius: 4px;'>متأخر يوم (أصفر)</span> | <span style='background-color: #ffcccc; color: #990000; padding: 2px 6px; border-radius: 4px;'>متأخر 3 أيام فأكثر (أحمر)</span>", unsafe_allow_html=True)
            
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
                            if int(row.get("id", 0)) == int(primary_id):
                                ws_p.update_cell(idx, 9, int(total_qty))
                                ws_p.update_cell(idx, 10, float(total_cost_merged))
                                break
                        for remove_id in ids[1:]:
                            for idx, row in enumerate(all_rows, start=2):
                                if int(row.get("id", 0)) == int(remove_id):
                                    ws_p.delete_rows(idx)
                                    break
                        st.success("تم الدمج بنجاح! (قم بتحديث البيانات)")

            event = st.dataframe(safe_display_df(target_df_view), use_container_width=True, on_select="rerun", selection_mode="single-row")
            selected_rows = event.selection.rows if hasattr(event, "selection") else []
            
            if selected_rows:
                selected_row_data = target_df.iloc[selected_rows[0]]
                req_id = int(selected_row_data["id"])
                co = selected_row_data
                
                sel_item_num = str(co["item_number"]).strip()
                sel_nupco = str(co["nupco_number"]).strip()
                sel_name = str(co["item_name"]).strip()
                
                # إظهار الطلبات المعتمدة نهائياً فقط (واستبعاد المعلقة، غير المعتمدة، والمرفوضة) في سجل الطلبات السابقة
                if not df_all_p.empty:
                    similar_orders = df_all_p[
                        (
                            ((df_all_p["item_number"] == sel_item_num) & (sel_item_num != "")) |
                            ((df_all_p["nupco_number"] == sel_nupco) & (sel_nupco != "")) |
                            ((df_all_p["item_name"] == sel_name) & (sel_name != ""))
                        ) & 
                        (df_all_p["id"] != req_id) &
                        (df_all_p["status"] == "معتمد")
                    ]
                else:
                    similar_orders = pd.DataFrame()
                
                if not similar_orders.empty:
                    st.markdown("---")
                    st.info(f"📌 **سجل الطلبات المعتمدة نهائياً السابقة لنفس الصنف:**")
                    similar_orders["unit_price"] = pd.to_numeric(similar_orders["unit_price"], errors="coerce").fillna(0.0)
                    similar_orders["total_cost"] = pd.to_numeric(similar_orders["total_cost"], errors="coerce").fillna(0.0)
                    sim_view = similar_orders.rename(columns={"id": "رقم الطلب", "hospital": "المستشفى", "item_number": "رقم البند", "nupco_number": "رقم نوبكو", "item_name": "اسم الصنف", "quantity": "الكمية", "total_cost": "الإجمالي", "status": "الحالة", "created_at": "تاريخ الإنشاء"})
                    st.dataframe(safe_display_df(sim_view[["رقم الطلب", "المستشفى", "رقم البند", "رقم نوبكو", "اسم الصنف", "الكمية", "الإجمالي", "الحالة", "تاريخ الإنشاء"]]), use_container_width=True)
                
                st.markdown("---")
                st.subheader(f"⚙️ تعديل الطلب رقم: {req_id}")
                with st.form(f"edit_review_form_{req_id}", clear_on_submit=False):
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        new_item_number = st.text_input("رقم البند", value=str(co["item_number"]))
                        new_nupco_number = st.text_input("رقم نوبكو", value=str(co["nupco_number"]))
                        new_e_market_code = st.text_input("كود السوق", value=str(co["e_market_code"]))
                    with c2:
                        new_item_name = st.text_input("اسم الصنف", value=str(co["item_name"]))
                        saved_unit_price = float(co["unit_price"]) if not pd.isna(co["unit_price"]) else 0.0
                        new_unit_price = st.number_input("السعر الأفرادي", value=saved_unit_price, min_value=0.0, step=1.0)
                        saved_qty = int(co["quantity"]) if not pd.isna(co["quantity"]) else 1
                        new_quantity = st.number_input("الكمية", value=saved_qty, min_value=1, step=1)
                    with c3:
                        curr_imp = str(co["importance_criteria"])
                        imp_options = ["عالي جداً (حرج)", "عالي", "متوسط", "منخفض"]
                        imp_idx = imp_options.index(curr_imp) if curr_imp in imp_options else 0
                        new_importance = st.selectbox("معيار الأهمية", imp_options, index=imp_idx)
                        new_reason = st.text_area("السبب", value=str(co["reason"] or ""))
                    
                    review_notes = st.text_input("ملاحظات المراجعة")
                    action = st.selectbox("قرار المراجعة", ["تحويل للإمداد", "رفض الطلب"])
                    
                    if st.form_submit_button("حفظ التعديلات وتنفيذ القرار"):
                        new_total = float(new_unit_price * new_quantity)
                        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                        new_status = "التخطيط بالإمداد" if action == "تحويل للإمداد" else "مرفوض من التخطيط بالمستشفى"
                        
                        ws_p = get_worksheet("purchases")
                        all_rows = ws_p.get_all_records()
                        for idx, row in enumerate(all_rows, start=2):
                            if int(row.get("id", 0)) == int(req_id):
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
                        st.session_state.db_purchases.loc[st.session_state.db_purchases["id"] == req_id, "status"] = new_status
                        st.success("✅ تم تحديث الطلب ونقله للمرحلة التالية بنجاح!")
                        st.rerun()
        else:
            st.info(f"لا توجد طلبات معلقة للمراجعة في ({review_hospital}).")

    # ==================== الشاشة الثالثة (إدارة التخطيط بالإمداد) ====================
    elif selected_screen == "الشاشة 3: إدارة التخطيط بالإمداد":
        app_hospital_selection = ["جميع المستشفيات"] + HOSPITALS_LIST
        selected_app_filter = st.selectbox("اختيار المستشفى للإعتماد:", app_hospital_selection, index=0, key="app_hosp_sb")

        st.header(f"✅ الشاشة الثالثة: إدارة التخطيط بالإمداد ({selected_app_filter})")
        df_all_p = st.session_state.db_purchases
        
        if not df_all_p.empty:
            df_all_p["unit_price"] = pd.to_numeric(df_all_p["unit_price"], errors="coerce").fillna(0.0)
            df_all_p["total_cost"] = pd.to_numeric(df_all_p["total_cost"], errors="coerce").fillna(0.0)
            df_all_approved = df_all_p[df_all_p["status"] == 'معتمد']
        else:
            df_all_approved = pd.DataFrame()

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
            df_approve = df_all_p[df_all_p["status"] == 'التخطيط بالإمداد']
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
            st.markdown("⚠️ **مفتاح تلوين التأخير:** <span style='background-color: #fff3cd; color: #856404; padding: 2px 6px; border-radius: 4px;'>متأخر يوم (أصفر)</span> | <span style='background-color: #ffcccc; color: #990000; padding: 2px 6px; border-radius: 4px;'>متأخر 3 أيام فأكثر (أحمر)</span>", unsafe_allow_html=True)
            
            event_app = st.dataframe(safe_display_df(df_approve_view), use_container_width=True, on_select="rerun", selection_mode="single-row")
            sel_rows_app = event_app.selection.rows if hasattr(event_app, "selection") else []
            
            if sel_rows_app:
                selected_app_row = df_approve.iloc[sel_rows_app[0]]
                app_req_id = int(selected_app_row["id"])
                co = selected_app_row
                
                sel_item_num = str(co["item_number"]).strip()
                sel_nupco = str(co["nupco_number"]).strip()
                sel_name = str(co["item_name"]).strip()
                
                # إظهار الطلبات المعتمدة نهائياً فقط في شاشة الإمداد
                if not df_all_p.empty:
                    similar_orders = df_all_p[
                        (
                            ((df_all_p["item_number"] == sel_item_num) & (sel_item_num != "")) |
                            ((df_all_p["nupco_number"] == sel_nupco) & (sel_nupco != "")) |
                            ((df_all_p["item_name"] == sel_name) & (sel_name != ""))
                        ) & 
                        (df_all_p["id"] != app_req_id) &
                        (df_all_p["status"] == "معتمد")
                    ]
                else:
                    similar_orders = pd.DataFrame()
                
                if not similar_orders.empty:
                    st.markdown("---")
                    st.info(f"📌 **سجل الطلبات المعتمدة نهائياً السابقة لنفس الصنف:**")
                    similar_orders["unit_price"] = pd.to_numeric(similar_orders["unit_price"], errors="coerce").fillna(0.0)
                    similar_orders["total_cost"] = pd.to_numeric(similar_orders["total_cost"], errors="coerce").fillna(0.0)
                    sim_view = similar_orders.rename(columns={"id": "رقم الطلب", "hospital": "المستشفى", "item_number": "رقم البند", "nupco_number": "رقم نوبكو", "item_name": "اسم الصنف", "quantity": "الكمية", "total_cost": "الإجمالي", "status": "الحالة", "created_at": "تاريخ الإنشاء"})
                    st.dataframe(safe_display_df(sim_view[["رقم الطلب", "المستشفى", "رقم البند", "رقم نوبكو", "اسم الصنف", "الكمية", "الإجمالي", "الحالة", "تاريخ الإنشاء"]]), use_container_width=True)
                
                st.markdown("---")
                st.subheader(f"⚖️ تعديل الطلب واتخاذ القرار رقم: {app_req_id}")
                with st.form(f"approval_action_form_{app_req_id}", clear_on_submit=False):
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        app_item_number = st.text_input("رقم البند", value=str(co["item_number"]))
                        app_nupco_number = st.text_input("رقم نوبكو", value=str(co["nupco_number"]))
                        app_e_market_code = st.text_input("كود السوق", value=str(co["e_market_code"]))
                    with c2:
                        app_item_name = st.text_input("اسم الصنف", value=str(co["item_name"]))
                        saved_unit_price = float(co["unit_price"]) if not pd.isna(co["unit_price"]) else 0.0
                        app_unit_price = st.number_input("السعر الأفرادي", value=saved_unit_price, min_value=0.0, step=1.0)
                        saved_qty = int(co["quantity"]) if not pd.isna(co["quantity"]) else 1
                        app_quantity = st.number_input("الكمية", value=saved_qty, min_value=1, step=1)
                    with c3:
                        curr_imp = str(co["importance_criteria"])
                        imp_options = ["عالي جداً (حرج)", "عالي", "متوسط", "منخفض"]
                        imp_idx = imp_options.index(curr_imp) if curr_imp in imp_options else 0
                        app_importance = st.selectbox("معيار الأهمية", imp_options, index=imp_idx)
                        app_reason = st.text_area("السبب", value=str(co["reason"] or ""))
                    
                    approver_notes = st.text_input("ملاحظات المعتمد")
                    app_action = st.selectbox("قرار الاعتماد", ["تحويل إلى لجنة الشراء الطارئ", "رفض الطلب"])
                    
                    if st.form_submit_button("حفظ التعديلات وتنفيذ القرار"):
                        app_total = float(app_unit_price * app_quantity)
                        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                        final_status = "لجنة الشراء الطارئ" if app_action == "تحويل إلى لجنة الشراء الطارئ" else "مرفوض من التخطيط بالإمداد"
                        
                        ws_p = get_worksheet("purchases")
                        all_rows = ws_p.get_all_records()
                        for idx, row in enumerate(all_rows, start=2):
                            if int(row.get("id", 0)) == int(app_req_id):
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
                        st.session_state.db_purchases.loc[st.session_state.db_purchases["id"] == app_req_id, "status"] = final_status
                        st.success("✅ تم تحديث الطلب ونقله للمرحلة التالية بنجاح!")
                        st.rerun()
        else:
            st.info(f"لا توجد طلبات بانتظار الاعتماد في ({selected_app_filter}).")

    # ==================== الشاشة الرابعة (اعتماد لجنة الشراء الطارئ) ====================
    elif selected_screen == "الشاشة 4: اعتماد لجنة الشراء الطارئ":
        emg_hospital_selection = ["جميع المستشفيات"] + HOSPITALS_LIST
        selected_emg_filter = st.selectbox("اختيار المستشفى للجنة الشراء الطارئ:", emg_hospital_selection, index=0, key="emg_hosp_sb")

        st.header(f"🚨 الشاشة الرابعة: اعتماد لجنة الشراء الطارئ ({selected_emg_filter})")
        df_all_p = st.session_state.db_purchases
        
        if not df_all_p.empty:
            df_all_p["unit_price"] = pd.to_numeric(df_all_p["unit_price"], errors="coerce").fillna(0.0)
            df_all_p["total_cost"] = pd.to_numeric(df_all_p["total_cost"], errors="coerce").fillna(0.0)
            
            df_emg_approved_export = df_all_p[df_all_p["status"] == 'معتمد']
            if selected_emg_filter != "جميع المستشفيات":
                df_emg_approved_export = df_emg_approved_export[df_emg_approved_export["hospital"] == selected_emg_filter]

            if not df_emg_approved_export.empty:
                excel_bytes_emg = to_excel_bytes(df_emg_approved_export)
                st.download_button(
                    label="📥 تصدير قائمة طلبات الطوارئ المعتمدة إلى ملف Excel (.xls)",
                    data=excel_bytes_emg,
                    file_name=f"emergency_approved_purchases_{datetime.now().strftime('%Y%m%d_%H%M')}.xls",
                    mime="application/vnd.ms-excel"
                )
                st.markdown("---")

            df_emergency = df_all_p[df_all_p["status"] == 'لجنة الشراء الطارئ']
            if selected_emg_filter != "جميع المستشفيات":
                df_emergency = df_emergency[df_emergency["hospital"] == selected_emg_filter]
        else:
            df_emergency = pd.DataFrame()
        
        if not df_emergency.empty:
            df_emg_view = df_emergency.rename(columns={
                "id": "رقم الطلب", "requester": "المستخدم", "hospital": "المستشفى", "item_number": "رقم البند",
                "nupco_number": "رقم نوبكو", "item_name": "اسم الصنف", "total_cost": "الإجمالي", "status": "الحالة", "reason": "السبب", "created_at": "تاريخ الإنشاء"
            })
            
            st.subheader("📦 قائمة طلبات الشراء الطارئة (الحرجة جداً بانتظار الاعتماد)")
            st.markdown("⚠️ **مفتاح تلوين التأخير (الشاشة 4):** <span style='background-color: #fff3cd; color: #856404; padding: 2px 6px; border-radius: 4px;'>متأخر 7-10 أيام (أصفر)</span> | <span style='background-color: #ffcccc; color: #990000; padding: 2px 6px; border-radius: 4px;'>متأخر أكثر من 10 أيام (أحمر)</span>", unsafe_allow_html=True)
            
            event_emg = st.dataframe(safe_display_df(df_emg_view), use_container_width=True, on_select="rerun", selection_mode="single-row")
            sel_rows_emg = event_emg.selection.rows if hasattr(event_emg, "selection") else []
            
            if sel_rows_emg:
                selected_emg_row = df_emergency.iloc[sel_rows_emg[0]]
                emg_req_id = int(selected_emg_row["id"])
                co_emg = selected_emg_row
                
                sel_item_num = str(co_emg["item_number"]).strip()
                sel_nupco = str(co_emg["nupco_number"]).strip()
                sel_name = str(co_emg["item_name"]).strip()
                
                # إظهار الطلبات المعتمدة نهائياً فقط في لجنة الطوارئ
                if not df_all_p.empty:
                    similar_orders = df_all_p[
                        (
                            ((df_all_p["item_number"] == sel_item_num) & (sel_item_num != "")) |
                            ((df_all_p["nupco_number"] == sel_nupco) & (sel_nupco != "")) |
                            ((df_all_p["item_name"] == sel_name) & (sel_name != ""))
                        ) & 
                        (df_all_p["id"] != emg_req_id) &
                        (df_all_p["status"] == "معتمد")
                    ]
                else:
                    similar_orders = pd.DataFrame()

                if not similar_orders.empty:
                    st.markdown("---")
                    st.info(f"📌 **سجل الطلبات المعتمدة نهائياً السابقة لنفس الصنف:**")
                    similar_orders["unit_price"] = pd.to_numeric(similar_orders["unit_price"], errors="coerce").fillna(0.0)
                    similar_orders["total_cost"] = pd.to_numeric(similar_orders["total_cost"], errors="coerce").fillna(0.0)
                    sim_view = similar_orders.rename(columns={"id": "رقم الطلب", "hospital": "المستشفى", "item_number": "رقم البند", "nupco_number": "رقم نوبكو", "item_name": "اسم الصنف", "quantity": "الكمية", "total_cost": "الإجمالي", "status": "الحالة", "created_at": "تاريخ الإنشاء"})
                    st.dataframe(safe_display_df(sim_view[["رقم الطلب", "المستشفى", "رقم البند", "رقم نوبكو", "اسم الصنف", "الكمية", "الإجمالي", "الحالة", "تاريخ الإنشاء"]]), use_container_width=True)

                st.markdown("---")
                st.subheader(f"⚖️ تعديل ومعالجة طلب الطوارئ رقم: {emg_req_id}")
                with st.form(f"emergency_action_form_{emg_req_id}", clear_on_submit=False):
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        emg_item_number = st.text_input("رقم البند", value=str(co_emg["item_number"]), key="emg_in")
                        emg_nupco_number = st.text_input("رقم نوبكو", value=str(co_emg["nupco_number"]), key="emg_nu")
                        emg_e_market_code = st.text_input("كود السوق", value=str(co_emg["e_market_code"]), key="emg_em")
                    with c2:
                        emg_item_name = st.text_input("اسم الصنف", value=str(co_emg["item_name"]), key="emg_na")
                        saved_unit_price = float(co_emg["unit_price"]) if not pd.isna(co_emg["unit_price"]) else 0.0
                        emg_unit_price = st.number_input("السعر الأفرادي", value=saved_unit_price, min_value=0.0, step=1.0, key="emg_pr")
                        saved_qty = int(co_emg["quantity"]) if not pd.isna(co_emg["quantity"]) else 1
                        emg_quantity = st.number_input("الكمية", value=saved_qty, min_value=1, step=1, key="emg_qu")
                    with c3:
                        curr_imp = str(co_emg["importance_criteria"])
                        imp_options = ["عالي جداً (حرج)", "عالي", "متوسط", "منخفض"]
                        imp_idx = imp_options.index(curr_imp) if curr_imp in imp_options else 0
                        emg_importance = st.selectbox("معيار الأهمية", imp_options, index=imp_idx, key="emg_im")
                        emg_reason = st.text_area("السبب / المبرر", value=str(co_emg["reason"] or ""), key="emg_re")
                    
                    emg_notes = st.text_input("ملاحظات لجنة الشراء الطارئ", key="emg_no")
                    emg_action = st.selectbox("قرار اللجنة الطارئة", ["اعتماد", "رفض"], key="emg_ac")
                    
                    if st.form_submit_button("حفظ وتنفيذ قرار لجنة الطوارئ"):
                        emg_total = float(emg_unit_price * emg_quantity)
                        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                        emg_final_status = "معتمد" if emg_action == "اعتماد" else "مرفوض من لجنة الشراء الطارئ"
                        
                        ws_p = get_worksheet("purchases")
                        all_rows = ws_p.get_all_records()
                        for idx, row in enumerate(all_rows, start=2):
                            if int(row.get("id", 0)) == int(emg_req_id):
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
                        st.session_state.db_purchases.loc[st.session_state.db_purchases["id"] == emg_req_id, "status"] = emg_final_status
                        st.success("✅ تم تحديث ومعالجة طلب الشراء بنجاح!")
                        st.rerun()
        else:
            st.info(f"لا توجد طلبات طارئة بانتظار لجنة الطوارئ في ({selected_emg_filter}).")

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
                                        st.success(f"تم حذف المستخدم {u_name} (قم بالتحديث)")
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
                        all_roles_options = ["رفع طلبات", "مراجعة الطلبات", "معتمد الطلبات", "اعتماد لجنة الشراء الطارئ", "إدارة الصلاحيات", "عرض الداش بورد", "البحث الشامل", "الشكاوى والاقتراحات", "مدير النظام (Admin)"]
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
                                st.success("تم تحديث المستخدم والموافقة عليه بنجاح! (قم بتحديث البيانات)")

            with tab2:
                with st.form("add_new_user_form"):
                    st.subheader("إضافة حساب مستخدم جديد مباشرة")
                    new_u_name = st.text_input("اسم المستخدم الجديد")
                    new_u_pass = st.text_input("كلمة المرور", type="password")
                    new_u_hosp = st.selectbox("المستشفى التابع له", HOSPITALS_LIST)
                    all_roles_options = ["رفع طلبات", "مراجعة الطلبات", "معتمد الطلبات", "اعتماد لجنة الشراء الطارئ", "إدارة الصلاحيات", "عرض الداش بورد", "البحث الشامل", "الشكاوى والاقتراحات", "مدير النظام (Admin)"]
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
                                st.success(f"تمت إضافة المستخدم {new_u_name} واعتماده بنجاح! (قم بتحديث البيانات)")

    # ==================== الشاشة السادسة (Dashboard التفصيلية) ====================
    elif selected_screen == "الشاشة 6: لوحة التحكّم التفصيلية (Dashboard)":
        st.header("📊 الشاشة السادسة: لوحة المؤشرات والإحصائيات العامة (Dashboard)")
        
        df_all = st.session_state.db_purchases
        users_df = st.session_state.db_users
        
        if "مدير النظام (Admin)" in st.session_state.user_roles:
            dash_hosp_filter = st.selectbox("تصفية لوحة التحكم حسب المستشفى:", ["جميع المستشفيات"] + HOSPITALS_LIST)
            if dash_hosp_filter != "جميع المستشفيات" and not df_all.empty:
                df_all = df_all[df_all['hospital'] == dash_hosp_filter]
        else:
            dash_hosp_filter = st.session_state.user_hospital
            st.info(f"📌 يتم استعراض لوحة المؤشرات الخاصة بمستشفى: **{dash_hosp_filter}**")
            if not df_all.empty:
                df_all = df_all[df_all['hospital'] == dash_hosp_filter]
        
        if not df_all.empty:
            df_all["unit_price"] = pd.to_numeric(df_all["unit_price"], errors="coerce").fillna(0.0)
            df_all["total_cost"] = pd.to_numeric(df_all["total_cost"], errors="coerce").fillna(0.0)
            
            total_orders = len(df_all)
            
            hosp_pending = len(df_all[df_all['status'] == 'التخطيط بالمستشفى'])
            hosp_rejected = len(df_all[df_all['status'] == 'مرفوض من التخطيط بالمستشفى'])
            hosp_approved = len(df_all[df_all['status'].isin(['التخطيط بالإمداد', 'لجنة الشراء الطارئ', 'معتمد', 'مرفوض من التخطيط بالإمداد', 'مرفوض من لجنة الشراء الطارئ'])])

            supply_pending = len(df_all[df_all['status'] == 'التخطيط بالإمداد'])
            supply_rejected = len(df_all[df_all['status'] == 'مرفوض من التخطيط بالإمداد'])
            supply_approved = len(df_all[df_all['status'].isin(['لجنة الشراء الطارئ', 'معتمد', 'مرفوض من لجنة الشراء الطارئ'])])

            emg_pending = len(df_all[df_all['status'] == 'لجنة الشراء الطارئ'])
            emg_rejected = len(df_all[df_all['status'] == 'مرفوض من لجنة الشراء الطارئ'])
            emg_approved = len(df_all[df_all['status'] == 'معتمد'])

            df_emg_approved_total = df_all[df_all['status'] == 'معتمد']
            emg_approved_cost = df_emg_approved_total['total_cost'].sum() if not df_emg_approved_total.empty else 0.0

            st.metric("📦 إجمالي كافة الطلبات بالمستشفى / النظام", total_orders)
            st.markdown("---")

            col_hosp, col_supply, col_emg = st.columns(3)
            with col_hosp:
                st.subheader("🏥 إدارة تخطيط المستشفى")
                st.metric("الطلبات المعتمدة", hosp_approved)
                st.metric("الطلبات المرفوضة", hosp_rejected)
                st.metric("الطلبات المعلقة", hosp_pending)

            with col_supply:
                st.subheader("📦 إدارة تخطيط الإمداد")
                st.metric("الطلبات المعتمدة", supply_approved)
                st.metric("الطلبات المرفوضة", supply_rejected)
                st.metric("الطلبات المعلقة", supply_pending)

            with col_emg:
                st.subheader("🚨 لجنة الشراء الطارئ")
                st.metric("الطلبات المعتمدة", emg_approved)
                st.metric("الطلبات المرفوضة", emg_rejected)
                st.metric("الطلبات المعلقة", emg_pending)

            st.markdown("---")
            st.subheader("💰 التكلفة الإجمالية للطلبات المعتمدة في لجنة الشراء الطارئ")
            st.metric("التكلفة الإجمالية المعتمدة", f"{emg_approved_cost:,.2f} ر.س")

            st.markdown("---")
            st.subheader("⏱️ مؤشرات متوسط التأخير في كل شاشة (بالأيام)")
            
            df_s2_pending = df_all[df_all['status'] == 'التخطيط بالمستشفى']
            avg_delay_s2 = 0.0
            if not df_s2_pending.empty:
                dates_s2 = pd.to_datetime(df_s2_pending['created_at'], errors='coerce')
                avg_delay_s2 = ((datetime.now() - dates_s2).dt.total_seconds() / 86400).mean()

            df_s3_pending = df_all[df_all['status'] == 'التخطيط بالإمداد']
            avg_delay_s3 = 0.0
            if not df_s3_pending.empty:
                ref_s3 = df_s3_pending['reviewed_at'].apply(lambda x: x if str(x).strip() != "" else None).fillna(df_s3_pending['created_at'])
                dates_s3 = pd.to_datetime(ref_s3, errors='coerce')
                avg_delay_s3 = ((datetime.now() - dates_s3).dt.total_seconds() / 86400).mean()

            df_s4_pending = df_all[df_all['status'] == 'لجنة الشراء الطارئ']
            avg_delay_s4 = 0.0
            if not df_s4_pending.empty:
                ref_s4 = df_s4_pending['approved_at'].apply(lambda x: x if str(x).strip() != "" else None).fillna(df_s4_pending['created_at'])
                dates_s4 = pd.to_datetime(ref_s4, errors='coerce')
                avg_delay_s4 = ((datetime.now() - dates_s4).dt.total_seconds() / 86400).mean()

            dc1, dc2, dc3 = st.columns(3)
            dc1.metric("معدل تأخير (شاشة التخطيط بالمستشفى)", f"{avg_delay_s2:.1f} يوم")
            dc2.metric("معدل تأخير (شاشة التخطيط بالإمداد)", f"{avg_delay_s3:.1f} يوم")
            dc3.metric("معدل تأخير (شاشة لجنة الشراء الطارئ)", f"{avg_delay_s4:.1f} يوم")
            
            st.markdown("---")
            st.subheader("📊 الرسوم البيانية (عمودان لكل مستشفى)")
            
            chart_data_list = []
            target_hospitals_for_chart = HOSPITALS_LIST if "مدير النظام (Admin)" in st.session_state.user_roles else [st.session_state.user_hospital]
            
            for hosp in target_hospitals_for_chart:
                h_df = st.session_state.db_purchases[st.session_state.db_purchases['hospital'] == hosp] if not st.session_state.db_purchases.empty else pd.DataFrame()
                tot_req = len(h_df)
                h_app = len(h_df[h_df['status'] == 'معتمد'])
                h_rej = len(h_df[h_df['status'].str.contains('مرفوض', na=False)])
                h_pen = tot_req - (h_app + h_rej)
                
                chart_data_list.append({"المستشفى": hosp, "مجموع الطلبات المرفوعة": tot_req, "طلبات معتمدة": h_app, "طلبات مرفوضة": h_rej, "طلبات معلقة": h_pen})
            
            df_chart = pd.DataFrame(chart_data_list)
            if not df_chart.empty:
                df_chart.set_index("المستشفى", inplace=True)
                st.bar_chart(df_chart)

            st.markdown("---")
            st.subheader("📋 تفاصيل كافة الطلبات المعتمدة نهائياً")
            df_app_dash = df_all[df_all['status'] == 'معتمد']
            if not df_app_dash.empty:
                st.dataframe(safe_display_df(df_app_dash), use_container_width=True)
            else:
                st.info("لا توجد طلبات معتمدة نهائياً حتى الآن.")
        else:
            st.info("لا توجد بيانات مسجلة في النظام بعد.")
        
        if "مدير النظام (Admin)" in st.session_state.user_roles:
            st.markdown("---")
            st.subheader("👥 ملخص الحسابات والمستخدمين في النظام")
            st.dataframe(safe_display_df(users_df), use_container_width=True)

    # ==================== الشاشة السابعة (البحث الشامل في كافة الطلبات) ====================
    elif selected_screen == "الشاشة 7: البحث الشامل في كافة الطلبات":
        st.header("🔎 الشاشة السابعة: البحث الشامل في كافة الطلبات والإجراءات المتخذة")
        
        df_all_p = st.session_state.db_purchases
        
        if not df_all_p.empty:
            df_all_p["unit_price"] = pd.to_numeric(df_all_p["unit_price"], errors="coerce").fillna(0.0)
            df_all_p["total_cost"] = pd.to_numeric(df_all_p["total_cost"], errors="coerce").fillna(0.0)
            
            if "مدير النظام (Admin)" in st.session_state.user_roles:
                hosp_filter = st.selectbox("تصفية حسب المستشفى:", ["الكل"] + HOSPITALS_LIST)
            else:
                hosp_filter = st.session_state.user_hospital
                st.info(f"📌 يتم البحث حصراً في طلبات مستشفى: **{st.session_state.user_hospital}**")

            c1, c2 = st.columns(2)
            with c1:
                search_text = st.text_input("بحث برقم البند، نوبكو، أو اسم الصنف:")
            with c2:
                status_filter = st.selectbox("تصفية حسب الحالة:", ["الكل"] + df_all_p['status'].dropna().unique().tolist())

            filtered_df = df_all_p.copy()
            if "مدير النظام (Admin)" in st.session_state.user_roles:
                if hosp_filter != "الكل":
                    filtered_df = filtered_df[filtered_df['hospital'] == hosp_filter]
            else:
                filtered_df = filtered_df[filtered_df['hospital'] == st.session_state.user_hospital]
                
            if search_text.strip():
                st_q = search_text.strip().lower()
                filtered_df = filtered_df[
                    filtered_df['item_number'].astype(str).str.lower().str.contains(st_q, na=False) |
                    filtered_df['nupco_number'].astype(str).str.lower().str.contains(st_q, na=False) |
                    filtered_df['item_name'].astype(str).str.lower().str.contains(st_q, na=False) |
                    filtered_df['id'].astype(str).str.lower().str.contains(st_q, na=False)
                ]
            if status_filter != "الكل":
                filtered_df = filtered_df[filtered_df['status'] == status_filter]

            st.markdown(f"**عدد النتائج المطابقة:** `{len(filtered_df)}` طلب")
            
            excel_bytes_search = to_excel_bytes(filtered_df)
            st.download_button(
                label="📥 تصدير نتيجة البحث (كامل الطلبات المطابقة) إلى ملف Excel (.xls)",
                data=excel_bytes_search,
                file_name=f"search_results_{datetime.now().strftime('%Y%m%d_%H%M')}.xls",
                mime="application/vnd.ms-excel"
            )
            st.markdown("---")

            view_search_df = filtered_df.rename(columns={
                "id": "رقم الطلب", "requester": "المستخدم", "hospital": "المستشفى", "item_number": "رقم البند",
                "nupco_number": "رقم نوبكو", "e_market_code": "كود السوق", "item_name": "اسم الصنف",
                "unit_price": "السعر الأفرادي", "quantity": "الكمية", "total_cost": "الإجمالي",
                "importance_criteria": "الأهمية", "reason": "السبب", "status": "الحالة",
                "created_at": "تاريخ الإنشاء", "reviewed_at": "تاريخ المراجعة", "approved_at": "تاريخ الاعتماد",
                "reviewer_notes": "ملاحظات المراجعة", "approver_notes": "ملاحظات الاعتماد"
            })
            
            st.dataframe(safe_display_df(view_search_df), use_container_width=True)
        else:
            st.info("لا توجد طلبات مسجلة في النظام للبحث عنها.")

    # ==================== الشاشة الثامنة (الشكاوى والاقتراحات) ====================
    elif selected_screen == "الشاشة 8: الشكاوى والاقتراحات":
        st.header("💬 الشاشة الثامنة: نظام الشكاوى والاقتراحات")
        
        tab_send, tab_view = st.tabs(["إرسال شكوى أو اقتراح جديد", "استعراض ومتابعة الشكاوى والاقتراحات"])
        
        with tab_send:
            with st.form("complaint_form", clear_on_submit=True):
                comp_type = st.selectbox("نوع المشاركة:", ["اقتراح", "شكوى", "استفسار"])
                comp_content = st.text_area("تفاصيل الشكوى أو الاقتراح *")
                
                if st.form_submit_button("إرسال"):
                    if not comp_content.strip():
                        st.error("الرجاء كتابة محتوى الشكوى أو الاقتراح.")
                    else:
                        df_c = st.session_state.db_complaints
                        new_c_id = int(df_c["id"].max()) + 1 if not df_c.empty and not pd.isna(df_c["id"].max()) else 1
                        
                        new_c_row = {
                            "id": new_c_id,
                            "username": st.session_state.username,
                            "hospital": st.session_state.user_hospital,
                            "type": comp_type,
                            "content": comp_content.strip(),
                            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "status": "قيد المتابعة",
                            "admin_reply": ""
                        }
                        
                        ws_c = get_worksheet("complaints")
                        ws_c.append_row(list(new_c_row.values()))
                        st.session_state.db_complaints = pd.concat([st.session_state.db_complaints, pd.DataFrame([new_c_row])], ignore_index=True)
                        st.success("✅ تم إرسال مشاركتك وتفريغ الحقول بنجاح!")

        with tab_view:
            st.subheader("📋 سجل الشكاوى والاقتراحات المسجلة")
            df_c_all = st.session_state.db_complaints
            
            if not df_c_all.empty:
                display_df = df_c_all.copy()
                if "مدير النظام (Admin)" not in st.session_state.user_roles:
                    display_df = display_df[display_df["username"] == st.session_state.username]
                
                view_c_df = display_df.rename(columns={
                    "id": "الرقم", "username": "المستخدم", "hospital": "المستشفى",
                    "type": "النوع", "content": "المحتوى", "created_at": "تاريخ الإرسال",
                    "status": "الحالة", "admin_reply": "رد الإدارة"
                })
                st.dataframe(safe_display_df(view_c_df), use_container_width=True)
                
                if "مدير النظام (Admin)" in st.session_state.user_roles:
                    st.markdown("---")
                    st.subheader("✍️ رد مدير النظام (Admin) على الشكاوى والاقتراحات")
                    c_ids = display_df["id"].tolist()
                    selected_c_id = st.selectbox("اختر رقم الشكوى/الاقتراح للرد:", c_ids)
                    
                    selected_c_row = display_df[display_df["id"] == selected_c_id].iloc[0]
                    st.write(f"**المستخدم:** {selected_c_row['username']} ({selected_c_row['hospital']})")
                    st.write(f"**المحتوى:** {selected_c_row['content']}")
                    
                    with st.form("admin_reply_form", clear_on_submit=True):
                        admin_reply_text = st.text_area("أدخل الرد الخاص بالإدارة:", value=str(selected_c_row.get("admin_reply") or ""))
                        if st.form_submit_button("حفظ الرد وتحديث الحالة إلى 'تم الرد'"):
                            ws_c = get_worksheet("complaints")
                            all_c_records = ws_c.get_all_records()
                            for idx, r in enumerate(all_c_records, start=2):
                                if int(r.get("id", 0)) == int(selected_c_id):
                                    ws_c.update_cell(idx, 7, "تم الرد")
                                    ws_c.update_cell(idx, 8, str(admin_reply_text))
                                    break
                            st.session_state.db_complaints.loc[st.session_state.db_complaints["id"] == selected_c_id, "status"] = "تم الرد"
                            st.session_state.db_complaints.loc[st.session_state.db_complaints["id"] == selected_c_id, "admin_reply"] = str(admin_reply_text)
                            st.success("✅ تم حفظ الرد وتحديث البيانات بنجاح!")
            else:
                st.info("لا توجد شكاوى أو اقتراحات مسجلة.")
