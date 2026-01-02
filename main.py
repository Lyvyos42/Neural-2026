"""
⚡ Neural Quantum Ultimate Trading Bot
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Automated trading bot with Telegram notifications
Receives webhooks from TradingView Pine Script
Tracks trades and sends real-time updates
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
from apscheduler.triggers.cron import CronTrigger

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('trading_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

@dataclass
class Trade:
    """Trade data structure"""
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
    quantum_mode: bool
    zero_lag: bool
    timestamp: str
    
    # Trade state
    tp1_hit: bool = False
    tp2_hit: bool = False
    tp3_hit: bool = False
    sl_hit: bool = False
    closed: bool = False
    final_result: str = "ACTIVE"
    profit_r: float = 0.0
    
    # Notification tracking (prevent duplicates)
    tp1_notified: bool = False
    tp2_notified: bool = False
    tp3_notified: bool = False
    sl_notified: bool = False
    
    def to_dict(self):
        return asdict(self)

class TradeTracker:
    """Track all trades with duplicate prevention"""
    
    def __init__(self):
        self.active_trades: Dict[str, Trade] = {}
        self.closed_trades: List[Trade] = []
        self.daily_trades: List[Trade] = []
        self.weekly_trades: List[Trade] = []
        
        # Track which trade IDs have been notified for each TP/SL
        self.tp1_sent: Set[str] = set()
        self.tp2_sent: Set[str] = set()
        self.tp3_sent: Set[str] = set()
        self.sl_sent: Set[str] = set()
    
    def add_trade(self, trade: Trade):
        """Add new trade"""
        self.active_trades[trade.id] = trade
        self.daily_trades.append(trade)
        self.weekly_trades.append(trade)
        logger.info(f"📊 New trade added: {trade.id} | {trade.symbol} {trade.direction}")
    
    def should_send_tp1(self, trade_id: str) -> bool:
        """Check if TP1 notification should be sent"""
        if trade_id in self.tp1_sent:
            logger.info(f"⏭️  TP1 already sent for {trade_id}, skipping")
            return False
        self.tp1_sent.add(trade_id)
        return True
    
    def should_send_tp2(self, trade_id: str) -> bool:
        """Check if TP2 notification should be sent"""
        if trade_id in self.tp2_sent:
            logger.info(f"⏭️  TP2 already sent for {trade_id}, skipping")
            return False
        self.tp2_sent.add(trade_id)
        return True
    
    def should_send_tp3(self, trade_id: str) -> bool:
        """Check if TP3 notification should be sent"""
        if trade_id in self.tp3_sent:
            logger.info(f"⏭️  TP3 already sent for {trade_id}, skipping")
            return False
        self.tp3_sent.add(trade_id)
        return True
    
    def should_send_sl(self, trade_id: str) -> bool:
        """Check if SL notification should be sent"""
        if trade_id in self.sl_sent:
            logger.info(f"⏭️  SL already sent for {trade_id}, skipping")
            return False
        self.sl_sent.add(trade_id)
        return True
    
    def update_trade_tp(self, trade_id: str, level: str, price: float):
        """Update trade when TP is hit"""
        if trade_id not in self.active_trades:
            logger.warning(f"⚠️  Trade {trade_id} not found in active trades")
            return
            
        trade = self.active_trades[trade_id]
        
        if level == "TP1" and not trade.tp1_notified:
            trade.tp1_hit = True
            trade.tp1_notified = True
            trade.profit_r = 1.5
            logger.info(f"✅ {trade_id}: TP1 hit at {price}")
            
        elif level == "TP2" and not trade.tp2_notified:
            trade.tp2_hit = True
            trade.tp2_notified = True
            trade.profit_r = 2.5
            logger.info(f"✅ {trade_id}: TP2 hit at {price}")
            
        elif level == "TP3" and not trade.tp3_notified:
            trade.tp3_hit = True
            trade.tp3_notified = True
            trade.final_result = "TP3"
            trade.profit_r = 4.0
            trade.closed = True
            self.close_trade(trade_id)
            logger.info(f"🎉 {trade_id}: TP3 hit at {price} - FULL TARGET!")
    
    def update_trade_sl(self, trade_id: str, price: float):
        """Update trade when SL is hit"""
        if trade_id not in self.active_trades:
            logger.warning(f"⚠️  Trade {trade_id} not found in active trades")
            return
            
        trade = self.active_trades[trade_id]
        
        if not trade.sl_notified:
            trade.sl_hit = True
            trade.sl_notified = True
            trade.final_result = "SL"
            trade.profit_r = -1.0
            trade.closed = True
            self.close_trade(trade_id)
            logger.info(f"❌ {trade_id}: SL hit at {price}")
    
    def close_trade(self, trade_id: str):
        """Close trade and move to history"""
        if trade_id in self.active_trades:
            trade = self.active_trades.pop(trade_id)
            self.closed_trades.append(trade)
            logger.info(f"🔒 Trade closed: {trade_id}")
    
    def get_daily_stats(self) -> Optional[Dict]:
        """Calculate daily statistics"""
        if not self.daily_trades:
            return None
        
        total = len(self.daily_trades)
        closed = [t for t in self.daily_trades if t.closed]
        
        if not closed:
            return {
                "total_signals": total,
                "closed_trades": 0,
                "active_trades": total
            }
        
        tp3 = len([t for t in closed if t.final_result == "TP3"])
        tp2 = len([t for t in closed if t.final_result == "TP2"])
        tp1 = len([t for t in closed if t.final_result == "TP1"])
        sl = len([t for t in closed if t.final_result == "SL"])
        
        wins = tp3 + tp2 + tp1
        win_rate = (wins / len(closed) * 100) if closed else 0
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
            "win_rate": win_rate,
            "total_r": total_r,
            "avg_r": avg_r
        }
    
    def get_weekly_stats(self) -> Optional[Dict]:
        """Calculate weekly statistics"""
        if not self.weekly_trades:
            return None
        
        total = len(self.weekly_trades)
        closed = [t for t in self.weekly_trades if t.closed]
        
        if not closed:
            return {
                "total_signals": total,
                "closed_trades": 0,
                "active_trades": total
            }
        
        tp3 = len([t for t in closed if t.final_result == "TP3"])
        tp2 = len([t for t in closed if t.final_result == "TP2"])
        tp1 = len([t for t in closed if t.final_result == "TP1"])
        sl = len([t for t in closed if t.final_result == "SL"])
        
        wins = tp3 + tp2 + tp1
        win_rate = (wins / len(closed) * 100) if closed else 0
        total_r = sum([t.profit_r for t in closed])
        avg_r = total_r / len(closed) if closed else 0
        
        # Stats by symbol
        by_symbol = {}
        for t in closed:
            if t.symbol not in by_symbol:
                by_symbol[t.symbol] = {"wins": 0, "losses": 0, "total_r": 0}
            
            if t.final_result in ["TP1", "TP2", "TP3"]:
                by_symbol[t.symbol]["wins"] += 1
            else:
                by_symbol[t.symbol]["losses"] += 1
            
            by_symbol[t.symbol]["total_r"] += t.profit_r
        
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
            "win_rate": win_rate,
            "total_r": total_r,
            "avg_r": avg_r,
            "by_symbol": by_symbol
        }
    
    def reset_daily(self):
        """Reset daily statistics"""
        self.daily_trades = []
        logger.info("🔄 Daily statistics reset")
    
    def reset_weekly(self):
        """Reset weekly statistics"""
        self.weekly_trades = []
        self.tp1_sent.clear()
        self.tp2_sent.clear()
        self.tp3_sent.clear()
        self.sl_sent.clear()
        logger.info("🔄 Weekly statistics reset")

class TelegramNotifier:
    """Send Telegram notifications with retry logic and message queue"""
    
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}/"
        self.failed_messages = []  # Queue for failed messages
        logger.info("✅ Telegram notifier initialized with retry logic")
    
    def send_message(self, text: str, parse_mode: str = "HTML", max_retries: int = 3) -> bool:
        """Send message to Telegram with retry logic"""
        for attempt in range(max_retries):
            try:
                url = f"{self.base_url}sendMessage"
                payload = {
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": parse_mode
                }
                
                response = requests.post(url, json=payload, timeout=5)
                
                if response.status_code == 200:
                    logger.info(f"✅ Telegram message sent successfully (attempt {attempt + 1}/{max_retries})")
                    return True
                elif response.status_code == 429:
                    # Rate limit hit
                    retry_after = int(response.headers.get('Retry-After', 2))
                    logger.warning(f"⚠️ Rate limit hit, waiting {retry_after}s before retry")
                    time.sleep(retry_after)
                    continue
                else:
                    logger.error(f"❌ Telegram API error (attempt {attempt + 1}/{max_retries}): {response.status_code} - {response.text}")
                    if attempt < max_retries - 1:
                        time.sleep(2)  # Wait before retry
                        continue
                    return False
                    
            except requests.exceptions.Timeout:
                logger.error(f"⏱️ Timeout (attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                return False
            except requests.exceptions.ConnectionError:
                logger.error(f"🔌 Connection error (attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                return False
            except Exception as e:
                logger.error(f"❌ Error sending Telegram message (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                return False
        
        logger.error(f"❌ Failed to send message after {max_retries} attempts")
        return False
    
    def log_payload(self, data: Dict, event_type: str):
        """Log webhook payload for debugging"""
        try:
            log_file = "telegram_payloads.log"
            timestamp = datetime.now().isoformat()
            log_entry = f"\n{'='*60}\n"
            log_entry += f"Timestamp: {timestamp}\n"
            log_entry += f"Event Type: {event_type}\n"
            log_entry += f"Payload: {json.dumps(data, indent=2)}\n"
            log_entry += f"{'='*60}\n"
            
            with open(log_file, 'a') as f:
                f.write(log_entry)
            
            logger.info(f"📝 Payload logged to {log_file}")
        except Exception as e:
            logger.error(f"❌ Error logging payload: {e}")
    
    def retry_failed_messages(self):
        """Retry sending failed messages"""
        if not self.failed_messages:
            return
        
        logger.info(f"🔄 Retrying {len(self.failed_messages)} failed messages")
        
        retry_queue = self.failed_messages.copy()
        self.failed_messages.clear()
        
        for message_data in retry_queue:
            message_text = message_data.get('text', '')
            event_type = message_data.get('type', 'UNKNOWN')
            
            if self.send_message(message_text):
                logger.info(f"✅ Successfully sent queued message: {event_type}")
            else:
                logger.error(f"❌ Failed to send queued message: {event_type}")
                self.failed_messages.append(message_data)  # Re-queue if still failing
    
    def format_price(self, price: float, symbol: str) -> str:
        """Format price based on symbol"""
        if "XAU" in symbol or "XAG" in symbol:
            return f"{price:.2f}"
        elif "BTC" in symbol or "ETH" in symbol:
            return f"{price:.2f}"
        elif "JPY" in symbol:
            return f"{price:.3f}"
        else:
            return f"{price:.5f}"
    
    def send_new_trade_signal(self, data: Dict) -> bool:
        """Send new trade signal notification with gold-specific formatting"""
        try:
            # Log payload for debugging
            self.log_payload(data, "NEW_TRADE")
            
            symbol = data.get('symbol', 'UNKNOWN')
            direction = data.get('direction', 'UNKNOWN')
            signal_type = data.get('signal_type', 'UNKNOWN')
            pattern = data.get('pattern', 'UNKNOWN')
            entry = float(data.get('entry', 0))
            sl = float(data.get('stop_loss', 0))
            tp1 = float(data.get('tp1', 0))
            tp2 = float(data.get('tp2', 0))
            tp3 = float(data.get('tp3', 0))
            score = int(data.get('score', 0))
            timeframe = data.get('timeframe', '?')
            session = data.get('session', 'UNKNOWN')
            bubble_strength = int(data.get('bubble_strength', 0))
            
            # GOLD-SPECIFIC DATA
            trading_mode = data.get('trading_mode', 'UNKNOWN')
            is_scalp = data.get('is_scalp', False)
            is_swing = data.get('is_swing', False)
            gold_optimized = data.get('gold_optimized', False)
            scalp_pips = data.get('scalp_pips', '')
            bubble_auto = data.get('bubble_auto_entry', False)
            
            # Direction formatting
            dir_emoji = "🟢" if direction == "LONG" else "🔴"
            dir_text = "LONG / BUY" if direction == "LONG" else "SHORT / SELL"
            head_emoji = "🚀" if direction == "LONG" else "📉"
            
            # Signal type emoji and text
            if signal_type == "BUBBLE_AUTO":
                type_emoji = "🥇💎"
                type_text = "BUBBLE AUTO-ENTRY"
            elif signal_type == "LONDON_KILL":
                type_emoji = "🔪"
                type_text = "LONDON KILLZONE"
            elif signal_type == "ASIAN_BREAK":
                type_emoji = "🌅"
                type_text = "ASIAN BREAKOUT"
            elif signal_type == "NY_OPEN":
                type_emoji = "🗽"
                type_text = "NY OPEN VOLATILITY"
            elif signal_type == "PDH_PDL_SWEEP":
                type_emoji = "💧"
                type_text = "PDH/PDL SWEEP"
            elif signal_type == "FIB_BOUNCE":
                type_emoji = "📐"
                type_text = "FIBONACCI BOUNCE"
            elif signal_type == "LIQ_GRAB":
                type_emoji = "🎣"
                type_text = "LIQUIDITY GRAB"
            else:
                type_emoji = "⚡"
                type_text = signal_type
            
            # TRADING MODE BADGE - VERY PROMINENT
            if is_scalp:
                mode_badge = "🎯 SCALP"
                mode_desc = "Focus: 1m, 3m, 5m timeframe entries"
                mode_color = "SCALPING"
            elif is_swing:
                mode_badge = "📈 SWING"
                mode_desc = "Focus: 15m, 1h timeframe entries"
                mode_color = "SWING TRADING"
            else:
                mode_badge = "📊 TRADE"
                mode_desc = "Standard entry"
                mode_color = "TRADING"
            
            # Session emoji
            if session == "LONDON_KILL":
                session_emoji = "🔪🇬🇧"
                session_text = "LONDON KILLZONE"
            elif session == "NY_OPEN":
                session_emoji = "🗽🇺🇸"
                session_text = "NY OPEN"
            elif session == "OVERLAP":
                session_emoji = "⚡🌍"
                session_text = "OVERLAP"
            elif session == "LONDON":
                session_emoji = "🇬🇧"
                session_text = "LONDON"
            elif session == "NY":
                session_emoji = "🇺🇸"
                session_text = "NY"
            else:
                session_emoji = "🌙"
                session_text = session
            
            # Bubble formatting
            if bubble_strength == 5:
                bubble_text = "🥇🥇🥇🥇🥇 LEVEL 5 (HOLY GRAIL!)"
            elif bubble_strength == 4:
                bubble_text = "🥇🥇🥇🥇 LEVEL 4 (EXTREME)"
            elif bubble_strength == 3:
                bubble_text = "🥇🥇🥇 LEVEL 3 (STRONG)"
            elif bubble_strength == 2:
                bubble_text = "🥇🥇 LEVEL 2"
            elif bubble_strength >= 1:
                bubble_text = "🥇 LEVEL 1"
            else:
                bubble_text = "None"
            
            # Score quality
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
            
            # Calculate pips profit
            risk = abs(entry - sl)
            tp1_pips_profit = int(abs(tp1 - entry) / 0.01)
            tp2_pips_profit = int(abs(tp2 - entry) / 0.01)
            tp3_pips_profit = int(abs(tp3 - entry) / 0.01)
            
            # Build message with PROMINENT mode display
            message = f"""
