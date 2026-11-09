"""Log filter of the writer: the Anthropic key never reaches a log line"""

import logging
import re

KEY_PATTERN = re.compile(r"sk-ant-[A-Za-z0-9_-]+")
HIDDEN = "[hidden]"


class SecretFilter(logging.Filter):
    """Class that removes the key, and anything shaped like a key, from every log record"""

    def __init__(self, secret: str | None) -> None:
        """Keep the exact key, when there is one"""

        super().__init__()
        self.secret = secret

    def filter(self, record: logging.LogRecord) -> bool:
        """Replace the message by its cleaned text and drop any attached traceback"""

        text = record.getMessage()
        if self.secret:
            text = text.replace(self.secret, HIDDEN)
        record.msg = KEY_PATTERN.sub(HIDDEN, text)
        record.args = None
        record.exc_info = None
        record.exc_text = None
        return True


def install_secret_filter(secret: str | None) -> None:
    """Add the filter to every handler of the root logger: handlers see the records of every logger"""

    for handler in logging.getLogger().handlers:
        handler.addFilter(SecretFilter(secret))
