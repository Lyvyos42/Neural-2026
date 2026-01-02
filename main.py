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
from apscheduler.triggers.cron import CronTrigger

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

@dataclass
class Trade:
    """Trade data"""
    id: str
    symbol: str
    direction: str
    signal_type: str
    pattern: str
    entry: float
    stop_loss: float
    tp1: float
    tp2: float
    tp3: float
    score: int
    mode: str
    session: str
    timeframe: str
    bubble_strength: int
    exhaustion_detected: bool
    htf_trend: str
    strict_mode: bool
    timestamp: str
    
    tp1_hit: bool = False
    tp2_hit: bool = False
    tp3_hit: bool = False
    sl_hit: bool = False
    closed: bool = False
    final_result: str = "ACTIVE"
    profit_r: float = 0.0
    
    # FIXED: Track which notifications have been SENT
    tp1_notified: bool = False
    tp2_notified: bool = False
    tp3_notified: bool = False
    sl_notified: bool = False
    
    def to_dict(self):
        return asdict(self)

class TradeTracker:
    """Track all trades"""
    
    def __init__(self):
        self.active_trades: Dict[str, Trade] = {}
        self.closed_trades: List[Trade] = []
        self.daily_trades: List[Trade] = []
        self.weekly_trades: List[Trade] = []
        
        # FIXED: Track which trade IDs have already received each TP/SL
        self.tp1_sent: Set[str] = set()
        self.tp2_sent: Set[str] = set()
        self.tp3_sent: Set[str] = set()
        self.sl_sent: Set[str] = set()
    
    def add_trade(self, trade: Trade):
        """Add new trade"""
        self.active_trades[trade.id] = trade
        self.daily_trades.append(trade)
        self.weekly_trades.append(trade)
        logger.info(f"📊 Added trade: {trade.id}")
    
    def should_send_tp1(self, trade_id: str) -> bool:
        """Check if TP1 notification should be sent"""
        if trade_id in self.tp1_sent:
            logger.info(f"⏭️ TP1 already sent for {trade_id}")
            return False
        self.tp1_sent.add(trade_id)
        return True
    
    def should_send_tp2(self, trade_id: str) -> bool:
        """Check if TP2 notification should be sent"""
        if trade_id in self.tp2_sent:
            logger.info(f"⏭️ TP2 already sent for {trade_id}")
            return False
        self.tp2_sent.add(trade_id)
        return True
    
    def should_send_tp3(self, trade_id: str) -> bool:
        """Check if TP3 notification should be sent"""
        if trade_id in self.tp3_sent:
            logger.info(f"⏭️ TP3 already sent for {trade_id}")
            return False
        self.tp3_sent.add(trade_id)
        return True
    
    def should_send_sl(self, trade_id: str) -> bool:
        """Check if SL notification should be sent"""
        if trade_id in self.sl_sent:
            logger.info(f"⏭️ SL already sent for {trade_id}")
            return False
        self.sl_sent.add(trade_id)
        return True
    
    def update_trade_tp(self, trade_id: str, level: str, price: float):
        """Update trade TP"""
        if trade_id in self.active_trades:
            trade = self.active_trades[trade_id]
            
            if level == "TP1" and not trade.tp1_notified:
                trade.tp1_hit = True
                trade.tp1_notified = True
                trade.profit_r = 1.5
            elif level == "TP2" and not trade.tp2_notified:
                trade.tp2_hit = True
                trade.tp2_notified = True
                trade.profit_r = 2.5
            elif level == "TP3" and not trade.tp3_notified:
                trade.tp3_hit = True
                trade.tp3_notified = True
                trade.final_result = "TP3"
                trade.profit_r = 4.0
                trade.closed = True
                self.close_trade(trade_id)
            
            logger.info(f"✅ {trade_id}: {level} hit")
    
    def update_trade_sl(self, trade_id: str):
        """Update trade SL"""
        if trade_id in self.active_trades:
            trade = self.active_trades[trade_id]
            if not trade.sl_notified:
                trade.sl_hit = True
                trade.sl_notified = True
                trade.final_result = "SL"
                trade.profit_r = -1.0
                trade.closed = True
                self.close_trade(trade_id)
                logger.info(f"❌ {trade_id}: SL hit")
    
    def close_trade(self, trade_id: str):
        """Close trade"""
        if trade_id in self.active_trades:
            trade = self.active_trades.pop(trade_id)
            self.closed_trades.append(trade)
            logger.info(f"🔒 Closed: {trade_id}")
    
    def get_daily_stats(self) -> Dict:
        """Daily stats"""
        if not self.daily_trades:
            return None
        
        total = len(self.daily_trades)
        closed = [t for t in self.daily_trades if t.closed]
        
        if not closed:
            return {"total_signals": total, "closed_trades": 0, "active_trades": total}
        
        tp3 = len([t for t in closed if t.final_result == "TP3"])
        tp2 = len([t for t in closed if t.final_result == "TP2"])
        tp1 = len([t for t in closed if t.final_result == "TP1"])
        sl = len([t for t in closed if t.final_result == "SL"])
        
        wins = tp3 + tp2 + tp1
        wr = (wins / len(closed) * 100) if closed else 0
        total_r = sum([t.profit_r for t in closed])
        avg_r = total_r / len(closed) if closed else 0
        
        return {
            "total_signals": total,
            "closed_trades": len(closed),
            "active_trades": total - len(closed),
            "tp3_count": tp3,
            "tp2_count": tp2,
            "tp1_count": tp1,
            "sl_count": sl,
            "wins": wins,
            "losses": sl,
            "win_rate": wr,
            "total_r": total_r,
            "avg_r": avg_r
        }
    
    def get_weekly_stats(self) -> Dict:
        """Weekly stats"""
        if not self.weekly_trades:
            return None
        
        total = len(self.weekly_trades)
        closed = [t for t in self.weekly_trades if t.closed]
        
        if not closed:
            return {"total_signals": total, "closed_trades": 0, "active_trades": total}
        
        tp3 = len([t for t in closed if t.final_result == "TP3"])
        tp2 = len([t for t in closed if t.final_result == "TP2"])
        tp1 = len([t for t in closed if t.final_result == "TP1"])
        sl = len([t for t in closed if t.final_result == "SL"])
        
        wins = tp3 + tp2 + tp1
        wr = (wins / len(closed) * 100) if closed else 0
        total_r = sum([t.profit_r for t in closed])
        avg_r = total_r / len(closed) if closed else 0
        
        by_sym = {}
        for t in closed:
            if t.symbol not in by_sym:
                by_sym[t.symbol] = {"wins": 0, "losses": 0, "total_r": 0}
            if t.final_result in ["TP1", "TP2", "TP3"]:
                by_sym[t.symbol]["wins"] += 1
            else:
                by_sym[t.symbol]["losses"] += 1
            by_sym[t.symbol]["total_r"] += t.profit_r
        
        return {
            "total_signals": total,
            "closed_trades": len(closed),
            "active_trades": total - len(closed),
            "tp3_count": tp3,
            "tp2_count": tp2,
            "tp1_count": tp1,
            "sl_count": sl,
            "wins": wins,
            "losses": sl,
            "win_rate": wr,
            "total_r": total_r,
            "avg_r": avg_r,
            "by_symbol": by_sym
        }
    
    def reset_daily(self):
        """Reset daily"""
        self.daily_trades = []
        logger.info("🔄 Daily reset")
    
    def reset_weekly(self):
        """Reset weekly"""
        self.weekly_trades = []
        self.tp1_sent.clear()
        self.tp2_sent.clear()
        self.tp3_sent.clear()
        self.sl_sent.clear()
        logger.info("🔄 Weekly reset")