<b>🥇 GOLD QUANTUM MASTER</b>
<b>{mode_badge} • {mode_color}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{head_emoji} <b>XAUUSD • {timeframe}</b>
{dir_emoji} <b>{dir_text}</b>
{type_emoji} <b>{type_text}</b>

<b>⏰ {mode_desc}</b>

<b>📊 ENTRY</b>
├ Entry: <code>{self.format_price(entry, symbol)}</code>
├ SL: <code>{self.format_price(sl, symbol)}</code>
└ Risk: {risk:.2f} ({int(risk/0.01)} pips)

<b>🎯 TARGETS - {scalp_pips if scalp_pips else 'OPTIMIZED'} PIPS</b>
1️⃣ <code>{self.format_price(tp1, symbol)}</code> (+{tp1_pips_profit} pips)
2️⃣ <code>{self.format_price(tp2, symbol)}</code> (+{tp2_pips_profit} pips)
3️⃣ <code>{self.format_price(tp3, symbol)}</code> (+{tp3_pips_profit} pips) 🏆

<b>🧠 ANALYSIS</b>
├ Score: {score_emoji} {score}/100 ({quality})
├ Pattern: {pattern}
├ Session: {session_emoji} {session_text}
└ Timeframe: {timeframe}

<b>💎 SMART MONEY</b>
└ Bubble: {bubble_text}

