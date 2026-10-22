import customtkinter as ctk
import threading
import sys
import os
import time
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters
from dotenv import load_dotenv
import pandas as pd
import numpy as np
import joblib
import json

from pocket_client import PocketClient
from ai_engine import AIEngine
import stats_manager

# إعداد المظهر
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

bot_application = None
is_bot_running = False

# ==========================================
# كود البوت
# ==========================================
load_dotenv()
TOKEN = os.getenv('TELEGRAM_TOKEN')
SCAN_INTERVAL = int(os.getenv('SCAN_INTERVAL_MINUTES', 5))
MIN_CONF = float(os.getenv('MIN_CONFIDENCE', 75.0))
MAX_LOSSES = int(os.getenv('MAX_CONSECUTIVE_LOSSES', 3))
MULTIPLIER = float(os.getenv('MARTINGALE_MULTIPLIER', 2.0))
ASSETS = ["EURUSD_otc", "GBPUSD_otc", "USDJPY_otc", "AUDCAD_otc"]
USER_CHAT_ID = None 
CHOOSING_ASSET, CHOOSING_AMOUNT, CUSTOM_AMOUNT, CHOOSING_TIME, CUSTOM_TIME = range(5)

pocket = PocketClient()
ai = AIEngine()

def log_to_gui(message):
    if hasattr(sys, '_gui_app'):
        sys._gui_app.log(message)

# واجهات المستخدم
def get_main_keyboard():
    account_status = "🟢 حقيقي" if pocket.current_account == 'live' else "🔵 تجريبي"
    keyboard = [
        [InlineKeyboardButton("💰 الرصيد", callback_data='balance')],
        [InlineKeyboardButton("🧠 تحليل السوق الشامل", callback_data='analyze_menu')],
        [InlineKeyboardButton("🚀 تنفيذ صفقة (يدوي)", callback_data='trade_menu')],
        [InlineKeyboardButton("🔥 التداول التلقائي (مضاعفة)", callback_data='martingale_menu')],
        [InlineKeyboardButton("📊 الإحصائيات", callback_data='stats')],
        [InlineKeyboardButton(f"🔀 تبديل الحساب (الحالي: {account_status})", callback_data='switch_account')],
        [InlineKeyboardButton("🔄 تحديث القائمة", callback_data='main_menu')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_assets_keyboard(action):
    keyboard = [[InlineKeyboardButton(asset, callback_data=f"{action}_{asset}")] for asset in ASSETS]
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data='main_menu')])
    return InlineKeyboardMarkup(keyboard)

