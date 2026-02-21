# handlers.py — ВСЕ ХЭНДЛЕРЫ (кнопки, команды, сообщения)

import uuid
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import ADMIN_IDS, MIN_BET, MAX_BET, MIN_DEPOSIT, MIN_WITHDRAW, REQUIRED_CHANNELS
from database import load_db, save_db, get_user, upd, fmt, vip_label, now
from games import (
    game_slots, game_dice, game_mines, game_bowling,
    game_coin, game_wheel, game_crash,
    make_deck, hand_val, bj_text
)
from payments import cryptobot_create_invoice, cryptobot_get_invoice

log = logging.getLogger(__name__)


# ════════════════════════════════════════════════
#              КЛАВИАТУРЫ
# ════════════════════════════════════════════════

def kb_main():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮  Играть",      callback_data="play"),
         InlineKeyboardButton("👤  Профиль",     callback_data="profile")],
        [InlineKeyboardButton("💰  Пополнить",   callback_data="deposit"),
         InlineKeyboardButton("💸  Вывести",     callback_data="withdraw")],
        [InlineKeyboardButton("🎁  Промокод",    callback_data="promo"),
         InlineKeyboardButton("🏆  Топ игроков", callback_data="top")],
    ])

def kb_games():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎰  Слоты",    callback_data="g_slots"),
         InlineKeyboardButton("🎲  Кости",    callback_data="g_dice_menu")],
        [InlineKeyboardButton("💣  Мины",     callback_data="g_mines_menu"),
         InlineKeyboardButton("🎳  Боулинг",  callback_data="g_bowling")],
        [InlineKeyboardButton("🪙  Монетка",  callback_data="g_coin_menu"),
         InlineKeyboardButton("🎡  Колесо",   callback_data="g_wheel")],
        [InlineKeyboardButton("🚀  Краш",     callback_data="g_crash_menu"),
         InlineKeyboardButton("🃏  Блэкджек", callback_data="g_bj_start")],
        [InlineKeyboardButton("🔙  Главное меню", callback_data="main")],
    ])

def kb_back(dest="main"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙  Назад", callback_data=dest)]])

def kb_after_game(repeat_cb: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄  Ещё раз", callback_data=repeat_cb),
         InlineKeyboardButton("🎮  Игры",    callback_data="games")],
        [InlineKeyboardButton("🏠  Меню",    callback_data="main")],
    ])

def kb_admin():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Статистика",       callback_data="adm_stats"),
         InlineKeyboardButton("👥 Пользователи",     callback_data="adm_users")],
        [InlineKeyboardButton("🎁 Создать промо",    callback_data="adm_promo_create"),
         InlineKeyboardButton("📋 Все промо",        callback_data="adm_promo_list")],
        [InlineKeyboardButton("💸 Заявки вывода",    callback_data="adm_withdraws"),
         InlineKeyboardButton("💰 Начислить баланс", callback_data="adm_give_balance")],
        [InlineKeyboardButton("📢 Рассылка",         callback_data="adm_broadcast"),
         InlineKeyboardButton("🔙 Меню",             callback_data="main")],
    ])


# ════════════════════════════════════════════════
#              ПОДПИСКА НА КАНАЛЫ
# ════════════════════════════════════════════════

async def get_unsub_channels(bot, uid: int) -> list:
    bad = []
    for ch in REQUIRED_CHANNELS:
        try:
            m = await bot.get_chat_member(ch["id"], uid)
            if m.status in ("left", "kicked", "banned"):
                bad.append(ch)
        except Exception:
            bad.append(ch)
    return bad