<b>📋 TRADE MANAGEMENT</b>
├ <i>TP1: Move SL to breakeven</i>
├ <i>TP2: Take 50% profit, trail SL</i>
└ <i>TP3: Close all, bank profits!</i>

<i>{datetime.now().strftime('%Y-%m-%d %H:%M UTC')}</i>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#XAUUSD #{direction} #{mode_color.replace(' ', '')}
"""
            
            # Add special notice for high-quality setups
            if bubble_auto and bubble_strength >= 4:
                message += "\n<b>⚠️ HIGH-QUALITY BUBBLE!</b>\n<i>Institutional money moving NOW!</i>\n"
            
            if session in ["LONDON_KILL", "NY_OPEN"]:
                message += f"\n<b>🔥 PREMIUM SESSION!</b>\n<i>{session_text} - Highest win rate!</i>\n"
            
            # Try to send
            success = self.send_message(message)
            
            # If failed, queue for retry
            if not success:
                logger.warning("⚠️ Message failed, adding to retry queue")
                self.failed_messages.append({
                    'text': message,
                    'type': 'NEW_TRADE',
                    'data': data
                })
            
            return success
            
        except Exception as e:
            logger.error(f"❌ Error sending new trade signal: {e}")
            return False
    
    def send_tp_hit(self, data: Dict, level: int) -> bool:
        """Send TP hit notification"""
        try:
            # Log payload
            self.log_payload(data, f"TP{level}_HIT")
            
            symbol = data.get('symbol', 'UNKNOWN')
            direction = data.get('direction', 'UNKNOWN')
            price = float(data.get('price', 0))
            
            if level == 1:
                profit_r = 1.5
                action = "<b>→ MOVE SL TO BREAKEVEN NOW</b>"
                next_target = "Next: TP2 (+2.5R)"
                title = f"💰 TP1 HIT: {symbol}"
            elif level == 2:
                profit_r = 2.5
                action = "→ Take 50% profit\n→ Trail SL to TP1"
                next_target = "Next: TP3 (+4.0R)"
                title = f"💰💰 TP2 HIT: {symbol}"
            else:  # level 3
                profit_r = 4.0
                action = "<b>🏆 TRADE CLOSED - FULL TARGET!</b>"
                next_target = "Exceptional execution!"
                title = f"🚀🔥 TP3 - FULL TARGET!"
            
            message = f"""
