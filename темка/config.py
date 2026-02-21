# config.py — НАСТРОЙКИ БОТА

BOT_TOKEN       = "8549677975:AAG439WeO2-z87w65vVwIPmjAqbEo6yrFfg"        # @BotFather
ADMIN_IDS       = [7681037970]               # Ваш Telegram ID
CRYPTOBOT_TOKEN = "535596:AAtdcVhWxTGeCAHbh9K8259wv1ksTK1uhRs"   # @CryptoBot → Мои приложения
BOT_USERNAME    = "catarcasinobot"                 # username бота без @

# Каналы для обязательной подписки
REQUIRED_CHANNELS = [
    # {"id": "@catarcasino", "name": "Новостной канал", "url": "https://t.me/catarcasino"},
    
]

MIN_BET          = 0.10
MAX_BET          = 10000.0
MIN_DEPOSIT      = 0.30
MIN_WITHDRAW     = 1.0
STARTING_BALANCE = 0.5      # стартовый бонус USDT

CRYPTOBOT_API = "https://pay.crypt.bot/api"
DB_FILE       = "casino_db.json"