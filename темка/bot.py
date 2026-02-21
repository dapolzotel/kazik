# bot.py — ЗАПУСК БОТА

import logging
import asyncio
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters,
)
from config import BOT_TOKEN
from handlers import cmd_start, cmd_admin, on_button, on_message
from database import load_db, save_db, get_user, upd, fmt
from payments import cryptobot_get_invoice

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
log = logging.getLogger(__name__)


async def check_pending_invoices(app: Application):
    while True:
        await asyncio.sleep(30)
        try:
            db      = load_db()
            pending = {k: v for k, v in db.get("invoices", {}).items() if v.get("status") == "pending"}
            for key, inv in pending.items():
                cb_inv = await cryptobot_get_invoice(inv["cb_id"])
                if cb_inv and cb_inv.get("status") == "paid":
                    amount  = float(cb_inv.get("amount", inv["amount"]))
                    user_id = inv["user_id"]
                    db["invoices"][key]["status"] = "paid"
                    save_db(db)
                    db2 = load_db()
                    u   = get_user(db2, user_id)
                    upd(db2, user_id, {
                        "balance":         round(u["balance"] + amount, 8),
                        "total_deposited": round(u["total_deposited"] + amount, 8),
                    })
                    db3 = load_db()
                    u3  = get_user(db3, user_id)
                    try:
                        await app.bot.send_message(
                            chat_id    = user_id,
                            text       = (
                                f"✅ *Оплата получена!*\n\n"
                                f"💵 Зачислено: *+{fmt(amount)} USDT*\n"
                                f"💰 Баланс: *{fmt(u3['balance'])} USDT*\n\n"
                                f"Удачной игры! 🎰"
                            ),
                            parse_mode = "Markdown"
                        )
                    except Exception as e:
                        log.error(f"Не удалось уведомить {user_id}: {e}")
        except Exception as e:
            log.error(f"Ошибка фоновой проверки: {e}")


async def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    print("🎰 Casino Bot запущен!")
    print("🔄 Фоновая проверка оплат: каждые 30 секунд")

    async with app:
        await app.start()
        asyncio.create_task(check_pending_invoices(app))
        await app.updater.start_polling(drop_pending_updates=True)
        await asyncio.Event().wait()  # держим бота запущенным


if __name__ == "__main__":
    asyncio.run(main())