<b>{title}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Level:</b> TP{level}
<b>Direction:</b> {direction}
<b>Price:</b> <code>{self.format_price(price, symbol)}</code>
<b>Profit:</b> +{profit_r}R

<b>⚡ ACTION:</b>
{action}

{next_target}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#{symbol.replace('/', '')} #TP{level}
"""
            
            success = self.send_message(message)
            
            # Queue if failed
            if not success:
                logger.warning(f"⚠️ TP{level} message failed, adding to retry queue")
                self.failed_messages.append({
                    'text': message,
                    'type': f'TP{level}_HIT',
                    'data': data
                })
            
            return success
            
        except Exception as e:
            logger.error(f"❌ Error sending TP hit notification: {e}")
            return False
    
    def send_sl_hit(self, data: Dict) -> bool:
        """Send SL hit notification"""
        try:
            # Log payload
            self.log_payload(data, "SL_HIT")
            
            symbol = data.get('symbol', 'UNKNOWN')
            direction = data.get('direction', 'UNKNOWN')
            price = float(data.get('price', 0))
            
            message = f"""
<b>❌ SL HIT: {symbol}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Direction:</b> {direction}
<b>Price:</b> <code>{self.format_price(price, symbol)}</code>
<b>Loss:</b> -1.0R

Controlled loss. Part of trading.

