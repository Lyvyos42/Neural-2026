"""
🤖 PROFESSIONAL TRADING ALERTS BOT - Optimized & Production-Ready
Handles alerts from Gold Quantum Master Pro & Smart Money Forex Pro Enhanced
Author: Senior Python Developer
Version: 2.0.0
"""

import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum
import asyncio
from functools import lru_cache
import telegram
from telegram import Bot, ParseMode
from telegram.error import TelegramError, RetryAfter
import time

# ═══════════════════════════════════════════════════════════════════════════
# 📊 CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

# CRITICAL: Set your credentials here
TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID_HERE"

# Performance settings
MAX_RETRIES = 3
RETRY_DELAY = 2
MESSAGE_BATCH_SIZE = 5
CACHE_SIZE = 128

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

# ═══════════════════════════════════════════════════════════════════════════
# 📝 DATA MODELS (Type-Safe)
# ═══════════════════════════════════════════════════════════════════════════

class Indicator(Enum):
    """Supported trading indicators"""
    GOLD_QUANTUM = "GOLD_QUANTUM_MASTER_PRO"
    SMART_MONEY = "SMART_MONEY_FOREX_PRO"
    UNKNOWN = "UNKNOWN"

class EventType(Enum):
    """Alert event types"""
    NEW_TRADE = "NEW_TRADE"
    TP_HIT = "TP_HIT"
    SL_HIT = "SL_HIT"
    TRAIL_HIT = "TRAIL_HIT"
    PARTIAL_HIT = "PARTIAL_HIT"

class Direction(Enum):
    """Trade directions"""
    LONG = "LONG"
    SHORT = "SHORT"

@dataclass
class TradeAlert:
    """Structured trade alert data"""
    indicator: Indicator
    event: EventType
    symbol: str
    timeframe: str
    direction: Optional[Direction] = None
    
    # Entry data
    entry: Optional[float] = None
    stop_loss: Optional[float] = None
    tp1: Optional[float] = None
    tp2: Optional[float] = None
    tp3: Optional[float] = None
    
    # Pips
    risk_pips: Optional[float] = None
    tp1_pips: Optional[float] = None
    tp2_pips: Optional[float] = None
    tp3_pips: Optional[float] = None
    rr_ratio: Optional[float] = None
    
    # Analysis
    score: Optional[int] = None
    pattern: Optional[str] = None
    trigger: Optional[str] = None
    session: Optional[str] = None
    
    # Enhanced features
    ob_stars: Optional[int] = None
    zone: Optional[str] = None
    htf_timeframe: Optional[str] = None
    htf_aligned: Optional[bool] = None
    structure: Optional[str] = None
    
    # Smart Money specific
    liquidity_sweep: Optional[bool] = None
    order_block: Optional[bool] = None
    fvg: Optional[bool] = None
    confluence: Optional[bool] = None
    institutional: Optional[bool] = None
    exhaustion: Optional[bool] = None
    
    # Gold specific
    bubble_strength: Optional[int] = None
    bubble_auto_entry: Optional[bool] = None
    market_state: Optional[str] = None
    is_trending: Optional[bool] = None
    
    # Performance
    win_rate: Optional[float] = None
    total_trades: Optional[int] = None
    profit_factor: Optional[float] = None
    total_pips: Optional[float] = None
    
    # Instrument flags
    is_bitcoin: Optional[bool] = None
    is_crypto: Optional[bool] = None
    is_forex: Optional[bool] = None
    is_gold: Optional[bool] = None
    
    # Metadata
    trade_id: Optional[str] = None
    timestamp: Optional[str] = None
    
    # TP/SL specific
    level: Optional[str] = None
    price: Optional[float] = None
    entry_price: Optional[float] = None
    pips: Optional[float] = None
    trade_closed: Optional[bool] = None
    
    # Additional data
    raw_data: Dict[str, Any] = field(default_factory=dict)