async def check_sub(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    if not REQUIRED_CHANNELS:
        return True
    uid = update.effective_user.id
    bad = await get_unsub_channels(ctx.bot, uid)
    if bad:
        btns = [[InlineKeyboardButton(f"📢 {c['name']}", url=c['url'])] for c in bad]
        btns.append([InlineKeyboardButton("✅ Я подписался!", callback_data="verify_sub")])
        msg = update.message or update.callback_query.message
        await msg.reply_text(
            "🔒 *Для доступа к боту подпишитесь на каналы:*\n" +
            "\n".join(f"• {c['name']}" for c in bad),
            reply_markup=InlineKeyboardMarkup(btns),
            parse_mode="Markdown"
        )
        return False
    return True


# ════════════════════════════════════════════════
#         ОБЩАЯ ФУНКЦИЯ ЗАВЕРШЕНИЯ ИГРЫ
# ════════════════════════════════════════════════

async def finish_game(q, ctx, db, uid, u, bet, win, text, repeat_cb):
    """Списывает ставку, начисляет выигрыш, обновляет статистику."""
    if u["balance"] < bet:
        await q.answer("❌ Недостаточно средств!", show_alert=True)
        return

    new_bal = round(u["balance"] - bet + win, 8)
    is_win  = win > 0
    upd(db, uid, {
        "balance":       new_bal,
        "games_played":  u["games_played"] + 1,
        "wins":          u["wins"]   + (1 if is_win else 0),
        "losses":        u["losses"] + (0 if is_win else 1),
        "total_wagered": round(u["total_wagered"] + bet, 8),
        "total_won":     round(u["total_won"]     + win, 8),
        "biggest_win":   max(u["biggest_win"],  win),
        "biggest_loss":  max(u["biggest_loss"], bet if not is_win else 0),
    })

    result = (f"\n\n🏆 Выигрыш: *+{fmt(win)} USDT*" if is_win
              else f"\n\n💸 Проигрыш: *-{fmt(bet)} USDT*")
    balance_line = f"\n💵 Баланс: *{fmt(new_bal)} USDT*"

    await q.edit_message_text(
        text + result + balance_line,
        reply_markup=kb_after_game(repeat_cb),
        parse_mode="Markdown"
    )


async def run_game(q, ctx, db, uid, u, game_fn):
    """Запускает игровую функцию с текущей ставкой."""
    bet = ctx.user_data.get("bet", 0)
    if bet <= 0:
        await q.answer("❌ Сначала введите ставку!", show_alert=True)
        return
    if u["balance"] < bet:
        await q.answer("❌ Недостаточно средств!", show_alert=True)
        return
    text, win, repeat_cb = game_fn(bet)
    await finish_game(q, ctx, db, uid, u, bet, win, text, repeat_cb)


# ════════════════════════════════════════════════
#              КОМАНДЫ
# ════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check_sub(update, ctx): return
    db   = load_db()
    user = update.effective_user
    u    = get_user(db, user.id)
    upd(db, user.id, {"username": user.username or "", "first_name": user.first_name or ""})
    await update.message.reply_text(
        f"🎰 *CASINO BOT*\n\n"
        f"Привет, *{user.first_name}*! 👋\n\n"
        f"💵 Ваш баланс: *{fmt(u['balance'])} USDT*\n\n"
        f"Выберите действие:",
        reply_markup=kb_main(), parse_mode="Markdown"
    )

async def cmd_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return await update.message.reply_text("❌ Нет доступа.")
    await update.message.reply_text(
        "⚙️ *АДМИН ПАНЕЛЬ*",
        reply_markup=kb_admin(), parse_mode="Markdown"
    )


# ════════════════════════════════════════════════
#         ОБРАБОТЧИК ТЕКСТОВЫХ СООБЩЕНИЙ
# ════════════════════════════════════════════════

async def on_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check_sub(update, ctx): return
    text = update.message.text.strip()
    uid  = update.effective_user.id
    db   = load_db()
    u    = get_user(db, uid)

    # ── Ввод ставки ──────────────────────────────────────────
    if ctx.user_data.get("await_bet"):
        ctx.user_data.pop("await_bet")
        try:
            bet = float(text.replace(",", "."))
        except ValueError:
            await update.message.reply_text("❌ Введите число, например: `5.50`", parse_mode="Markdown")
            return
        if bet < MIN_BET:
            await update.message.reply_text(f"❌ Минимальная ставка: *{MIN_BET} USDT*", parse_mode="Markdown")
            return
        if bet > MAX_BET:
            await update.message.reply_text(f"❌ Максимальная ставка: *{MAX_BET} USDT*", parse_mode="Markdown")
            return
        if u["balance"] < bet:
            await update.message.reply_text(
                f"❌ Недостаточно средств!\n💵 Ваш баланс: *{fmt(u['balance'])} USDT*",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("💰 Пополнить", callback_data="deposit")
                ]]),
                parse_mode="Markdown"
            )
            return
        ctx.user_data["bet"] = bet
        await update.message.reply_text(
            f"✅ Ставка установлена: *{fmt(bet)} USDT*\n\nВыберите игру:",
            reply_markup=kb_games(), parse_mode="Markdown"
        )
        return

    # ── Ввод промокода ───────────────────────────────────────
    if ctx.user_data.get("await_promo"):
        ctx.user_data.pop("await_promo")
        code    = text.upper().strip()
        promos  = db.get("promo_codes", {})
        uid_str = str(uid)
        if code not in promos:
            await update.message.reply_text("❌ Промокод не найден.", reply_markup=kb_back("profile"))
            return
        p = promos[code]
        if p["uses_left"] <= 0:
            await update.message.reply_text("❌ Промокод закончился.", reply_markup=kb_back("profile"))
            return
        if code in u.get("promo_used", []):
            await update.message.reply_text("❌ Вы уже использовали этот промокод.", reply_markup=kb_back("profile"))
            return
        bonus = p["amount"]
        promos[code]["uses_left"] -= 1
        used = u.get("promo_used", []) + [code]
        upd(db, uid, {"balance": u["balance"] + bonus, "promo_used": used})
        save_db(db)
        await update.message.reply_text(
            f"🎁 *Промокод активирован!*\n\n💵 Начислено: *+{fmt(bonus)} USDT*\n"
            f"💰 Баланс: *{fmt(u['balance']+bonus)} USDT*",
            reply_markup=kb_back("profile"), parse_mode="Markdown"
        )
        return

    # ── Ввод суммы вывода ────────────────────────────────────
    if ctx.user_data.get("await_withdraw"):
        ctx.user_data.pop("await_withdraw")
        parts = text.split()
        if len(parts) != 2:
            await update.message.reply_text(
                "❌ Неверный формат.\nПример: `5.00 TYourWalletAddress`",
                parse_mode="Markdown"
            )
            return
        try:
            amount = float(parts[0].replace(",", "."))
        except ValueError:
            await update.message.reply_text("❌ Неверная сумма.")
            return
        address = parts[1]
        if amount < MIN_WITHDRAW:
            await update.message.reply_text(f"❌ Минимальная сумма вывода: *{MIN_WITHDRAW} USDT*", parse_mode="Markdown")
            return
        if u["balance"] < amount:
            await update.message.reply_text(
                f"❌ Недостаточно средств!\n💵 Баланс: *{fmt(u['balance'])} USDT*",
                parse_mode="Markdown"
            )
            return
        upd(db, uid, {"balance": u["balance"] - amount, "total_withdrawn": u["total_withdrawn"] + amount})
        db["withdraw_requests"].append({
            "user_id": uid,
            "username": u.get("username",""),
            "amount":  amount,
            "address": address,
            "date":    now(),
            "status":  "pending",
        })
        save_db(db)
        db2 = load_db(); u2 = get_user(db2, uid)
        await update.message.reply_text(
            f"✅ *Заявка на вывод отправлена!*\n\n"
            f"💸 Сумма: *{fmt(amount)} USDT*\n"
            f"📬 Адрес: `{address}`\n"
            f"⏳ Обработка: до 24 часов\n\n"
            f"💵 Баланс: *{fmt(u2['balance'])} USDT*",
            reply_markup=kb_back("profile"), parse_mode="Markdown"
        )
        # Уведомление админу
        for aid in ADMIN_IDS:
            try:
                await ctx.bot.send_message(
                    aid,
                    f"💸 *НОВАЯ ЗАЯВКА НА ВЫВОД*\n\n"
                    f"👤 @{u.get('username','?')} (ID: `{uid}`)\n"
                    f"💰 Сумма: *{fmt(amount)} USDT*\n"
                    f"📬 Адрес: `{address}`",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
        return

    # ── Ввод суммы депозита (произвольная сумма) ─────────────
    if ctx.user_data.get("await_deposit_amount"):
        ctx.user_data.pop("await_deposit_amount")
        try:
            amount = float(text.replace(",", "."))
        except ValueError:
            await update.message.reply_text("❌ Введите число.")
            return
        if amount < MIN_DEPOSIT:
            await update.message.reply_text(f"❌ Минимум: *{MIN_DEPOSIT} USDT*", parse_mode="Markdown")
            return
        await process_deposit(update.message, ctx, db, uid, amount)
        return

    # ── Админ: создание промо ─────────────────────────────────
    if ctx.user_data.get("adm_creating_promo") and uid in ADMIN_IDS:
        ctx.user_data.pop("adm_creating_promo")
        parts = text.split()
        if len(parts) != 3:
            await update.message.reply_text("❌ Формат: `КОД СУММА КОЛИЧЕСТВО`\nПример: `LUCKY100 10 50`", parse_mode="Markdown")
            return
        try:
            code, amount, uses = parts[0].upper(), float(parts[1]), int(parts[2])
        except ValueError:
            await update.message.reply_text("❌ Неверный формат чисел.")
            return
        db["promo_codes"][code] = {"amount": amount, "uses_left": uses, "created": now()}
        save_db(db)
        await update.message.reply_text(
            f"✅ *Промокод создан!*\n\n🎁 Код: `{code}`\n💵 Сумма: *{fmt(amount)} USDT*\n🔢 Активаций: *{uses}*",
            parse_mode="Markdown"
        )
        return

    # ── Админ: рассылка ───────────────────────────────────────
    if ctx.user_data.get("adm_broadcast") and uid in ADMIN_IDS:
        ctx.user_data.pop("adm_broadcast")
        users   = db.get("users", {})
        sent, fail = 0, 0
        for user_id in users:
            try:
                await ctx.bot.send_message(int(user_id), f"📢 *Сообщение от казино:*\n\n{text}", parse_mode="Markdown")
                sent += 1
            except Exception:
                fail += 1
        await update.message.reply_text(f"📢 Рассылка завершена.\n✅ Отправлено: {sent}\n❌ Ошибок: {fail}")
        return

    # ── Админ: начисление баланса ─────────────────────────────
    if ctx.user_data.get("adm_give_balance") and uid in ADMIN_IDS:
        ctx.user_data.pop("adm_give_balance")
        parts = text.split()
        if len(parts) != 2:
            await update.message.reply_text("❌ Формат: `USER_ID СУММА`")
            return
        try:
            target_id = int(parts[0]); amount = float(parts[1])
        except ValueError:
            await update.message.reply_text("❌ Неверный формат.")
            return
        tu = get_user(db, target_id)
        upd(db, target_id, {"balance": tu["balance"] + amount})
        await update.message.reply_text(
            f"✅ Начислено *{fmt(amount)} USDT* пользователю `{target_id}`.\nНовый баланс: *{fmt(tu['balance']+amount)} USDT*",
            parse_mode="Markdown"
        )
        return


# ════════════════════════════════════════════════
#              ДЕПОЗИТ
# ════════════════════════════════════════════════

async def process_deposit(msg_or_q, ctx, db, uid, amount):
    """Создаёт счёт CryptoBot и отправляет ссылку."""
    invoice_key = str(uuid.uuid4())
    result      = await cryptobot_create_invoice(amount, invoice_key)

    if not result:
        text = "❌ Ошибка создания счёта. Попробуйте позже."
        if hasattr(msg_or_q, "reply_text"):
            await msg_or_q.reply_text(text)
        else:
            await msg_or_q.edit_message_text(text, reply_markup=kb_back("deposit"))
        return

    cb_invoice_id = result["invoice_id"]
    pay_url       = result["pay_url"]

    db["invoices"][invoice_key] = {
        "user_id":    uid,
        "amount":     amount,
        "cb_id":      cb_invoice_id,
        "status":     "pending",
        "created_at": now(),
    }
    save_db(db)

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"💳 Оплатить {fmt(amount)} USDT", url=pay_url)],
        [InlineKeyboardButton("✅ Проверить оплату", callback_data=f"check_pay_{invoice_key}")],
        [InlineKeyboardButton("🔙 Назад", callback_data="deposit")],
    ])
    text = (
        f"💰 *ПОПОЛНЕНИЕ БАЛАНСА*\n\n"
        f"💵 Сумма: *{fmt(amount)} USDT*\n"
        f"🔐 Оплата через: *CryptoBot*\n\n"
        f"1. Нажмите *«Оплатить»*\n"
        f"2. Оплатите счёт в боте @CryptoBot\n"
        f"3. Нажмите *«Проверить оплату»*\n\n"
        f"⏳ Счёт действует 24 часа."
    )
    if hasattr(msg_or_q, "reply_text"):
        await msg_or_q.reply_text(text, reply_markup=kb, parse_mode="Markdown")
    else:
        await msg_or_q.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")


