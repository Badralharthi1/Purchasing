import streamlit as st
import pandas as pd
import hashlib
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

# --- إعداد الصفحة والتصميم ---
st.set_page_config(page_title="نظام تتبع عمليات الشراء", layout="wide", page_icon="📝")

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
.metric-card {
    background-color: #f8f9fa;
    border-radius: 10px;
    padding: 15px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    text-align: center;
}
div.stButton > button:first-child {
    background-color: #28a745;
    color: white;
    font-weight: bold;
    border-radius: 8px;
    padding: 0.5rem 1rem;
    border: none;
}
div.stButton > button:first-child:hover {
    background-color: #218838;
}
</style>
""", unsafe_allow_html=True)

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

# --- التشفير والحسابات ---
def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    return make_hashes(password) == hashed_text

def load_users():
    sheet = get_worksheet("users")
    records = sheet.get_all_records()
    if not records:
        default_user = [
            {"username": "admin", "password": make_hashes("admin123"), "role": "أدمن النظام", "status": "نشط"}
        ]
        df_default = pd.DataFrame(default_user)
        sheet.update([df_default.columns.values.tolist()] + df_default.values.tolist())
        return df_default
    return pd.DataFrame(records)

def save_user(username, password, role, status="نشط"):
    sheet = get_worksheet("users")
    hashed_pw = make_hashes(password)
    sheet.append_row([username, hashed_pw, role, status])

# --- إدارة بيانات الشراء ---
def load_purchases():
    sheet = get_worksheet("purchases")
    records = sheet.get_all_records()
    if not records:
        return pd.DataFrame(columns=[
            "id", "requester", "hospital", "item_name", "quantity", 
            "estimated_cost", "status", "created_at", "updated_at"
        ])
    return pd.DataFrame(records)

def save_purchase_request(requester, hospital, item_name, quantity, estimated_cost):
    sheet = get_worksheet("purchases")
    records = sheet.get_all_records()
    new_id = len(records) + 1
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    new_row = [
        new_id, requester, hospital, item_name, quantity, 
        estimated_cost, "جديد", now_str, now_str
    ]
    sheet.append_row(new_row)

def update_purchase_status(req_id, new_status):
    sheet = get_worksheet("purchases")
    records = sheet.get_all_records()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    for idx, row in enumerate(records, start=2):
        if str(row.get("id")) == str(req_id):
            sheet.update_cell(idx, 7, new_status)  # العمود 7 هو status
            sheet.update_cell(idx, 9, now_str)     # العمود 9 هو updated_at
            break

# --- الجلسة ---
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "username" not in st.session_state:
    st.session_state["username"] = ""
if "role" not in st.session_state:
    st.session_state["role"] = ""

# --- تسجيل الدخول ---
def login_screen():
    st.markdown("<h1 class='main-title'>🔒 نظام تتبع عمليات الشراء</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.subheader("تسجيل الدخول")
        username = st.text_input("اسم المستخدم")
        password = st.text_input("كلمة المرور", type="password")
        
        if st.button("دخول"):
            users_df = load_users()
            user_row = users_df[users_df["username"] == username]
            
            if not user_row.empty:
                stored_hash = user_row.iloc[0]["password"]
                role = user_row.iloc[0]["role"]
                status = user_row.iloc[0]["status"]
                
                if status != "نشط":
                    st.error("هذا الحساب معطل، يرجى مراجعة أدمن النظام.")
                elif check_hashes(password, stored_hash):
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = username
                    st.session_state["role"] = role
                    st.success(f"مرحباً بك {username}")
                    st.rerun()
                else:
                    st.error("كلمة المرور غير صحيحة.")
            else:
                st.error("اسم المستخدم غير موجود.")

# --- الواجهة الرئيسية بـ 6 شاشات ---
def main_app():
    st.sidebar.title(f"👤 مرحباً: {st.session_state['username']}")
    st.sidebar.write(f"**الصلاحية:** {st.session_state['role']}")
    
    if st.sidebar.button("تسجيل الخروج"):
        st.session_state["logged_in"] = False
        st.session_state["username"] = ""
        st.session_state["role"] = ""
        st.rerun()

    st.markdown("<h1 class='main-title'>📦 نظام تتبع طلبات الشراء للمستشفيات</h1>", unsafe_allow_html=True)
    
    # القوائم والشاشات الست
    menu_options = [
        "📊 الداش بورد", 
        "➕ رفع الطلبات", 
        "📋 عرض وطلب حالات الشراء",
        "🔍 شاشة المراجعة", 
        "✅ شاشة الاعتماد", 
        "👥 إدارة المستخدمين"
    ]
    
    choice = st.sidebar.radio("الشاشات والأقسام", menu_options)
    df_purchases = load_purchases()

    # 1️⃣ شاشة الداش بورد
    if choice == "📊 الداش بورد":
        st.subheader("📊 لوحة المؤشرات والإحصائيات العامة")
        
        c1, c2, c3, c4 = st.columns(4)
        total_requests = len(df_purchases)
        new_requests = len(df_purchases[df_purchases["status"] == "جديد"]) if not df_purchases.empty else 0
        under_review = len(df_purchases[df_purchases["status"] == "قيد المراجعة"]) if not df_purchases.empty else 0
        approved = len(df_purchases[df_purchases["status"] == "معتمد"]) if not df_purchases.empty else 0
        
        c1.metric("إجمالي الطلبات", total_requests)
        c2.metric("طلبات جديدة", new_requests)
        c3.metric("قيد المراجعة", under_review)
        c4.metric("طلبات معتمدة", approved)
        
        st.markdown("---")
        if not df_purchases.empty:
            col_chart1, col_chart2 = st.columns(2)
            with col_chart1:
                st.markdown("### 🏥 توزيع الطلبات حسب المستشفى")
                st.bar_chart(df_purchases["hospital"].value_counts())
            with col_chart2:
                st.markdown("### 📌 توزيع حالات الطلبات")
                st.bar_chart(df_purchases["status"].value_counts())
        else:
            st.info("لا توجد بيانات للعرض في الداش بورد حالياً.")

    # 2️⃣ شاشة رفع الطلبات
    elif choice == "➕ رفع الطلبات":
        st.subheader("➕ رفع طلب شراء جديد")
        with st.form("purchase_form"):
            hospital = st.selectbox("المستشفى / الجهة", HOSPITALS_LIST)
            item_name = st.text_input("اسم البند / الصنف المطلوب")
            quantity = st.number_input("الكمية", min_value=1, value=1, step=1)
            estimated_cost = st.number_input("التكلفة التقديرية (ريال)", min_value=0.0, value=0.0, step=100.0)
            
            submitted = st.form_submit_button("إرسال الطلب")
            if submitted:
                if not item_name.strip():
                    st.warning("يرجى كتابة اسم البند المطلوب.")
                else:
                    save_purchase_request(st.session_state["username"], hospital, item_name, quantity, estimated_cost)
                    st.success("تم رفع الطلب بنجاح وهو الآن قيد المراجعة.")
                    st.rerun()

    # 3️⃣ شاشة عرض وطلب حالات الشراء
    elif choice == "📋 عرض وطلب حالات الشراء":
        st.subheader("📋 قائمة الطلبات وتتبع الحالات")
        if df_purchases.empty:
            st.info("لا توجد طلبات مسجلة حالياً.")
        else:
            if st.session_state["role"] not in ["أدمن النظام", "مدير المشتريات"]:
                df_display = df_purchases[df_purchases["requester"] == st.session_state["username"]]
            else:
                df_display = df_purchases
            st.dataframe(df_display, use_container_width=True)

    # 4️⃣ شاشة المراجعة
    elif choice == "🔍 شاشة المراجعة":
        st.subheader("🔍 مراجعة الطلبات والتدقيق الأول")
        if st.session_state["role"] not in ["أدمن النظام", "مدير المشتريات", "مراجع"]:
            st.warning("عذراً، هذه الشاشة مخصصة للمراجعين ومدراء المشتريات فقط.")
        else:
            if df_purchases.empty:
                st.info("لا توجد طلبات للمراجعة.")
            else:
                st.dataframe(df_purchases, use_container_width=True)
                st.markdown("---")
                c1, c2 = st.columns(2)
                with c1:
                    req_id = st.number_input("رقم الطلب (ID) للمراجعة", min_value=1, step=1)
                with c2:
                    new_status = st.selectbox("تحديث حالة المراجعة", ["قيد المراجعة", "مستوفى الشروط", "يحتاج تعديل", "مرفوض"])
                if st.button("حفظ المراجعة"):
                    update_purchase_status(req_id, new_status)
                    st.success(f"تمت مراجعة الطلب رقم {req_id} وتغيير حالته إلى: {new_status}")
                    st.rerun()

    # 5️⃣ شاشة الاعتماد
    elif choice == "✅ شاشة الاعتماد":
        st.subheader("✅ شاشة الاعتماد النهائي لطلبات الشراء")
        if st.session_state["role"] not in ["أدمن النظام", "مدير المشتريات"]:
            st.warning("عذراً، هذه الشاشة مخصصة لمدراء المشتريات وأدمن النظام فقط.")
        else:
            pending_approval = df_purchases[df_purchases["status"].isin(["جديد", "قيد المراجعة", "مستوفى الشروط"])] if not df_purchases.empty else pd.DataFrame()
            if pending_approval.empty:
                st.info("لا توجد طلبات معلقة بانتظار الاعتماد.")
            else:
                st.dataframe(pending_approval, use_container_width=True)
                st.markdown("---")
                c1, c2 = st.columns(2)
                with c1:
                    req_id = st.number_input("رقم الطلب (ID) للاعتماد", min_value=1, step=1)
                with c2:
                    approval_status = st.selectbox("قرار الاعتماد النهائي", ["معتمد", "مرفوض نهائياً"])
                if st.button("تأكيد القرار"):
                    update_purchase_status(req_id, approval_status)
                    st.success(f"تم اعتماد القرار للطلب رقم {req_id}: {approval_status}")
                    st.rerun()

    # 6️⃣ شاشة إدارة المستخدمين
    elif choice == "👥 إدارة المستخدمين":
        st.subheader("👥 إدارة المستخدمين وصلاحياتهم")
        if st.session_state["role"] != "أدمن النظام":
            st.warning("عذراً، هذه الشاشة مخصصة لأدمن النظام فقط.")
        else:
            tab1, tab2 = st.tabs(["قائمة المستخدمين", "إضافة مستخدم جديد"])
            with tab1:
                df_users = load_users()
                display_users = df_users.drop(columns=["password"], errors="ignore")
                st.dataframe(display_users, use_container_width=True)
            with tab2:
                with st.form("new_user_form"):
                    new_username = st.text_input("اسم المستخدم الجديد")
                    new_password = st.text_input("كلمة المرور", type="password")
                    new_role = st.selectbox("الصلاحية", ["طالب شراء", "مراجع", "مدير المشتريات", "أدمن النظام"])
                    
                    user_submit = st.form_submit_button("إضافة المستخدم")
                    if user_submit:
                        if not new_username.strip() or not new_password.strip():
                            st.warning("يرجى ملء جميع الحقول.")
                        else:
                            df_users = load_users()
                            if new_username in df_users["username"].values:
                                st.error("اسم المستخدم موجود بالفعل.")
                            else:
                                save_user(new_username, new_password, new_role)
                                st.success(f"تمت إضافة المستخدم {new_username} بنجاح!")
                                st.rerun()

# --- التشغيل الرئيسي ---
if __name__ == "__main__":
    if st.session_state["logged_in"]:
        main_app()
    else:
        login_screen()
