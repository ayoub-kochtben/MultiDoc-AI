import logging
import sys


def setup_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        stream=sys.stdout,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    for noisy in ("httpx", "httpcore", "urllib3", "PIL", "docling", "RapidOCR"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