Next setup has high probability.

<i>Wait for next signal.</i>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#{symbol.replace('/', '')} #SL
"""
            
            success = self.send_message(message)
            
            # Queue if failed
            if not success:
                logger.warning("⚠️ SL message failed, adding to retry queue")
                self.failed_messages.append({
                    'text': message,
                    'type': 'SL_HIT',
                    'data': data
                })
            
            return success
            
        except Exception as e:
            logger.error(f"❌ Error sending SL hit notification: {e}")
            return False
    
    def send_daily_summary(self, stats: Optional[Dict]) -> bool:
        """Send daily summary"""
        try:
            if not stats:
                msg = """<b>📊 DAILY SUMMARY</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
No trades today.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""
            elif stats['closed_trades'] == 0:
                msg = f"""<b>📊 DAILY SUMMARY</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Signals: {stats['total_signals']}
Active: {stats['active_trades']}

All trades still running.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""
            else:
                wr = stats['win_rate']
                emoji = "🔥🔥" if wr >= 90 else "🔥" if wr >= 80 else "✅"
                
                msg = f"""<b>📊 DAILY SUMMARY</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Signals: {stats['total_signals']}
Closed: {stats['closed_trades']}
Active: {stats['active_trades']}

{emoji} Win Rate: {wr:.1f}%
Total R: {stats['total_r']:+.1f}R
Avg R: {stats['avg_r']:+.2f}R

