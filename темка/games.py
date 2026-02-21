# games.py — ВСЕ ИГРЫ

import random

# ── 🎰 СЛОТЫ ──────────────────────────────────────────────────
SLOT_SYM  = ["🍒","🍋","🍊","🍇","⭐","💎","7️⃣"]
SLOT_W    = [30, 22, 18, 13, 9, 5, 3]
SLOT_MULT = {"7️⃣":20,"💎":15,"⭐":10,"🍇":6,"🍊":4,"🍋":3,"🍒":2}

def game_slots(bet: float) -> tuple:
    r    = [random.choices(SLOT_SYM, weights=SLOT_W)[0] for _ in range(3)]
    line = " │ ".join(r)
    box  = f"┌─────────────┐\n│  {line}  │\n└─────────────┘"
    if r[0] == r[1] == r[2]:
        m = SLOT_MULT[r[0]]
        return f"🎰 *СЛОТЫ*\n\n{box}\n\n🎊 *ДЖЕКПОТ! ×{m}*", bet * m, "g_slots"
    if r[0]==r[1] or r[1]==r[2] or r[0]==r[2]:
        return f"🎰 *СЛОТЫ*\n\n{box}\n\n✨ *Две одинаковые! ×1.5*", bet * 1.5, "g_slots"
    return f"🎰 *СЛОТЫ*\n\n{box}\n\n😔 *Не повезло...*", 0.0, "g_slots"


# ── 🎲 КОСТИ ──────────────────────────────────────────────────
DICE_FACE = ["","⚀","⚁","⚂","⚃","⚄","⚅"]

def game_dice(bet: float, guess: int) -> tuple:
    roll = random.randint(1, 6)
    won  = roll == guess
    txt  = (f"🎲 *КОСТИ*\n\nВыпало: {DICE_FACE[roll]} *{roll}*"
            f"\nВаша ставка: *{guess}*\n\n"
            + ("🎊 *Угадали! ×5.5*" if won else "😔 *Мимо...*"))
    return txt, bet * 5.5 if won else 0.0, f"g_dice_{guess}"


# ── 💣 МИНЫ ───────────────────────────────────────────────────
MINES_MULTS = {1:1.1, 2:1.4, 3:1.9, 5:4.0, 8:9.0, 10:21.0}

def game_mines(bet: float, clicks: int) -> tuple:
    p_safe = 1.0
    for i in range(clicks):
        p_safe *= (20 - i) / (25 - i)
    hit = random.random() > p_safe

    grid_s = "🟦"; grid_m = "💥"; grid_b = "⬛"
    size   = min(clicks, 9)

    if hit:
        g   = grid_m + grid_s * (size - 1) + grid_b * (9 - size)
        txt = f"💣 *МИНЫ*\n\n{g}\n\n💥 *Бум! Наткнулись на мину!*\nОткрыто безопасно: *{max(0,clicks-1)}*"
        return txt, 0.0, "g_mines_menu"

    m   = MINES_MULTS.get(clicks, 1.1)
    g   = grid_s * size + grid_b * (9 - size)
    phr = "клетку" if clicks==1 else "клетки" if clicks<5 else "клеток"
    txt = f"💣 *МИНЫ*\n\n{g}\n\n✅ *Прошли {clicks} {phr} без мин!*\nМножитель: *×{m}*"
    return txt, bet * m, "g_mines_menu"


# ── 🎳 БОУЛИНГ ────────────────────────────────────────────────
def game_bowling(bet: float) -> tuple:
    pins = random.randint(0, 10)
    bar  = "🎳" * pins + "⚪" * (10 - pins)
    if pins == 10:
        return f"🎳 *БОУЛИНГ*\n\n{bar}\n\n🎊 *СТРАЙК! Все 10! ×3*", bet*3, "g_bowling"
    if pins >= 7:
        return f"🎳 *БОУЛИНГ*\n\n{bar}\n\n✨ *{pins} кеглей! ×1.5*", bet*1.5, "g_bowling"
    if pins >= 4:
        return f"🎳 *БОУЛИНГ*\n\n{bar}\n\n😐 *{pins} кеглей. Возврат ×0.5*", bet*0.5, "g_bowling"
    return f"🎳 *БОУЛИНГ*\n\n{bar}\n\n😔 *{pins} кеглей. Мимо...*", 0.0, "g_bowling"