class TelegramNotifier:
    """Telegram notifications"""
    
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}/"
        
    def send_message(self, text: str, parse_mode: str = "HTML"):
        """Send message"""
        try:
            url = f"{self.base_url}sendMessage"
            payload = {"chat_id": self.chat_id, "text": text, "parse_mode": parse_mode}
            
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                logger.info("✅ Telegram sent")
                return True
            else:
                logger.error(f"❌ Telegram failed: {response.text}")
                return False
        except Exception as e:
            logger.error(f"❌ Error: {e}")
            return False
    
    def send_elite_signal(self, data: Dict):
        """Send signal"""
        try:
            symbol = data.get('symbol', 'UNKNOWN')
            direction = data.get('direction', 'UNKNOWN')
            signal_type = data.get('signal_type', 'UNKNOWN')
            pattern = data.get('pattern', 'UNKNOWN')
            entry = data.get('entry', 0)
            sl = data.get('stop_loss', 0)
            tp1 = data.get('tp1', 0)
            tp2 = data.get('tp2', 0)
            tp3 = data.get('tp3', 0)
            score = data.get('score', 0)
            mode = data.get('mode', 'UNKNOWN')
            session = data.get('session', 'UNKNOWN')
            timeframe = data.get('timeframe', '?')
            bubble_strength = data.get('bubble_strength', 0)
            exhaustion = data.get('exhaustion_detected', False)
            htf = data.get('htf_trend', 'UNKNOWN')
            
            dir_emoji = "🟢" if direction == "LONG" else "🔴"
            dir_text = "LONG / BUY" if direction == "LONG" else "SHORT / SELL"
            head_emoji = "🚀" if direction == "LONG" else "📉"
            
            type_emoji = "🔄" if signal_type == "REVERSAL" else "⚡" if signal_type == "QUICK_SCALP" else "➡️"
            
            if bubble_strength == 5:
                bubble_text = "⚡⚡⚡⚡⚡ LEVEL 5 (HOLY GRAIL!)"
            elif bubble_strength == 4:
                bubble_text = "⚡⚡⚡⚡ LEVEL 4 (EXTREME)"
            elif bubble_strength == 3:
                bubble_text = "⚡⚡⚡ LEVEL 3 (STRONG)"
            elif bubble_strength == 2:
                bubble_text = "⚡⚡ LEVEL 2"
            else:
                bubble_text = "⚡ LEVEL 1"
            
            exh_text = "⚠️ YES" if exhaustion else "None"
            
            if score >= 90:
                score_emoji = "🔥🔥🔥"
                quality = "EXCEPTIONAL"
            elif score >= 80:
                score_emoji = "🔥🔥"
                quality = "EXCELLENT"
            elif score >= 70:
                score_emoji = "🔥"
                quality = "GOOD"
            else:
                score_emoji = "✅"
                quality = "VALID"
            
            def fmt(price):
                if "XAU" in symbol or "XAG" in symbol:
                    return f"{price:.2f}"
                elif "BTC" in symbol or "ETH" in symbol:
                    return f"{price:.2f}"
                elif "JPY" in symbol:
                    return f"{price:.3f}"
                return f"{price:.5f}"
            
            risk = abs(entry - sl)
            rr1 = abs(tp1 - entry) / risk if risk > 0 else 0
            rr2 = abs(tp2 - entry) / risk if risk > 0 else 0
            rr3 = abs(tp3 - entry) / risk if risk > 0 else 0
            
            message = f"""
<b>⚡ QUANTUM FUSION</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{head_emoji} <b>{symbol} • {timeframe}</b>
{dir_emoji} <b>{dir_text}</b>
{type_emoji} <b>{signal_type}</b> • {pattern}

<b>📊 ENTRY</b>
├ Entry: <code>{fmt(entry)}</code>
├ SL: <code>{fmt(sl)}</code>
└ Risk: {risk:.2f}

<b>🎯 TARGETS</b>
1️⃣ <code>{fmt(tp1)}</code> ({rr1:.1f}R)
2️⃣ <code>{fmt(tp2)}</code> ({rr2:.1f}R)
3️⃣ <code>{fmt(tp3)}</code> ({rr3:.1f}R)

<b>🧠 ANALYSIS</b>
├ Score: {score_emoji} {score}/100 ({quality})
├ Session: {session}
└ HTF: {htf}

<b>💎 SMART MONEY</b>
├ Bubble: {bubble_text}
└ Exhaustion: {exh_text}

<b>📋 MANAGEMENT</b>
├ <i>TP1: Move SL to BE</i>
├ <i>TP2: Trail SL</i>
└ <i>TP3: Full target</i>

<i>{datetime.now().strftime('%Y-%m-%d %H:%M UTC')}</i>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#{symbol.replace('/', '')} #{direction}
"""
            return self.send_message(message)
        except Exception as e:
            logger.error(f"❌ Error: {e}")
            return False
    
    def send_tp1_hit(self, data: Dict):
        """TP1 hit"""
        try:
            symbol = data.get('symbol', 'UNKNOWN')
            direction = data.get('direction', 'UNKNOWN')
            price = data.get('price', 0)
            
            def fmt(p):
                if "XAU" in symbol or "XAG" in symbol or "BTC" in symbol or "ETH" in symbol:
                    return f"{p:.2f}"
                elif "JPY" in symbol:
                    return f"{p:.3f}"
                return f"{p:.5f}"
            
            message = f"""
<b>💰 TP1 HIT: {symbol}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Level:</b> TP1
<b>Direction:</b> {direction}
<b>Price:</b> <code>{fmt(price)}</code>
<b>Profit:</b> +1.5R

<b>⚡ ACTION:</b>
<b>→ MOVE SL TO BREAKEVEN NOW</b>

Lock in risk-free trade!

<i>Next: TP2 (+2.5R)</i>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#{symbol.replace('/', '')} #TP1
"""
            return self.send_message(message)
        except Exception as e:
            logger.error(f"❌ Error: {e}")
            return False
    
    def send_tp2_hit(self, data: Dict):
        """TP2 hit"""
        try:
            symbol = data.get('symbol', 'UNKNOWN')
            direction = data.get('direction', 'UNKNOWN')
            price = data.get('price', 0)
            
            def fmt(p):
                if "XAU" in symbol or "XAG" in symbol or "BTC" in symbol or "ETH" in symbol:
                    return f"{p:.2f}"
                elif "JPY" in symbol:
                    return f"{p:.3f}"
                return f"{p:.5f}"
            
            message = f"""
<b>💰💰 TP2 HIT: {symbol}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Level:</b> TP2
<b>Direction:</b> {direction}
<b>Price:</b> <code>{fmt(price)}</code>
<b>Profit:</b> +2.5R

<b>⚡ OPTIONS:</b>
→ Take 50% profit
→ Trail SL to TP1

<i>Next: TP3 (+4.0R)</i>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#{symbol.replace('/', '')} #TP2
"""
            return self.send_message(message)
        except Exception as e:
            logger.error(f"❌ Error: {e}")
            return False
    
    def send_tp3_hit(self, data: Dict):
        """TP3 hit"""
        try:
            symbol = data.get('symbol', 'UNKNOWN')
            direction = data.get('direction', 'UNKNOWN')
            price = data.get('price', 0)
            
            def fmt(p):
                if "XAU" in symbol or "XAG" in symbol or "BTC" in symbol or "ETH" in symbol:
                    return f"{p:.2f}"
                elif "JPY" in symbol:
                    return f"{p:.3f}"
                return f"{p:.5f}"
            
            message = f"""
<b>🚀🔥 TP3 - FULL TARGET!</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>{symbol} - PERFECT ✨</b>

<b>Level:</b> TP3 (FULL)
<b>Direction:</b> {direction}
<b>Price:</b> <code>{fmt(price)}</code>
<b>Profit:</b> <b>+4.0R</b> 🎉

<b>🏆 TRADE CLOSED</b>

Exceptional execution!

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#{symbol.replace('/', '')} #TP3 #Winner
"""
            return self.send_message(message)
        except Exception as e:
            logger.error(f"❌ Error: {e}")
            return False
    
    def send_sl_hit(self, data: Dict):
        """SL hit"""
        try:
            symbol = data.get('symbol', 'UNKNOWN')
            direction = data.get('direction', 'UNKNOWN')
            price = data.get('price', 0)
            
            def fmt(p):
                if "XAU" in symbol or "XAG" in symbol or "BTC" in symbol or "ETH" in symbol:
                    return f"{p:.2f}"
                elif "JPY" in symbol:
                    return f"{p:.3f}"
                return f"{p:.5f}"
            
            message = f"""
<b>❌ SL HIT: {symbol}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Direction:</b> {direction}
<b>Price:</b> <code>{fmt(price)}</code>
<b>Loss:</b> -1.0R

Controlled loss. Part of trading.

Next setup has high probability.

<i>Wait for next signal.</i>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#{symbol.replace('/', '')} #SL
"""
            return self.send_message(message)
        except Exception as e:
            logger.error(f"❌ Error: {e}")
            return False
    
    def send_daily_summary(self, stats: Dict):
        """Daily summary"""
        try:
            if not stats:
                msg = """<b>📊 DAILY SUMMARY</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
No trades today.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""
            else:
                if stats['closed_trades'] == 0:
                    msg = f"""<b>📊 DAILY SUMMARY</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Signals: {stats['total_signals']}