TP3: {stats['tp3_count']} 🎯
TP2: {stats['tp2_count']} 💰
TP1: {stats['tp1_count']} ✅
SL: {stats['sl_count']} ❌

{datetime.now().strftime('%Y-%m-%d')}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#Daily #Quantum
"""
            return self.send_message(msg)
            
        except Exception as e:
            logger.error(f"❌ Error sending daily summary: {e}")
            return False
    
    def send_weekly_summary(self, stats: Optional[Dict]) -> bool:
        """Send weekly summary"""
        try:
            if not stats:
                msg = """<b>📊 WEEKLY SUMMARY</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
No trades this week.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""
            elif stats['closed_trades'] == 0:
                msg = f"""<b>📊 WEEKLY SUMMARY</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Signals: {stats['total_signals']}

All trades still active.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""
            else:
                wr = stats['win_rate']
                emoji = "🔥🔥🔥" if wr >= 90 else "🔥🔥" if wr >= 85 else "🔥" if wr >= 80 else "✅"
                
                by_sym_text = ""
                for sym, data in stats['by_symbol'].items():
                    by_sym_text += f"├ {sym}: {data['wins']}W/{data['losses']}L ({data['total_r']:+.1f}R)\n"
                
                msg = f"""<b>📊 WEEKLY SUMMARY</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Signals: {stats['total_signals']}
