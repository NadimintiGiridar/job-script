import logging
import sys
from config import LOG_FILE

def setup_logger(name: str = "scheduler") -> logging.Logger:
    """Configures and returns a logger that writes to both file and console."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # Logger is already configured
        
    logger.setLevel(logging.DEBUG)

    # File Handler
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    
    # Custom Formatter
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(filename)s:%(lineno)d]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Console Handler (only warning and above to keep the console UI clean, or optional)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.ERROR)  # Console only gets severe errors to avoid disrupting UI
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger

# Global logger instance
logger = setup_logger()
