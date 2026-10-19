import os
import pandas as pd
import streamlit as st

# دالة تحميل الملف المرجعي وتخزينه في الذاكرة المؤقتة للسرعة
@st.cache_data
def load_catalog():
    file_path = "استهلاك كل قسم على حدا.xlsx"
    if os.path.exists(file_path):
        # قراءة الملف باستخدام openpyxl
        df = pd.read_excel(file_path, engine='openpyxl')
        
        # تنظيف وتنسيق الأعمدة
        df['رقم نوبكو'] = df['رقم نوبكو'].astype(str).str.strip()
        df['اسم الصنف'] = df['اسم الصنف'].astype(str).str.strip()
        df['رقم البند'] = df['رقم البند'].fillna('').astype(str).str.strip()
        
        # إنشاء عمود البحث المدمج
        df['display_label'] = df['اسم الصنف'] + " | نوبكو: " + df['رقم نوبكو'] + " | بند: " + df['رقم البند']
        return df
    else:
        return pd.DataFrame()

catalog_df = load_catalog()

if not catalog_df.empty:
    st.success(f"✅ تم تحميل {len(catalog_df):,} صنف من ملف الإكسل بنجاح!")
else:
    st.error("⚠️ لم يتم العثور على ملف 'استهلاك كل قسم على حدا.xlsx' في مجلد المشروع على GitHub.")
