import pandas as pd
import numpy as np

class AIEngine:
    def __init__(self):
        self.last_prediction = None

    def calculate_rsi(self, prices, period=14):
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def calculate_macd(self, prices, fast=12, slow=26, signal=9):
        ema_fast = prices.ewm(span=fast, adjust=False).mean()
        ema_slow = prices.ewm(span=slow, adjust=False).mean()
        macd = ema_fast - ema_slow
        macd_signal = macd.ewm(span=signal, adjust=False).mean()
        return macd, macd_signal

    def calculate_stoch_rsi(self, prices, period=14, k=3, d=3):
        rsi = self.calculate_rsi(prices, period)
        stoch_rsi = (rsi - rsi.rolling(period).min()) / (rsi.rolling(period).max() - rsi.rolling(period).min())
        stoch_rsi_k = stoch_rsi.rolling(k).mean() * 100
        stoch_rsi_d = stoch_rsi_k.rolling(d).mean()
        return stoch_rsi_k, stoch_rsi_d

    def final_decision(self, candles, asset_name='EURUSD_otc', balance=1000):
        try:
            df = pd.DataFrame(candles)
            if 'time' in df.columns:
                df['time'] = pd.to_datetime(df['time'], unit='s')
                df = df.sort_values('time')
            
            # 1. حساب المؤشرات الأساسية
            df['rsi'] = self.calculate_rsi(df['close'])
            df['macd'], df['macd_signal'] = self.calculate_macd(df['close'])
            df['ema_9'] = df['close'].ewm(span=9).mean()
            df['ema_21'] = df['close'].ewm(span=21).mean()
            df['ema_50'] = df['close'].ewm(span=50).mean()
            df['bb_high'] = df['close'].rolling(20).mean() + 2 * df['close'].rolling(20).std()
            df['bb_low'] = df['close'].rolling(20).mean() - 2 * df['close'].rolling(20).std()
            df['stoch_rsi_k'], df['stoch_rsi_d'] = self.calculate_stoch_rsi(df['close'])

            latest = df.iloc[-1]
            previous = df.iloc[-2]
            current_price = latest['close']

            buy_votes = 0
            sell_votes = 0
            total_weight = 0

            # 1. فلتر الاتجاه العام (Trend Filter) - الوزن الأكبر
            # إذا كان السعر فوق المتوسطات، الاتجاه صاعد (شراء). إذا كان تحتها، هابط (بيع).
            if latest['ema_9'] > latest['ema_21'] > latest['ema_50']:
                buy_votes += 3
                total_weight += 3
            elif latest['ema_9'] < latest['ema_21'] < latest['ema_50']:
                sell_votes += 3
                total_weight += 3

            # 2. مؤشر Stochastic RSI (تشبع قوي جداً)
            if latest['stoch_rsi_k'] < 20 and latest['stoch_rsi_k'] > latest['stoch_rsi_d']: # تقاطع لأعلى من منطقة التشبع البيعي
                buy_votes += 2
                total_weight += 2
            elif latest['stoch_rsi_k'] > 80 and latest['stoch_rsi_k'] < latest['stoch_rsi_d']: # تقاطع لأسفل من منطقة التشبع الشرائي
                sell_votes += 2
                total_weight += 2

            # 3. مؤشر MACD (تقاطع الزخم)
            if latest['macd'] > latest['macd_signal'] and previous['macd'] <= previous['macd_signal']:
                buy_votes += 2
                total_weight += 2
            elif latest['macd'] < latest['macd_signal'] and previous['macd'] >= previous['macd_signal']:
                sell_votes += 2
                total_weight += 2

            # 4. مؤشر RSI (تشبع كلاسيكي)
            if latest['rsi'] < 30: 
                buy_votes += 1.5
                total_weight += 1.5
            elif latest['rsi'] > 70: 
                sell_votes += 1.5
                total_weight += 1.5

            # 5. Bollinger Bands (مناطق الارتداد)
            if current_price <= latest['bb_low']:
                buy_votes += 1.5
                total_weight += 1.5
            elif current_price >= latest['bb_high']:
                sell_votes += 1.5
                total_weight += 1.5

            # حساب الإشارة والثقة
            if buy_votes > sell_votes:
                direction = 'CALL'
                # الثقة تعتمد على الفرق بين الأصوات
                confidence = min(95.0, 50.0 + (buy_votes - sell_votes) / max(total_weight, 1) * 50)
            elif sell_votes > buy_votes:
                direction = 'PUT'
                confidence = min(95.0, 50.0 + (sell_votes - buy_votes) / max(total_weight, 1) * 50)
            else:
                direction = 'NEUTRAL'
                confidence = 0

            # شرط الحماية: لا نتداول إلا إذا كانت الثقة عالية (أكثر من 65%) وكانت الأصوات متأكدة
            if confidence < 65.0 or total_weight < 3:
                direction = 'NEUTRAL'
                confidence = 0

            return {
                'signal': 1 if direction == 'CALL' else -1 if direction == 'PUT' else 0,
                'direction': direction,
                'confidence': round(confidence, 1),
                'buy_votes': round(buy_votes, 1),
                'sell_votes': round(sell_votes, 1),
                'current_price': current_price,
                'rsi': round(latest['rsi'], 1),
                'stoch': round(latest['stoch_rsi_k'], 1)
            }
            
        except Exception as e:
            print(f"خطأ في محرك التحليل: {e}")
            return {
                'signal': 0, 'direction': 'NEUTRAL', 'confidence': 0,
                'buy_votes': 0, 'sell_votes': 0, 'current_price': 0, 'rsi': 0, 'stoch': 0
            }
