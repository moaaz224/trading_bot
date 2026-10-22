import time
from pocketoptionapi.stable_api import PocketOption

class PocketClient:
    def __init__(self):
        # تحديد الحساب (تجريبي أو حقيقي)
        self.is_demo = True 
        self.api = None

    def connect(self):
        """الاتصال بالمنصة (يفتح متصفح للدخول إذا لزم الأمر)"""
        if not self.api:
            print("🔄 جاري الاتصال بمنصة Pocket Option...")
            self.api = PocketOption(demo_account=self.is_demo)
            time.sleep(2) # انتظار بسيط للاتصال
        return self.api

    def switch_account(self, account_type):
        """تبديل الحساب وإعادة الاتصال"""
        self.is_demo = (account_type == 'demo')
        self.api = None # إعادة تعيين الاتصال
        print(f"🔄 تم التبديل إلى الحساب {'التجريبي' if self.is_demo else 'الحقيقي'}")
        self.connect()

    def get_balance(self):
        """جلب الرصيد الحالي"""
        api = self.connect()
        try:
            balance = api.GetBalance()
            return balance
        except Exception as e:
            print(f"❌ خطأ في جلب الرصيد: {e}")
            return 0.0

    def get_candles(self, asset="EURUSD_otc", period=60, count=100):
        """جلب الشموع للتحليل"""
        api = self.connect()
        try:
            candles = api.GetCandles(asset, period, count)
            # المكتبة ترجع الشموع بصيغة معينة، سنحولها للصيغة التي يفهمها محرك التحليل
            formatted_candles = []
            for c in candles:
                formatted_candles.append({
                    'time': c['time'],
                    'open': c['open'],
                    'high': c['high'],
                    'low': c['low'],
                    'close': c['close'],
                })
            return formatted_candles
        except Exception as e:
            print(f"❌ خطأ في جلب الشموع: {e}")
            return []

    def execute_trade(self, asset, amount, direction, duration):
        """تنفيذ الصفقة (شراء أو بيع)"""
        api = self.connect()
        try:
            # تحويل الاتجاه إلى الصيغة التي تفهمها المكتبة
            action = "call" if direction.lower() == 'call' else "put"
            
            # تنفيذ الصفقة (المكتبة قد تستخدم أسماء دوال مختلفة)
            if action == "call":
                result = api.Buy(amount, asset, duration)
            else:
                result = api.Sell(amount, asset, duration)
                
            return result
        except Exception as e:
            print(f"❌ خطأ في تنفيذ الصفقة: {e}")
            return None