def get_amounts_keyboard(asset, is_martingale=False):
    prefix = "m_amt" if is_martingale else "amt"
    keyboard = [
        [InlineKeyboardButton("$1", callback_data=f"{prefix}_1_{asset}"), InlineKeyboardButton("$5", callback_data=f"{prefix}_5_{asset}"), InlineKeyboardButton("$10", callback_data=f"{prefix}_10_{asset}")],
        [InlineKeyboardButton("مبلغ مخصص 💵", callback_data=f"{prefix}_custom_{asset}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data='main_menu')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_time_keyboard(asset, amount, is_martingale=False):
    prefix = "m_time" if is_martingale else "time"
    keyboard = [
        [InlineKeyboardButton("30 ثانية", callback_data=f"{prefix}_30"), InlineKeyboardButton("دقيقة 60ث", callback_data=f"{prefix}_60")],
        [InlineKeyboardButton("دقيقتين 120ث", callback_data=f"{prefix}_120"), InlineKeyboardButton("5 دقائق", callback_data=f"{prefix}_300")],
        [InlineKeyboardButton("🔙 إلغاء", callback_data='main_menu')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_analysis_results_keyboard(results):
    keyboard = []
    for asset, decision, winrate in results:
        btn_text = f"{asset} | ثقة: {decision['confidence']}% | نجاح: {winrate:.0f}%"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"details_{asset}")])
    keyboard.append([InlineKeyboardButton("🔄 تحديث الأزواج", callback_data='refresh_analyze'), InlineKeyboardButton("🚀 ابدأ التداول", callback_data='trade_menu')])
    keyboard.append([InlineKeyboardButton("🔙 رجوع للقائمة", callback_data='main_menu')])
    return InlineKeyboardMarkup(keyboard)

# --- الدوال الأساسية ---
async def clear_previous_result(context, chat_id):
    if 'last_result_msg_id' in context.user_data:
        try: await context.bot.delete_message(chat_id=chat_id, message_id=context.user_data['last_result_msg_id'])
        except: pass
        del context.user_data['last_result_msg_id']

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global USER_CHAT_ID
    USER_CHAT_ID = update.effective_chat.id
    context.user_data.clear()
    await clear_previous_result(context, USER_CHAT_ID)
    account_name = "الحقيقي 🟢" if pocket.current_account == 'live' else "التجريبي 🔵"
    msg = f"🧠 مرحباً بك!\n💼 الحساب النشط: {account_name}\nاختر من القائمة:"
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(msg, reply_markup=get_main_keyboard())
    else:
        await update.message.reply_text(msg, reply_markup=get_main_keyboard())
    return ConversationHandler.END

async def switch_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    new_type = 'live' if pocket.current_account == 'demo' else 'demo'
    pocket.switch_account(new_type)
    account_name = "الحقيقي 🟢" if pocket.current_account == 'live' else "التجريبي 🔵"
    log_to_gui(f"تم التبديل إلى الحساب: {account_name}")
    await query.edit_message_text(f"✅ تم التبديل بنجاح!\n💼 الحساب النشط الآن: {account_name}", reply_markup=get_main_keyboard())

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await clear_previous_result(context, query.message.chat_id)
    account_name = "الحقيقي 🟢" if pocket.current_account == 'live' else "التجريبي 🔵"
    await query.edit_message_text(f"⏳ جاري جلب الرصيد ({account_name})...", reply_markup=get_main_keyboard())
    try:
        bal = await asyncio.wait_for(pocket.get_balance(), timeout=15.0)
        await query.edit_message_text(f"💰 رصيدك ({account_name}): ${bal:.2f}", reply_markup=get_main_keyboard())
    except Exception as e:
        await query.edit_message_text(f"❌ خطأ: {str(e)}", reply_markup=get_main_keyboard())

async def analyze_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await clear_previous_result(context, query.message.chat_id)
    await query.edit_message_text("⏳ جاري تحليل جميع الأزواج...")
    results = []
    for asset in ASSETS:
        try:
            candles = await pocket.get_candles(asset, 60)
            if candles:
                bal = await pocket.get_balance()
                decision = ai.final_decision(candles, asset, bal)
                winrate = stats_manager.get_asset_winrate(asset)
                results.append((asset, decision, winrate))
            else:
                results.append((asset, {'confidence': 0, 'direction': 'خطأ'}, 0.0))
        except: pass
    await query.edit_message_text("🧠 نظرة عامة على السوق\nاختر زوجاً لعرض تفاصيله:", reply_markup=get_analysis_results_keyboard(results))

async def analyze_asset_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await clear_previous_result(context, query.message.chat_id)
    asset = query.data.split('_', 1)[1]
    await query.edit_message_text(f"⏳ جاري جلب تفاصيل {asset}...")
    try:
        candles = await pocket.get_candles(asset, 60)
        bal = await pocket.get_balance()
        decision = ai.final_decision(candles, asset, bal)
        winrate = stats_manager.get_asset_winrate(asset)
        msg = (f"🧠 تحليل: {asset}\n➖➖➖➖➖➖➖➖\n📈 السعر: {decision['current_price']:.5f}\n🎯 الإشارة: {decision['direction']}\n🔒 الثقة: {decision['confidence']}%\n⚖️ الأصوات: {decision.get('buy_votes', 0)} شراء / {decision.get('sell_votes', 0)} بيع\n🏆 النجاح: {winrate:.1f}%")
        keyboard = [[InlineKeyboardButton("🚀 أخذ الصفقة", callback_data=f"take_trade_{asset}")], [InlineKeyboardButton("🔙 رجوع للتحليل", callback_data='refresh_analyze')]]
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        await query.edit_message_text(f"❌ خطأ: {str(e)}")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await clear_previous_result(context, query.message.chat_id)
    await query.edit_message_text(stats_manager.get_full_stats(), reply_markup=get_main_keyboard())

async def trade_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await clear_previous_result(context, query.message.chat_id)
    await query.edit_message_text("اختر الزوج لتنفيذ صفقة:", reply_markup=get_assets_keyboard('trade'))
    return CHOOSING_ASSET

async def take_trade_from_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    asset = query.data.split('_', 2)[2] 
    context.user_data['trade_asset'] = asset
    await query.edit_message_text(f"💵 اختر مبلغ الصفقة لـ {asset}:", reply_markup=get_amounts_keyboard(asset, False))
    return CHOOSING_AMOUNT

async def trade_asset_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    asset = query.data.split('_', 1)[1]
    context.user_data['trade_asset'] = asset
    await query.edit_message_text(f"💵 اختر مبلغ الصفقة لـ {asset}:", reply_markup=get_amounts_keyboard(asset, False))
    return CHOOSING_AMOUNT

async def amount_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split('_')
    if parts[1] == 'custom':
        await query.edit_message_text("✍️ أرسل المبلغ:")
        return CUSTOM_AMOUNT
    else:
        amount = float(parts[1])
        asset = context.user_data.get('trade_asset')
        context.user_data['trade_amount'] = amount
        await query.edit_message_text(f"⏱ اختر وقت الصفقة:", reply_markup=get_time_keyboard(asset, amount, False))
        return CHOOSING_TIME

async def custom_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text.strip())
        asset = context.user_data.get('trade_asset')
        context.user_data['trade_amount'] = amount
        await update.message.reply_text(f"⏱ اختر وقت الصفقة:", reply_markup=get_time_keyboard(asset, amount, False))
        return CHOOSING_TIME
    except:
        await update.message.reply_text("❌ رقم غير صحيح:")
        return CUSTOM_AMOUNT

async def time_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    duration = int(query.data.split('_')[1])
    await execute_manual_trade(query, context, context.user_data.get('trade_asset'), context.user_data.get('trade_amount'), duration)
    return ConversationHandler.END

async def martingale_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await clear_previous_result(context, query.message.chat_id)
    await query.edit_message_text("🔥 اختر الزوج للتداول التلقائي:", reply_markup=get_assets_keyboard('m_trade'))
    return CHOOSING_ASSET

async def m_trade_asset_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    asset = query.data.split('_', 2)[2]
    context.user_data['trade_asset'] = asset
    await query.edit_message_text(f"💵 اختر المبلغ الأساسي:", reply_markup=get_amounts_keyboard(asset, True))
    return CHOOSING_AMOUNT

async def m_amount_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split('_') 
    if parts[2] == 'custom':
        await query.edit_message_text("✍️ أرسل المبلغ الأساسي:")
        return CUSTOM_AMOUNT
    else:
        amount = float(parts[2])
        asset = context.user_data.get('trade_asset')
        context.user_data['trade_amount'] = amount
        await query.edit_message_text(f"⏱ اختر وقت الصفقة:", reply_markup=get_time_keyboard(asset, amount, True))
        return CHOOSING_TIME

async def m_custom_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text.strip())
        asset = context.user_data.get('trade_asset')
        context.user_data['trade_amount'] = amount
        await update.message.reply_text(f"⏱ اختر وقت الصفقة:", reply_markup=get_time_keyboard(asset, amount, True))
        return CHOOSING_TIME
    except:
        await update.message.reply_text("❌ رقم غير صحيح:")
        return CUSTOM_AMOUNT