Closed: {stats['closed_trades']}
Active: {stats['active_trades']}

{emoji} Win Rate: {wr:.1f}%
Total R: {stats['total_r']:+.1f}R
Avg R: {stats['avg_r']:+.2f}R

TP3: {stats['tp3_count']} 🎯
TP2: {stats['tp2_count']} 💰
TP1: {stats['tp1_count']} ✅
SL: {stats['sl_count']} ❌

<b>By Asset:</b>
{by_sym_text}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#Weekly #Quantum
"""
            return self.send_message(msg)
            
        except Exception as e:
            logger.error(f"❌ Error sending weekly summary: {e}")
            return False

class TradingBot:
    """Main trading bot"""
    
    def __init__(self):
        self.telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        
        if not self.telegram_token or not self.chat_id:
            logger.warning("⚠️  Telegram credentials not set! Bot will run without notifications.")
            self.telegram = None
        else:
            self.telegram = TelegramNotifier(self.telegram_token, self.chat_id)
            logger.info("✅ Telegram notifications enabled")
        
        self.tracker = TradeTracker()
        self.setup_scheduler()
        logger.info("🚀 Trading bot initialized")
    
    def setup_scheduler(self):
        """Setup automated summary scheduler and message retry"""
        self.scheduler = BackgroundScheduler()
        
        # Daily summary at 23:59
        self.scheduler.add_job(
            self.send_daily_summary,
            CronTrigger(hour=23, minute=59),
            id='daily_summary'
        )
        
        # Weekly summary on Sunday at 23:59
        self.scheduler.add_job(
            self.send_weekly_summary,
            CronTrigger(day_of_week='sun', hour=23, minute=59),
            id='weekly_summary'
        )
        
        # Retry failed messages every 5 minutes
        self.scheduler.add_job(
            self.retry_failed_messages,
            'interval',
            minutes=5,
            id='retry_failed_messages'
        )
        
        self.scheduler.start()
        logger.info("⏰ Summary scheduler started with message retry every 5 minutes")
    
    def retry_failed_messages(self):
        """Retry sending queued messages"""
        if self.telegram and hasattr(self.telegram, 'failed_messages'):
            if self.telegram.failed_messages:
                logger.info(f"🔄 Retrying {len(self.telegram.failed_messages)} failed messages")
                self.telegram.retry_failed_messages()
        else:
            logger.debug("No telegram instance or no failed messages to retry")
    
    def send_daily_summary(self):
        """Send daily summary"""
        logger.info("📊 Sending daily summary")
        stats = self.tracker.get_daily_stats()
        if self.telegram:
            self.telegram.send_daily_summary(stats)
        self.tracker.reset_daily()
    
    def send_weekly_summary(self):
        """Send weekly summary"""
        logger.info("📊 Sending weekly summary")
        stats = self.tracker.get_weekly_stats()
        if self.telegram:
            self.telegram.send_weekly_summary(stats)
        self.tracker.reset_weekly()
    
    def process_webhook(self, data: Dict) -> bool:
        """Process incoming webhook"""
        try:
            event = data.get('event', 'UNKNOWN')
            logger.info(f"📥 Processing webhook: {event}")
            
            if event == 'NEW_TRADE':
                return self.handle_new_trade(data)
            elif event == 'TP_HIT':
                return self.handle_tp_hit(data)
            elif event == 'SL_HIT':
                return self.handle_sl_hit(data)
            else:
                logger.warning(f"⚠️  Unknown event type: {event}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error processing webhook: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def handle_new_trade(self, data: Dict) -> bool:
        """Handle new trade signal"""
        try:
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
                quantum_mode=data.get('quantum_mode', True),
                zero_lag=data.get('zero_lag', True),
                timestamp=datetime.now().isoformat()
            )
            
            self.tracker.add_trade(trade)
            
            if self.telegram:
                return self.telegram.send_new_trade_signal(data)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error handling new trade: {e}")
            return False
    
    def handle_tp_hit(self, data: Dict) -> bool:
        """Handle TP hit"""
        try:
            trade_id = data.get('id', 'unknown')
            level = data.get('level', 'UNKNOWN')
            price = float(data.get('price', 0))
            
            # Check if already sent
            if level == "TP1":
                if not self.tracker.should_send_tp1(trade_id):
                    return True
                tp_level = 1
            elif level == "TP2":
                if not self.tracker.should_send_tp2(trade_id):
                    return True
                tp_level = 2
            elif level == "TP3":
                if not self.tracker.should_send_tp3(trade_id):
                    return True
                tp_level = 3
            else:
                logger.warning(f"⚠️  Unknown TP level: {level}")
                return False
            
            # Update trade
            self.tracker.update_trade_tp(trade_id, level, price)
            
            # Send notification
            if self.telegram:
                return self.telegram.send_tp_hit(data, tp_level)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error handling TP hit: {e}")
            return False
    
    def handle_sl_hit(self, data: Dict) -> bool:
        """Handle SL hit"""
        try:
            trade_id = data.get('id', 'unknown')
            price = float(data.get('price', 0))
            
            # Check if already sent
            if not self.tracker.should_send_sl(trade_id):
                return True
            
            # Update trade
            self.tracker.update_trade_sl(trade_id, price)
            
            # Send notification
            if self.telegram:
                return self.telegram.send_sl_hit(data)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error handling SL hit: {e}")
            return False

# Initialize bot
bot = TradingBot()

# Flask routes
@app.route('/')
def home():
    """Health check endpoint"""
    return jsonify({
        "status": "online",
        "bot": "Neural Quantum Ultimate Trading Bot",
        "version": "2.0",
        "active_trades": len(bot.tracker.active_trades)
    }), 200

@app.route('/webhook', methods=['POST'])
def webhook():
    """Webhook endpoint for TradingView alerts"""
    if request.method != 'POST':
        return jsonify({"error": "Method not allowed"}), 405
    
    logger.info(f"📨 Received webhook payload: {request.data}")
    
    try:
        # Try to parse JSON
        data = request.get_json(force=True, silent=True)
        if not data and request.data:
            data = json.loads(request.data.decode('utf-8'))
    except Exception as e:
        logger.error(f"❌ JSON parse error: {e}")
        return jsonify({"error": "Invalid JSON"}), 400
    
    if not data:
        logger.error("❌ No data received")
        return jsonify({"error": "No data"}), 400
    
    # Process webhook
    success = bot.process_webhook(data)
    
    if success:
        logger.info("✅ Webhook processed successfully")
        return jsonify({"status": "success"}), 200
    else:
        logger.warning("⚠️  Webhook processing failed")
        return jsonify({"status": "failed"}), 200

@app.route('/stats/daily', methods=['GET'])
def get_daily_stats():
    """Get daily statistics"""
    stats = bot.tracker.get_daily_stats()
    return jsonify(stats if stats else {"message": "No trades today"}), 200

@app.route('/stats/weekly', methods=['GET'])
def get_weekly_stats():
    """Get weekly statistics"""
    stats = bot.tracker.get_weekly_stats()
    return jsonify(stats if stats else {"message": "No trades this week"}), 200

@app.route('/trades/active', methods=['GET'])
def get_active_trades():
    """Get active trades"""
    trades = [t.to_dict() for t in bot.tracker.active_trades.values()]
    return jsonify({
        "count": len(trades),
        "trades": trades
    }), 200

@app.route('/trades/history', methods=['GET'])
def get_trade_history():
    """Get trade history"""
    trades = [t.to_dict() for t in bot.tracker.closed_trades]
    return jsonify({
        "count": len(trades),
        "trades": trades
    }), 200

def main():
    """Main entry point"""
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"🚀 Starting Neural Quantum Ultimate Bot on port {port}")
    logger.info(f"🌐 Webhook URL: http://localhost:{port}/webhook")
    
    app.run(host='0.0.0.0', port=port, debug=False)

if __name__ == "__main__":
    main()