# ════════════════════════════════════════════════
#         ОБРАБОТЧИК ВСЕХ КНОПОК
# ════════════════════════════════════════════════

async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    await q.answer()
    data = q.data
    uid  = update.effective_user.id
    db   = load_db()
    u    = get_user(db, uid)

    # ── Проверка подписки ────────────────────────────────────
    if data == "verify_sub":
        bad = await get_unsub_channels(ctx.bot, uid)
        if bad:
            await q.answer("❌ Вы ещё не подписались на все каналы!", show_alert=True)
        else:
            await q.message.delete()
            await ctx.bot.send_message(
                uid,
                f"✅ *Подписка подтверждена!*\n\n💵 Баланс: *{fmt(u['balance'])} USDT*\n\nВыберите действие:",
                reply_markup=kb_main(), parse_mode="Markdown"
            )
        return

    if not await check_sub(update, ctx): return

    # ── Главное меню ─────────────────────────────────────────
    if data == "main":
        db = load_db(); u = get_user(db, uid)
        await q.edit_message_text(
            f"🎰 *CASINO BOT*\n\n💵 Баланс: *{fmt(u['balance'])} USDT*\n\nВыберите действие:",
            reply_markup=kb_main(), parse_mode="Markdown"
        )

    # ── Ввод ставки ──────────────────────────────────────────
    elif data == "play":
        ctx.user_data["await_bet"] = True
        ctx.user_data.pop("await_withdraw", None)
        ctx.user_data.pop("await_promo", None)
        await q.edit_message_text(
            f"🎮 *ИГРЫ*\n\n💵 Ваш баланс: *{fmt(u['balance'])} USDT*\n\n"
            f"Введите сумму ставки (мин. {MIN_BET} USDT):",
            reply_markup=kb_back("main"), parse_mode="Markdown"
        )

    # ── Меню игр ─────────────────────────────────────────────
    elif data == "games":
        bet = ctx.user_data.get("bet", 0)
        await q.edit_message_text(
            f"🎮 *ВЫБОР ИГРЫ*\n\n💵 Баланс: *{fmt(u['balance'])} USDT*\n"
            f"🎯 Ставка: *{fmt(bet)} USDT*\n\nВыберите игру:",
            reply_markup=kb_games(), parse_mode="Markdown"
        )

    # ════ СЛОТЫ ══════════════════════════════════════════════
    elif data == "g_slots":
        await run_game(q, ctx, db, uid, u, game_slots)

    # ════ КОСТИ ══════════════════════════════════════════════
    elif data == "g_dice_menu":
        bet = ctx.user_data.get("bet", 0)
        btns = [
            [InlineKeyboardButton("⚀ 1", callback_data="g_dice_1"),
             InlineKeyboardButton("⚁ 2", callback_data="g_dice_2"),
             InlineKeyboardButton("⚂ 3", callback_data="g_dice_3")],
            [InlineKeyboardButton("⚃ 4", callback_data="g_dice_4"),
             InlineKeyboardButton("⚄ 5", callback_data="g_dice_5"),
             InlineKeyboardButton("⚅ 6", callback_data="g_dice_6")],
            [InlineKeyboardButton("🔙 Назад", callback_data="games")],
        ]
        await q.edit_message_text(
            f"🎲 *КОСТИ*\n\n💵 Ставка: *{fmt(bet)} USDT*\n"
            f"Угадайте число 1–6 → выплата *×5.5*\nВыберите число:",
            reply_markup=InlineKeyboardMarkup(btns), parse_mode="Markdown"
        )

    elif data.startswith("g_dice_") and data[7:].isdigit():
        guess = int(data[7:])
        await run_game(q, ctx, db, uid, u, lambda bet: game_dice(bet, guess))

    # ════ МИНЫ ═══════════════════════════════════════════════
    elif data == "g_mines_menu":
        bet = ctx.user_data.get("bet", 0)
        btns = [
            [InlineKeyboardButton("1 клетка  ×1.1", callback_data="g_mines_1"),
             InlineKeyboardButton("2 клетки  ×1.4", callback_data="g_mines_2")],
            [InlineKeyboardButton("3 клетки  ×1.9", callback_data="g_mines_3"),
             InlineKeyboardButton("5 клеток  ×4.0", callback_data="g_mines_5")],
            [InlineKeyboardButton("8 клеток  ×9.0", callback_data="g_mines_8"),
             InlineKeyboardButton("10 клеток ×21",  callback_data="g_mines_10")],
            [InlineKeyboardButton("🔙 Назад", callback_data="games")],
        ]
        await q.edit_message_text(
            f"💣 *МИНЫ*\n\n💵 Ставка: *{fmt(bet)} USDT*\n"
            f"25 клеток, 5 мин. Чем больше кликов — тем выше выплата!\nВыберите:",
            reply_markup=InlineKeyboardMarkup(btns), parse_mode="Markdown"
        )

    elif data.startswith("g_mines_") and data[8:].isdigit():
        clicks = int(data[8:])
        await run_game(q, ctx, db, uid, u, lambda bet: game_mines(bet, clicks))

    # ════ БОУЛИНГ ════════════════════════════════════════════
    elif data == "g_bowling":
        await run_game(q, ctx, db, uid, u, game_bowling)

    # ════ МОНЕТКА ════════════════════════════════════════════
    elif data == "g_coin_menu":
        bet = ctx.user_data.get("bet", 0)
        btns = [
            [InlineKeyboardButton("👑 Орёл",  callback_data="g_coin_heads"),
             InlineKeyboardButton("🌀 Решка", callback_data="g_coin_tails")],
            [InlineKeyboardButton("🔙 Назад", callback_data="games")],
        ]
        await q.edit_message_text(
            f"🪙 *МОНЕТКА*\n\n💵 Ставка: *{fmt(bet)} USDT*\nВыплата *×1.95*\nВыберите:",
            reply_markup=InlineKeyboardMarkup(btns), parse_mode="Markdown"
        )

    elif data in ("g_coin_heads", "g_coin_tails"):
        choice = data.split("_")[2]
        await run_game(q, ctx, db, uid, u, lambda bet: game_coin(bet, choice))

    # ════ КОЛЕСО ═════════════════════════════════════════════
    elif data == "g_wheel":
        await run_game(q, ctx, db, uid, u, game_wheel)

    # ════ КРАШ ═══════════════════════════════════════════════
    elif data == "g_crash_menu":
        bet = ctx.user_data.get("bet", 0)
        btns = [
            [InlineKeyboardButton("×1.2", callback_data="g_crash_1.2"),
             InlineKeyboardButton("×1.5", callback_data="g_crash_1.5"),
             InlineKeyboardButton("×2.0", callback_data="g_crash_2.0")],
            [InlineKeyboardButton("×3.0", callback_data="g_crash_3.0"),
             InlineKeyboardButton("×5.0", callback_data="g_crash_5.0"),
             InlineKeyboardButton("×10",  callback_data="g_crash_10.0")],
            [InlineKeyboardButton("×25",  callback_data="g_crash_25.0"),
             InlineKeyboardButton("×50",  callback_data="g_crash_50.0"),
             InlineKeyboardButton("×100", callback_data="g_crash_100.0")],
            [InlineKeyboardButton("🔙 Назад", callback_data="games")],
        ]
        await q.edit_message_text(
            f"🚀 *КРАШ*\n\n💵 Ставка: *{fmt(bet)} USDT*\n"
            f"Ракета взлетает. Выберите точку выхода.\nЕсли ракета рухнет раньше — ставка сгорает!\nВыберите ×:",
            reply_markup=InlineKeyboardMarkup(btns), parse_mode="Markdown"
        )

    elif data.startswith("g_crash_") and not data.endswith("menu"):
        try:
            cashout = float(data[8:])
            await run_game(q, ctx, db, uid, u, lambda bet: game_crash(bet, cashout))
        except ValueError:
            pass

    # ════ БЛЭКДЖЕК ═══════════════════════════════════════════
    elif data == "g_bj_start":
        bet = ctx.user_data.get("bet", 0)
        if not bet:
            await q.answer("❌ Сначала введите ставку!", show_alert=True); return
        if u["balance"] < bet:
            await q.answer("❌ Недостаточно средств!", show_alert=True); return

        from games import make_deck, hand_val, bj_text
        deck   = make_deck()
        player = [deck.pop(), deck.pop()]
        dealer = [deck.pop(), deck.pop()]
        ctx.user_data["bj"] = {"deck": deck, "player": player, "dealer": dealer, "bet": bet}
        new_bal = round(u["balance"] - bet, 8)
        upd(db, uid, {"balance": new_bal})

        pv = hand_val(player)
        if pv == 21:
            dv  = hand_val(dealer)
            win = bet * 2.5 if dv != 21 else bet
            label = "🎊 *БЛЭКДЖЕК! ×2.5*" if dv != 21 else "🤝 *Ничья — блэкджек у обоих*"
            db2 = load_db(); u2 = get_user(db2, uid)
            upd(db2, uid, {"balance": new_bal + win,
                "games_played": u["games_played"]+1, "wins": u["wins"]+1,
                "total_wagered": round(u["total_wagered"]+bet, 8),
                "total_won": round(u["total_won"]+win, 8),
                "biggest_win": max(u["biggest_win"], win)})
            db3 = load_db(); u3 = get_user(db3, uid)
            await q.edit_message_text(
                bj_text(player, dealer[0], dealer) + f"\n\n{label}\n\n💵 Баланс: *{fmt(u3['balance'])} USDT*",
                reply_markup=kb_after_game("g_bj_start"), parse_mode="Markdown"
            )
            return

        btns = [
            [InlineKeyboardButton("➕ Ещё карту", callback_data="bj_hit"),
             InlineKeyboardButton("✋ Хватит",    callback_data="bj_stand")],
            [InlineKeyboardButton("🏠 Меню",      callback_data="games")],
        ]
        await q.edit_message_text(
            bj_text(player, dealer[0]) + f"\n\n💵 Баланс: *{fmt(new_bal)} USDT*",
            reply_markup=InlineKeyboardMarkup(btns), parse_mode="Markdown"
        )

    elif data in ("bj_hit", "bj_stand"):
        from games import hand_val, bj_text
        bj = ctx.user_data.get("bj")
        if not bj:
            await q.edit_message_text("❌ Игра не найдена.", reply_markup=kb_back("main"))
            return
        db = load_db(); u = get_user(db, uid)

        if data == "bj_hit":
            bj["player"].append(bj["deck"].pop())
            pv = hand_val(bj["player"])
            if pv > 21:
                upd(db, uid, {
                    "losses": u["losses"]+1, "games_played": u["games_played"]+1,
                    "total_wagered": round(u["total_wagered"]+bj["bet"], 8),
                    "biggest_loss": max(u["biggest_loss"], bj["bet"])
                })
                db2 = load_db(); u2 = get_user(db2, uid)
                await q.edit_message_text(
                    bj_text(bj["player"], bj["dealer"][0]) +
                    f"\n\n💥 *Перебор! ({pv})*\n\n💵 Баланс: *{fmt(u2['balance'])} USDT*",
                    reply_markup=kb_after_game("g_bj_start"), parse_mode="Markdown"
                )
                return
            if pv == 21:
                data = "bj_stand"
            else:
                btns = [
                    [InlineKeyboardButton("➕ Ещё карту", callback_data="bj_hit"),
                     InlineKeyboardButton("✋ Хватит",    callback_data="bj_stand")],
                ]
                await q.edit_message_text(
                    bj_text(bj["player"], bj["dealer"][0]) + f"\n\n💵 Баланс: *{fmt(u['balance'])} USDT*",
                    reply_markup=InlineKeyboardMarkup(btns), parse_mode="Markdown"
                )
                return

        if data == "bj_stand":
            while hand_val(bj["dealer"]) < 17:
                bj["dealer"].append(bj["deck"].pop())
            pv = hand_val(bj["player"])
            dv = hand_val(bj["dealer"])
            if dv > 21 or pv > dv:
                win, label = bj["bet"]*2, "🎊 *Вы победили! ×2*"
            elif pv == dv:
                win, label = bj["bet"],   "🤝 *Ничья!*"
            else:
                win, label = 0,           "😔 *Дилер победил...*"
            is_win = win > 0
            upd(db, uid, {
                "balance":       round(u["balance"] + win, 8),
                "games_played":  u["games_played"] + 1,
                "wins":          u["wins"]   + (1 if is_win else 0),
                "losses":        u["losses"] + (0 if is_win else 1),
                "total_wagered": round(u["total_wagered"] + bj["bet"], 8),
                "total_won":     round(u["total_won"]     + win, 8),
                "biggest_win":   max(u["biggest_win"],  win),
                "biggest_loss":  max(u["biggest_loss"], bj["bet"] if not is_win else 0),
            })
            db2 = load_db(); u2 = get_user(db2, uid)
            await q.edit_message_text(
                bj_text(bj["player"], bj["dealer"][0], bj["dealer"]) +
                f"\n\n{label}\n\n💵 Баланс: *{fmt(u2['balance'])} USDT*",
                reply_markup=kb_after_game("g_bj_start"), parse_mode="Markdown"
            )

    # ════ ПРОФИЛЬ ════════════════════════════════════════════
    elif data == "profile":
        db = load_db(); u = get_user(db, uid)
        wr  = (u["wins"] / u["games_played"] * 100) if u["games_played"] else 0
        vip = vip_label(u["total_wagered"])
        net = u["total_won"] - u["total_wagered"]
        txt = (
            f"👤 *ПРОФИЛЬ*\n\n"
            f"🏷 Имя: *{u.get('first_name','?')}*\n"
            f"🎖 VIP: *{vip}*\n"
            f"📅 С нами с: *{u['registered_at'][:10]}*\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💵 Баланс: *{fmt(u['balance'])} USDT*\n"
            f"💳 Пополнено: *{fmt(u['total_deposited'])} USDT*\n"
            f"💸 Выведено: *{fmt(u['total_withdrawn'])} USDT*\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🎮 Всего игр: *{u['games_played']}*\n"
            f"✅ Побед: *{u['wins']}*   ❌ Поражений: *{u['losses']}*\n"
            f"📈 Винрейт: *{wr:.1f}%*\n\n"
            f"💰 Оборот ставок: *{fmt(u['total_wagered'])} USDT*\n"
            f"🏆 Крупнейший выигрыш: *{fmt(u['biggest_win'])} USDT*\n"
            f"📉 Крупнейший проигрыш: *{fmt(u['biggest_loss'])} USDT*\n"
            f"{'📈' if net >= 0 else '📉'} Итог: *{'+' if net>=0 else ''}{fmt(net)} USDT*\n"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("💰 Пополнить", callback_data="deposit"),
             InlineKeyboardButton("💸 Вывести",   callback_data="withdraw")],
            [InlineKeyboardButton("🎁 Промокод",  callback_data="promo"),
             InlineKeyboardButton("🔙 Назад",     callback_data="main")],
        ])
        await q.edit_message_text(txt, reply_markup=kb, parse_mode="Markdown")

    # ════ ПОПОЛНЕНИЕ ═════════════════════════════════════════
    elif data == "deposit":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("1 USDT",   callback_data="dep_1"),
             InlineKeyboardButton("5 USDT",   callback_data="dep_5"),
             InlineKeyboardButton("10 USDT",  callback_data="dep_10")],
            [InlineKeyboardButton("25 USDT",  callback_data="dep_25"),
             InlineKeyboardButton("50 USDT",  callback_data="dep_50"),
             InlineKeyboardButton("100 USDT", callback_data="dep_100")],
            [InlineKeyboardButton("✏️ Своя сумма", callback_data="dep_custom")],
            [InlineKeyboardButton("🔙 Назад", callback_data="profile")],
        ])
        await q.edit_message_text(
            f"💰 *ПОПОЛНЕНИЕ БАЛАНСА*\n\n"
            f"Минимум: *{MIN_DEPOSIT} USDT*\n"
            f"Оплата через: *@CryptoBot*\n\nВыберите сумму:",
            reply_markup=kb, parse_mode="Markdown"
        )

    elif data.startswith("dep_") and data != "dep_custom":
        amount = float(data[4:])
        await process_deposit(q, ctx, db, uid, amount)

    elif data == "dep_custom":
        ctx.user_data["await_deposit_amount"] = True
        await q.edit_message_text(
            f"💰 *СВОЯ СУММА*\n\nВведите сумму пополнения (мин. {MIN_DEPOSIT} USDT):",
            reply_markup=kb_back("deposit"), parse_mode="Markdown"
        )

    # ════ ПРОВЕРКА ОПЛАТЫ ════════════════════════════════════
    elif data.startswith("check_pay_"):
        invoice_key = data[10:]
        invoices    = db.get("invoices", {})
        inv         = invoices.get(invoice_key)
        if not inv:
            await q.answer("❌ Счёт не найден.", show_alert=True); return
        if inv["status"] == "paid":
            await q.answer(f"✅ Уже зачислено {fmt(inv['amount'])} USDT!", show_alert=True); return

        cb_inv = await cryptobot_get_invoice(inv["cb_id"])
        if cb_inv and cb_inv.get("status") == "paid":
            amount = float(cb_inv.get("amount", inv["amount"]))
            db["invoices"][invoice_key]["status"] = "paid"
            save_db(db)
            db2 = load_db(); u2 = get_user(db2, uid)
            upd(db2, uid, {
                "balance":         round(u2["balance"] + amount, 8),
                "total_deposited": round(u2["total_deposited"] + amount, 8),
            })
            db3 = load_db(); u3 = get_user(db3, uid)
            await q.edit_message_text(
                f"✅ *Оплата подтверждена!*\n\n"
                f"💵 Зачислено: *+{fmt(amount)} USDT*\n"
                f"💰 Баланс: *{fmt(u3['balance'])} USDT*",
                reply_markup=kb_main(), parse_mode="Markdown"
            )
        else:
            await q.answer("⏳ Оплата ещё не поступила. Попробуйте через минуту.", show_alert=True)

    # ════ ВЫВОД ══════════════════════════════════════════════
    elif data == "withdraw":
        db = load_db(); u = get_user(db, uid)
        ctx.user_data["await_withdraw"] = True
        await q.edit_message_text(
            f"💸 *ВЫВОД СРЕДСТВ*\n\n"
            f"💵 Баланс: *{fmt(u['balance'])} USDT*\n"
            f"Минимум вывода: *{MIN_WITHDRAW} USDT*\n\n"
            f"Введите *сумму* и *USDT TRC20 адрес* через пробел:\n\n"
            f"Пример:\n`5.00 TYourWalletAddressHere`",
            reply_markup=kb_back("profile"), parse_mode="Markdown"
        )

    # ════ ПРОМОКОД ═══════════════════════════════════════════
    elif data == "promo":
        ctx.user_data["await_promo"] = True
        await q.edit_message_text(
            "🎁 *ПРОМОКОД*\n\nВведите промокод:",
            reply_markup=kb_back("profile"), parse_mode="Markdown"
        )

    # ════ ТОП ИГРОКОВ ════════════════════════════════════════
    elif data == "top":
        users = list(db["users"].values())
        top   = sorted(users, key=lambda x: x.get("total_won", 0), reverse=True)[:10]
        medals = ["🥇","🥈","🥉","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
        txt = "🏆 *ТОП 10 ИГРОКОВ*\n_(по сумме выигрышей)_\n\n"
        for i, pu in enumerate(top):
            name = pu.get("username") or pu.get("first_name") or f"ID{pu['id']}"
            txt += f"{medals[i]} *{name}* — {fmt(pu.get('total_won',0))} USDT\n"
        await q.edit_message_text(txt, reply_markup=kb_back(), parse_mode="Markdown")

    # ════ АДМИН ПАНЕЛЬ ═══════════════════════════════════════
    elif data == "adm_stats":
        if uid not in ADMIN_IDS: return
        db      = load_db()
        users   = db["users"]
        today   = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
        active  = sum(1 for u2 in users.values() if u2.get("last_active","")[:10] == today)
        dep_sum = sum(u2.get("total_deposited",0) for u2 in users.values())
        wag_sum = sum(u2.get("total_wagered",0)   for u2 in users.values())
        won_sum = sum(u2.get("total_won",0)        for u2 in users.values())
        bal_sum = sum(u2.get("balance",0)          for u2 in users.values())
        profit  = wag_sum - won_sum
        txt = (
            f"📊 *СТАТИСТИКА КАЗИНО*\n\n"
            f"👥 Всего пользователей: *{len(users)}*\n"
            f"🟢 Активных сегодня: *{active}*\n\n"
            f"💵 Суммарный баланс: *{fmt(bal_sum)} USDT*\n"
            f"💳 Всего пополнено: *{fmt(dep_sum)} USDT*\n"
            f"🎲 Оборот ставок: *{fmt(wag_sum)} USDT*\n"
            f"💸 Всего выплачено: *{fmt(won_sum)} USDT*\n"
            f"📈 Прибыль казино: *{fmt(profit)} USDT*\n\n"
            f"🎁 Промокодов: *{len(db.get('promo_codes',{}))}*\n"
            f"📋 Заявок на вывод: *{len(db.get('withdraw_requests',[]))}*\n"
        )
        await q.edit_message_text(txt, reply_markup=kb_back("adm_panel"), parse_mode="Markdown")

    elif data == "adm_panel":
        if uid not in ADMIN_IDS: return
        await q.edit_message_text("⚙️ *АДМИН ПАНЕЛЬ*", reply_markup=kb_admin(), parse_mode="Markdown")

    elif data == "adm_users":
        if uid not in ADMIN_IDS: return
        db    = load_db()
        users = list(db["users"].values())
        users.sort(key=lambda x: x.get("balance",0), reverse=True)
        txt   = "👥 *ТОП ПОЛЬЗОВАТЕЛИ ПО БАЛАНСУ*\n\n"
        for u2 in users[:15]:
            name = u2.get("username") or u2.get("first_name") or f"ID{u2['id']}"
            txt += f"• *{name}* — {fmt(u2['balance'])} USDT | Игр: {u2['games_played']}\n"
        await q.edit_message_text(txt, reply_markup=kb_back("adm_panel"), parse_mode="Markdown")

    elif data == "adm_promo_create":
        if uid not in ADMIN_IDS: return
        ctx.user_data["adm_creating_promo"] = True
        await q.edit_message_text(
            "🎁 *СОЗДАНИЕ ПРОМОКОДА*\n\n"
            "Формат: `КОД СУММА КОЛИЧЕСТВО`\n\n"
            "Пример: `LUCKY100 10 50`\n"
            "_(промокод LUCKY100 на 10 USDT, 50 активаций)_",
            reply_markup=kb_back("adm_panel"), parse_mode="Markdown"
        )

    elif data == "adm_promo_list":
        if uid not in ADMIN_IDS: return
        db     = load_db()
        promos = db.get("promo_codes", {})
        if not promos:
            await q.edit_message_text("🎁 Промокодов нет.", reply_markup=kb_back("adm_panel"))
            return
        txt = "🎁 *ПРОМОКОДЫ*\n\n"
        for code, p in promos.items():
            txt += f"• `{code}` — {fmt(p['amount'])} USDT, осталось: *{p['uses_left']}*\n"
        await q.edit_message_text(txt, reply_markup=kb_back("adm_panel"), parse_mode="Markdown")

    elif data == "adm_withdraws":
        if uid not in ADMIN_IDS: return
        db   = load_db()
        reqs = db.get("withdraw_requests", [])
        if not reqs:
            await q.edit_message_text("📋 Заявок на вывод нет.", reply_markup=kb_back("adm_panel"))
            return
        txt = "💸 *ЗАЯВКИ НА ВЫВОД*\n\n"
        for r in reqs[-10:]:
            txt += (f"👤 @{r.get('username','?')} (`{r['user_id']}`)\n"
                    f"💵 {fmt(r['amount'])} USDT\n"
                    f"📬 `{r['address']}`\n"
                    f"📅 {r['date'][:10]}\n"
                    f"🔘 {r['status']}\n\n")
        await q.edit_message_text(txt, reply_markup=kb_back("adm_panel"), parse_mode="Markdown")

    elif data == "adm_give_balance":
        if uid not in ADMIN_IDS: return
        ctx.user_data["adm_give_balance"] = True
        await q.edit_message_text(
            "💰 *НАЧИСЛИТЬ БАЛАНС*\n\nФормат: `USER_ID СУММА`\nПример: `123456789 50`",
            reply_markup=kb_back("adm_panel"), parse_mode="Markdown"
        )

    elif data == "adm_broadcast":
        if uid not in ADMIN_IDS: return
        ctx.user_data["adm_broadcast"] = True
        await q.edit_message_text(
            "📢 *РАССЫЛКА*\n\nВведите текст сообщения для всех пользователей:",
            reply_markup=kb_back("adm_panel"), parse_mode="Markdown"
        )