async def m_time_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    duration = int(query.data.split('_')[2]) 
    asset = context.user_data.get('trade_asset')
    base_amount = context.user_data.get('trade_amount')
    await query.edit_message_text(f"🔥 بدء التداول التلقائي على {asset}...\nالمبلغ الأساسي: ${base_amount}")
    asyncio.create_task(run_martingale(query.message.chat_id, context, asset, base_amount, duration, attempt=1))
    return ConversationHandler.END

async def run_martingale(chat_id, context, asset, current_amount, duration, attempt):
    try:
        candles = await pocket.get_candles(asset, 60)
        bal_before = await pocket.get_balance()  
        decision = ai.final_decision(candles, asset, bal_before)
        while decision['direction'] == 'NEUTRAL':
            await context.bot.send_message(chat_id=chat_id, text="⏳ السوق غير مستقر (إشارة محايدة)، جاري إعادة التحليل...")
            await asyncio.sleep(3) 
            candles = await pocket.get_candles(asset, 60)
            decision = ai.final_decision(candles, asset, bal_before)
        await context.bot.send_message(chat_id=chat_id, text=f"🚀 محاولة {attempt} | {decision['direction']} على {asset}\n💵 المبلغ: ${current_amount:.2f}")
        result = await pocket.execute_trade(asset, current_amount, decision['direction'], duration)
        if result is not None:
            await asyncio.sleep(duration + 2) 
            bal_after = await pocket.get_balance()
            profit_loss = bal_after - bal_before
            won = profit_loss > 0
            stats_manager.save_trade(asset, decision['direction'], current_amount, won)
            status = "✅ ربحت!" if won else "❌ خسرت."
            await context.bot.send_message(chat_id=chat_id, text=f"🔔 محاولة {attempt}:\n{status}\n💵 الفرق: ${profit_loss:.2f}\n💰 الرصيد: ${bal_after:.2f}")
            if not won and attempt <= MAX_LOSSES:
                new_amount = current_amount * MULTIPLIER
                await context.bot.send_message(chat_id=chat_id, text=f"🔄 خسارة! جاري المضاعفة...\n💵 المبلغ الجديد: ${new_amount:.2f}")
                await asyncio.sleep(1) 
                await run_martingale(chat_id, context, asset, new_amount, duration, attempt + 1)
            elif not won and attempt > MAX_LOSSES:
                await context.bot.send_message(chat_id=chat_id, text=f"🛑 تم الوصول للحد الأقصى. إيقاف.")
                await asyncio.sleep(1)
                await context.bot.send_message(chat_id=chat_id, text="القائمة الرئيسية:", reply_markup=get_main_keyboard())
            elif won:
                await context.bot.send_message(chat_id=chat_id, text=f"🎉 مبروك! ربحت في المحاولة {attempt}.")
                await asyncio.sleep(1)
                await context.bot.send_message(chat_id=chat_id, text="القائمة الرئيسية:", reply_markup=get_main_keyboard())
        else:
            await context.bot.send_message(chat_id=chat_id, text="❌ فشل التنفيذ. (المكتبة أعادت None)")
            await context.bot.send_message(chat_id=chat_id, text="القائمة الرئيسية:", reply_markup=get_main_keyboard())
    except Exception as e:
        log_to_gui(f"❌ خطأ في المضاعفة: {str(e)}")
        await context.bot.send_message(chat_id=chat_id, text=f"❌ خطأ: {str(e)}")

