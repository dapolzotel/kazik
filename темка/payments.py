# payments.py — CRYPTOBOT ОПЛАТА

import aiohttp
import logging
from config import CRYPTOBOT_TOKEN, CRYPTOBOT_API, BOT_USERNAME

log = logging.getLogger(__name__)


async def cryptobot_create_invoice(amount: float, invoice_key: str) -> dict | None:
    """Создаёт счёт в CryptoBot. Возвращает dict с pay_url и invoice_id или None."""
    headers = {"Crypto-Pay-API-Token": CRYPTOBOT_TOKEN}
    payload = {
        "asset":           "USDT",
        "amount":          str(round(amount, 2)),
        "description":     f"💰 Пополнение Casino — {amount} USDT",
        "payload":         invoice_key,          # наш внутренний ключ
        "allow_comments":  False,
        "allow_anonymous": False,
        "paid_btn_name":   "openBot",
        "paid_btn_url":    f"https://t.me/{BOT_USERNAME}",
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{CRYPTOBOT_API}/createInvoice",
                json=payload, headers=headers
            ) as r:
                data = await r.json()
                if data.get("ok"):
                    return data["result"]
                log.error(f"CryptoBot createInvoice error: {data}")
    except Exception as e:
        log.error(f"CryptoBot request failed: {e}")
    return None


async def cryptobot_get_invoice(invoice_id: int) -> dict | None:
    """Проверяет статус счёта по его CryptoBot ID."""
    headers = {"Crypto-Pay-API-Token": CRYPTOBOT_TOKEN}
    params  = {"invoice_ids": invoice_id}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"{CRYPTOBOT_API}/getInvoices",
                params=params, headers=headers
            ) as r:
                data = await r.json()
                if data.get("ok") and data["result"]["items"]:
                    return data["result"]["items"][0]
    except Exception as e:
        log.error(f"CryptoBot getInvoices failed: {e}")
    return None