# ── 🪙 МОНЕТКА ────────────────────────────────────────────────
def game_coin(bet: float, choice: str) -> tuple:
    result = random.choice(["heads", "tails"])
    em     = {"heads": "👑 Орёл", "tails": "🌀 Решка"}
    won    = result == choice
    txt    = (f"🪙 *МОНЕТКА*\n\nВыпало: *{em[result]}*\n"
              f"Ваш выбор: *{em[choice]}*\n\n"
              + ("🎊 *Угадали! ×1.95*" if won else "😔 *Не угадали...*"))
    return txt, bet*1.95 if won else 0.0, f"g_coin_{choice}"


# ── 🎡 КОЛЕСО ФОРТУНЫ ─────────────────────────────────────────
WHEEL = [
    ("💀 Банкрот",  0,    5),
    ("×1.2",        1.2, 20),
    ("×1.5",        1.5, 20),
    ("×2",          2.0, 18),
    ("💀 Банкрот",  0,    5),
    ("×1.5",        1.5, 18),
    ("×3",          3.0,  7),
    ("💀 Банкрот",  0,    4),
    ("×5",          5.0,  2),
    ("🌟 ×10",     10.0,  1),
]

def game_wheel(bet: float) -> tuple:
    labels  = [w[0] for w in WHEEL]
    mults   = [w[1] for w in WHEEL]
    weights = [w[2] for w in WHEEL]
    idx     = random.choices(range(len(WHEEL)), weights=weights)[0]
    label, mult = labels[idx], mults[idx]
    win  = bet * mult
    txt  = (f"🎡 *КОЛЕСО ФОРТУНЫ*\n\n"
            f"Стрелка → *{label}*\n\n"
            + (f"🎊 *Выигрыш ×{mult}!*" if mult > 0 else "💀 *Банкрот!*"))
    return txt, win, "g_wheel"


# ── 🚀 КРАШ ───────────────────────────────────────────────────
def game_crash(bet: float, cashout: float) -> tuple:
    r     = random.random()
    crash = round(max(1.0, 0.99 / (1 - r * 0.99)), 2) if r > 0.01 else 1.0
    if cashout <= crash:
        txt = (f"🚀 *КРАШ*\n\nРакета упала на: ×*{crash}*\n"
               f"Вы забрали на: ×*{cashout}*\n\n🎊 *Успели! ×{cashout}*")
        return txt, bet * cashout, f"g_crash_{cashout}"
    txt = (f"🚀 *КРАШ*\n\nРакета упала на: ×*{crash}*\n"
           f"Вы хотели на: ×*{cashout}*\n\n💥 *Взорвались!*")
    return txt, 0.0, f"g_crash_{cashout}"


# ── 🃏 БЛЭКДЖЕК ───────────────────────────────────────────────
SUITS = ["♠","♥","♦","♣"]
RANKS = ["2","3","4","5","6","7","8","9","10","J","Q","K","A"]

def make_deck() -> list:
    d = [r+s for s in SUITS for r in RANKS]
    random.shuffle(d)
    return d

def card_val(c: str) -> int:
    r = c[:-1]
    if r in ("J","Q","K"): return 10
    if r == "A": return 11
    return int(r)

def hand_val(h: list) -> int:
    v    = sum(card_val(c) for c in h)
    aces = sum(1 for c in h if c[:-1]=="A")
    while v > 21 and aces:
        v -= 10; aces -= 1
    return v

def bj_text(player: list, dealer_card: str, dealer: list = None) -> str:
    pv = hand_val(player)
    ph = " ".join(player)
    if dealer:
        dv = hand_val(dealer)
        dh = " ".join(dealer)
        return f"🃏 *БЛЭКДЖЕК*\n\nВаши: {ph} = *{pv}*\nДилер: {dh} = *{dv}*"
    return f"🃏 *БЛЭКДЖЕК*\n\nВаши: {ph} = *{pv}*\nДилер: {dealer_card} 🂠"