async def execute_manual_trade(reply_obj, context, asset, amount, duration):
    chat_id = reply_obj.message.chat_id
    await context.bot.send_message(chat_id=chat_id, text=f"🚀 جاري التنفيذ على {asset}...")
    asyncio.create_task(_run_manual_task(chat_id, context, asset, amount, duration))

async def _run_manual_task(chat_id, context, asset, amount, duration):
    try:
        candles = await pocket.get_candles(asset, 60)
        bal_before = await pocket.get_balance()  
        decision = ai.final_decision(candles, asset, bal_before)
        if decision['direction'] == 'NEUTRAL':
            await context.bot.send_message(chat_id=chat_id, text="⚠️ الإشارة محايدة.")
            return
        result = await pocket.execute_trade(asset, amount, decision['direction'], duration)
        if result is not None:
            await asyncio.sleep(duration + 2) 
            bal_after = await pocket.get_balance()
            profit_loss = bal_after - bal_before
            won = profit_loss > 0
            stats_manager.save_trade(asset, decision['direction'], amount, won)
            result_text = f"✅ ربحت! +${profit_loss:.2f}" if won else f"❌ خسرت. ${profit_loss:.2f}"
            await context.bot.send_message(chat_id=chat_id, text=f"🔔 النتيجة ({asset}):\n{result_text}\n💰 الرصيد: ${bal_after:.2f}")
            await asyncio.sleep(1)
            await context.bot.send_message(chat_id=chat_id, text="القائمة الرئيسية:", reply_markup=get_main_keyboard())
        else:
            await context.bot.send_message(chat_id=chat_id, text="❌ فشل التنفيذ.")
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ خطأ: {str(e)}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data
    if data == 'main_menu': await start(update, context)
    elif data == 'balance': await balance(update, context)
    elif data == 'switch_account': await switch_account(update, context) # زر التبديل
    elif data in ['analyze_menu', 'refresh_analyze']: await analyze_menu(update, context)
    elif data.startswith('details_'): await analyze_asset_details(update, context)
    elif data == 'stats': await stats(update, context)

