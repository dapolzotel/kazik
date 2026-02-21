# referral.py

from database import load_db, save_db, get_user, upd, fmt

REFERRAL_BONUS_PERCENT = 5.0   # % от пополнения реферала
REFERRAL_REG_BONUS     = 0.5   # USDT за нового реферала


def get_ref_code(uid: int) -> str:
    db = load_db()
    u  = get_user(db, uid)
    if not u.get("referral_code"):
        code = str(uid)[-6:] + str(abs(hash(str(uid))))[-4:]
        upd(db, uid, {"referral_code": code})
        return code
    return u["referral_code"]


def find_by_code(code: str):
    db = load_db()
    for u in db["users"].values():
        if u.get("referral_code") == code:
            return u
    return None


def apply_ref(new_uid: int, code: str) -> bool:
    db = load_db()
    u  = get_user(db, new_uid)
    if u.get("referred_by") or str(new_uid) == code:
        return False
    referrer = find_by_code(code)
    if not referrer:
        return False
    referrer_id = referrer["id"]
    upd(db, new_uid, {"referred_by": referrer_id})
    db2 = load_db()
    r   = get_user(db2, referrer_id)
    upd(db2, referrer_id, {
        "referral_count":  r.get("referral_count", 0) + 1,
        "referral_earned": round(r.get("referral_earned", 0.0) + REFERRAL_REG_BONUS, 8),
        "balance":         round(r["balance"] + REFERRAL_REG_BONUS, 8),
    })
    return True


async def pay_ref_bonus(app, depositor_uid: int, amount: float):
    db = load_db()
    u  = get_user(db, depositor_uid)
    referrer_id = u.get("referred_by")
    if not referrer_id:
        return
    bonus = round(amount * REFERRAL_BONUS_PERCENT / 100, 8)
    if bonus <= 0:
        return
    db2 = load_db()
    r   = get_user(db2, referrer_id)
    upd(db2, referrer_id, {
        "balance":         round(r["balance"] + bonus, 8),
        "referral_earned": round(r.get("referral_earned", 0.0) + bonus, 8),
    })
    try:
        await app.bot.send_message(
            chat_id    = referrer_id,
            text       = (
                f"👥 *Реферальный бонус!*\n\n"
                f"Ваш реферал пополнил баланс.\n"
                f"💵 Начислено: *+{fmt(bonus)} USDT*\n"
                f"💰 Ваш баланс: *{fmt(r['balance'] + bonus)} USDT*"
            ),
            parse_mode = "Markdown"
        )
    except Exception:
        pass
