from pocketoptionapi.stable_api import PocketOption
import time

print("⏳ جاري الاتصال بالمنصة...")

# القيمة True للحساب التجريبي، و False للحساب الحقيقي
demo = True

# التهيئة الصحيحة: نمرر القيمة مباشرة بدون اسم الوسيط
api = PocketOption(demo)

try:
    # ستفتح نافذة متصفح لتسجيل الدخول إذا لم تكن الجلسة محفوظة
    api.connect()
    time.sleep(3)
    
    # جلب الرصيد للتأكد من الاتصال
    balance = api.GetBalance()
    print(f"✅ تم الاتصال بنجاح! رصيدك: ${balance:.2f}")
    
except Exception as e:
    print(f"❌ حدث خطأ: {e}")