async def run_bot_async():
    global bot_application
    if not TOKEN:
        log_to_gui("❌ التوكن غير موجود في ملف .env")
        return
        
    try: asyncio.get_event_loop()
    except RuntimeError: asyncio.set_event_loop(asyncio.new_event_loop())

    bot_application = Application.builder().token(TOKEN).build()
    if bot_application.job_queue:
        bot_application.job_queue.run_repeating(auto_scanner, interval=SCAN_INTERVAL * 60, first=10)

    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(trade_menu, pattern='^trade_menu$'),
            CallbackQueryHandler(take_trade_from_analysis, pattern='^take_trade_'),
            CallbackQueryHandler(martingale_menu, pattern='^martingale_menu$')
        ],
        states={
            CHOOSING_ASSET: [CallbackQueryHandler(trade_asset_selected, pattern='^trade_'), CallbackQueryHandler(m_trade_asset_selected, pattern='^m_trade_')],
            CHOOSING_AMOUNT: [CallbackQueryHandler(amount_selected, pattern='^amt_'), CallbackQueryHandler(m_amount_selected, pattern='^m_amt_')],
            CUSTOM_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, custom_amount_received), MessageHandler(filters.TEXT & ~filters.COMMAND, m_custom_amount_received)],
            CHOOSING_TIME: [CallbackQueryHandler(time_selected, pattern='^time_'), CallbackQueryHandler(m_time_selected, pattern='^m_time_')]
        },
        fallbacks=[CommandHandler('start', start), CallbackQueryHandler(start, pattern='^main_menu$')],
        per_message=False
    )

    bot_application.add_handler(conv_handler)
    bot_application.add_handler(CommandHandler("start", start))
    bot_application.add_handler(CallbackQueryHandler(button_handler))
    
    log_to_gui("🚀 البوت يعمل بكفاءة...")
    
    await bot_application.initialize()
    await bot_application.start()
    await bot_application.updater.start_polling()
    
    while is_bot_running:
        await asyncio.sleep(1)
        
    await bot_application.updater.stop()
    await bot_application.stop()
    await bot_application.shutdown()