# ═══════════════════════════════════════════════════════════════════════════
# 🎨 EMOJI & FORMATTING HELPERS
# ═══════════════════════════════════════════════════════════════════════════

class EmojiHelper:
    """Centralized emoji management"""
    
    # Symbols
    BITCOIN = "₿"
    GOLD = "🥇"
    FOREX = "💱"
    
    # Directions
    LONG = "🟢"
    SHORT = "🔴"
    
    # Status
    SUCCESS = "✅"
    FAILURE = "❌"
    WARNING = "⚠️"
    INFO = "ℹ️"
    
    # Trade events
    ENTRY = "📊"
    TARGETS = "🎯"
    STOP_LOSS = "🛑"
    ANALYSIS = "📈"
    SMART_MONEY = "💎"
    PERFORMANCE = "📊"
    TRADE_MGMT = "📋"
    
    # Patterns
    BUBBLE = "🥇💎"
    ORDER_BLOCK = "📦"
    LIQUIDITY = "💧"
    CONFLUENCE = "💎⚡"
    INSTITUTIONAL = "🏛️"
    EXHAUSTION = "💥"
    
    # Sessions
    LONDON_KILL = "🔪🔥"
    NY_OPEN = "🗽"
    ASIAN = "🌅"
    
    @staticmethod
    def get_symbol_emoji(symbol: str, is_bitcoin: bool = False, is_gold: bool = False) -> str:
        """Get appropriate symbol emoji"""
        if is_bitcoin or "BTC" in symbol.upper():
            return EmojiHelper.BITCOIN
        if is_gold or "XAU" in symbol.upper() or "GOLD" in symbol.upper():
            return EmojiHelper.GOLD
        return EmojiHelper.FOREX
    
    @staticmethod
    def get_direction_emoji(direction: str) -> str:
        """Get direction emoji"""
        return EmojiHelper.LONG if direction == "LONG" else EmojiHelper.SHORT
    
    @staticmethod
    def get_session_emoji(session: str) -> str:
        """Get session emoji"""
        if "LONDON_KILL" in session:
            return EmojiHelper.LONDON_KILL
        if "NY" in session:
            return EmojiHelper.NY_OPEN
        if "ASIAN" in session:
            return EmojiHelper.ASIAN
        return "📅"
    
    @staticmethod
    def get_pattern_emoji(pattern: str, trigger: str = "") -> str:
        """Get pattern emoji"""
        pattern_upper = pattern.upper()
        trigger_upper = trigger.upper()
        
        if "BUBBLE" in pattern_upper:
            return EmojiHelper.BUBBLE
        if "CONFLUENCE" in pattern_upper or "CONFLUENCE" in trigger_upper:
            return EmojiHelper.CONFLUENCE
        if "LIQUIDITY" in pattern_upper or "SWEEP" in trigger_upper:
            return EmojiHelper.LIQUIDITY
        if "ORDER_BLOCK" in trigger_upper:
            return EmojiHelper.ORDER_BLOCK
        if "INSTITUTIONAL" in trigger_upper:
            return EmojiHelper.INSTITUTIONAL
        if "EXHAUSTION" in trigger_upper:
            return EmojiHelper.EXHAUSTION
        
        return "⚡"

