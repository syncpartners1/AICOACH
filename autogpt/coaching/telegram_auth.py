"""Telegram OAuth / Login Widget data verification module.

Per Telegram OAuth specification:
https://core.telegram.org/widgets/login#checking-authorization
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def verify_telegram_auth(auth_data: Dict[str, Any], bot_token: str) -> bool:
    """Verify data received from Telegram Login Widget or Web App.

    auth_data must contain 'hash' along with fields like id, first_name, auth_date, etc.
    Returns True if valid, False otherwise.
    """
    check_hash = auth_data.get("hash")
    if not check_hash or not bot_token:
        return False

    # Filter out hash and format key=value\n sorted by key
    data_check_arr = []
    for k, v in sorted(auth_data.items()):
        if k != "hash" and v is not None:
            data_check_arr.append(f"{k}={v}")

    data_check_string = "\n".join(data_check_arr)

    # Secret key is SHA256 of bot_token
    secret_key = hashlib.sha256(bot_token.encode("utf-8")).digest()
    calculated_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(calculated_hash, check_hash)