# دالة المسح التلقائي للخلفية
async def auto_scanner(context: ContextTypes.DEFAULT_TYPE):
    global USER_CHAT_ID
    if not USER_CHAT_ID: return
    for asset in ASSETS:
        try:
            candles = await pocket.get_candles(asset, 60)
            if not candles: continue
            bal = await pocket.get_balance()
            decision = ai.final_decision(candles, asset, bal)
            if decision['direction'] != 'NEUTRAL' and decision['confidence'] >= MIN_CONF:
                msg = (f"🚨 إشارة تلقائية جديدة 🚨\n➖➖➖➖➖➖➖➖\n💎 الزوج: {asset}\n📈 السعر: {decision['current_price']:.5f}\n🎯 الاتجاه: {decision['direction']}\n🔒 الثقة: {decision['confidence']}%")
                await context.bot.send_message(chat_id=USER_CHAT_ID, text=msg)
        except Exception as e:
            log_to_gui(f"خطأ في المسح التلقائي: {e}")

# ==========================================
# واجهة المستخدم (GUI)
# ==========================================
class TradingBotApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        sys._gui_app = self

        self.title("Trading AI Bot - Control Panel")
        self.geometry("600x500")
        self.resizable(False, False)

        self.title_label = ctk.CTkLabel(self, text="🤖 نظام التداول الذكي", font=ctk.CTkFont(size=24, weight="bold"))
        self.title_label.pack(pady=20)

        self.status_label = ctk.CTkLabel(self, text="⏹️ الحالة: متوقف", text_color="red", font=ctk.CTkFont(size=18))
        self.status_label.pack(pady=10)

        self.btn_frame = ctk.CTkFrame(self)
        self.btn_frame.pack(pady=10)

        self.start_btn = ctk.CTkButton(self.btn_frame, text="▶️ تشغيل البوت", fg_color="green", hover_color="darkgreen", command=self.start_bot)
        self.start_btn.grid(row=0, column=0, padx=20, pady=10)

        self.stop_btn = ctk.CTkButton(self.btn_frame, text="⏹️ إيقاف البوت", fg_color="red", hover_color="darkred", command=self.stop_bot, state="disabled")
        self.stop_btn.grid(row=0, column=1, padx=20, pady=10)

        self.log_label = ctk.CTkLabel(self, text="📋 سجل العمليات:", font=ctk.CTkFont(size=14))
        self.log_label.pack(anchor="w", padx=20)

        self.log_textbox = ctk.CTkTextbox(self, width=550, height=250, font=ctk.CTkFont(family="Courier", size=12))
        self.log_textbox.pack(pady=10, padx=20)
        self.log_textbox.configure(state="disabled")

        self.log("مرحباً بك في لوحة التحكم. اضغط على 'تشغيل البوت' للبدء.")

    def log(self, message):
        self.log_textbox.configure(state="normal")
        self.log_textbox.insert("end", f"[{time.strftime('%H:%M:%S')}] {message}\n")
        self.log_textbox.see("end")
        self.log_textbox.configure(state="disabled")

    def start_bot(self):
        global is_bot_running
        if not is_bot_running:
            is_bot_running = True
            self.status_label.configure(text="▶️ الحالة: يعمل الآن", text_color="green")
            self.start_btn.configure(state="disabled")
            self.stop_btn.configure(state="normal")
            self.log("🚀 تم تشغيل البوت بنجاح...")
            
            def bot_thread():
                asyncio.run(run_bot_async())
            threading.Thread(target=bot_thread, daemon=True).start()

    def stop_bot(self):
        global is_bot_running
        if is_bot_running:
            is_bot_running = False
            self.status_label.configure(text="⏹️ الحالة: متوقف", text_color="red")
            self.start_btn.configure(state="normal")
            self.stop_btn.configure(state="disabled")
            self.log("🛑 تم إيقاف البوت.")

if __name__ == "__main__":
    app = TradingBotApp()
    app.mainloop()