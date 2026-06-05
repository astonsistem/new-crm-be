import logging
import sys
from logging.handlers import TimedRotatingFileHandler
import os


LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Third-party loggers that are too noisy — always silenced to WARNING or above
_NOISY_LOGGERS = [
    "sqlalchemy.engine",
    "sqlalchemy.engine.base",
    "sqlalchemy.pool",
    "sqlalchemy.dialects",
    "sqlalchemy.orm",
    "uvicorn.access",
    "uvicorn.error",
    "apscheduler",
    "watchfiles",
    "asyncio",
]


def setup_logging(debug: bool = False) -> None:
    """
    Configure root logger and named loggers for the application.
    Outputs to stdout (always) and a rotating daily log file.

    Third-party loggers (SQLAlchemy, uvicorn, apscheduler) are capped at
    WARNING to prevent SQL query spam and double-logging caused by uvicorn's
    own default handlers sharing the root logger.
    """
    app_level = logging.DEBUG if debug else logging.INFO

    formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT)

    # --- stdout handler ---
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(app_level)
    console_handler.setFormatter(formatter)

    # --- rotating file handler ---
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    file_handler = TimedRotatingFileHandler(
        filename=os.path.join(log_dir, "app.log"),
        when="midnight",
        backupCount=14,
        encoding="utf-8",
    )
    file_handler.setLevel(app_level)
    file_handler.setFormatter(formatter)

    # --- root logger: replace ALL existing handlers (including uvicorn's) ---
    root_logger = logging.getLogger()
    root_logger.setLevel(app_level)
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # --- silence & disable propagation for noisy third-party loggers ---
    # propagate=False prevents uvicorn / sqlalchemy from reaching root logger
    # with their own handlers when uvicorn reconfigures logging after startup.
    for name in _NOISY_LOGGERS:
        lg = logging.getLogger(name)
        lg.setLevel(logging.WARNING)
        lg.propagate = False   # do NOT bubble up to root
        lg.handlers.clear()
        lg.addHandler(console_handler)   # still write WARNINGs+ in our format

    # uvicorn access log is redundant — we have RequestLoggingMiddleware
    logging.getLogger("uvicorn.access").setLevel(logging.ERROR)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger for a module."""
    return logging.getLogger(name)
