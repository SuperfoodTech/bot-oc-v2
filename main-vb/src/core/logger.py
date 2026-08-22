import logging
import os
import sys
from datetime import datetime

class DiscordWebhookHandler(logging.Handler):
    """
    Handler kustom untuk meneruskan log berlevel ERROR atau CRITICAL ke Discord Webhook.
    """
    def __init__(self, level=logging.ERROR):
        super().__init__(level)

    def emit(self, record):
        try:
            from core.notifier import send_discord_error
            msg = record.getMessage()
            send_discord_error(
                message=msg,
                title="❌ Eror Bot Patroli",
                logger_name=record.name
            )
        except Exception:
            pass


_LOGGERS = {}


class Logger:
    _instance = None

    def __new__(cls, name="shopee_pro"):
        return get_logger(name)


def get_logger(name="shopee_pro"):
    if name in _LOGGERS:
        return _LOGGERS[name]

    logger = logging.getLogger(name)
    logger.propagate = False

    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logger.setLevel(level)

    if not logger.handlers:
        # Console Handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)

        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%H:%M:%S'
        )
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # Discord Webhook Handler untuk ERROR & CRITICAL
        if os.getenv("DISCORD_WEBHOOK_URL"):
            discord_handler = DiscordWebhookHandler(level=logging.ERROR)
            logger.addHandler(discord_handler)

    _LOGGERS[name] = logger
    return logger