class FormatHelper:
    """Text formatting utilities"""
    
    @staticmethod
    def format_price(price: float, is_crypto: bool = False) -> str:
        """Format price based on instrument type"""
        if is_crypto:
            return f"{price:,.2f}"
        return f"{price:.5f}"
    
    @staticmethod
    def format_pips(pips: float) -> str:
        """Format pips display"""
        return f"{pips:+.1f}" if pips else "0.0"
    
    @staticmethod
    def format_percentage(value: float) -> str:
        """Format percentage"""
        return f"{value:.1f}%"
    
    @staticmethod
    def format_ratio(ratio: float) -> str:
        """Format R:R ratio"""
        return f"1:{ratio:.2f}"
    
    @staticmethod
    def format_score(score: int) -> str:
        """Format score with fire emojis"""
        if score >= 90:
            return f"🔥🔥🔥 {score}/100 (EXCEPTIONAL)"
        elif score >= 80:
            return f"🔥🔥 {score}/100 (EXCELLENT)"
        elif score >= 70:
            return f"🔥 {score}/100 (GOOD)"
        else:
            return f"{score}/100"
    
    @staticmethod
    def format_stars(stars: int) -> str:
        """Format star rating"""
        if stars == 5:
            return "⭐⭐⭐⭐⭐ LEVEL 5 (HOLY GRAIL!)"
        elif stars == 4:
            return "⭐⭐⭐⭐ LEVEL 4"
        elif stars == 3:
            return "⭐⭐⭐ LEVEL 3"
        elif stars == 2:
            return "⭐⭐ LEVEL 2"
        else:
            return "⭐ LEVEL 1"
    
    @staticmethod
    @lru_cache(maxsize=CACHE_SIZE)
    def format_timeframe(tf: str) -> str:
        """Format timeframe display (cached)"""
        if tf.isdigit():
            minutes = int(tf)
            if minutes < 60:
                return f"{minutes}m"
            elif minutes == 60:
                return "1H"
            elif minutes == 240:
                return "4H"
            elif minutes == 1440:
                return "1D"
        return tf

# ═══════════════════════════════════════════════════════════════════════════
# 🔧 ALERT PARSER (Optimized)
# ═══════════════════════════════════════════════════════════════════════════