Active: {stats['active_trades']}
Trades still running.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""
                else:
                    wr = stats['win_rate']
                    emoji = "🔥" if wr >= 80 else "✅"
                    msg = f"""<b>📊 DAILY SUMMARY</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Signals: {stats['total_signals']}
Closed: {stats['closed_trades']}
Active: {stats['active_trades']}

{emoji} Win Rate: {wr:.1f}%
Total R: {stats['total_r']:+.1f}R
Avg R: {stats['avg_r']:+.2f}R

TP3: {stats['tp3_count']}
TP2: {stats['tp2_count']}
TP1: {stats['tp1_count']}
SL: {stats['sl_count']}

{datetime.now().strftime('%Y-%m-%d')}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#Daily #QuantumFusion"""
            return self.send_message(msg)
        except Exception as e:
            logger.error(f"❌ Error: {e}")
            return False
    
    def send_weekly_summary(self, stats: Dict):
        """Weekly summary"""
        try:
            if not stats:
                msg = """<b>📊 WEEKLY SUMMARY</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
No trades this week.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""
            else:
                if stats['closed_trades'] == 0:
                    msg = f"""<b>📊 WEEKLY SUMMARY</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Signals: {stats['total_signals']}
All active.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""
                else:
                    wr = stats['win_rate']
                    emoji = "🔥🔥🔥" if wr >= 85 else "🔥🔥" if wr >= 75 else "🔥"
                    
                    by_sym = ""
                    for sym, d in stats['by_symbol'].items():
                        by_sym += f"├ {sym}: {d['wins']}W/{d['losses']}L ({d['total_r']:+.1f}R)\n"
                    
                    msg = f"""<b>📊 WEEKLY SUMMARY</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Signals: {stats['total_signals']}
Closed: {stats['closed_trades']}
Active: {stats['active_trades']}

{emoji} Win Rate: {wr:.1f}%
Total R: {stats['total_r']:+.1f}R
Avg R: {stats['avg_r']:+.2f}R

TP3: {stats['tp3_count']}
TP2: {stats['tp2_count']}
TP1: {stats['tp1_count']}
SL: {stats['sl_count']}

<b>By Asset:</b>
{by_sym}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#Weekly #QuantumFusion"""
            return self.send_message(msg)
        except Exception as e:
            logger.error(f"❌ Error: {e}")
            return False

