"""
⚡ Smart Money Pro Trading Bot
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Automated trading bot with Telegram notifications
Compatible with Smart Money Forex Pro v3.3 (Final Fix)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import time
import logging
import requests
import os
import json
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, asdict
from datetime import datetime
from flask import Flask, request, jsonify
from apscheduler.schedulers.background import BackgroundScheduler

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.FileHandler('bot.log'), logging.StreamHandler()])
logger = logging.getLogger(__name__)

app = Flask(__name__)

@dataclass
class Trade:
    id: str
    symbol: str
    direction: str
    entry: float
    tp1: float
    tp2: float
    tp3: float
    # Flags
    tp1_hit: bool = False
    tp2_hit: bool = False
    tp3_hit: bool = False
    sl_hit: bool = False
    closed: bool = False

class TradeTracker:
    def __init__(self):
        self.active_trades: Dict[str, Trade] = {}
        self.sent_alerts: Set[str] = set()

    def add_trade(self, trade: Trade):
        self.active_trades[trade.id] = trade
        logger.info(f"➕ New Trade Tracked: {trade.id}")

    def update_tp(self, trade_id, level, price):
        if trade_id not in self.active_trades: return None
        trade = self.active_trades[trade_id]
        
        r_profit = 1.5 if level == "TP1" else 2.5 if level == "TP2" else 4.0
        
        if level == "TP1": trade.tp1_hit = True
        elif level == "TP2": trade.tp2_hit = True
        elif level == "TP3": 
            trade.tp3_hit = True
            trade.closed = True
            self.active_trades.pop(trade_id, None)
        
        return {"symbol": trade.symbol, "profit_r": r_profit}

    def update_sl(self, trade_id, price):
        if trade_id not in self.active_trades: return None
        trade = self.active_trades[trade_id]
        trade.sl_hit = True
        trade.closed = True
        self.active_trades.pop(trade_id, None)
        return {"symbol": trade.symbol, "profit_r": -1.0}

    def is_duplicate(self, alert_id):
        if alert_id in self.sent_alerts: return True
        self.sent_alerts.add(alert_id)
        return False

class TelegramNotifier:
    def __init__(self, token, chat_id):
        self.token = token
        self.chat_id = chat_id
        self.url = f"https://api.telegram.org/bot{token}/sendMessage"

    def send(self, text):
        if not self.token or not self.chat_id: return False
        try:
            requests.post(self.url, json={"chat_id": self.chat_id, "text": text, "parse_mode": "HTML"}, timeout=5)
            return True
        except Exception as e:
            logger.error(f"Telegram Error: {e}")
            return False

    def format_price(self, price, symbol):
        try: p = float(price)
        except: return "0.00"
        if "JPY" in str(symbol): return f"{p:.3f}"
        if "XAU" in str(symbol) or "BTC" in str(symbol) or "ETH" in str(symbol): return f"{p:.2f}"
        return f"{p:.5f}"

    def send_new_trade(self, data):
        try:
            symbol = data.get('symbol', 'UNKNOWN')
            direction = data.get('direction', 'UNKNOWN')
            trigger = data.get('trigger', 'SMC').replace('_', ' ')
            
            entry = float(data.get('entry', 0))
            sl = float(data.get('stop_loss', 0))
            tp1 = float(data.get('tp1', 0))
            tp2 = float(data.get('tp2', 0))
            tp3 = float(data.get('tp3', 0))
            
            risk_pips = float(data.get('risk_pips', 0))
            tp3_pips = float(data.get('tp3_pips', 0))
            risk_amt = abs(entry - sl)

            tp1_pips = 0.0; tp2_pips = 0.0
            if risk_pips > 0 and risk_amt > 0:
                implied_pip_size = risk_amt / risk_pips
                if implied_pip_size > 0:
                    tp1_pips = abs(tp1 - entry) / implied_pip_size
                    tp2_pips = abs(tp2 - entry) / implied_pip_size

            dir_emoji = "🟢" if direction == "LONG" else "🔴"

            msg = f"""
<b>💎 SMART MONEY PRO</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚀 <b>{symbol} • {data.get('timeframe', 'M5')}</b>
{dir_emoji} <b>{direction} / {trigger}</b>

<b>📊 ENTRY</b>
├ Entry: <code>{self.format_price(entry, symbol)}</code>
├ SL: <code>{self.format_price(sl, symbol)}</code>
└ Risk: {self.format_price(risk_amt, symbol)} ({risk_pips:.1f} pips)

<b>🎯 TARGETS</b>
1️⃣ <code>{self.format_price(tp1, symbol)}</code> (+{tp1_pips:.1f} pips)
2️⃣ <code>{self.format_price(tp2, symbol)}</code> (+{tp2_pips:.1f} pips)
3️⃣ <code>{self.format_price(tp3, symbol)}</code> (+{tp3_pips:.1f} pips) 🏆
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#{symbol} #SMC
"""
            return self.send(msg)
        except Exception as e:
            logger.error(f"Error building msg: {e}")
            return False

    def send_update(self, event, data, r_profit):
        try:
            symbol = data.get('symbol', 'UNKNOWN')
            level = data.get('level', 'UNKNOWN')
            price = float(data.get('price', 0))
            
            if event == "TP_HIT":
                emoji = "💰" if level == "TP1" else "💰💰" if level == "TP2" else "🚀🔥"
                msg = f"""<b>{emoji} {level} HIT: {symbol}</b>\nPrice: <code>{self.format_price(price, symbol)}</code>\nProfit: +{r_profit}R"""
            else: 
                msg = f"""<b>❌ SL HIT: {symbol}</b>\nPrice: <code>{self.format_price(price, symbol)}</code>\nLoss: -1.0R"""
            
            return self.send(msg)
        except Exception as e:
            logger.error(f"Error building update msg: {e}")
            return False

bot = TelegramNotifier(os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID"))
tracker = TradeTracker()

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json(force=True, silent=True)
        if not data: return jsonify({"error": "No data"}), 400
        
        event = data.get('event', 'UNKNOWN')
        tid = data.get('trade_id', 'unknown')
        unique_id = f"{tid}-{event}-{data.get('level', '')}"
        
        if tracker.is_duplicate(unique_id): return jsonify({"status": "duplicate"}), 200

        if event == 'NEW_TRADE':
            tracker.add_trade(Trade(id=tid, symbol=data.get('symbol'), direction=data.get('direction'), entry=float(data.get('entry', 0)), tp1=float(data.get('tp1', 0)), tp2=float(data.get('tp2', 0)), tp3=float(data.get('tp3', 0))))
            bot.send_new_trade(data)
        elif event == 'TP_HIT':
            res = tracker.update_tp(tid, data.get('level'), float(data.get('price', 0)))
            if res: bot.send_update("TP_HIT", data, res['profit_r'])
        elif event == 'SL_HIT':
            res = tracker.update_sl(tid, float(data.get('price', 0)))
            if res: bot.send_update("SL_HIT", data, res['profit_r'])

        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