class AlertParser:
    """Efficient JSON alert parser with validation"""
    
    @staticmethod
    def parse(raw_json: str) -> Optional[TradeAlert]:
        """
        Parse JSON alert into TradeAlert object
        Returns None if parsing fails
        """
        try:
            data = json.loads(raw_json)
            
            # Determine indicator
            indicator_str = data.get('indicator', 'UNKNOWN')
            indicator = AlertParser._parse_indicator(indicator_str)
            
            # Determine event
            event_str = data.get('event', 'NEW_TRADE')
            event = AlertParser._parse_event(event_str)
            
            # Determine direction
            direction = None
            if 'direction' in data:
                direction = Direction[data['direction']]
            
            # Build TradeAlert object
            alert = TradeAlert(
                indicator=indicator,
                event=event,
                symbol=data.get('symbol', 'UNKNOWN'),
                timeframe=data.get('timeframe', '?'),
                direction=direction,
                
                # Entry data
                entry=AlertParser._safe_float(data.get('entry')),
                stop_loss=AlertParser._safe_float(data.get('stop_loss')),
                tp1=AlertParser._safe_float(data.get('tp1')),
                tp2=AlertParser._safe_float(data.get('tp2')),
                tp3=AlertParser._safe_float(data.get('tp3')),
                
                # Pips
                risk_pips=AlertParser._safe_float(data.get('risk_pips')),
                tp1_pips=AlertParser._safe_float(data.get('tp1_pips')),
                tp2_pips=AlertParser._safe_float(data.get('tp2_pips')),
                tp3_pips=AlertParser._safe_float(data.get('tp3_pips')),
                rr_ratio=AlertParser._safe_float(data.get('rr_ratio')),
                
                # Analysis
                score=AlertParser._safe_int(data.get('score')),
                pattern=data.get('pattern'),
                trigger=data.get('trigger'),
                session=data.get('session'),
                
                # Enhanced
                ob_stars=AlertParser._safe_int(data.get('ob_stars')),
                zone=data.get('zone'),
                htf_timeframe=data.get('htf_timeframe'),
                htf_aligned=AlertParser._safe_bool(data.get('htf_aligned')),
                structure=data.get('structure'),
                
                # Smart Money
                liquidity_sweep=AlertParser._safe_bool(data.get('liquidity_sweep')),
                order_block=AlertParser._safe_bool(data.get('order_block')),
                fvg=AlertParser._safe_bool(data.get('fvg')),
                confluence=AlertParser._safe_bool(data.get('confluence')),
                institutional=AlertParser._safe_bool(data.get('institutional')),
                exhaustion=AlertParser._safe_bool(data.get('exhaustion')),
                
                # Gold specific
                bubble_strength=AlertParser._safe_int(data.get('bubble_strength')),
                bubble_auto_entry=AlertParser._safe_bool(data.get('bubble_auto_entry')),
                market_state=data.get('market_state'),
                is_trending=AlertParser._safe_bool(data.get('is_trending')),
                
                # Performance
                win_rate=AlertParser._safe_float(data.get('win_rate')),
                total_trades=AlertParser._safe_int(data.get('total_trades')),
                profit_factor=AlertParser._safe_float(data.get('profit_factor')),
                total_pips=AlertParser._safe_float(data.get('total_pips')),
                
                # Instrument
                is_bitcoin=AlertParser._safe_bool(data.get('is_bitcoin')),
                is_crypto=AlertParser._safe_bool(data.get('is_crypto')),
                is_forex=AlertParser._safe_bool(data.get('is_forex')),
                is_gold=AlertParser._safe_bool(data.get('is_gold')),
                
                # Metadata
                trade_id=data.get('trade_id') or data.get('id'),
                timestamp=data.get('timestamp'),
                
                # TP/SL specific
                level=data.get('level'),
                price=AlertParser._safe_float(data.get('price')),
                entry_price=AlertParser._safe_float(data.get('entry_price')),
                pips=AlertParser._safe_float(data.get('pips')),
                trade_closed=AlertParser._safe_bool(data.get('trade_closed')),
                
                # Store raw data
                raw_data=data
            )
            
            return alert
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            return None
        except Exception as e:
            logger.error(f"Parse error: {e}")
            return None
    
    @staticmethod
    def _parse_indicator(indicator_str: str) -> Indicator:
        """Parse indicator type"""
        if "GOLD_QUANTUM" in indicator_str:
            return Indicator.GOLD_QUANTUM
        elif "SMART_MONEY" in indicator_str:
            return Indicator.SMART_MONEY
        return Indicator.UNKNOWN
    
    @staticmethod
    def _parse_event(event_str: str) -> EventType:
        """Parse event type"""
        try:
            return EventType[event_str]
        except KeyError:
            return EventType.NEW_TRADE
    
    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        """Safely convert to float"""
        if value is None or value == '':
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    
    @staticmethod
    def _safe_int(value: Any) -> Optional[int]:
        """Safely convert to int"""
        if value is None or value == '':
            return None
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return None
    
    @staticmethod
    def _safe_bool(value: Any) -> Optional[bool]:
        """Safely convert to bool"""
        if value is None or value == '':
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ('true', '1', 'yes')
        return bool(value)

# ═══════════════════════════════════════════════════════════════════════════
# 📨 MESSAGE BUILDERS (Optimized)
# ═══════════════════════════════════════════════════════════════════════════

