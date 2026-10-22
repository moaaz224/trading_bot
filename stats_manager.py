import json
import os
from datetime import datetime

DATA_FILE = "trades_data.json"

def load_stats():
    if not os.path.exists(DATA_FILE):
        return {"assets": {}} # هيكل جديد يدعم عدة أزواج
    with open(DATA_FILE, 'r') as f:
        return json.load(f)

def save_trade(asset, direction, amount, result_status):
    stats = load_stats()
    if asset not in stats["assets"]:
        stats["assets"][asset] = {"total": 0, "wins": 0, "losses": 0, "history": []}
    
    asset_stats = stats["assets"][asset]
    asset_stats["total"] += 1
    if result_status:
        asset_stats["wins"] += 1
    else:
        asset_stats["losses"] += 1
        
    trade_record = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "direction": direction,
        "amount": amount,
        "won": result_status
    }
    asset_stats["history"].append(trade_record)
    
    with open(DATA_FILE, 'w') as f:
        json.dump(stats, f, indent=4)

def get_asset_winrate(asset):
    stats = load_stats()
    if asset in stats["assets"] and stats["assets"][asset]["total"] > 0:
        a_stats = stats["assets"][asset]
        return (a_stats["wins"] / a_stats["total"]) * 100
    return 0.0

def get_full_stats():
    stats = load_stats()
    if not stats["assets"]:
        return "📊 لا توجد صفقات مسجلة حتى الآن."
    
    text = "📊 **إحصائيات الأداء الشاملة**\n➖➖➖➖➖➖➖➖\n"
    for asset, data in stats["assets"].items():
        winrate = (data["wins"] / data["total"] * 100) if data["total"] > 0 else 0
        text += f"🔹 **{asset}**\n"
        text += f"   إجمالي: {data['total']} | ربح: {data['wins']} | خسارة: {data['losses']}\n"
        text += f"   نسبة النجاح: {winrate:.1f}%\n\n"
    
    return text
