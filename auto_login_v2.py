from pocketoptionapi.stable_api import PocketOption
import time

# True للحساب التجريبي، و False للحساب الحقيقي
demo_account = True 

# تهيئة المكتبة (ستفتح نافذة لتسجيل الدخول إذا لم تكن الجلسة محفوظة)
api = PocketOption(demo_account)

# الاتصال
api.connect()
time.sleep(3) # انتظار بسيط لإتمام الاتصال

# التحقق من الرصيد
try:
    saldo = api.GetBalance()
    print(f"✅ تم الاتصال بنجاح! الرصيد: ${saldo:.2f}")
except Exception as e:
    print(f"❌ فشل الاتصال: {e}")

# (اختياري) اختبار جلب الأزواج
# pairs = api.GetPairs()
# print(f"عدد الأزواج المتاحة: {len(pairs)}")