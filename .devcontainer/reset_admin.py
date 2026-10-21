import sqlite3
import hashlib

# دالة التشفير المستخدمة في النظام
def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

# الاتصال بقاعدة البيانات (تأكد من مطابقة اسم ملف قاعدة البيانات لدسيك)
conn = sqlite3.connect('purchase_system.db')
cursor = conn.cursor()

# كلمة المرور الجديدة التي تريدها
new_password = 'admin123'
hashed_password = make_hashes(new_password)

# تحديث كلمة مرور الأدمن في جدول المستخدمين
cursor.execute('''
    UPDATE users 
    SET password = ? 
    WHERE username = 'admin'
''', (hashed_password,))

conn.commit()
conn.close()

print("تم إعادة تعيين كلمة مرور الأدمن بنجاح إلى: admin123")