class MessageBuilder:
    """Efficient message building with caching"""
    
    @staticmethod
    def build_new_trade_message(alert: TradeAlert) -> str:
        """Build new trade alert message"""
        if alert.indicator == Indicator.GOLD_QUANTUM:
            return MessageBuilder._build_gold_new_trade(alert)
        elif alert.indicator == Indicator.SMART_MONEY:
            return MessageBuilder._build_smart_money_new_trade(alert)
        else:
            return MessageBuilder._build_generic_new_trade(alert)
    
    @staticmethod
    def _build_gold_new_trade(alert: TradeAlert) -> str:
        """Build Gold Quantum Master Pro message"""
        symbol_emoji = EmojiHelper.get_symbol_emoji(
            alert.symbol, 
            alert.is_bitcoin or False,
            alert.is_gold or False
        )
        direction_emoji = EmojiHelper.get_direction_emoji(alert.direction.value)
        pattern_emoji = EmojiHelper.get_pattern_emoji(alert.pattern or "", alert.trigger or "")
        
        # Header
        lines = [
            "👑 GOLD QUANTUM MASTER PRO",
            "📊 TRADE • TRADING",
            "",
            f"🚀 {symbol_emoji} {alert.symbol} • {FormatHelper.format_timeframe(alert.timeframe)}",
            f"{direction_emoji} {alert.direction.value} / {'BUY' if alert.direction == Direction.LONG else 'SELL'}",
            f"{pattern_emoji} {alert.pattern or 'UNKNOWN'}",
            "",
            "⏰ Standard entry",
            ""
        ]
        
        # Entry section
        lines.extend([
            f"{EmojiHelper.ENTRY} ENTRY",
            f"├ Entry: {FormatHelper.format_price(alert.entry, alert.is_crypto)}",
            f"├ SL: {FormatHelper.format_price(alert.stop_loss, alert.is_crypto)}",
            f"└ Risk: {FormatHelper.format_pips(alert.risk_pips)} pips",
            ""
        ])
        
        # Targets section
        lines.extend([
            f"{EmojiHelper.TARGETS} TARGETS - OPTIMIZED PIPS",
            f"├ 1️⃣ {FormatHelper.format_price(alert.tp1, alert.is_crypto)} ({FormatHelper.format_pips(alert.tp1_pips)} pips)",
            f"├ 2️⃣ {FormatHelper.format_price(alert.tp2, alert.is_crypto)} ({FormatHelper.format_pips(alert.tp2_pips)} pips)",
            f"└ 3️⃣ {FormatHelper.format_price(alert.tp3, alert.is_crypto)} ({FormatHelper.format_pips(alert.tp3_pips)} pips) 🏆",
            ""
        ])
        
        # Analysis section
        lines.extend([
            f"{EmojiHelper.ANALYSIS} ANALYSIS",
            f"├ Score: {FormatHelper.format_score(alert.score or 0)}",
            f"├ Pattern: {alert.pattern or 'UNKNOWN'}",
            f"├ Session: {EmojiHelper.get_session_emoji(alert.session or '')} {alert.session or 'UNKNOWN'}",
            f"└ Timeframe: {FormatHelper.format_timeframe(alert.timeframe)}",
            ""
        ])
        
        # Smart Money section (for bubble)
        if alert.bubble_strength:
            lines.extend([
                f"{EmojiHelper.SMART_MONEY} SMART MONEY",
                f"└ Bubble: {FormatHelper.format_stars(alert.bubble_strength)}",
                ""
            ])
        
        # Performance
        if alert.total_trades and alert.total_trades > 0:
            lines.extend([
                f"{EmojiHelper.PERFORMANCE} PERFORMANCE",
                f"├ Win Rate: {FormatHelper.format_percentage(alert.win_rate or 0)}",
                f"├ Total Trades: {alert.total_trades}",
                f"└ Profit Factor: {alert.profit_factor:.2f}",
                ""
            ])
        
        lines.append(f"🆔 {alert.trade_id}")
        lines.append(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
        
        return "\n".join(lines)
    
    @staticmethod
    def _build_smart_money_new_trade(alert: TradeAlert) -> str:
        """Build Smart Money Forex Pro message"""
        symbol_emoji = EmojiHelper.get_symbol_emoji(alert.symbol, alert.is_bitcoin or False)
        direction_emoji = EmojiHelper.get_direction_emoji(alert.direction.value)
        pattern_emoji = EmojiHelper.get_pattern_emoji(alert.pattern or "", alert.trigger or "")
        
        # Header
        lines = [
            "💎 SMART MONEY FOREX PRO",
            "",
            f"{symbol_emoji} {alert.symbol} • {FormatHelper.format_timeframe(alert.timeframe)}",
            f"{direction_emoji} {alert.direction.value} / {'BUY' if alert.direction == Direction.LONG else 'SELL'}",
            f"{pattern_emoji} {alert.trigger or alert.pattern or 'SMC_SETUP'}",
            ""
        ]
        
        # Entry
        lines.extend([
            f"{EmojiHelper.ENTRY} ENTRY",
            f"├ Entry: {FormatHelper.format_price(alert.entry, alert.is_crypto)}",
            f"├ SL: {FormatHelper.format_price(alert.stop_loss, alert.is_crypto)}",
            f"└ Risk: {FormatHelper.format_pips(alert.risk_pips)} pips",
            ""
        ])
        
        # Targets
        lines.extend([
            f"{EmojiHelper.TARGETS} TARGETS",
            f"├ TP1: {FormatHelper.format_price(alert.tp1, alert.is_crypto)} ({FormatHelper.format_pips(alert.tp1_pips)} pips) - {FormatHelper.format_ratio(alert.tp1_pips / alert.risk_pips if alert.risk_pips else 1)}",
            f"├ TP2: {FormatHelper.format_price(alert.tp2, alert.is_crypto)} ({FormatHelper.format_pips(alert.tp2_pips)} pips) - {FormatHelper.format_ratio(alert.tp2_pips / alert.risk_pips if alert.risk_pips else 2)}",
            f"└ TP3: {FormatHelper.format_price(alert.tp3, alert.is_crypto)} ({FormatHelper.format_pips(alert.tp3_pips)} pips) - {FormatHelper.format_ratio(alert.rr_ratio or 0)} 🏆",
            ""
        ])
        
        # Analysis
        lines.extend([
            f"{EmojiHelper.ANALYSIS} ANALYSIS",
            f"├ Score: {alert.score}/100",
        ])
        
        if alert.ob_stars and alert.ob_stars > 0:
            lines.append(f"├ OB Stars: {'⭐' * alert.ob_stars}")
        
        lines.extend([
            f"├ HTF Aligned: {EmojiHelper.SUCCESS if alert.htf_aligned else EmojiHelper.FAILURE}",
            f"├ Zone: {alert.zone or 'UNKNOWN'}",
            f"├ Structure: {alert.structure or 'UNKNOWN'}",
            f"└ Session: {EmojiHelper.get_session_emoji(alert.session or '')} {alert.session or 'UNKNOWN'}",
            ""
        ])
        
        # Smart Money features
        lines.extend([
            f"{EmojiHelper.SMART_MONEY} SMART MONEY",
            f"├ Order Block: {EmojiHelper.SUCCESS if alert.order_block else EmojiHelper.FAILURE}",
            f"├ Liquidity Sweep: {EmojiHelper.SUCCESS if alert.liquidity_sweep else EmojiHelper.FAILURE}",
            f"├ FVG: {EmojiHelper.SUCCESS if alert.fvg else EmojiHelper.FAILURE}",
            f"├ Confluence: {EmojiHelper.SUCCESS if alert.confluence else EmojiHelper.FAILURE}",
            f"├ Institutional: {EmojiHelper.SUCCESS if alert.institutional else EmojiHelper.FAILURE}",
            f"└ Exhaustion: {EmojiHelper.SUCCESS if alert.exhaustion else EmojiHelper.FAILURE}",
            ""
        ])
        
        # Performance
        if alert.total_trades and alert.total_trades > 0:
            lines.extend([
                f"{EmojiHelper.PERFORMANCE} PERFORMANCE",
                f"├ Win Rate: {FormatHelper.format_percentage(alert.win_rate or 0)}",
                f"├ Total Trades: {alert.total_trades}",
                f"├ Total Pips: {FormatHelper.format_pips(alert.total_pips or 0)}",
                f"└ Profit Factor: {alert.profit_factor:.2f}",
                ""
            ])
        
        lines.append(f"🆔 {alert.trade_id}")
        lines.append(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
        
        return "\n".join(lines)
    
    @staticmethod
    def _build_generic_new_trade(alert: TradeAlert) -> str:
        """Build generic trade message for unknown indicators"""
        return f"""
🤖 TRADE ALERT

Symbol: {alert.symbol}
Direction: {alert.direction.value if alert.direction else 'UNKNOWN'}
Timeframe: {alert.timeframe}

Entry: {alert.entry}
SL: {alert.stop_loss}
TP1: {alert.tp1}
TP2: {alert.tp2}
TP3: {alert.tp3}

ID: {alert.trade_id}
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
    
    @staticmethod
    def build_tp_sl_message(alert: TradeAlert) -> str:
        """Build TP/SL hit message"""
        symbol_emoji = EmojiHelper.get_symbol_emoji(
            alert.symbol,
            alert.is_bitcoin or False,
            alert.is_gold or False if alert.indicator == Indicator.GOLD_QUANTUM else False
        )
        
        event_emoji = "🎯" if alert.event == EventType.TP_HIT else "🛑" if alert.event == EventType.SL_HIT else "📍"
        event_text = alert.event.value.replace("_", " ")
        
        indicator_name = "GOLD QUANTUM MASTER PRO" if alert.indicator == Indicator.GOLD_QUANTUM else "SMART MONEY FOREX PRO"
        
        lines = [
            f"{event_emoji} {event_text}",
            f"{'👑' if alert.indicator == Indicator.GOLD_QUANTUM else '💎'} {indicator_name}",
            "",
            f"{symbol_emoji} {alert.symbol} • {FormatHelper.format_timeframe(alert.timeframe)}",
            f"Direction: {alert.direction.value if alert.direction else 'UNKNOWN'}",
            f"Level: {alert.level}",
            "",
            f"Price: {FormatHelper.format_price(alert.price, alert.is_crypto)}",
            f"Entry: {FormatHelper.format_price(alert.entry_price, alert.is_crypto)}",
            f"Profit/Loss: {FormatHelper.format_pips(alert.pips)} pips",
            ""
        ]
        
        if alert.trade_closed:
            lines.append("🔒 TRADE CLOSED")
        else:
            lines.append("📊 TRADE CONTINUES")
        
        lines.append("")
        
        if alert.total_trades and alert.total_trades > 0:
            lines.extend([
                f"{EmojiHelper.PERFORMANCE} CURRENT STATS",
                f"├ Win Rate: {FormatHelper.format_percentage(alert.win_rate or 0)}",
                f"├ Total Trades: {alert.total_trades}",
                f"└ Profit Factor: {alert.profit_factor:.2f}" if alert.profit_factor else "",
                ""
            ])
        
        lines.append(f"🆔 {alert.trade_id}")
        lines.append(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
        
        return "\n".join(filter(None, lines))

# ═══════════════════════════════════════════════════════════════════════════
# 📤 TELEGRAM SENDER (Async + Retry Logic)
# ═══════════════════════════════════════════════════════════════════════════

class TelegramSender:
    """Async Telegram message sender with retry logic"""
    
    def __init__(self, bot_token: str, chat_id: str):
        self.bot = Bot(token=bot_token)
        self.chat_id = chat_id
        self.message_queue = []
    
    async def send_message(self, message: str, retries: int = MAX_RETRIES) -> bool:
        """
        Send message with retry logic
        Returns True if successful, False otherwise
        """
        for attempt in range(retries):
            try:
                await self.bot.send_message(
                    chat_id=self.chat_id,
                    text=message,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True
                )
                logger.info(f"Message sent successfully (attempt {attempt + 1})")
                return True
                
            except RetryAfter as e:
                wait_time = e.retry_after
                logger.warning(f"Rate limited. Waiting {wait_time}s...")
                await asyncio.sleep(wait_time)
                
            except TelegramError as e:
                logger.error(f"Telegram error (attempt {attempt + 1}): {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                    
            except Exception as e:
                logger.error(f"Unexpected error (attempt {attempt + 1}): {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(RETRY_DELAY)
        
        logger.error("Failed to send message after all retries")
        return False
    
    def queue_message(self, message: str):
        """Add message to queue for batch sending"""
        self.message_queue.append(message)
    
    async def send_queued_messages(self):
        """Send all queued messages in batches"""
        if not self.message_queue:
            return
        
        logger.info(f"Sending {len(self.message_queue)} queued messages...")
        
        while self.message_queue:
            batch = self.message_queue[:MESSAGE_BATCH_SIZE]
            self.message_queue = self.message_queue[MESSAGE_BATCH_SIZE:]
            
            for message in batch:
                await self.send_message(message)
                await asyncio.sleep(0.5)  # Avoid rate limiting

# ═══════════════════════════════════════════════════════════════════════════
# 🎯 MAIN BOT CLASS
# ═══════════════════════════════════════════════════════════════════════════

class TradingAlertsBot:
    """Main trading alerts bot orchestrator"""
    
    def __init__(self, bot_token: str, chat_id: str):
        self.sender = TelegramSender(bot_token, chat_id)
        self.parser = AlertParser()
        self.message_builder = MessageBuilder()
        
        logger.info("🤖 Trading Alerts Bot initialized")
    
    async def process_alert(self, raw_json: str) -> bool:
        """
        Process incoming alert
        Returns True if processed successfully
        """
        # Parse alert
        alert = self.parser.parse(raw_json)
        if not alert:
            logger.error("Failed to parse alert")
            return False
        
        logger.info(f"Processing {alert.event.value} for {alert.symbol}")
        
        # Build message
        if alert.event == EventType.NEW_TRADE:
            message = self.message_builder.build_new_trade_message(alert)
        else:
            message = self.message_builder.build_tp_sl_message(alert)
        
        # Send message
        success = await self.sender.send_message(message)
        
        if success:
            logger.info(f"✅ Alert processed successfully: {alert.trade_id}")
        else:
            logger.error(f"❌ Failed to process alert: {alert.trade_id}")
        
        return success
    
    async def process_batch(self, alerts: List[str]) -> Dict[str, int]:
        """
        Process multiple alerts in batch
        Returns stats dict
        """
        stats = {"total": len(alerts), "success": 0, "failed": 0}
        
        for raw_json in alerts:
            success = await self.process_alert(raw_json)
            if success:
                stats["success"] += 1
            else:
                stats["failed"] += 1
        
        logger.info(f"Batch processed: {stats}")
        return stats

# ═══════════════════════════════════════════════════════════════════════════
# 🚀 USAGE EXAMPLES
# ═══════════════════════════════════════════════════════════════════════════

async def main():
    """Example usage"""
    
    # Initialize bot
    bot = TradingAlertsBot(
        bot_token=TELEGRAM_BOT_TOKEN,
        chat_id=TELEGRAM_CHAT_ID
    )
    
    # Example: Process single alert
    example_alert = """{
        "event": "NEW_TRADE",
        "indicator": "SMART_MONEY_FOREX_PRO",
        "symbol": "EURUSD",
        "timeframe": "15",
        "direction": "LONG",
        "trigger": "ORDER_BLOCK",
        "pattern": "ORDER_BLOCK",
        "entry": 1.08500,
        "stop_loss": 1.08380,
        "tp1": 1.08650,
        "tp2": 1.08800,
        "tp3": 1.09000,
        "risk_pips": 12.0,
        "tp1_pips": 15.0,
        "tp2_pips": 30.0,
        "tp3_pips": 50.0,
        "rr_ratio": 4.17,
        "score": 85,
        "ob_stars": 4,
        "zone": "DISCOUNT",
        "htf_aligned": true,
        "session": "LONDON_KILL",
        "win_rate": 73.5,
        "total_trades": 34,
        "profit_factor": 2.47,
        "trade_id": "EURUSD-15-L-1704268800"
    }"""
    
    await bot.process_alert(example_alert)
    
    logger.info("✅ Bot test completed")

if __name__ == "__main__":
    # Run async main
    asyncio.run(main())