class TradingBot:
    """Bot with fixed TP/SL tracking"""
    
    def __init__(self):
        self.telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        
        if not self.telegram_token or not self.chat_id:
            logger.warning("⚠️ Credentials not set!")
        else:
            self.telegram = TelegramNotifier(self.telegram_token, self.chat_id)
            logger.info("✅ Telegram initialized")
        
        self.tracker = TradeTracker()
        self.setup_scheduler()
    
    def setup_scheduler(self):
        """Setup summaries"""
        self.scheduler = BackgroundScheduler()
        self.scheduler.add_job(self.send_daily_summary, CronTrigger(hour=23, minute=59), id='daily')
        self.scheduler.add_job(self.send_weekly_summary, CronTrigger(day_of_week='sun', hour=23, minute=59), id='weekly')
        self.scheduler.start()
        logger.info("⏰ Scheduler started")
    
    def send_daily_summary(self):
        """Daily"""
        stats = self.tracker.get_daily_stats()
        if self.telegram:
            self.telegram.send_daily_summary(stats)
        self.tracker.reset_daily()
    
    def send_weekly_summary(self):
        """Weekly"""
        stats = self.tracker.get_weekly_stats()
        if self.telegram:
            self.telegram.send_weekly_summary(stats)
        self.tracker.reset_weekly()
    
    def process_webhook(self, data: Dict) -> bool:
        """Process webhook - FIXED: Only send each TP/SL once"""
        try:
            logger.info(f"📥 Webhook: {data}")
            
            event = data.get('event', 'UNKNOWN')
            
            if event == 'NEW_TRADE':
                logger.info("🚀 NEW_TRADE")
                
                trade = Trade(
                    id=data.get('id', 'unknown'),
                    symbol=data.get('symbol', 'UNKNOWN'),
                    direction=data.get('direction', 'UNKNOWN'),
                    signal_type=data.get('signal_type', 'UNKNOWN'),
                    pattern=data.get('pattern', 'UNKNOWN'),
                    entry=float(data.get('entry', 0)),
                    stop_loss=float(data.get('stop_loss', 0)),
                    tp1=float(data.get('tp1', 0)),
                    tp2=float(data.get('tp2', 0)),
                    tp3=float(data.get('tp3', 0)),
                    score=int(data.get('score', 0)),
                    mode=data.get('mode', 'UNKNOWN'),
                    session=data.get('session', 'UNKNOWN'),
                    timeframe=data.get('timeframe', 'UNKNOWN'),
                    bubble_strength=int(data.get('bubble_strength', 0)),
                    exhaustion_detected=data.get('exhaustion_detected', False),
                    htf_trend=data.get('htf_trend', 'UNKNOWN'),
                    strict_mode=data.get('strict_mode', False),
                    timestamp=datetime.now().isoformat()
                )
                
                self.tracker.add_trade(trade)
                
                if self.telegram:
                    return self.telegram.send_elite_signal(data)
                return False
            
            elif event == 'TP_HIT':
                logger.info("💰 TP_HIT")
                level = data.get('level', 'UNKNOWN')
                trade_id = data.get('id', 'unknown')
                price = float(data.get('price', 0))
                
                # FIXED: Check if already sent
                should_send = False
                if level == "TP1":
                    should_send = self.tracker.should_send_tp1(trade_id)
                elif level == "TP2":
                    should_send = self.tracker.should_send_tp2(trade_id)
                elif level == "TP3":
                    should_send = self.tracker.should_send_tp3(trade_id)
                
                if not should_send:
                    return True  # Already sent, skip
                
                self.tracker.update_trade_tp(trade_id, level, price)
                
                if self.telegram:
                    if level == "TP1":
                        return self.telegram.send_tp1_hit(data)
                    elif level == "TP2":
                        return self.telegram.send_tp2_hit(data)
                    elif level == "TP3":
                        return self.telegram.send_tp3_hit(data)
                return False
            
            elif event == 'SL_HIT':
                logger.info("❌ SL_HIT")
                trade_id = data.get('id', 'unknown')
                
                # FIXED: Check if already sent
                if not self.tracker.should_send_sl(trade_id):
                    return True  # Already sent, skip
                
                self.tracker.update_trade_sl(trade_id)
                
                if self.telegram:
                    return self.telegram.send_sl_hit(data)
                return False
            
            else:
                logger.warning(f"⚠️ Unknown: {event}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

bot = TradingBot()

@app.route('/')
def home():
    return "⚡ Quantum Fusion Bot 🟢", 200

@app.route('/webhook', methods=['POST'])
def webhook():
    if request.method == 'POST':
        logger.info(f"📨 Payload: {request.data}")
        
        try:
            data = request.get_json(force=True, silent=True)
            if not data and request.data:
                data = json.loads(request.data.decode('utf-8'))
        except Exception as e:
            logger.error(f"❌ Parse error: {e}")
            return jsonify({"error": "Invalid JSON"}), 400
            
        if not data:
            return jsonify({"error": "No data"}), 400
        
        success = bot.process_webhook(data)
        
        if success:
            logger.info("✅ Success")
            return jsonify({"status": "success"}), 200
        else:
            logger.warning("⚠️ Failed")
            return jsonify({"status": "failed"}), 200
            
    return jsonify({"error": "Method not allowed"}), 405

@app.route('/stats/daily', methods=['GET'])
def get_daily():
    stats = bot.tracker.get_daily_stats()
    return jsonify(stats if stats else {"message": "No trades"}), 200

@app.route('/stats/weekly', methods=['GET'])
def get_weekly():
    stats = bot.tracker.get_weekly_stats()
    return jsonify(stats if stats else {"message": "No trades"}), 200

def main():
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"🚀 Starting bot on port {port}")
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    main()
