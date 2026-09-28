import sys
import os
import asyncio
from datetime import datetime
from loguru import logger
from typing import List, Callable, Dict, Any

# Ensure logs directory exists
os.makedirs("logs", exist_ok=True)

# Web log queue subscribers
_log_listeners: List[Callable[[Dict[str, Any]], None]] = []

def add_log_listener(listener: Callable[[Dict[str, Any]], None]):
    """Registers an async or sync callback to receive formatted log records."""
    if listener not in _log_listeners:
        _log_listeners.append(listener)

def remove_log_listener(listener: Callable[[Dict[str, Any]], None]):
    if listener in _log_listeners:
        _log_listeners.remove(listener)

def _web_sink(message):
    record = message.record
    log_data = {
        "timestamp": record["time"].strftime("%H:%M:%S.%f")[:-3],
        "level": record["level"].name,
        "message": record["message"],
        "module": record["name"],
        "line": record["line"],
    }
    for listener in _log_listeners:
        try:
            listener(log_data)
        except Exception:
            pass

# Configure Loguru
logger.remove()

# 1. Console Output with Colorized Format
logger.add(
    sys.stdout,
    colorize=True,
    format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO"
)

# 2. Daily Rotating Structured File Output
logger.add(
    "logs/trader_{time:YYYY-MM-DD}.log",
    rotation="00:00",
    retention="14 days",
    compression="zip",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{line} - {message}",
    level="DEBUG",
    enqueue=True
)

# 3. Dynamic UI Webhook Sink
logger.add(
    _web_sink,
    level="INFO",
    enqueue=True
)

__all__ = ["logger", "add_log_listener", "remove_log_listener"]
