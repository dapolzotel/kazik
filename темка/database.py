# database.py — БАЗА ДАННЫХ

import json, os
from datetime import datetime
from config import DB_FILE, STARTING_BALANCE


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_db() -> dict:
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "users": {},
        "promo_codes": {},
        "invoices": {},
        "withdraw_requests": [],
    }


def save_db(db: dict):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)


def get_user(db: dict, uid: int) -> dict:
    key = str(uid)
    if key not in db["users"]:
        db["users"][key] = {
            "id":              uid,
            "balance":         STARTING_BALANCE,
            "total_deposited": 0.0,
            "total_withdrawn": 0.0,
            "total_wagered":   0.0,
            "total_won":       0.0,
            "games_played":    0,
            "wins":            0,
            "losses":          0,
            "biggest_win":     0.0,
            "biggest_loss":    0.0,
            "username":        "",
            "first_name":      "",
            "registered_at":   now(),
            "last_active":     now(),
            "promo_used":      [],
        }
        save_db(db)
    return db["users"][key]


def upd(db: dict, uid: int, data: dict):
    db["users"][str(uid)].update(data)
    db["users"][str(uid)]["last_active"] = now()
    save_db(db)


def fmt(n: float) -> str:
    return f"{n:.2f}"


def vip_label(wagered: float) -> str:
    if wagered >= 100_000: return "💎 Diamond"
    if wagered >= 50_000:  return "👑 Platinum"
    if wagered >= 10_000:  return "🥇 Gold"
    if wagered >= 1_000:   return "🥈 Silver"
    return "🥉 Bronze"