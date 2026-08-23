# -*- coding: utf-8 -*-
"""
بازی «طویله» — ربات تلگرام
یه اسب پرورش بده، مزرعه بکار، تو پیست مسابقه بده و طویله‌ت رو بزرگ کن!
"""

import telebot
import sqlite3
import random
import threading
import time
import os
import math
from datetime import datetime, timedelta, date

# =========================================================
#                    ⚙️  تنظیمات بازی  ⚙️
#   هر عددی که اینجا عوض کنی، رفتار بازی عوض میشه.
# =========================================================

TOKEN = "8974177847:AAFd7ZC4aO74DdJ3PlpcngIDGHeyMvr24Qc"

# آیدی عددی تلگرام خودت — فقط همین آیدی به دستورای تست مخفی (مثل جلو انداختن زمان
# سیستم دایناسور) دسترسی داره. با ربات‌هایی مثل @userinfobot آیدی عددیتو پیدا کن.
OWNER_TELEGRAM_ID = 0  # TODO: این رو با آیدی عددی خودت جایگزین کن

DB_PATH = "stable_game.db"

STARTING_COINS = 20

# ---------- نژادهای اسب ----------
# hunger_max/energy_max: سقف نوارهای اسب | race_minutes: زمان پایه‌ی هر دور پیست
# price: قیمت خرید | rarity_days_per_week: به‌طور میانگین چند روز از ۷ روز موجوده
HORSE_BREEDS = {
    "کره_اسب": {
        "display": "🐴 کره‌اسب", "hunger_max": 2, "energy_max": 2,
        "race_minutes": 60, "price": 0, "rarity_days_per_week": 7,
    },
    "ترکمن": {
        "display": "🐎 اسب ترکمن", "hunger_max": 3, "energy_max": 3,
        "race_minutes": 45, "price": 500, "rarity_days_per_week": 5,
    },
    "عرب": {
        "display": "🏇 اسب عرب", "hunger_max": 4, "energy_max": 4,
        "race_minutes": 30, "price": 1500, "rarity_days_per_week": 4,
    },
    "کرد": {
        "display": "🐎 اسب کرد", "hunger_max": 4, "energy_max": 5,
        "race_minutes": 25, "price": 2500, "rarity_days_per_week": 3,
    },
    "تروبرد": {
        "display": "👑 تروبرد انگلیسی", "hunger_max": 5, "energy_max": 5,
        "race_minutes": 15, "price": 5000, "rarity_days_per_week": 2,
    },
    "نجدی": {
        "display": "💎 عرب اصیل نجدی", "hunger_max": 6, "energy_max": 6,
        "race_minutes": 10, "price": 10000, "rarity_days_per_week": 1,
    },
}
STARTER_BREED = "کره_اسب"

# ---------- انرژی و گشنگی ----------
ENERGY_REGEN_MINUTES = 60      # پایه: وقتی گشنگی صفره، هر ۱ واحد انرژی این‌قدر طول می‌کشه
ENERGY_REGEN_MINUTES_FULL_HUNGER = 40  # وقتی گشنگی کامله (سیر)، انرژی سریع‌تر پر میشه
HAY_PER_FEED_UNIT = 5          # هر واحد گشنگی با ۵ یونجه پر میشه

# ---------- مزرعه ----------
PLOT_BUSHES = 10               # هر قطعه چند بوته داره (فقط جنبه‌ی نمایشی)
PLOT_PLANT_COST = 4            # هزینه‌ی کاشتن یه قطعه‌ی کامل (پایین‌تر از خرید مستقیم از فروشگاه، تا کشاورزی واقعاً به‌صرفه باشه)
PLOT_GROW_MINUTES = 60         # زمان رشد
HAY_PER_HARVEST = 20           # یونجه‌ی هر برداشت کامل

# ---------- پیست و تماشاچی ----------
INITIAL_AUDIENCE_CAPACITY = 5
TICKET_PRICE = 2
AUDIENCE_FLEE_PERCENT = 0.10
AUDIENCE_RETURN_HOURS = 24
AUDIENCE_GROWTH_HOURS = 3      # وقتی ظرفیت پیست از تعداد فعلی تماشاچی بیشتره، طی این‌همه ساعت به مرور پر میشه

# ---------- ارتقاها (قیمت پایه + رشد ۲۰٪ بعد از هر خرید) ----------
UPGRADE_BASE_PRICES = {"stable": 120, "track": 96, "farm": 72}
UPGRADE_GROWTH_RATE = 1.40

# ---------- فروشگاه ----------
SHOP_HAY_BUY_PER_10 = 5
SHOP_HAY_SELL_PER_10 = 3
SHOP_ENERGY_POTION_PRICE = 20
SHOP_HORSESHOE_GOOD_PRICE = 100    # ۱۵٪ سریع‌تر
HORSESHOE_LEVELS = {"none": 0, "good": 1, "great": 2}
HORSESHOE_DISPLAY = {"none": "بدون نعل", "good": "خوب", "great": "عالی"}
SHOP_HORSESHOE_GREAT_PRICE = 300   # ۳۰٪ سریع‌تر
HORSESHOE_GOOD_REDUCTION = 0.15
HORSESHOE_GREAT_REDUCTION = 0.30

# ---------- قرعه‌کشی روزانه ----------
LOTTERY_PRIZE = 15
LOTTERY_CHECK_INTERVAL_SECONDS = 3600  # هر ساعت چک می‌کنیم که آیا امروز قرعه‌کشی انجام شده یا نه

# ---------- شیهه‌پوینت ----------
SHIHE_COOLDOWN_MINUTES = 30
SHIHE_MIN_POINTS = 10
SHIHE_MAX_POINTS = 15

# ---------- احساسات اسب ----------
# هر چند ساعت یه‌بار (وقتی اسب مریض/ناراحت نباشه)، احساسش دوباره رندوم تعیین میشه
EMOTION_ROLL_INTERVAL_HOURS = 6
EMOTION_CHECK_LOOP_SECONDS = 600  # هر ۱۰ دقیقه چک می‌کنیم

# احتمال هر حالت (باید جمعاً ۱۰۰ باشه): شاد عادی ۶۰، هیجان‌زده ۱۰، ناراحت ۱۵، افسرده ۱۵
EMOTION_WEIGHTS = [
    ("happy", 60),
    ("excited", 10),
    ("sad", 15),
    ("depressed", 15),
]
NEGATIVE_EMOTIONS = ("sad", "depressed")
EMOTION_NATURAL_HEAL_HOURS = 8

# تأثیر هر احساس روی سرعت (روی زمان دویدن اعمال میشه؛ منفی = سریع‌تر، مثبت = کندتر)
EMOTION_SPEED_EFFECT = {
    "happy": 0.0,
    "excited": -0.15,   # ۱۵٪ سریع‌تر
    "sad": 0.10,         # ۱۰٪ کندتر
    "depressed": 0.30,   # ۳۰٪ کندتر
}

EMOTION_DISPLAY = {
    "happy": "😊 شاد",
    "excited": "🤩 هیجان‌زده",
    "sad": "😔 ناراحت",
    "depressed": "😞 افسرده",
}

# آیتم‌های درمان احساسات (کلید، اسم نمایشی، مدت درمان به ساعت، قیمت شیهه‌پوینت)
SHIHE_HEALING_ITEMS = {
    "قند": ("🍬 حبه‌قند", 4, 60),
    "بز": ("🐐 بز", 2, 80),
    "برس": ("💋 بوس", 6, 0),
    "موسیقی": ("🎵 موسیقی آرامش‌بخش", 5, 40),
    "اینه": ("🪟 آینه‌ی اصطبل", 4, 60),
}

# ---------- لباس و تزئینات (خرید با شیهه‌پوینت) ----------
# کلید: (اسم نمایشی، قیمت شیهه‌پوینت)
CLOTHING_ITEMS = {
    "روسری_قرمز": ("🧣 روسری قرمز", 20),
    "کلاه_حصیری": ("👒 کلاه حصیری", 25),
    "یال_بافته": ("💇 یال بافته‌شده", 30),
    "پتوی_راه‌راه": ("🏇 پتوی راه‌راه", 35),
    "نعل_طلایی": ("✨ نعل تزئینی طلایی", 90),
    "دم_روبان": ("🎀 روبان دم", 20),
    "زین_چرمی": ("🪑 زین چرمی ساده", 50),
    "زین_طلاکوب": ("👑 زین طلاکوب", 120),
    "گردنبند_مهره‌ای": ("📿 گردنبند مهره‌ای", 40),
    "عینک_افتابی": ("🕶️ عینک آفتابی", 45),
    "پیراهن_مسابقه": ("🎽 پیراهن مسابقه‌ای", 70),
    "پتوی_زمستانی": ("🧥 پتوی زمستانی", 55),
    "گل_سر": ("🌸 گل سر تزئینی", 15),
    "کفش_نعل_نقره": ("🥈 نعل نقره‌ای", 80),
    "تاج_ملکه": ("👸 تاج ملکه‌ی زیبایی", 150),
}

# ---------- مسابقه‌ی زیبایی ----------
BEAUTY_CONTEST_DAYS = (0, 3)   # ۰=دوشنبه ، ۳=پنجشنبه (بر اساس تقویم پایتون: دوشنبه=0)
BEAUTY_CONTEST_HOUR = 20        # ساعت ۸ شب
BEAUTY_CONTEST_PRIZE = 50

# ---------- سیستم لول ----------
# آستانه‌ی سکه‌ی کل کسب‌شده برای رسیدن به هر لول. بعد از آخرین لول تعریف‌شده،
# هر لول بعدی تقریباً ۲.۵ برابر فاصله‌ی لول قبلیش سکه لازم داره (رشد نمایی ملایم).
LEVEL_THRESHOLDS = [0, 50, 150]   # ایندکس ۰=لول۱, ۱=لول۲, ۲=لول۳ ...
LEVEL_GROWTH_RATE = 2.5           # نرخ رشد فاصله‌ی لول‌ها بعد از آخرین آستانه‌ی تعریف‌شده
LEAGUE_UNLOCK_LEVEL = 3
CITY_UNLOCK_LEVEL = 2             # لول لازم برای حساب شدن «تو شهر» و سرقت دایناسوری

# ---------- لیگ اسبی (اصطبل مشترک) ----------
# کلید: (اسم نمایشی، سطح قدرت). قدرت روی همون مقیاس compute_horse_power حساب میشه.
LEAGUE_NPC_TEAMS = {
    "godolphin":   ("🏆 گودولفین (Godolphin)", 9.0),
    "coolmore":    ("👑 کولمور (Coolmore)", 9.0),
    "juddmonte":   ("⚜️ جودمانت (Juddmonte Farms)", 7.0),
    "darley":      ("🔥 دارلی (Darley)", 7.0),
    "shadwell":    ("⚡ شادول استیت (Shadwell Estate)", 5.0),
    "ballydoyle":  ("🌙 بالیدویل (Ballydoyle)", 5.0),
    "winstar":     ("🍀 وین‌استار فارم (WinStar Farm)", 3.5),
    "spendthrift": ("🌾 اسپندریفت فارم (Spendthrift Farm)", 2.5),
    "calumet":     ("🐎 کالومت فارم (Calumet Farm)", 1.5),
}
LEAGUE_REWARD_BY_RANK = {1: 800, 2: 600, 3: 400, 4: 100, 5: 100, 6: 100, 7: 100, 8: 50, 9: 50, 10: 0}
LEAGUE_REMINDER_WEEKDAY = 2   # چهارشنبه (دوشنبه=0, سه‌شنبه=1, چهارشنبه=2 در تقویم پایتون)
LEAGUE_REMINDER_HOUR = 21
LEAGUE_ANNOUNCE_HOUR = 10     # ساعت اعلام ثبت‌نام جمعه صبح
LEAGUE_CHECK_INTERVAL_SECONDS = 300

# ---------- آب‌وهوا ----------
WEATHER_TYPES = {
    "sunny": {"display": "☀️ آفتابی", "speed_bonus": -0.05, "hay_bonus": 0.0},
    "rainy": {"display": "🌧️ بارونی", "speed_bonus": 0.0, "hay_bonus": 0.25},
    "cloudy": {"display": "⛅ ابری", "speed_bonus": 0.0, "hay_bonus": 0.0},
}

# =========================================================
#                    🗄️  دیتابیس  🗄️
# =========================================================

db_lock = threading.Lock()

# اگه متغیر محیطی DATABASE_URL ست شده باشه (روی Render)، از Supabase/Postgres استفاده می‌کنیم.
# وگرنه (مثلاً موقع تست روی Pydroid)، همون فایل محلی SQLite کار می‌کنه.
DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL:
    import psycopg2
    import psycopg2.extras

    PK_AUTOINCREMENT = "SERIAL PRIMARY KEY"

    # اتصال دائمی به Supabase — به‌جای اینکه هر کوئری یه اتصال تازه باز/بسته کنه
    # (که کند بود)، همیشه از همین یه اتصال زنده استفاده می‌کنیم. چون همه‌ی
    # دسترسی‌ها زیر db_lock سریالایز می‌شن، یه اتصال مشترک کاملاً امنه.
    _pg_conn = None

    def _get_persistent_pg_connection():
        global _pg_conn
        if _pg_conn is not None:
            try:
                if _pg_conn.closed:
                    _pg_conn = None
                else:
                    # اگه تراکنش قبلی خراب مونده بود (بعد از یه خطا)، تمیزش کن
                    if _pg_conn.get_transaction_status() != psycopg2.extensions.TRANSACTION_STATUS_IDLE:
                        _pg_conn.rollback()
            except Exception:
                _pg_conn = None
        if _pg_conn is None:
            _pg_conn = psycopg2.connect(DATABASE_URL)
            _pg_conn.autocommit = False
        return _pg_conn

    class PGConnWrapper:
        """این کلاس رفتار sqlite3 رو شبیه‌سازی می‌کنه تا بقیه‌ی کد نیازی به تغییر نداشته باشه."""
        def __init__(self):
            self._conn = _get_persistent_pg_connection()

        def execute(self, query, params=()):
            q = query.replace("?", "%s")
            cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            try:
                cur.execute(q, params)
            except Exception:
                # اگه کوئری خطا داد، تراکنش رو برگردون که اتصال برای دفعه‌ی بعد قابل استفاده بمونه
                try:
                    self._conn.rollback()
                except Exception:
                    pass
                raise
            return cur

        def cursor(self):
            return self._conn.cursor()

        def commit(self):
            self._conn.commit()

        def close(self):
            # عمداً اتصال واقعی رو نمی‌بندیم — این اتصال بین کوئری‌ها زنده می‌مونه.
            pass

    def get_conn():
        return PGConnWrapper()

else:
    PK_AUTOINCREMENT = "INTEGER PRIMARY KEY AUTOINCREMENT"

    def get_conn():
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn


def init_db():
    with db_lock:
        conn = get_conn()
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                coins INTEGER DEFAULT 0,
                hay INTEGER DEFAULT 0,
                stable_capacity INTEGER DEFAULT 1,
                track_capacity INTEGER DEFAULT 5,
                track_audience INTEGER DEFAULT 0,
                stable_upgrades INTEGER DEFAULT 0,
                track_upgrades INTEGER DEFAULT 0,
                farm_upgrades INTEGER DEFAULT 0
            )
        """)
        c.execute(f"""
            CREATE TABLE IF NOT EXISTS horses (
                id {PK_AUTOINCREMENT},
                user_id BIGINT,
                breed_key TEXT,
                energy INTEGER,
                hunger INTEGER,
                last_energy_update TEXT,
                horseshoe TEXT DEFAULT 'none',
                racing_until TEXT
            )
        """)
        c.execute(f"""
            CREATE TABLE IF NOT EXISTS farm_plots (
                id {PK_AUTOINCREMENT},
                user_id BIGINT,
                status TEXT DEFAULT 'empty',
                planted_at TEXT
            )
        """)
        c.execute(f"""
            CREATE TABLE IF NOT EXISTS audience_returns (
                id {PK_AUTOINCREMENT},
                user_id BIGINT,
                amount INTEGER,
                return_at TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS daily_market (
                breed_key TEXT PRIMARY KEY,
                market_date TEXT,
                available INTEGER
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS active_chats (
                chat_id BIGINT PRIMARY KEY,
                last_seen TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS menu_owners (
                chat_id BIGINT,
                message_id BIGINT,
                user_id BIGINT,
                PRIMARY KEY (chat_id, message_id)
            )
        """)
        c.execute(f"""
            CREATE TABLE IF NOT EXISTS league_registrations (
                id {PK_AUTOINCREMENT},
                user_id BIGINT,
                week_start TEXT,
                registered_at TEXT,
                UNIQUE(user_id, week_start)
            )
        """)
        c.execute(f"""
            CREATE TABLE IF NOT EXISTS league_races (
                id {PK_AUTOINCREMENT},
                user_id BIGINT,
                week_start TEXT,
                opponent_key TEXT,
                result TEXT,
                raced_at TEXT,
                UNIQUE(user_id, week_start)
            )
        """)
        c.execute(f"""
            CREATE TABLE IF NOT EXISTS league_npc_scores (
                id {PK_AUTOINCREMENT},
                week_start TEXT,
                npc_key TEXT,
                score INTEGER,
                UNIQUE(week_start, npc_key)
            )
        """)
        c.execute(f"""
            CREATE TABLE IF NOT EXISTS league_history (
                id {PK_AUTOINCREMENT},
                week_start TEXT UNIQUE,
                our_score INTEGER,
                rank INTEGER,
                reward_per_person INTEGER,
                participants INTEGER,
                finalized_at TEXT
            )
        """)
        conn.commit()
        conn.close()

    run_migrations()


# ستون‌های جدیدی که با آپدیت‌های بعدی اضافه شدن (روی جدول موجود، بدون پاک کردن اطلاعات قبلی)
NEW_COLUMNS = [
    ("users", "shihe_points", "INTEGER DEFAULT 0"),
    ("users", "last_shihe", "TEXT"),
    ("users", "total_coins_earned", "INTEGER DEFAULT 0"),
    ("horses", "emotion", "TEXT DEFAULT 'happy'"),
    ("horses", "emotion_until", "TEXT"),
    ("horses", "emotion_next_roll", "TEXT"),
    ("horses", "clothing", "TEXT"),
    ("users", "decoration_spent", "INTEGER DEFAULT 0"),
    ("users", "audience_growth_start", "TEXT"),
    ("users", "audience_growth_base", "INTEGER"),
    ("dino_catches", "used", "INTEGER DEFAULT 0"),
    # این ۴ تا برای فیکس باگ «مسابقه‌ی گم‌شده بعد از ری‌استارت» هستن: چون قبلاً
    # coins_earned و performance فقط تو حافظه‌ی threading.Timer بودن، با ری‌استارت Render
    # کاملاً از بین می‌رفتن. حالا تو خودِ ردیف اسب ذخیره میشن تا بشه بعد از بالا اومدن
    # دوباره‌ی ربات، مسابقه‌های ناتموم رو پیدا و تسویه کرد.
    ("horses", "race_chat_id", "BIGINT"),
    ("horses", "race_coins_earned", "INTEGER"),
    ("horses", "race_performance", "TEXT"),
    ("horses", "race_settled", "INTEGER DEFAULT 1"),
    # فیکس باگ «جنگ همون لحظه‌ی شروع تموم میشه»: قبلاً زمان رزولوشن بر اساس
    # نزدیک‌ترین ساعتِ جنگیِ روی کلاک محاسبه می‌شد، نه زمان واقعی اعلام. با تست
    # دستی (یا هر بی‌نظمی دیگه) این باعث می‌شد رزولوشن قبل از شروع مهلت برسه.
    # حالا زمان اعلام واقعی هر دور ذخیره میشه و مهلت دقیقاً ۲.۵ ساعت بعدشه.
    ("dino_war_rounds", "announced_at", "TEXT"),
]


def run_migrations():
    for table, col, coltype in NEW_COLUMNS:
        try:
            with db_lock:
                conn = get_conn()
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}")
                conn.commit()
                conn.close()
        except Exception:
            # یعنی احتمالاً ستون از قبل وجود داشته، مشکلی نیست
            try:
                conn.close()
            except Exception:
                pass


def mark_chat_active(chat_id):
    """هر بار که پیامی از یه گروه میاد، اونو تو لیست گروه‌های فعال ثبت/آپدیت می‌کنه."""
    with db_lock:
        conn = get_conn()
        conn.execute(
            "INSERT INTO active_chats (chat_id, last_seen) VALUES (?, ?) "
            "ON CONFLICT(chat_id) DO UPDATE SET last_seen=excluded.last_seen",
            (chat_id, now().isoformat())
        )
        conn.commit()
        conn.close()


def get_active_chat_ids():
    """لیست همه‌ی گروه‌هایی که ربات توشون فعاله رو برمی‌گردونه (برای پخش اعلامیه‌ها)."""
    with db_lock:
        conn = get_conn()
        rows = conn.execute("SELECT chat_id FROM active_chats").fetchall()
        conn.close()
        return [r["chat_id"] for r in rows]


def set_setting(key, value):
    with db_lock:
        conn = get_conn()
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value))
        )
        conn.commit()
        conn.close()


def get_setting(key):
    with db_lock:
        conn = get_conn()
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        conn.close()
        return row["value"] if row else None


def increment_setting_counter(key, amount=1):
    """یه شمارنده‌ی روزانه (مثلاً برای روزنامه) رو با مقدار داده‌شده افزایش میده."""
    with db_lock:
        conn = get_conn()
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        current = int(row["value"]) if row and row["value"] else 0
        new_value = current + amount
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(new_value))
        )
        conn.commit()
        conn.close()
        return new_value


def now():
    return datetime.now()


def parse_time(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


# ---------------------------------------------------------
# کاربر
# ---------------------------------------------------------

def user_exists(user_id):
    with db_lock:
        conn = get_conn()
        row = conn.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,)).fetchone()
        conn.close()
        return row is not None


def ensure_user(user_id, username):
    """اگه کاربر جدیده، طویله‌ی اولیه، اسب رایگان، مزرعه‌ی خالی و سکه‌ی شروع رو براش می‌سازه."""
    if user_exists(user_id):
        # فقط یوزرنیم رو آپدیت کن اگه عوض شده
        with db_lock:
            conn = get_conn()
            conn.execute("UPDATE users SET username=? WHERE user_id=?", (username or "", user_id))
            conn.commit()
            conn.close()
        return

    with db_lock:
        conn = get_conn()
        conn.execute(
            """INSERT INTO users (user_id, username, coins, hay, stable_capacity, track_capacity, track_audience)
               VALUES (?, ?, ?, 0, 1, ?, ?)""",
            (user_id, username or "", STARTING_COINS, INITIAL_AUDIENCE_CAPACITY, INITIAL_AUDIENCE_CAPACITY)
        )
        # اسب اولیه: خسته و گشنه (انرژی و گشنگی صفر)
        next_roll = (now() + timedelta(hours=EMOTION_ROLL_INTERVAL_HOURS)).isoformat()
        conn.execute(
            """INSERT INTO horses (user_id, breed_key, energy, hunger, last_energy_update, horseshoe, emotion, emotion_next_roll)
               VALUES (?, ?, 0, 0, ?, 'none', 'happy', ?)""",
            (user_id, STARTER_BREED, now().isoformat(), next_roll)
        )
        # یه قطعه‌ی مزرعه‌ی خالی
        conn.execute(
            "INSERT INTO farm_plots (user_id, status) VALUES (?, 'empty')",
            (user_id,)
        )
        conn.commit()
        conn.close()


def get_user_row(user_id):
    with db_lock:
        conn = get_conn()
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        conn.close()
        return dict(row) if row else None


def find_user_by_username(username):
    username = username.lstrip("@").lower()
    with db_lock:
        conn = get_conn()
        row = conn.execute(
            "SELECT * FROM users WHERE LOWER(username)=?", (username,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None


def get_all_user_ids():
    with db_lock:
        conn = get_conn()
        rows = conn.execute("SELECT user_id FROM users").fetchall()
        conn.close()
        return [r["user_id"] for r in rows]


def adjust_coins(user_id, delta):
    """این تابع اتمیک هست: تو یه قفل واحد چک و کم/زیاد می‌کنه، برای جلوگیری از باگ کسر نشدن موجودی.
    اگه delta مثبت باشه، به مجموع سکه‌ی کل کسب‌شده (برای سیستم لول) هم اضافه میشه."""
    with db_lock:
        conn = get_conn()
        row = conn.execute("SELECT coins, total_coins_earned FROM users WHERE user_id=?", (user_id,)).fetchone()
        if row is None:
            conn.close()
            return False, 0
        new_value = row["coins"] + delta
        if new_value < 0:
            conn.close()
            return False, row["coins"]
        if delta > 0:
            new_total = (row["total_coins_earned"] or 0) + delta
            conn.execute("UPDATE users SET coins=?, total_coins_earned=? WHERE user_id=?", (new_value, new_total, user_id))
        else:
            conn.execute("UPDATE users SET coins=? WHERE user_id=?", (new_value, user_id))
        conn.commit()
        conn.close()
        return True, new_value


def adjust_hay(user_id, delta):
    with db_lock:
        conn = get_conn()
        row = conn.execute("SELECT hay FROM users WHERE user_id=?", (user_id,)).fetchone()
        if row is None:
            conn.close()
            return False, 0
        new_value = row["hay"] + delta
        if new_value < 0:
            conn.close()
            return False, row["hay"]
        conn.execute("UPDATE users SET hay=? WHERE user_id=?", (new_value, user_id))
        conn.commit()
        conn.close()
        return True, new_value


def adjust_shihe(user_id, delta):
    with db_lock:
        conn = get_conn()
        row = conn.execute("SELECT shihe_points FROM users WHERE user_id=?", (user_id,)).fetchone()
        if row is None:
            conn.close()
            return False, 0
        current = row["shihe_points"] or 0
        new_value = current + delta
        if new_value < 0:
            conn.close()
            return False, current
        conn.execute("UPDATE users SET shihe_points=? WHERE user_id=?", (new_value, user_id))
        conn.commit()
        conn.close()
        return True, new_value


def update_user_fields(user_id, **fields):
    if not fields:
        return
    with db_lock:
        conn = get_conn()
        cols = ", ".join(f"{k}=?" for k in fields)
        values = list(fields.values()) + [user_id]
        conn.execute(f"UPDATE users SET {cols} WHERE user_id=?", values)
        conn.commit()
        conn.close()


# ---------------------------------------------------------
# اسب‌ها
# ---------------------------------------------------------

def get_horses(user_id):
    with db_lock:
        conn = get_conn()
        rows = conn.execute(
            "SELECT * FROM horses WHERE user_id=? ORDER BY id", (user_id,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]


def get_horse_by_index(user_id, index):
    """index از ۱ شروع میشه (اسب شماره ۱، ۲، ...)"""
    horses = get_horses(user_id)
    if 1 <= index <= len(horses):
        return horses[index - 1]
    return None


def update_horse(horse_id, **fields):
    if not fields:
        return
    with db_lock:
        conn = get_conn()
        cols = ", ".join(f"{k}=?" for k in fields)
        values = list(fields.values()) + [horse_id]
        conn.execute(f"UPDATE horses SET {cols} WHERE id=?", values)
        conn.commit()
        conn.close()


def add_horse(user_id, breed_key, energy=None, hunger=None):
    breed = HORSE_BREEDS[breed_key]
    e = breed["energy_max"] if energy is None else energy
    h = breed["hunger_max"] if hunger is None else hunger
    next_roll = (now() + timedelta(hours=EMOTION_ROLL_INTERVAL_HOURS)).isoformat()
    with db_lock:
        conn = get_conn()
        conn.execute(
            """INSERT INTO horses (user_id, breed_key, energy, hunger, last_energy_update, horseshoe, emotion, emotion_next_roll)
               VALUES (?, ?, ?, ?, ?, 'none', 'happy', ?)""",
            (user_id, breed_key, e, h, now().isoformat(), next_roll)
        )
        conn.commit()
        conn.close()


def is_horse_racing(horse):
    racing_until = parse_time(horse.get("racing_until"))
    return racing_until is not None and racing_until > now()


def get_energy_regen_minutes(horse, breed):
    """هرچی گشنگی به سقفش نزدیک‌تر باشه (سیرتر باشه)، انرژی سریع‌تر پر میشه:
    از ENERGY_REGEN_MINUTES (گشنگی صفر) تا ENERGY_REGEN_MINUTES_FULL_HUNGER (گشنگی کامل)."""
    hunger_max = breed["hunger_max"]
    if hunger_max <= 0:
        return ENERGY_REGEN_MINUTES
    hunger_frac = min(1.0, max(0.0, horse["hunger"] / hunger_max))
    span = ENERGY_REGEN_MINUTES - ENERGY_REGEN_MINUTES_FULL_HUNGER
    return ENERGY_REGEN_MINUTES - hunger_frac * span


def apply_energy_regen(horse):
    """محاسبه‌ی تنبل (Lazy) انرژی: بر اساس زمان گذشته و گشنگی فعلی، انرژی رو آپدیت و ذخیره می‌کنه."""
    breed = HORSE_BREEDS[horse["breed_key"]]
    max_energy = breed["energy_max"]
    if horse["energy"] >= max_energy:
        # وقتی انرژی پره، ساعتِ آخرین آپدیت رو همین الان نگه می‌داریم (نه قدیمی ول میشه).
        # وگرنه بعداً که انرژی از پر کم بشه (مثلاً بعد مسابقه)، فکر می‌کنه از یه تایم‌استمپ
        # خیلی قدیمی زمان گذشته و یهو انرژی رو مجانی و آنی پر می‌کنه.
        current_ts = now().isoformat()
        if horse["last_energy_update"] != current_ts:
            update_horse(horse["id"], last_energy_update=current_ts)
            horse["last_energy_update"] = current_ts
        return horse

    last_update = parse_time(horse["last_energy_update"]) or now()
    elapsed_minutes = (now() - last_update).total_seconds() / 60
    regen_minutes = get_energy_regen_minutes(horse, breed)
    units_gained = int(elapsed_minutes // regen_minutes)

    if units_gained <= 0:
        return horse

    new_energy = min(max_energy, horse["energy"] + units_gained)
    # ساعتِ آخرین آپدیت رو به اندازه‌ی واحدهای مصرف‌شده جلو می‌بریم (نه به now کامل، تا واحد اضافه هدر نره)
    new_last_update = last_update + timedelta(minutes=units_gained * regen_minutes)

    update_horse(horse["id"], energy=new_energy, last_energy_update=new_last_update.isoformat())
    horse["energy"] = new_energy
    horse["last_energy_update"] = new_last_update.isoformat()
    return horse


def get_horse_emotion(horse):
    """اگه فیلد emotion هنوز خالی باشه (اسبای قدیمی قبل از این آپدیت)، پیش‌فرض شاد در نظر گرفته میشه."""
    return horse.get("emotion") or "happy"


def get_emotion_speed_factor(horse):
    emotion = get_horse_emotion(horse)
    return EMOTION_SPEED_EFFECT.get(emotion, 0.0)


def roll_random_emotion():
    total = sum(w for _, w in EMOTION_WEIGHTS)
    r = random.uniform(0, total)
    upto = 0
    for emotion, weight in EMOTION_WEIGHTS:
        upto += weight
        if r <= upto:
            return emotion
    return "happy"


def compute_level(user):
    total = user.get("total_coins_earned") or 0
    level = 1
    threshold = 0
    gap = LEVEL_THRESHOLDS[1] if len(LEVEL_THRESHOLDS) > 1 else 50
    i = 1
    while True:
        if i < len(LEVEL_THRESHOLDS):
            threshold = LEVEL_THRESHOLDS[i]
        else:
            gap = round(gap * LEVEL_GROWTH_RATE)
            threshold += gap
        if total < threshold:
            break
        level = i + 1
        i += 1
    return level


def coins_needed_for_level(target_level):
    """چند سکه‌ی کل کسب‌شده لازمه برای رسیدن به یه لول مشخص."""
    if target_level <= 1:
        return 0
    threshold = 0
    gap = LEVEL_THRESHOLDS[1] if len(LEVEL_THRESHOLDS) > 1 else 50
    for i in range(1, target_level):
        if i < len(LEVEL_THRESHOLDS):
            threshold = LEVEL_THRESHOLDS[i]
        else:
            gap = round(gap * LEVEL_GROWTH_RATE)
            threshold += gap
    return threshold




# ---------------------------------------------------------
# مزرعه
# ---------------------------------------------------------

def get_plots(user_id):
    with db_lock:
        conn = get_conn()
        rows = conn.execute(
            "SELECT * FROM farm_plots WHERE user_id=? ORDER BY id", (user_id,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]


def refresh_plot_status(plot):
    """اگه قطعه در حال رشد بود و زمانش تموم شده، وضعیتش رو به آماده تغییر میده."""
    if plot["status"] == "growing":
        planted_at = parse_time(plot["planted_at"])
        if planted_at and (now() - planted_at).total_seconds() / 60 >= PLOT_GROW_MINUTES:
            with db_lock:
                conn = get_conn()
                conn.execute("UPDATE farm_plots SET status='ready' WHERE id=?", (plot["id"],))
                conn.commit()
                conn.close()
            plot["status"] = "ready"
    return plot


def add_plot(user_id):
    with db_lock:
        conn = get_conn()
        conn.execute("INSERT INTO farm_plots (user_id, status) VALUES (?, 'empty')", (user_id,))
        conn.commit()
        conn.close()


def set_plot(plot_id, **fields):
    with db_lock:
        conn = get_conn()
        cols = ", ".join(f"{k}=?" for k in fields)
        values = list(fields.values()) + [plot_id]
        conn.execute(f"UPDATE farm_plots SET {cols} WHERE id=?", values)
        conn.commit()
        conn.close()


# ---------------------------------------------------------
# تماشاچی‌های فراری (برگشت بعد از ۲۴ ساعت)
# ---------------------------------------------------------

def process_audience_returns(user_id):
    """هر رکورد فرارِ تاریخ‌گذشته رو دوباره به تماشاچی‌های فعلی اضافه می‌کنه."""
    with db_lock:
        conn = get_conn()
        rows = conn.execute(
            "SELECT * FROM audience_returns WHERE user_id=? AND return_at<=?",
            (user_id, now().isoformat())
        ).fetchall()
        if not rows:
            conn.close()
            return

        total_return = sum(r["amount"] for r in rows)
        user_row = conn.execute("SELECT track_audience, track_capacity FROM users WHERE user_id=?", (user_id,)).fetchone()
        new_audience = min(user_row["track_capacity"], user_row["track_audience"] + total_return)
        conn.execute("UPDATE users SET track_audience=? WHERE user_id=?", (new_audience, user_id))
        conn.execute("DELETE FROM audience_returns WHERE user_id=? AND return_at<=?", (user_id, now().isoformat()))
        conn.commit()
        conn.close()


def schedule_audience_return(user_id, amount):
    with db_lock:
        conn = get_conn()
        return_at = (now() + timedelta(hours=AUDIENCE_RETURN_HOURS)).isoformat()
        conn.execute(
            "INSERT INTO audience_returns (user_id, amount, return_at) VALUES (?, ?, ?)",
            (user_id, amount, return_at)
        )
        conn.commit()
        conn.close()


def apply_audience_growth(user_id):
    """محاسبه‌ی تنبل (Lazy): وقتی ظرفیت پیست از تعداد تماشاچی فعلی بیشتره،
    به مرور و به‌صورت خطی طی AUDIENCE_GROWTH_HOURS ساعت پرش می‌کنه
    (مثلاً وقتی پیست ارتقا پیدا می‌کنه و جای خالی باز میشه)."""
    with db_lock:
        conn = get_conn()
        row = conn.execute(
            "SELECT track_audience, track_capacity, audience_growth_start, audience_growth_base "
            "FROM users WHERE user_id=?",
            (user_id,)
        ).fetchone()
        conn.close()

    if row is None:
        return

    audience = row["track_audience"]
    capacity = row["track_capacity"]

    if audience >= capacity:
        # جای خالی نیست؛ اگه پنجره‌ی رشدی از قبل باز مونده، ببندش
        if row["audience_growth_start"]:
            update_user_fields(user_id, audience_growth_start=None, audience_growth_base=None)
        return

    growth_start = parse_time(row["audience_growth_start"])
    if growth_start is None:
        # یه پنجره‌ی رشد جدید شروع کن از همین لحظه
        update_user_fields(user_id, audience_growth_start=now().isoformat(), audience_growth_base=audience)
        return

    growth_base = row["audience_growth_base"] if row["audience_growth_base"] is not None else audience
    elapsed_hours = (now() - growth_start).total_seconds() / 3600
    fraction = min(1.0, elapsed_hours / AUDIENCE_GROWTH_HOURS)
    grown = growth_base + int(round(fraction * (capacity - growth_base)))
    new_audience = min(capacity, max(audience, grown))

    if new_audience != audience:
        update_user_fields(user_id, track_audience=new_audience)

    if fraction >= 1.0:
        update_user_fields(user_id, audience_growth_start=None, audience_growth_base=None)


# ---------------------------------------------------------
# بازار روزانه‌ی اسب
# ---------------------------------------------------------

def refresh_daily_market():
    today = date.today().isoformat()
    stored_date = get_setting("market_date")
    if stored_date == today:
        return

    with db_lock:
        conn = get_conn()
        for breed_key, info in HORSE_BREEDS.items():
            if breed_key == STARTER_BREED:
                continue
            chance = info["rarity_days_per_week"] / 7
            available = 1 if random.random() < chance else 0
            conn.execute(
                """INSERT INTO daily_market (breed_key, market_date, available) VALUES (?, ?, ?)
                   ON CONFLICT(breed_key) DO UPDATE SET market_date=excluded.market_date, available=excluded.available""",
                (breed_key, today, available)
            )
        conn.commit()
        conn.close()
    set_setting("market_date", today)


def get_market():
    refresh_daily_market()
    with db_lock:
        conn = get_conn()
        rows = conn.execute("SELECT * FROM daily_market").fetchall()
        conn.close()
        return {r["breed_key"]: bool(r["available"]) for r in rows}


def get_today_weather():
    """آب‌وهوای امروز رو برمی‌گردونه؛ اگه هنوز برای امروز تعیین نشده، یه‌بار رندوم انتخاب و ذخیره می‌کنه."""
    today = date.today().isoformat()
    stored_date = get_setting("weather_date")
    if stored_date == today:
        return get_setting("weather_type") or "cloudy"

    weather_type = random.choice(list(WEATHER_TYPES.keys()))
    set_setting("weather_date", today)
    set_setting("weather_type", weather_type)
    return weather_type


# =========================================================
#                    🤖  راه‌اندازی ربات  🤖
# =========================================================

bot = telebot.TeleBot(TOKEN, parse_mode=None)

_proxy = os.environ.get("https_proxy") or os.environ.get("http_proxy")
if _proxy:
    telebot.apihelper.proxy = {"https": _proxy}


def is_group(message):
    return message.chat.type in ("group", "supergroup")


def group_only(func):
    def wrapper(message):
        if not is_group(message):
            bot.reply_to(message, "این بازی فقط توی گروه قابل بازیه 🐴")
            return
        mark_chat_active(message.chat.id)
        user_id = message.from_user.id
        username = message.from_user.username or message.from_user.first_name or ""
        ensure_user(user_id, username)
        process_audience_returns(user_id)
        apply_audience_growth(user_id)
        return func(message)
    return wrapper


def broadcast_to_all_chats(text):
    """پیام رو به همه‌ی گروه‌هایی که ربات توشون فعاله می‌فرسته (نه فقط آخرین گروه)."""
    for chat_id in get_active_chat_ids():
        try:
            bot.send_message(int(chat_id), text)
        except Exception:
            pass


def display_name_of(message):
    return message.from_user.username or message.from_user.first_name or str(message.from_user.id)


# =========================================================
#                    🐴 اسب و پیست 🐴
# =========================================================

def format_horse_line(index, horse):
    breed = HORSE_BREEDS[horse["breed_key"]]
    status = ""
    if is_horse_racing(horse):
        remaining = parse_time(horse["racing_until"]) - now()
        minutes_left = max(0, int(remaining.total_seconds() // 60) + 1)
        status = f" 🏃 (تو پیست، {minutes_left} دقیقه مونده)"
    shoe = ""
    if horse["horseshoe"] == "good":
        shoe = " 🔨(نعل خوب)"
    elif horse["horseshoe"] == "great":
        shoe = " 🔨(نعل عالی)"

    emotion = get_horse_emotion(horse)
    emotion_text = EMOTION_DISPLAY.get(emotion, "😊 شاد")

    return (
        f"{index}. {breed['display']}{shoe}\n"
        f"   ⚡ انرژی: {horse['energy']}/{breed['energy_max']}   "
        f"🌾 گشنگی: {horse['hunger']}/{breed['hunger_max']}\n"
        f"   {emotion_text}{status}"
    )


@bot.message_handler(commands=["نسخه", "version"])
def handle_version(message):
    # فقط برای تست اینکه رندر واقعاً آخرین نسخه رو دیپلوی کرده یا نه -- کاملاً بی‌خطر
    bot.reply_to(message, "🔖 نسخه: v-2026-08-23-war-unique-round-key")


@bot.message_handler(commands=["اسب", "horse"])
@group_only
def handle_horses(message):
    user_id = message.from_user.id
    horses = get_horses(user_id)
    if not horses:
        bot.reply_to(message, "هنوز اسبی نداری!")
        return

    lines = ["🐴 اسب‌های تو:\n"]
    for i, horse in enumerate(horses, start=1):
        horse = apply_energy_regen(horse)
        lines.append(format_horse_line(i, horse))
    bot.reply_to(message, "\n\n".join(lines))


@bot.message_handler(commands=["بدو", "run"])
@group_only
def handle_race(message):
    user_id = message.from_user.id
    parts = message.text.strip().split()
    if len(parts) < 2 or not parts[1].isdigit():
        bot.reply_to(message, "طرز استفاده: /بدو <شماره اسب>\nمثال: /بدو 1")
        return

    index = int(parts[1])
    result = _do_race(user_id, index, message.chat.id)
    bot.reply_to(message, result)


def finish_race(user_id, chat_id, coins_earned, performance, horse_index):
    adjust_coins(user_id, coins_earned)

    horse = get_horse_by_index(user_id, horse_index)
    if horse is not None:
        update_horse(
            horse["id"],
            race_settled=1,
            race_chat_id=None,
            race_coins_earned=None,
            race_performance=None,
        )

    performance_text = {
        "excellent": "🌟 عملکرد عالی",
        "average": "🙂 عملکرد متوسط",
        "poor": "😞 عملکرد ضعیف (چندتا تماشاچی ناراضی رفتن)",
    }[performance]

    user = get_user_row(user_id)
    name_tag = f"@{user['username']}" if user and user.get("username") else "کاربر"

    try:
        bot.send_message(
            chat_id,
            f"🏁 {name_tag} نتیجه‌ی مسابقه‌ی اسب شماره {horse_index}:\n"
            f"{performance_text}\n"
            f"💰 {coins_earned} سکه به کیف پولت اضافه شد!"
        )
    except Exception:
        pass


@bot.message_handler(commands=["غذا", "feed"])
@group_only
def handle_feed(message):
    user_id = message.from_user.id
    parts = message.text.strip().split()
    if len(parts) < 2 or not parts[1].isdigit():
        bot.reply_to(message, "طرز استفاده: /غذا <شماره اسب>\nمثال: /غذا 1")
        return

    index = int(parts[1])
    horse = get_horse_by_index(user_id, index)
    if horse is None:
        bot.reply_to(message, "همچین اسبی نداری!")
        return

    breed = HORSE_BREEDS[horse["breed_key"]]
    if horse["hunger"] >= breed["hunger_max"]:
        bot.reply_to(message, "این اسب سیره، نیازی به غذا نداره 🌾")
        return

    # قبل از تغییر گشنگی، بدهی انرژی رو با نرخ قدیمی تسویه کن تا محاسبه دقیق بمونه
    horse = apply_energy_regen(horse)

    ok, remaining_hay = adjust_hay(user_id, -HAY_PER_FEED_UNIT)
    if not ok:
        bot.reply_to(
            message,
            f"یونجه‌ی کافی نداری! هر وعده {HAY_PER_FEED_UNIT} یونجه لازمه و تو {remaining_hay} تا داری."
        )
        return

    update_horse(horse["id"], hunger=horse["hunger"] + 1)
    bot.reply_to(message, f"🌾 به اسب شماره {index} غذا دادی! گشنگی: {horse['hunger']+1}/{breed['hunger_max']}")


# =========================================================
#                    🌾 مزرعه 🌾
# =========================================================

@bot.message_handler(commands=["مزرعه", "farm"])
@group_only
def handle_farm(message):
    user_id = message.from_user.id
    plots = get_plots(user_id)
    plots = [refresh_plot_status(p) for p in plots]

    lines = ["🌾 وضعیت مزرعه:\n"]
    status_fa = {"empty": "🟫 خالی", "growing": "🌱 در حال رشد", "ready": "✅ آماده‌ی برداشت"}
    for i, plot in enumerate(plots, start=1):
        line = f"{i}. قطعه ({PLOT_BUSHES} بوته) — {status_fa[plot['status']]}"
        if plot["status"] == "growing":
            planted_at = parse_time(plot["planted_at"])
            remaining = PLOT_GROW_MINUTES - (now() - planted_at).total_seconds() / 60
            line += f" (حدود {max(0,int(remaining))} دقیقه مونده)"
        lines.append(line)
    bot.reply_to(message, "\n".join(lines))


@bot.message_handler(commands=["بکار", "plant"])
@group_only
def handle_plant(message):
    user_id = message.from_user.id
    plots = get_plots(user_id)
    empty_plot = next((p for p in plots if p["status"] == "empty"), None)

    if empty_plot is None:
        bot.reply_to(message, "هیچ قطعه‌ی خالی نداری! یا صبر کن برداشت کنی، یا مزرعه رو با /ارتقا بزرگ کن.")
        return

    ok, remaining = adjust_coins(user_id, -PLOT_PLANT_COST)
    if not ok:
        bot.reply_to(message, f"سکه‌ی کافی نداری! کاشتن {PLOT_PLANT_COST} سکه هزینه داره و تو {remaining} تا داری.")
        return

    set_plot(empty_plot["id"], status="growing", planted_at=now().isoformat())
    bot.reply_to(message, f"🌱 کاشتی! تا {PLOT_GROW_MINUTES} دقیقه‌ی دیگه آماده‌ی برداشته.")


@bot.message_handler(commands=["برداشت", "harvest"])
@group_only
def handle_harvest(message):
    user_id = message.from_user.id
    plots = get_plots(user_id)
    plots = [refresh_plot_status(p) for p in plots]
    ready_plots = [p for p in plots if p["status"] == "ready"]

    if not ready_plots:
        bot.reply_to(message, "هیچ قطعه‌ی آماده‌ای نداری!")
        return

    weather = get_today_weather()
    hay_per_plot = int(HAY_PER_HARVEST * (1 + WEATHER_TYPES[weather]["hay_bonus"]))
    total_hay = len(ready_plots) * hay_per_plot
    for plot in ready_plots:
        set_plot(plot["id"], status="empty", planted_at=None)

    adjust_hay(user_id, total_hay)
    increment_setting_counter("daily_hay_harvested", total_hay)
    bot.reply_to(message, f"🌾 {len(ready_plots)} قطعه برداشت کردی و {total_hay} یونجه گرفتی!")


@bot.message_handler(commands=["انبار", "warehouse"])
@group_only
def handle_warehouse(message):
    user = get_user_row(message.from_user.id)
    bot.reply_to(message, f"🌾 موجودی انبار یونجه: {user['hay']}")


# =========================================================
#                    🎪 پیست 🎪
# =========================================================

@bot.message_handler(commands=["پیست", "track"])
@group_only
def handle_track(message):
    user_id = message.from_user.id
    process_audience_returns(user_id)
    apply_audience_growth(user_id)
    user = get_user_row(user_id)
    bot.reply_to(
        message,
        f"🎪 وضعیت پیست:\n"
        f"👥 تماشاچی: {user['track_audience']}/{user['track_capacity']}\n"
        f"🎫 هر بلیط: {TICKET_PRICE} سکه"
    )


# =========================================================
#                    🏠 طویله و ارتقاها 🏠
# =========================================================

def upgrade_price(base_price, upgrades_done):
    return round(base_price * (UPGRADE_GROWTH_RATE ** upgrades_done))


@bot.message_handler(commands=["طویله", "stable"])
@group_only
def handle_stable(message):
    user_id = message.from_user.id
    user = get_user_row(user_id)
    horses_count = len(get_horses(user_id))
    bot.reply_to(
        message,
        f"🏠 طویله:\n"
        f"🐴 ظرفیت: {horses_count}/{user['stable_capacity']}"
    )


@bot.message_handler(commands=["ارتقا", "upgrade"])
@group_only
def handle_upgrade_info(message):
    user = get_user_row(message.from_user.id)

    stable_price = upgrade_price(UPGRADE_BASE_PRICES["stable"], user["stable_upgrades"])
    track_price = upgrade_price(UPGRADE_BASE_PRICES["track"], user["track_upgrades"])
    farm_price = upgrade_price(UPGRADE_BASE_PRICES["farm"], user["farm_upgrades"])

    text = (
        "🏗️ ارتقاهای موجود:\n\n"
        f"🏠 بزرگ کردن طویله (+۱ جای اسب)\n"
        f"   قیمت: {stable_price} سکه — دستور: /ارتقا_طویله\n\n"
        f"🎪 بزرگ کردن پیست (+۵ ظرفیت تماشاچی)\n"
        f"   قیمت: {track_price} سکه — دستور: /ارتقا_پیست\n\n"
        f"🌾 بزرگ کردن مزرعه (+۱ قطعه‌ی کاشت)\n"
        f"   قیمت: {farm_price} سکه — دستور: /ارتقا_مزرعه"
    )
    bot.reply_to(message, text)


@bot.message_handler(commands=["ارتقا_طویله"])
@group_only
def handle_upgrade_stable(message):
    user_id = message.from_user.id
    user = get_user_row(user_id)
    price = upgrade_price(UPGRADE_BASE_PRICES["stable"], user["stable_upgrades"])

    ok, remaining = adjust_coins(user_id, -price)
    if not ok:
        bot.reply_to(message, f"سکه‌ی کافی نداری! این ارتقا {price} سکه هزینه داره و تو {remaining} تا داری.")
        return

    update_user_fields(
        user_id,
        stable_capacity=user["stable_capacity"] + 1,
        stable_upgrades=user["stable_upgrades"] + 1
    )
    bot.reply_to(message, f"🏠 طویله بزرگ‌تر شد! ظرفیت جدید: {user['stable_capacity']+1}")


@bot.message_handler(commands=["ارتقا_پیست"])
@group_only
def handle_upgrade_track(message):
    user_id = message.from_user.id
    user = get_user_row(user_id)
    price = upgrade_price(UPGRADE_BASE_PRICES["track"], user["track_upgrades"])

    ok, remaining = adjust_coins(user_id, -price)
    if not ok:
        bot.reply_to(message, f"سکه‌ی کافی نداری! این ارتقا {price} سکه هزینه داره و تو {remaining} تا داری.")
        return

    update_user_fields(
        user_id,
        track_capacity=user["track_capacity"] + 5,
        track_upgrades=user["track_upgrades"] + 1
    )
    bot.reply_to(message, f"🎪 پیست بزرگ‌تر شد! ظرفیت جدید تماشاچی: {user['track_capacity']+5}")


@bot.message_handler(commands=["ارتقا_مزرعه"])
@group_only
def handle_upgrade_farm(message):
    user_id = message.from_user.id
    user = get_user_row(user_id)
    price = upgrade_price(UPGRADE_BASE_PRICES["farm"], user["farm_upgrades"])

    ok, remaining = adjust_coins(user_id, -price)
    if not ok:
        bot.reply_to(message, f"سکه‌ی کافی نداری! این ارتقا {price} سکه هزینه داره و تو {remaining} تا داری.")
        return

    add_plot(user_id)
    update_user_fields(user_id, farm_upgrades=user["farm_upgrades"] + 1)
    bot.reply_to(message, "🌾 یه قطعه‌ی جدید به مزرعه اضافه شد!")


# =========================================================
#                    🐎 بازار اسب 🐎
# =========================================================

@bot.message_handler(commands=["فروشگاه_اسب", "horsemarket"])
@group_only
def handle_horse_market(message):
    market = get_market()
    lines = ["🐎 بازار اسب امروز:\n"]
    any_available = False
    for breed_key, info in HORSE_BREEDS.items():
        if breed_key == STARTER_BREED:
            continue
        if market.get(breed_key):
            any_available = True
            lines.append(
                f"✅ {info['display']} — {info['price']} سکه\n"
                f"   (خرید: /خرید_اسب {breed_key})"
            )
        else:
            lines.append(f"❌ {info['display']} — امروز موجود نیست")
    if not any_available:
        lines.append("\nامروز هیچ اسبی موجود نیست، فردا دوباره سر بزن!")
    bot.reply_to(message, "\n\n".join(lines))


@bot.message_handler(commands=["خرید_اسب"])
@group_only
def handle_buy_horse(message):
    user_id = message.from_user.id
    parts = message.text.strip().split()
    if len(parts) < 2 or parts[1] not in HORSE_BREEDS or parts[1] == STARTER_BREED:
        bot.reply_to(message, "طرز استفاده: /خرید_اسب <نام نژاد>\nلیست نژادها رو با /فروشگاه_اسب ببین.")
        return

    breed_key = parts[1]
    market = get_market()
    if not market.get(breed_key):
        bot.reply_to(message, "این نژاد امروز توی بازار موجود نیست!")
        return

    user = get_user_row(user_id)
    horses_count = len(get_horses(user_id))
    if horses_count >= user["stable_capacity"]:
        bot.reply_to(message, "طویله‌ت جا نداره! اول با /ارتقا_طویله بزرگش کن.")
        return

    price = HORSE_BREEDS[breed_key]["price"]
    ok, remaining = adjust_coins(user_id, -price)
    if not ok:
        bot.reply_to(message, f"سکه‌ی کافی نداری! این اسب {price} سکه هزینه داره و تو {remaining} تا داری.")
        return

    add_horse(user_id, breed_key)
    bot.reply_to(message, f"🎉 {HORSE_BREEDS[breed_key]['display']} رو خریدی! با /اسب ببینش.")


# =========================================================
#                    🛒 فروشگاه 🛒
# =========================================================

@bot.message_handler(commands=["فروشگاه", "shop"])
@group_only
def handle_shop(message):
    text = (
        "🛒 فروشگاه:\n\n"
        f"🌾 خرید ۱۰ یونجه: {SHOP_HAY_BUY_PER_10} سکه — /خرید_یونجه <مقدار>\n"
        f"🌾 فروش ۱۰ یونجه: {SHOP_HAY_SELL_PER_10} سکه — /فروش_یونجه <مقدار>\n"
        f"⚡ مکمل انرژی (پر کردن فوری): {SHOP_ENERGY_POTION_PRICE} سکه — /مکمل_انرژی <شماره اسب>\n"
        f"🔨 نعل خوب (۱۵٪ سریع‌تر): {SHOP_HORSESHOE_GOOD_PRICE} سکه — /نعل <شماره اسب> خوب\n"
        f"🔨 نعل عالی (۳۰٪ سریع‌تر): {SHOP_HORSESHOE_GREAT_PRICE} سکه — /نعل <شماره اسب> عالی"
    )
    bot.reply_to(message, text)


@bot.message_handler(commands=["خرید_یونجه"])
@group_only
def handle_buy_hay(message):
    user_id = message.from_user.id
    parts = message.text.strip().split()
    if len(parts) < 2 or not parts[1].isdigit() or int(parts[1]) <= 0:
        bot.reply_to(message, "طرز استفاده: /خرید_یونجه <مقدار>\nمثال: /خرید_یونجه 10")
        return

    amount = int(parts[1])
    cost = math.ceil(amount / 10 * SHOP_HAY_BUY_PER_10)

    ok, remaining = adjust_coins(user_id, -cost)
    if not ok:
        bot.reply_to(message, f"سکه‌ی کافی نداری! {amount} یونجه {cost} سکه هزینه داره و تو {remaining} تا داری.")
        return

    adjust_hay(user_id, amount)
    bot.reply_to(message, f"✅ {amount} یونجه خریدی! ({cost} سکه کم شد)")


@bot.message_handler(commands=["فروش_یونجه"])
@group_only
def handle_sell_hay(message):
    user_id = message.from_user.id
    parts = message.text.strip().split()
    if len(parts) < 2 or not parts[1].isdigit() or int(parts[1]) <= 0:
        bot.reply_to(message, "طرز استفاده: /فروش_یونجه <مقدار>\nمثال: /فروش_یونجه 10")
        return

    amount = int(parts[1])
    ok, remaining = adjust_hay(user_id, -amount)
    if not ok:
        bot.reply_to(message, f"یونجه‌ی کافی نداری! تو فقط {remaining} یونجه داری.")
        return

    earned = math.floor(amount / 10 * SHOP_HAY_SELL_PER_10)
    adjust_coins(user_id, earned)
    bot.reply_to(message, f"✅ {amount} یونجه فروختی و {earned} سکه گرفتی!")


@bot.message_handler(commands=["مکمل_انرژی"])
@group_only
def handle_energy_potion(message):
    user_id = message.from_user.id
    parts = message.text.strip().split()
    if len(parts) < 2 or not parts[1].isdigit():
        bot.reply_to(message, "طرز استفاده: /مکمل_انرژی <شماره اسب>\nمثال: /مکمل_انرژی 1")
        return

    index = int(parts[1])
    horse = get_horse_by_index(user_id, index)
    if horse is None:
        bot.reply_to(message, "همچین اسبی نداری!")
        return

    ok, remaining = adjust_coins(user_id, -SHOP_ENERGY_POTION_PRICE)
    if not ok:
        bot.reply_to(message, f"سکه‌ی کافی نداری! این مکمل {SHOP_ENERGY_POTION_PRICE} سکه هزینه داره و تو {remaining} تا داری.")
        return

    breed = HORSE_BREEDS[horse["breed_key"]]
    update_horse(horse["id"], energy=breed["energy_max"], last_energy_update=now().isoformat())
    bot.reply_to(message, f"⚡ انرژی اسب شماره {index} کامل پر شد!")


@bot.message_handler(commands=["نعل"])
@group_only
def handle_horseshoe(message):
    user_id = message.from_user.id
    parts = message.text.strip().split()
    if len(parts) < 3 or not parts[1].isdigit() or parts[2] not in ("خوب", "عالی"):
        bot.reply_to(message, "طرز استفاده: /نعل <شماره اسب> <خوب یا عالی>\nمثال: /نعل 1 خوب")
        return

    index = int(parts[1])
    horse = get_horse_by_index(user_id, index)
    if horse is None:
        bot.reply_to(message, "همچین اسبی نداری!")
        return

    grade = parts[2]
    price = SHOP_HORSESHOE_GOOD_PRICE if grade == "خوب" else SHOP_HORSESHOE_GREAT_PRICE
    shoe_value = "good" if grade == "خوب" else "great"

    current_shoe = horse.get("horseshoe") or "none"
    if HORSESHOE_LEVELS[shoe_value] <= HORSESHOE_LEVELS[current_shoe]:
        bot.reply_to(
            message,
            f"اسب شماره {index} از قبل نعل {HORSESHOE_DISPLAY[current_shoe]} داره که برابر یا بهتره؛ "
            f"نیازی به نعل {grade} نیست."
        )
        return

    ok, remaining = adjust_coins(user_id, -price)
    if not ok:
        bot.reply_to(message, f"سکه‌ی کافی نداری! نعل {grade} {price} سکه هزینه داره و تو {remaining} تا داری.")
        return

    update_horse(horse["id"], horseshoe=shoe_value)
    bot.reply_to(message, f"🔨 نعل {grade} به اسب شماره {index} زده شد!")


# =========================================================
#                    🤝 انتقال سکه 🤝
# =========================================================

@bot.message_handler(commands=["انتقال", "transfer"])
@group_only
def handle_transfer(message):
    user_id = message.from_user.id
    parts = message.text.strip().split()
    if len(parts) < 3 or not parts[1].startswith("@") or not parts[2].isdigit():
        bot.reply_to(message, "طرز استفاده: /انتقال @یوزرنیم مبلغ\nمثال: /انتقال @ali 50")
        return

    target_username = parts[1]
    amount = int(parts[2])
    if amount <= 0:
        bot.reply_to(message, "مبلغ باید مثبت باشه.")
        return

    target_user = find_user_by_username(target_username)
    if target_user is None:
        bot.reply_to(message, "این کاربر پیدا نشد. باید حداقل یه‌بار با ربات تعامل کرده باشه.")
        return

    if target_user["user_id"] == user_id:
        bot.reply_to(message, "نمی‌تونی به خودت سکه بفرستی!")
        return

    ok, remaining = adjust_coins(user_id, -amount)
    if not ok:
        bot.reply_to(message, f"سکه‌ی کافی نداری! تو فقط {remaining} سکه داری.")
        return

    adjust_coins(target_user["user_id"], amount)
    bot.reply_to(message, f"✅ {amount} سکه به {target_username} منتقل شد!")


@bot.message_handler(commands=["انتقال_یونجه"])
@group_only
def handle_transfer_hay(message):
    user_id = message.from_user.id
    parts = message.text.strip().split()
    if len(parts) < 3 or not parts[1].startswith("@") or not parts[2].isdigit():
        bot.reply_to(message, "طرز استفاده: /انتقال_یونجه @یوزرنیم مقدار\nمثال: /انتقال_یونجه @ali 20")
        return

    target_username = parts[1]
    amount = int(parts[2])
    if amount <= 0:
        bot.reply_to(message, "مقدار باید مثبت باشه.")
        return

    target_user = find_user_by_username(target_username)
    if target_user is None:
        bot.reply_to(message, "این کاربر پیدا نشد. باید حداقل یه‌بار با ربات تعامل کرده باشه.")
        return

    if target_user["user_id"] == user_id:
        bot.reply_to(message, "نمی‌تونی به خودت یونجه بفرستی!")
        return

    ok, remaining = adjust_hay(user_id, -amount)
    if not ok:
        bot.reply_to(message, f"یونجه‌ی کافی نداری! تو فقط {remaining} تا داری.")
        return

    adjust_hay(target_user["user_id"], amount)
    bot.reply_to(message, f"✅ {amount} یونجه به {target_username} منتقل شد!")


@bot.message_handler(commands=["انتقال_شیهه"])
@group_only
def handle_transfer_shihe(message):
    user_id = message.from_user.id
    parts = message.text.strip().split()
    if len(parts) < 3 or not parts[1].startswith("@") or not parts[2].isdigit():
        bot.reply_to(message, "طرز استفاده: /انتقال_شیهه @یوزرنیم مقدار\nمثال: /انتقال_شیهه @ali 30")
        return

    target_username = parts[1]
    amount = int(parts[2])
    if amount <= 0:
        bot.reply_to(message, "مقدار باید مثبت باشه.")
        return

    target_user = find_user_by_username(target_username)
    if target_user is None:
        bot.reply_to(message, "این کاربر پیدا نشد. باید حداقل یه‌بار با ربات تعامل کرده باشه.")
        return

    if target_user["user_id"] == user_id:
        bot.reply_to(message, "نمی‌تونی به خودت شیهه‌پوینت بفرستی!")
        return

    ok, remaining = adjust_shihe(user_id, -amount)
    if not ok:
        bot.reply_to(message, f"شیهه‌پوینت کافی نداری! تو فقط {remaining} تا داری.")
        return

    adjust_shihe(target_user["user_id"], amount)
    bot.reply_to(message, f"✅ {amount} شیهه‌پوینت به {target_username} منتقل شد!")


# =========================================================
#                    💰 کیف پول و راهنما 💰
# =========================================================

@bot.message_handler(commands=["پروفایل", "کیف_پول", "profile", "wallet"])
@group_only
def handle_wallet(message):
    user = get_user_row(message.from_user.id)
    level = compute_level(user)
    shihe = user.get("shihe_points") or 0
    text = (
        f"👤 پروفایل:\n\n"
        f"💰 سکه: {user['coins']}\n"
        f"🌾 یونجه: {user['hay']}\n"
        f"🌟 شیهه‌پوینت: {shihe}\n"
        f"📈 لول: {level}"
    )
    if level < LEAGUE_UNLOCK_LEVEL:
        needed = coins_needed_for_level(LEAGUE_UNLOCK_LEVEL) - (user.get("total_coins_earned") or 0)
        text += f"\n\n🔒 لیگ اسبی با لول {LEAGUE_UNLOCK_LEVEL} باز میشه ({max(0,needed)} سکه‌ی دیگه لازمه)"
    else:
        text += f"\n\n🏆 لیگ اسبی باز شده!"
    bot.reply_to(message, text)


HELP_TEXT = """🐴 به بازی «طویله» خوش اومدی!

📖 داستان:
یه طویله‌ی کوچیک داری با جای فقط یه اسب. اون اسبم یه کره‌اسب ضعیف، خسته و گشنه‌ست. کنار طویله یه تیکه زمین خالی هم هست که می‌تونی توش یونجه بکاری.

قراره باهم این طویله رو از صفر بسازیم: اول به اسبت غذا بده و بذار استراحت کنه، بعد بفرستش تو پیست تا بدوئه و برات از تماشاچیا سکه دربیاره. با اون سکه‌ها، یونجه بکار، طویله و پیست و مزرعه رو بزرگ‌تر کن، و کم‌کم اسبای بهتر و قوی‌تر بخر. هرچی بیشتر مراقب اسبت باشی (سیر و پرانرژی نگهش داری)، تو پیست بهتر می‌دوئه و پول بیشتری میاره.

━━━ 🐴 اسب ━━━
/اسب — وضعیت اسب‌هات
/بدو <شماره اسب> — فرستادن اسب به پیست

━━━ 🌾 مزرعه ━━━
/مزرعه — وضعیت قطعه‌های کاشت
/بکار — کاشتن یه قطعه‌ی خالی
/برداشت — برداشت قطعه‌های آماده

━━━ 🍽️ غذا و انبار ━━━
/انبار — موجودی یونجه
/غذا <شماره اسب> — غذا دادن به اسب

━━━ 🎪 پیست ━━━
/پیست — وضعیت تماشاچی‌ها

━━━ 🏠 طویله و ارتقا ━━━
/طویله — وضعیت طویله
/ارتقا — لیست ارتقاها با قیمت فعلی
/ارتقا_طویله — بزرگ کردن طویله
/ارتقا_پیست — بزرگ کردن پیست
/ارتقا_مزرعه — بزرگ کردن مزرعه

━━━ 🐎 بازار اسب ━━━
/فروشگاه_اسب — اسب‌های موجود امروز
/خرید_اسب <نژاد> — خرید اسب

━━━ 🛒 فروشگاه ━━━
/فروشگاه — لیست کالاها
/خرید_یونجه <مقدار>
/فروش_یونجه <مقدار>
/مکمل_انرژی <شماره اسب>
/نعل <شماره اسب> <خوب یا عالی>

━━━ 🤝 اجتماعی ━━━
/انتقال @یوزرنیم مبلغ — هدیه‌ی سکه
/انتقال_یونجه @یوزرنیم مقدار — هدیه‌ی یونجه
/انتقال_شیهه @یوزرنیم مقدار — هدیه‌ی شیهه‌پوینت

━━━ 🌟 شیهه‌پوینت ━━━
بنویس «شیهه» (بدون /) هر ۳۰ دقیقه یه‌بار برای گرفتن پوینت
/فروشگاه_شیهه — آیتم‌های درمان احساسات
/شفا <آیتم> <شماره اسب> — درمان اسب ناراحت/افسرده

━━━ 💰 عمومی ━━━
/پروفایل — سکه، یونجه، شیهه‌پوینت و لول
/منو — منوی دکمه‌ای بازی
/راهنما — همین صفحه

🎁 هر روز یه قرعه‌کشی خودکار برگزار میشه و یه نفر شانسی جایزه می‌گیره!"""


@bot.message_handler(commands=["start", "راهنما", "help"])
@group_only
def handle_help(message):
    bot.reply_to(message, HELP_TEXT)


# =========================================================
#                    🎛️ منو و دکمه‌های شیشه‌ای 🎛️
# =========================================================

from telebot import types

# نگه‌داشتن اینکه هر پیام‌منو مال کدوم کاربره، تا فقط خودش بتونه دکمه‌هاشو بزنه.
# تو دیتابیس ذخیره می‌شه (نه تو حافظه) که با ری‌استارت سرویس از بین نره.

def set_menu_owner(chat_id, message_id, user_id):
    with db_lock:
        conn = get_conn()
        try:
            conn.execute(
                "INSERT INTO menu_owners (chat_id, message_id, user_id) VALUES (?, ?, ?) "
                "ON CONFLICT(chat_id, message_id) DO UPDATE SET user_id=excluded.user_id",
                (chat_id, message_id, user_id)
            )
            conn.commit()
        except Exception:
            conn.commit()
        conn.close()


def get_menu_owner(chat_id, message_id):
    with db_lock:
        conn = get_conn()
        row = conn.execute(
            "SELECT user_id FROM menu_owners WHERE chat_id=? AND message_id=?",
            (chat_id, message_id)
        ).fetchone()
        conn.close()
        return row["user_id"] if row else None


def build_main_menu(user_id=None):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🐴 اسب‌ها", callback_data="menu:horses"),
        types.InlineKeyboardButton("🌾 مزرعه", callback_data="menu:farm"),
    )
    kb.add(
        types.InlineKeyboardButton("🎪 پیست", callback_data="menu:track"),
        types.InlineKeyboardButton("🏗️ ارتقاها", callback_data="menu:stable"),
    )
    kb.add(
        types.InlineKeyboardButton("🛒 فروشگاه", callback_data="menu:shop"),
        types.InlineKeyboardButton("👤 پروفایل", callback_data="menu:wallet"),
    )
    kb.add(
        types.InlineKeyboardButton("🐎 بازار اسب", callback_data="menu:horsemarket"),
        types.InlineKeyboardButton("🌟 فروشگاه شیهه", callback_data="shihe_shop:page1"),
    )
    if user_id is not None:
        user = get_user_row(user_id)
        if user and compute_level(user) >= LEAGUE_UNLOCK_LEVEL:
            kb.add(types.InlineKeyboardButton("🏆 لیگ اسبی", callback_data="league:main"))
    kb.add(
        types.InlineKeyboardButton("📖 راهنما", callback_data="menu:help"),
    )
    return kb


def back_button():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 برگشت به منو", callback_data="menu:main"))
    return kb


@bot.message_handler(commands=["منو", "menu"])
@group_only
def handle_menu(message):
    sent = bot.reply_to(message, "🐴 منوی طویله — یکی رو انتخاب کن:", reply_markup=build_main_menu(message.from_user.id))
    set_menu_owner(sent.chat.id, sent.message_id, message.from_user.id)


def render_horses_menu(user_id):
    horses = get_horses(user_id)
    if not horses:
        return "هنوز اسبی نداری!", back_button()

    lines = ["🐴 اسب‌های تو:\n"]
    kb = types.InlineKeyboardMarkup(row_width=2)
    for i, horse in enumerate(horses, start=1):
        horse = apply_energy_regen(horse)
        lines.append(format_horse_line(i, horse))
        if not is_horse_racing(horse):
            kb.add(
                types.InlineKeyboardButton(f"🏃 بدو (اسب {i})", callback_data=f"horse:run:{i}"),
                types.InlineKeyboardButton(f"🌾 غذا (اسب {i})", callback_data=f"horse:feed:{i}"),
            )
    kb.add(types.InlineKeyboardButton("🔙 برگشت به منو", callback_data="menu:main"))
    return "\n\n".join(lines), kb


def render_farm_menu(user_id):
    plots = get_plots(user_id)
    plots = [refresh_plot_status(p) for p in plots]
    status_fa = {"empty": "🟫 خالی", "growing": "🌱 در حال رشد", "ready": "✅ آماده‌ی برداشت"}

    lines = ["🌾 وضعیت مزرعه:\n"]
    for i, plot in enumerate(plots, start=1):
        line = f"{i}. قطعه ({PLOT_BUSHES} بوته) — {status_fa[plot['status']]}"
        if plot["status"] == "growing":
            planted_at = parse_time(plot["planted_at"])
            remaining = PLOT_GROW_MINUTES - (now() - planted_at).total_seconds() / 60
            line += f" (حدود {max(0,int(remaining))} دقیقه مونده)"
        lines.append(line)

    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🌱 بکار", callback_data="farm:plant"),
        types.InlineKeyboardButton("🌾 برداشت", callback_data="farm:harvest"),
    )
    kb.add(types.InlineKeyboardButton("🔙 برگشت به منو", callback_data="menu:main"))
    return "\n".join(lines), kb


def render_track_menu(user_id):
    process_audience_returns(user_id)
    apply_audience_growth(user_id)
    user = get_user_row(user_id)
    text = (
        f"🎪 وضعیت پیست:\n"
        f"👥 تماشاچی: {user['track_audience']}/{user['track_capacity']}\n"
        f"🎫 هر بلیط: {TICKET_PRICE} سکه"
    )
    return text, back_button()


def render_stable_menu(user_id):
    user = get_user_row(user_id)
    horses_count = len(get_horses(user_id))

    stable_price = upgrade_price(UPGRADE_BASE_PRICES["stable"], user["stable_upgrades"])
    track_price = upgrade_price(UPGRADE_BASE_PRICES["track"], user["track_upgrades"])
    farm_price = upgrade_price(UPGRADE_BASE_PRICES["farm"], user["farm_upgrades"])

    text = (
        f"🏗️ ارتقاها:\n"
        f"🐴 ظرفیت اسب: {horses_count}/{user['stable_capacity']}\n\n"
        f"🏗️ ارتقاها:\n"
        f"🏠 بزرگ کردن طویله — {stable_price} سکه\n"
        f"🎪 بزرگ کردن پیست — {track_price} سکه\n"
        f"🌾 بزرگ کردن مزرعه — {farm_price} سکه"
    )
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton(f"🏠 ارتقای طویله ({stable_price} سکه)", callback_data="upgrade:stable"),
        types.InlineKeyboardButton(f"🎪 ارتقای پیست ({track_price} سکه)", callback_data="upgrade:track"),
        types.InlineKeyboardButton(f"🌾 ارتقای مزرعه ({farm_price} سکه)", callback_data="upgrade:farm"),
    )
    kb.add(types.InlineKeyboardButton("🔙 برگشت به منو", callback_data="menu:main"))
    return text, kb


def render_shop_menu(user_id):
    text = (
        "🛒 فروشگاه:\n\n"
        f"⚡ مکمل انرژی: {SHOP_ENERGY_POTION_PRICE} سکه\n"
        f"🔨 نعل خوب: {SHOP_HORSESHOE_GOOD_PRICE} سکه\n"
        f"🔨 نعل عالی: {SHOP_HORSESHOE_GREAT_PRICE} سکه\n\n"
        "🌾 برای خرید/فروش یونجه از دستور استفاده کن:\n"
        "/خرید_یونجه <مقدار>\n"
        "/فروش_یونجه <مقدار>"
    )
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("⚡ خرید مکمل انرژی", callback_data="shop:choose_horse:energy"),
        types.InlineKeyboardButton("🔨 خرید نعل خوب", callback_data="shop:choose_horse:good"),
        types.InlineKeyboardButton("🔨 خرید نعل عالی", callback_data="shop:choose_horse:great"),
    )
    kb.add(types.InlineKeyboardButton("🔙 برگشت به منو", callback_data="menu:main"))
    return text, kb


def render_choose_horse_for_shop(user_id, item_type):
    horses = get_horses(user_id)
    if not horses:
        return "اسبی نداری!", back_button()
    kb = types.InlineKeyboardMarkup(row_width=1)
    for i, horse in enumerate(horses, start=1):
        breed = HORSE_BREEDS[horse["breed_key"]]
        kb.add(types.InlineKeyboardButton(
            f"اسب {i} — {breed['display']}",
            callback_data=f"shop:apply:{item_type}:{i}"
        ))
    kb.add(types.InlineKeyboardButton("🔙 برگشت", callback_data="menu:shop"))
    return "کدوم اسب؟", kb


def render_horsemarket_menu(user_id):
    market = get_market()
    user = get_user_row(user_id)
    horses_count = len(get_horses(user_id))

    lines = ["🐎 بازار اسب امروز:\n"]
    kb = types.InlineKeyboardMarkup(row_width=1)
    any_available = False
    for breed_key, info in HORSE_BREEDS.items():
        if breed_key == STARTER_BREED:
            continue
        if market.get(breed_key):
            any_available = True
            lines.append(f"✅ {info['display']} — {info['price']} سکه")
            kb.add(types.InlineKeyboardButton(
                f"خرید {info['display']} ({info['price']} سکه)",
                callback_data=f"horsemarket:buy:{breed_key}"
            ))
        else:
            lines.append(f"❌ {info['display']} — امروز موجود نیست")

    if not any_available:
        lines.append("\nامروز هیچ اسبی موجود نیست، فردا دوباره سر بزن!")

    if horses_count >= user["stable_capacity"]:
        lines.append("\n⚠️ طویله‌ت جا نداره! اول ارتقاش بده.")

    kb.add(types.InlineKeyboardButton("🔙 برگشت به منو", callback_data="menu:main"))
    return "\n".join(lines), kb


def render_wallet_menu(user_id):
    user = get_user_row(user_id)
    level = compute_level(user)
    shihe = user.get("shihe_points") or 0
    text = (
        f"👤 پروفایل:\n\n"
        f"💰 سکه: {user['coins']}\n"
        f"🌾 یونجه: {user['hay']}\n"
        f"🌟 شیهه‌پوینت: {shihe}\n"
        f"📈 لول: {level}"
    )
    return text, back_button()


@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = call.from_user.id
    username = call.from_user.username or call.from_user.first_name or ""

    owner_id = get_menu_owner(call.message.chat.id, call.message.message_id)
    if owner_id is not None and owner_id != user_id:
        bot.answer_callback_query(
            call.id, "این منو مال تو نیست! خودت /منو رو بزن 🐴", show_alert=True
        )
        return

    ensure_user(user_id, username)
    process_audience_returns(user_id)
    apply_audience_growth(user_id)

    data = call.data
    text, kb = None, None

    if data.startswith("dino:"):
        handle_dino_callback(call)
        return

    try:
        if data == "menu:main":
            text, kb = "🐴 منوی طویله — یکی رو انتخاب کن:", build_main_menu(user_id)

        elif data == "menu:horses":
            text, kb = render_horses_menu(user_id)

        elif data == "menu:farm":
            text, kb = render_farm_menu(user_id)

        elif data == "menu:track":
            text, kb = render_track_menu(user_id)

        elif data == "menu:stable":
            text, kb = render_stable_menu(user_id)

        elif data == "menu:shop":
            text, kb = render_shop_menu(user_id)

        elif data == "menu:wallet":
            text, kb = render_wallet_menu(user_id)

        elif data == "menu:horsemarket":
            text, kb = render_horsemarket_menu(user_id)

        elif data.startswith("horsemarket:buy:"):
            breed_key = data.split(":")[2]
            result = _do_buy_horse(user_id, breed_key)
            bot.answer_callback_query(call.id, result, show_alert=True)
            text, kb = render_horsemarket_menu(user_id)

        elif data == "menu:help":
            text, kb = HELP_TEXT, back_button()

        elif data == "league:main" or data == "league:back":
            text, kb = render_league_menu(user_id)

        elif data == "league:register":
            result = _do_league_register(user_id)
            bot.answer_callback_query(call.id, result, show_alert=True)
            text, kb = render_league_menu(user_id)

        elif data == "league:choose_horse":
            text, kb = render_league_choose_horse(user_id)

        elif data.startswith("league:race:"):
            index = int(data.split(":")[2])
            result_code, result_text = _do_league_race(user_id, index)
            bot.answer_callback_query(call.id, result_text, show_alert=True)
            text, kb = render_league_menu(user_id)

        elif data == "league:table":
            text, kb = render_league_table()

        elif data == "league:history":
            text, kb = render_league_history()

        elif data.startswith("horse:run:"):
            index = int(data.split(":")[2])
            result = _do_race(user_id, index, call.message.chat.id)
            bot.answer_callback_query(call.id, result, show_alert=True)
            text, kb = render_horses_menu(user_id)

        elif data.startswith("horse:feed:"):
            index = int(data.split(":")[2])
            result = _do_feed(user_id, index)
            bot.answer_callback_query(call.id, result, show_alert=True)
            text, kb = render_horses_menu(user_id)

        elif data == "farm:plant":
            result = _do_plant(user_id)
            bot.answer_callback_query(call.id, result, show_alert=True)
            text, kb = render_farm_menu(user_id)

        elif data == "farm:harvest":
            result = _do_harvest(user_id)
            bot.answer_callback_query(call.id, result, show_alert=True)
            text, kb = render_farm_menu(user_id)

        elif data == "upgrade:stable":
            result = _do_upgrade(user_id, "stable")
            bot.answer_callback_query(call.id, result, show_alert=True)
            text, kb = render_stable_menu(user_id)

        elif data == "upgrade:track":
            result = _do_upgrade(user_id, "track")
            bot.answer_callback_query(call.id, result, show_alert=True)
            text, kb = render_stable_menu(user_id)

        elif data == "upgrade:farm":
            result = _do_upgrade(user_id, "farm")
            bot.answer_callback_query(call.id, result, show_alert=True)
            text, kb = render_stable_menu(user_id)

        elif data.startswith("shop:choose_horse:"):
            item_type = data.split(":")[2]
            text, kb = render_choose_horse_for_shop(user_id, item_type)

        elif data.startswith("shop:apply:"):
            _, _, item_type, index_str = data.split(":")
            index = int(index_str)
            result = _do_shop_apply(user_id, item_type, index)
            bot.answer_callback_query(call.id, result, show_alert=True)
            text, kb = render_shop_menu(user_id)

        elif data == "shihe_shop:page1":
            text, kb = render_shihe_shop_page1()

        elif data == "shihe_shop:page2":
            text, kb = render_clothing_shop_page2()

        elif data.startswith("clothing:choose_horse:"):
            item_key = data.split(":", 2)[2]
            text, kb = render_choose_horse_for_clothing(user_id, item_key)

        elif data.startswith("clothing:apply:"):
            _, _, item_key, index_str = data.split(":")
            index = int(index_str)
            result = _do_buy_clothing(user_id, item_key, index)
            bot.answer_callback_query(call.id, result, show_alert=True)
            text, kb = render_clothing_shop_page2()

        else:
            bot.answer_callback_query(call.id)
            return

        bot.edit_message_text(
            text, call.message.chat.id, call.message.message_id, reply_markup=kb
        )
        bot.answer_callback_query(call.id)

    except Exception as e:
        try:
            bot.answer_callback_query(call.id, "یه مشکلی پیش اومد، دوباره امتحان کن.")
        except Exception:
            pass
        print("خطا در callback:", e)


# ---------------------------------------------------------
# توابع اجراکننده‌ی مشترک بین دستورات متنی و دکمه‌ها
# ---------------------------------------------------------

def _do_race(user_id, index, chat_id):
    horse = get_horse_by_index(user_id, index)
    if horse is None:
        return "همچین اسبی نداری!"
    if is_horse_racing(horse):
        return "این اسب همین الان تو پیسته!"

    horse = apply_energy_regen(horse)
    breed = HORSE_BREEDS[horse["breed_key"]]

    # عملکرد فقط بر اساس انرژی (گشنگی دیگه روی نتیجه‌ی مسابقه تأثیری نداره)
    energy_frac = horse["energy"] / breed["energy_max"]

    if horse["energy"] == 0:
        performance = "poor"
    elif energy_frac >= 0.5:
        performance = "excellent"
    else:
        performance = "average"

    new_energy = max(0, horse["energy"] - 1)
    new_hunger = max(0, horse["hunger"] - 1)

    increment_setting_counter("daily_races_count", 1)

    process_audience_returns(user_id)
    apply_audience_growth(user_id)
    user = get_user_row(user_id)
    audience = user["track_audience"]

    if performance == "excellent":
        coins_earned = audience * TICKET_PRICE
    elif performance == "average":
        coins_earned = int(audience * TICKET_PRICE * 0.5)
    else:
        coins_earned = int(audience * TICKET_PRICE * 0.2)
        fled = math.ceil(audience * AUDIENCE_FLEE_PERCENT)
        if fled > 0:
            update_user_fields(user_id, track_audience=audience - fled)
            schedule_audience_return(user_id, fled)

    duration_minutes = breed["race_minutes"]
    duration_minutes *= (1 + get_emotion_speed_factor(horse))
    weather = get_today_weather()
    duration_minutes *= (1 + WEATHER_TYPES[weather]["speed_bonus"])
    if horse["horseshoe"] == "good":
        duration_minutes *= (1 - HORSESHOE_GOOD_REDUCTION)
    elif horse["horseshoe"] == "great":
        duration_minutes *= (1 - HORSESHOE_GREAT_REDUCTION)
    duration_seconds = duration_minutes * 60

    racing_until = now() + timedelta(seconds=duration_seconds)

    # نکته‌ی مهم: ساعت انرژی رو به اندازه‌ی طول مسابقه جلو می‌بریم
    # تا این بازه‌ی زمانی جزو «استراحت» حساب نشه و انرژی توش رشد نکنه.
    last_update = parse_time(horse["last_energy_update"]) or now()
    new_last_update = last_update + timedelta(seconds=duration_seconds)

    update_horse(
        horse["id"],
        energy=new_energy,
        hunger=new_hunger,
        racing_until=racing_until.isoformat(),
        last_energy_update=new_last_update.isoformat(),
        race_chat_id=chat_id,
        race_coins_earned=coins_earned,
        race_performance=performance,
        race_settled=0,
    )

    timer = threading.Timer(
        duration_seconds, finish_race,
        args=(user_id, chat_id, coins_earned, performance, index)
    )
    timer.daemon = True
    timer.start()

    minutes_display = max(1, round(duration_minutes))
    return f"🏁 اسب رفت تو پیست! {minutes_display} دقیقه‌ی دیگه نتیجه اعلام میشه."


def _do_feed(user_id, index):
    horse = get_horse_by_index(user_id, index)
    if horse is None:
        return "همچین اسبی نداری!"

    breed = HORSE_BREEDS[horse["breed_key"]]
    if horse["hunger"] >= breed["hunger_max"]:
        return "این اسب سیره!"

    # قبل از تغییر گشنگی، بدهی انرژی رو با نرخ قدیمی تسویه کن تا محاسبه دقیق بمونه
    horse = apply_energy_regen(horse)

    ok, remaining_hay = adjust_hay(user_id, -HAY_PER_FEED_UNIT)
    if not ok:
        return f"یونجه‌ی کافی نداری! ({remaining_hay} تا داری)"

    update_horse(horse["id"], hunger=horse["hunger"] + 1)
    return f"🌾 غذا دادی! گشنگی: {horse['hunger']+1}/{breed['hunger_max']}"


def _do_plant(user_id):
    plots = get_plots(user_id)
    empty_plot = next((p for p in plots if p["status"] == "empty"), None)
    if empty_plot is None:
        return "قطعه‌ی خالی نداری!"

    ok, remaining = adjust_coins(user_id, -PLOT_PLANT_COST)
    if not ok:
        return f"سکه‌ی کافی نداری! ({remaining} تا داری)"

    set_plot(empty_plot["id"], status="growing", planted_at=now().isoformat())
    return f"🌱 کاشتی! تا {PLOT_GROW_MINUTES} دقیقه آماده‌ست."


def _do_harvest(user_id):
    plots = get_plots(user_id)
    plots = [refresh_plot_status(p) for p in plots]
    ready_plots = [p for p in plots if p["status"] == "ready"]
    if not ready_plots:
        return "قطعه‌ی آماده‌ای نداری!"

    weather = get_today_weather()
    hay_per_plot = int(HAY_PER_HARVEST * (1 + WEATHER_TYPES[weather]["hay_bonus"]))
    total_hay = len(ready_plots) * hay_per_plot
    for plot in ready_plots:
        set_plot(plot["id"], status="empty", planted_at=None)
    adjust_hay(user_id, total_hay)
    increment_setting_counter("daily_hay_harvested", total_hay)
    return f"🌾 {len(ready_plots)} قطعه برداشت کردی و {total_hay} یونجه گرفتی!"


def _do_upgrade(user_id, kind):
    user = get_user_row(user_id)
    field_map = {
        "stable": ("stable_upgrades", "stable_capacity", 1),
        "track": ("track_upgrades", "track_capacity", 5),
        "farm": ("farm_upgrades", None, None),
    }
    upgrades_field, capacity_field, increment = field_map[kind]
    price = upgrade_price(UPGRADE_BASE_PRICES[kind], user[upgrades_field])

    ok, remaining = adjust_coins(user_id, -price)
    if not ok:
        return f"سکه‌ی کافی نداری! ({remaining} تا داری، {price} لازمه)"

    if kind == "farm":
        add_plot(user_id)
        update_user_fields(user_id, farm_upgrades=user["farm_upgrades"] + 1)
        return "🌾 یه قطعه‌ی جدید اضافه شد!"
    else:
        update_user_fields(user_id, **{
            capacity_field: user[capacity_field] + increment,
            upgrades_field: user[upgrades_field] + 1
        })
        return "✅ ارتقا انجام شد!"


def _do_buy_horse(user_id, breed_key):
    if breed_key not in HORSE_BREEDS or breed_key == STARTER_BREED:
        return "این نژاد وجود نداره!"

    market = get_market()
    if not market.get(breed_key):
        return "این نژاد امروز موجود نیست!"

    user = get_user_row(user_id)
    horses_count = len(get_horses(user_id))
    if horses_count >= user["stable_capacity"]:
        return "طویله‌ت جا نداره! اول ارتقاش بده."

    price = HORSE_BREEDS[breed_key]["price"]
    ok, remaining = adjust_coins(user_id, -price)
    if not ok:
        return f"سکه‌ی کافی نداری! ({remaining} تا داری، {price} لازمه)"

    add_horse(user_id, breed_key)
    return f"🎉 {HORSE_BREEDS[breed_key]['display']} رو خریدی!"


def _do_shop_apply(user_id, item_type, index):
    horse = get_horse_by_index(user_id, index)
    if horse is None:
        return "همچین اسبی نداری!"

    if item_type == "energy":
        ok, remaining = adjust_coins(user_id, -SHOP_ENERGY_POTION_PRICE)
        if not ok:
            return f"سکه‌ی کافی نداری! ({remaining} تا داری)"
        breed = HORSE_BREEDS[horse["breed_key"]]
        update_horse(horse["id"], energy=breed["energy_max"], last_energy_update=now().isoformat())
        return "⚡ انرژی کامل پر شد!"

    elif item_type in ("good", "great"):
        price = SHOP_HORSESHOE_GOOD_PRICE if item_type == "good" else SHOP_HORSESHOE_GREAT_PRICE
        current_shoe = horse.get("horseshoe") or "none"
        if HORSESHOE_LEVELS[item_type] <= HORSESHOE_LEVELS[current_shoe]:
            return (
                f"اسب شماره {index} از قبل نعل {HORSESHOE_DISPLAY[current_shoe]} داره که برابر یا بهتره؛ "
                f"نیازی به این نعل نیست."
            )
        ok, remaining = adjust_coins(user_id, -price)
        if not ok:
            return f"سکه‌ی کافی نداری! ({remaining} تا داری)"
        update_horse(horse["id"], horseshoe=item_type)
        return "🔨 نعل زده شد!"

    return "چیز نامعتبری بود."


# =========================================================
#                    🐴 شیهه‌پوینت و احساسات اسب 🐴
# =========================================================

@bot.message_handler(func=lambda m: m.text and m.text.strip() == "شیهه")
@group_only
def handle_shihe_point(message):
    user_id = message.from_user.id
    user = get_user_row(user_id)

    last_shihe = parse_time(user.get("last_shihe"))
    if last_shihe:
        remaining = last_shihe + timedelta(minutes=SHIHE_COOLDOWN_MINUTES) - now()
        if remaining.total_seconds() > 0:
            minutes = int(remaining.total_seconds() // 60) + 1
            bot.reply_to(message, f"⏳ اسبت هنوز نفس نگرفته، {minutes} دقیقه‌ی دیگه دوباره شیهه بزن.")
            return

    points = random.randint(SHIHE_MIN_POINTS, SHIHE_MAX_POINTS)
    with db_lock:
        conn = get_conn()
        row = conn.execute("SELECT shihe_points FROM users WHERE user_id=?", (user_id,)).fetchone()
        new_total = (row["shihe_points"] or 0) + points
        conn.execute(
            "UPDATE users SET shihe_points=?, last_shihe=? WHERE user_id=?",
            (new_total, now().isoformat(), user_id)
        )
        conn.commit()
        conn.close()

    bot.reply_to(message, f"🐴 شیهه! {points} شیهه‌پوینت گرفتی. 🌟 (مجموع: {new_total})")


def render_shihe_shop_page1():
    lines = ["🌟 فروشگاه شیهه‌پوینت — صفحه‌ی ۱: آیتم‌های درمان احساسات\n"]
    for key, (name, hours, price) in SHIHE_HEALING_ITEMS.items():
        price_text = "رایگان" if price == 0 else f"{price} شیهه‌پوینت"
        lines.append(f"{name} — درمان در {hours} ساعت — {price_text}\n   خرید: /شفا {key} <شماره اسب>")
    text = "\n".join(lines)

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("➡️ صفحه‌ی بعد: لباس و تزئینات", callback_data="shihe_shop:page2"))
    kb.add(types.InlineKeyboardButton("🔙 برگشت به منو", callback_data="menu:main"))
    return text, kb


def render_shihe_shop_text():
    text, _ = render_shihe_shop_page1()
    return text


def render_clothing_shop_page2():
    lines = ["👗 فروشگاه شیهه‌پوینت — صفحه‌ی ۲: لباس و تزئینات\n"]
    lines.append("هرچی بیشتر روی لباس اسبت خرج کنی، شانس بردت تو مسابقه‌ی زیبایی (دوشنبه و پنجشنبه) بیشتره!\n")
    for key, (name, price) in CLOTHING_ITEMS.items():
        lines.append(f"{name} — {price} شیهه‌پوینت")
    text = "\n".join(lines)

    kb = types.InlineKeyboardMarkup(row_width=1)
    for key, (name, price) in CLOTHING_ITEMS.items():
        kb.add(types.InlineKeyboardButton(f"{name} ({price})", callback_data=f"clothing:choose_horse:{key}"))
    kb.add(types.InlineKeyboardButton("⬅️ صفحه‌ی قبل", callback_data="shihe_shop:page1"))
    kb.add(types.InlineKeyboardButton("🔙 برگشت به منو", callback_data="menu:main"))
    return text, kb


def render_choose_horse_for_clothing(user_id, item_key):
    horses = get_horses(user_id)
    if not horses:
        return "اسبی نداری!", back_button()
    kb = types.InlineKeyboardMarkup(row_width=1)
    for i, horse in enumerate(horses, start=1):
        breed = HORSE_BREEDS[horse["breed_key"]]
        kb.add(types.InlineKeyboardButton(
            f"اسب {i} — {breed['display']}",
            callback_data=f"clothing:apply:{item_key}:{i}"
        ))
    kb.add(types.InlineKeyboardButton("🔙 برگشت", callback_data="shihe_shop:page2"))
    return "کدوم اسب می‌خوای بپوشونیش؟", kb


def _do_buy_clothing(user_id, item_key, index):
    if item_key not in CLOTHING_ITEMS:
        return "این آیتم وجود نداره!"

    horse = get_horse_by_index(user_id, index)
    if horse is None:
        return "همچین اسبی نداری!"

    name, price = CLOTHING_ITEMS[item_key]

    with db_lock:
        conn = get_conn()
        row = conn.execute("SELECT shihe_points, decoration_spent FROM users WHERE user_id=?", (user_id,)).fetchone()
        current_points = row["shihe_points"] or 0
        if current_points < price:
            conn.close()
            return f"شیهه‌پوینت کافی نداری! {name} قیمتش {price} تاست و تو {current_points} تا داری."
        new_decoration = (row["decoration_spent"] or 0) + price
        conn.execute(
            "UPDATE users SET shihe_points=?, decoration_spent=? WHERE user_id=?",
            (current_points - price, new_decoration, user_id)
        )
        conn.commit()
        conn.close()

    update_horse(horse["id"], clothing=item_key)
    return f"{name} رو پوشوندی به اسب شماره {index}! 🎉"


@bot.message_handler(commands=["فروشگاه_شیهه"])
@group_only
def handle_shihe_shop(message):
    text, kb = render_shihe_shop_page1()
    bot.reply_to(message, text, reply_markup=kb)


@bot.message_handler(commands=["خرید_لباس"])
@group_only
def handle_buy_clothing_command(message):
    user_id = message.from_user.id
    parts = message.text.strip().split()
    if len(parts) < 3 or parts[1] not in CLOTHING_ITEMS or not parts[2].isdigit():
        bot.reply_to(message, "طرز استفاده: /خرید_لباس <کلید آیتم> <شماره اسب>\nلیست آیتم‌ها با /فروشگاه_شیهه")
        return
    result = _do_buy_clothing(user_id, parts[1], int(parts[2]))
    bot.reply_to(message, result)


@bot.message_handler(commands=["شفا"])
@group_only
def handle_heal_horse(message):
    user_id = message.from_user.id
    parts = message.text.strip().split()
    if len(parts) < 3 or parts[1] not in SHIHE_HEALING_ITEMS or not parts[2].isdigit():
        bot.reply_to(message, "طرز استفاده: /شفا <آیتم> <شماره اسب>\nمثال: /شفا بز 1\nلیست آیتم‌ها: /فروشگاه_شیهه")
        return

    item_key = parts[1]
    index = int(parts[2])
    horse = get_horse_by_index(user_id, index)
    if horse is None:
        bot.reply_to(message, "همچین اسبی نداری!")
        return

    emotion = get_horse_emotion(horse)
    if emotion not in NEGATIVE_EMOTIONS:
        bot.reply_to(message, f"این اسب مشکلی نداره! وضعیت فعلیش: {EMOTION_DISPLAY.get(emotion)}")
        return

    name, heal_hours, price = SHIHE_HEALING_ITEMS[item_key]

    with db_lock:
        conn = get_conn()
        row = conn.execute("SELECT shihe_points FROM users WHERE user_id=?", (user_id,)).fetchone()
        current_points = row["shihe_points"] or 0
        if current_points < price:
            conn.close()
            bot.reply_to(message, f"شیهه‌پوینت کافی نداری! {name} قیمتش {price} تاست و تو {current_points} تا داری.")
            return
        conn.execute(
            "UPDATE users SET shihe_points=? WHERE user_id=?",
            (current_points - price, user_id)
        )
        conn.commit()
        conn.close()

    new_until = now() + timedelta(hours=heal_hours)
    update_horse(horse["id"], emotion_until=new_until.isoformat())

    bot.reply_to(
        message,
        f"{name} رو کنار اسب شماره {index} گذاشتی! تا {heal_hours} ساعت دیگه حالش خوب میشه."
    )


def emotion_check_loop():
    """هر چند دقیقه یه‌بار چک می‌کنه: احساسات منفی که زمانشون تموم شده رو درمان می‌کنه،
    و اسبایی که وقت رول جدید احساسشون رسیده رو دوباره رندوم می‌کنه."""
    while True:
        time.sleep(EMOTION_CHECK_LOOP_SECONDS)
        try:
            with db_lock:
                conn = get_conn()
                horses = conn.execute("SELECT * FROM horses").fetchall()
                conn.close()

            for h in horses:
                horse = dict(h)
                emotion = get_horse_emotion(horse)
                next_roll = parse_time(horse.get("emotion_next_roll"))

                if emotion in NEGATIVE_EMOTIONS:
                    emotion_until = parse_time(horse.get("emotion_until"))
                    if emotion_until and emotion_until <= now():
                        new_next_roll = now() + timedelta(hours=EMOTION_ROLL_INTERVAL_HOURS)
                        update_horse(
                            horse["id"], emotion="happy", emotion_until=None,
                            emotion_next_roll=new_next_roll.isoformat()
                        )
                else:
                    if next_roll and next_roll <= now():
                        new_emotion = roll_random_emotion()
                        new_next_roll = now() + timedelta(hours=EMOTION_ROLL_INTERVAL_HOURS)
                        fields = {"emotion": new_emotion, "emotion_next_roll": new_next_roll.isoformat()}
                        if new_emotion in NEGATIVE_EMOTIONS:
                            fields["emotion_until"] = (now() + timedelta(hours=EMOTION_NATURAL_HEAL_HOURS)).isoformat()
                        else:
                            fields["emotion_until"] = None
                        update_horse(horse["id"], **fields)
        except Exception as e:
            print("خطا در چک احساسات:", e)


# =========================================================
#                    🎰 قرعه‌کشی روزانه 🎰
# =========================================================

def lottery_loop():
    while True:
        time.sleep(LOTTERY_CHECK_INTERVAL_SECONDS)
        try:
            today = date.today().isoformat()
            last_run = get_setting("lottery_date")
            if last_run == today:
                continue

            user_ids = get_all_user_ids()
            if not user_ids:
                set_setting("lottery_date", today)
                continue

            winner_id = random.choice(user_ids)
            prize_type = random.choice(["coins", "hay"])
            if prize_type == "coins":
                adjust_coins(winner_id, LOTTERY_PRIZE)
                prize_text = f"{LOTTERY_PRIZE} سکه"
            else:
                adjust_hay(winner_id, LOTTERY_PRIZE)
                prize_text = f"{LOTTERY_PRIZE} یونجه"

            set_setting("lottery_date", today)

            winner = get_user_row(winner_id)
            name = winner["username"] or f"کاربر{winner_id}"
            set_setting("last_lottery_winner_name", name)
            set_setting("last_lottery_prize_text", prize_text)
            broadcast_to_all_chats(f"🎰 قرعه‌کشی امروز!\n🎉 برنده: {name}\n🎁 جایزه: {prize_text}")
        except Exception as e:
            print("خطا در قرعه‌کشی:", e)


# =========================================================
#                    📰 روزنامه‌ی عسبستان 📰
# =========================================================

IRAN_UTC_OFFSET_HOURS = 3.5
NEWSPAPER_HOUR = 22  # ساعت ۱۰ شب به وقت ایران
NEWSPAPER_CHECK_INTERVAL_SECONDS = 30


def iran_now():
    return datetime.utcnow() + timedelta(hours=IRAN_UTC_OFFSET_HOURS)


def publish_newspaper():
    hay_harvested = get_setting("daily_hay_harvested") or "0"
    races_count = get_setting("daily_races_count") or "0"
    weather = get_today_weather()
    weather_display = WEATHER_TYPES[weather]["display"]

    lottery_winner = get_setting("last_lottery_winner_name")
    lottery_prize = get_setting("last_lottery_prize_text")

    lines = [
        "📰 روزنامه‌ی عسبستان — شماره‌ی امروز\n",
        f"🌤️ آب‌وهوای امروز: {weather_display}",
        f"🌾 مجموع یونجه‌ی برداشت‌شده امروز: {hay_harvested}",
        f"🏁 مجموع مسابقاتی که امروز داده شد: {races_count}",
    ]
    if lottery_winner:
        lines.append(f"🎰 برنده‌ی قرعه‌کشی امروز: {lottery_winner} ({lottery_prize})")

    lines.append("\nشب همگی بخیر و اسبای همگی سالم و شاد باشن! 🐴💤")

    broadcast_to_all_chats("\n".join(lines))

    # ریست کردن شمارنده‌های روزانه برای فردا
    set_setting("daily_hay_harvested", "0")
    set_setting("daily_races_count", "0")


def newspaper_loop():
    while True:
        time.sleep(NEWSPAPER_CHECK_INTERVAL_SECONDS)
        try:
            current = iran_now()
            today = current.date().isoformat()
            last_published = get_setting("newspaper_date")

            if current.hour == NEWSPAPER_HOUR and last_published != today:
                publish_newspaper()
                set_setting("newspaper_date", today)
        except Exception as e:
            print("خطا در روزنامه:", e)


# =========================================================
#                    💃 مسابقه‌ی زیبایی 💃
# =========================================================

def run_beauty_contest():
    with db_lock:
        conn = get_conn()
        rows = conn.execute(
            "SELECT user_id, username, decoration_spent FROM users WHERE decoration_spent > 0"
        ).fetchall()
        conn.close()

    if rows:
        candidates = [dict(r) for r in rows]
        weights = [c["decoration_spent"] for c in candidates]
        winner = random.choices(candidates, weights=weights, k=1)[0]
        winner_name = winner["username"] or f"کاربر{winner['user_id']}"

        adjust_coins(winner["user_id"], BEAUTY_CONTEST_PRIZE)

        broadcast_to_all_chats(
            f"💃🎉 تبریک اسب {winner_name} زیباترین اسب شهر شده! 👑✨\n"
            f"🎁 جایزه: {BEAUTY_CONTEST_PRIZE} سکه"
        )

    # لباس همه پاره میشه و همه چیز از اول شروع میشه (شانس برابر برای دور بعد)
    with db_lock:
        conn = get_conn()
        conn.execute("UPDATE horses SET clothing=NULL")
        conn.execute("UPDATE users SET decoration_spent=0")
        conn.commit()
        conn.close()


def beauty_contest_loop():
    while True:
        time.sleep(NEWSPAPER_CHECK_INTERVAL_SECONDS)
        try:
            current = iran_now()
            today = current.date().isoformat()
            last_run = get_setting("beauty_contest_date")

            if (current.weekday() in BEAUTY_CONTEST_DAYS
                    and current.hour == BEAUTY_CONTEST_HOUR
                    and last_run != today):
                run_beauty_contest()
                set_setting("beauty_contest_date", today)
        except Exception as e:
            print("خطا در مسابقه‌ی زیبایی:", e)


# =========================================================
#                    🏆 لیگ اسبی (اصطبل مشترک) 🏆
# =========================================================

def get_league_week_start(dt=None):
    """جمعه‌ی شروع هفته‌ی جاری (به وقت ایران) رو به‌صورت رشته‌ی تاریخ برمی‌گردونه."""
    current = dt or iran_now()
    days_since_friday = (current.weekday() - 4) % 7  # جمعه در پایتون = 4
    week_start_date = current.date() - timedelta(days=days_since_friday)
    return week_start_date.isoformat()


def get_league_phase(dt=None):
    """'registration' برای جمعه/شنبه، 'racing' برای یکشنبه تا پنج‌شنبه."""
    current = dt or iran_now()
    return "registration" if current.weekday() in (4, 5) else "racing"


def compute_horse_power(horse):
    """قدرت اسب برای مسابقه‌ی لیگ: بر اساس نژاد، انرژی فعلی، نعل و احساسات."""
    breed = HORSE_BREEDS[horse["breed_key"]]
    base = 100 / breed["race_minutes"]
    energy_frac = (horse["energy"] / breed["energy_max"]) if breed["energy_max"] else 0
    power = base * (0.5 + 0.5 * energy_frac)
    if horse["horseshoe"] == "good":
        power *= 1.10
    elif horse["horseshoe"] == "great":
        power *= 1.20
    power *= max(0.3, 1 - get_emotion_speed_factor(horse))
    return power


def league_is_registered(user_id, week_start):
    with db_lock:
        conn = get_conn()
        row = conn.execute(
            "SELECT 1 FROM league_registrations WHERE user_id=? AND week_start=?",
            (user_id, week_start)
        ).fetchone()
        conn.close()
        return row is not None


def league_register(user_id, week_start):
    with db_lock:
        conn = get_conn()
        try:
            conn.execute(
                "INSERT INTO league_registrations (user_id, week_start, registered_at) VALUES (?, ?, ?)",
                (user_id, week_start, now().isoformat())
            )
            conn.commit()
        except Exception:
            conn.commit()  # احتمالاً از قبل ثبت‌نام کرده (UNIQUE)
        conn.close()


def league_has_raced(user_id, week_start):
    with db_lock:
        conn = get_conn()
        row = conn.execute(
            "SELECT 1 FROM league_races WHERE user_id=? AND week_start=?",
            (user_id, week_start)
        ).fetchone()
        conn.close()
        return row is not None


def league_record_race(user_id, week_start, opponent_key, result):
    with db_lock:
        conn = get_conn()
        try:
            conn.execute(
                "INSERT INTO league_races (user_id, week_start, opponent_key, result, raced_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, week_start, opponent_key, result, now().isoformat())
            )
            conn.commit()
        except Exception:
            conn.commit()
        conn.close()


def league_get_our_score(week_start):
    with db_lock:
        conn = get_conn()
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM league_races WHERE week_start=? AND result='win'",
            (week_start,)
        ).fetchone()
        conn.close()
        return row["cnt"] if row else 0


def league_ensure_npc_scores(week_start):
    """اگه هنوز ردیف امتیاز تیم‌های رقیب برای این هفته ساخته نشده، با صفر می‌سازتشون
    (خودِ امتیاز روزبه‌روز با league_increment_npc_scores بالا میره، نه یه‌جا)."""
    with db_lock:
        conn = get_conn()
        existing = conn.execute(
            "SELECT COUNT(*) as cnt FROM league_npc_scores WHERE week_start=?", (week_start,)
        ).fetchone()
        if existing and existing["cnt"] >= len(LEAGUE_NPC_TEAMS):
            conn.close()
            return
        for npc_key in LEAGUE_NPC_TEAMS:
            try:
                conn.execute(
                    "INSERT INTO league_npc_scores (week_start, npc_key, score) VALUES (?, ?, 0)",
                    (week_start, npc_key)
                )
            except Exception:
                pass
        conn.commit()
        conn.close()


def league_increment_npc_scores(week_start):
    """هر روزِ بازه‌ی مسابقه، یه امتیاز تصادفی (بر اساس سطح قدرت هر باشگاه) به امتیازش اضافه می‌کنه.
    این باعث میشه جدول واقعاً روزبه‌روز عوض بشه، نه یهو از یکشنبه کامل معلوم باشه."""
    league_ensure_npc_scores(week_start)
    with db_lock:
        conn = get_conn()
        for npc_key, (_, power) in LEAGUE_NPC_TEAMS.items():
            daily_gain = max(0, round(power * random.uniform(0.1, 0.5)))
            if daily_gain > 0:
                conn.execute(
                    "UPDATE league_npc_scores SET score = score + ? WHERE week_start=? AND npc_key=?",
                    (daily_gain, week_start, npc_key)
                )
        conn.commit()
        conn.close()


def league_get_leaderboard(week_start):
    """لیست ۱۰ تیمی رو مرتب‌شده برمی‌گردونه: [(اسم, امتیاز, is_us), ...]
    تو روزای ثبت‌نام هفته‌ی *جاری* (جمعه/شنبه)، هنوز مسابقه‌ای رخ نداده، پس امتیاز
    باشگاه‌های رقیب ساخته نمی‌شه و صفر نشون داده می‌شه. برای هفته‌های تموم‌شده
    (مثلاً موقع جمع‌بندی) همیشه امتیاز واقعی محاسبه/نمایش داده می‌شه."""
    our_score = league_get_our_score(week_start)
    is_current_week = (week_start == get_league_week_start())
    show_zero = is_current_week and get_league_phase() == "registration"

    if not show_zero:
        league_ensure_npc_scores(week_start)
        with db_lock:
            conn = get_conn()
            rows = conn.execute(
                "SELECT npc_key, score FROM league_npc_scores WHERE week_start=?", (week_start,)
            ).fetchall()
            conn.close()
        entries = [(LEAGUE_NPC_TEAMS[r["npc_key"]][0], r["score"], False) for r in rows]
    else:
        entries = [(name, 0, False) for name, _ in LEAGUE_NPC_TEAMS.values()]

    entries.append(("🐴 اصطبل ما", our_score, True))
    entries.sort(key=lambda e: e[1], reverse=True)
    return entries


def league_get_our_rank(week_start):
    leaderboard = league_get_leaderboard(week_start)
    for i, (name, score, is_us) in enumerate(leaderboard, start=1):
        if is_us:
            return i, score
    return len(leaderboard), 0


def league_get_registered_not_raced(week_start):
    with db_lock:
        conn = get_conn()
        rows = conn.execute(
            """SELECT r.user_id, u.username FROM league_registrations r
               JOIN users u ON u.user_id = r.user_id
               WHERE r.week_start=? AND r.user_id NOT IN
               (SELECT user_id FROM league_races WHERE week_start=?)""",
            (week_start, week_start)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]


def league_get_participants(week_start):
    """کسایی که واقعاً این هفته مسابقه دادن (نه فقط ثبت‌نام)."""
    with db_lock:
        conn = get_conn()
        rows = conn.execute(
            "SELECT DISTINCT user_id FROM league_races WHERE week_start=?", (week_start,)
        ).fetchall()
        conn.close()
        return [r["user_id"] for r in rows]


def _do_league_register(user_id):
    user = get_user_row(user_id)
    level = compute_level(user)
    if level < LEAGUE_UNLOCK_LEVEL:
        return f"🔒 لیگ اسبی با لول {LEAGUE_UNLOCK_LEVEL} باز میشه."
    week_start = get_league_week_start()
    if get_league_phase() != "registration":
        return "الان بازه‌ی ثبت‌نام نیست! فقط جمعه و شنبه می‌تونی ثبت‌نام کنی."
    if league_is_registered(user_id, week_start):
        return "قبلاً برای این هفته ثبت‌نام کردی!"
    league_register(user_id, week_start)
    return "✅ برای لیگ اسبی این هفته ثبت‌نام شدی! از یکشنبه می‌تونی مسابقه بدی."


def _do_league_race(user_id, index):
    week_start = get_league_week_start()
    if get_league_phase() != "racing":
        return None, "الان بازه‌ی مسابقه‌ی لیگ نیست! فقط یکشنبه تا پنج‌شنبه می‌تونی مسابقه بدی."
    if not league_is_registered(user_id, week_start):
        return None, "برای این هفته ثبت‌نام نکردی!"
    if league_has_raced(user_id, week_start):
        return None, "این هفته دیگه مسابقه‌ی لیگ دادی!"

    horse = get_horse_by_index(user_id, index)
    if horse is None:
        return None, "همچین اسبی نداری!"
    if is_horse_racing(horse):
        return None, "این اسب همین الان تو پیسته!"

    horse = apply_energy_regen(horse)
    npc_key, (npc_name, npc_power) = random.choice(list(LEAGUE_NPC_TEAMS.items()))
    our_power = compute_horse_power(horse)
    win_prob = our_power / (our_power + npc_power)
    win_prob = max(0.05, min(0.95, win_prob))
    won = random.random() < win_prob

    result = "win" if won else "loss"
    league_record_race(user_id, week_start, npc_key, result)

    new_energy = max(0, horse["energy"] - 1)
    update_horse(horse["id"], energy=new_energy)

    if won:
        text = f"⚔️ مقابل «{npc_name}» بردی! 🎉 یه امتیاز برای اصطبل ما ثبت شد."
    else:
        text = f"⚔️ مقابل «{npc_name}» باختی. دفعه‌ی بعد بهتر می‌شه!"
    return result, text


def render_league_menu(user_id):
    user = get_user_row(user_id)
    level = compute_level(user)
    kb = types.InlineKeyboardMarkup(row_width=1)

    if level < LEAGUE_UNLOCK_LEVEL:
        text = f"🔒 لیگ اسبی با لول {LEAGUE_UNLOCK_LEVEL} باز میشه."
        kb.add(types.InlineKeyboardButton("🔙 برگشت به منو", callback_data="menu:main"))
        return text, kb

    week_start = get_league_week_start()
    phase = get_league_phase()
    registered = league_is_registered(user_id, week_start)
    raced = league_has_raced(user_id, week_start)
    rank, our_score = league_get_our_rank(week_start)

    lines = ["🏆 لیگ اسبی — اصطبل مشترک\n"]

    if phase == "registration":
        if registered:
            lines.append("✅ این هفته ثبت‌نام کردی!\n⏳ از یکشنبه می‌تونی مسابقه بدی.")
        else:
            lines.append("هنوز این هفته ثبت‌نام نکردی!\n⏳ تا پایان شنبه وقت داری ثبت‌نام کنی.")
            kb.add(types.InlineKeyboardButton("✅ ثبت‌نام برای این هفته", callback_data="league:register"))
    else:  # racing
        if not registered:
            lines.append("این هفته ثبت‌نام نکردی، پس نمی‌تونی مسابقه بدی.\n📅 جمعه‌ی بعد دوباره امتحان کن.")
        elif raced:
            lines.append("✅ این هفته مسابقه‌ی لیگ رو دادی!")
        else:
            lines.append("✅ ثبت‌نام کردی و هنوز مسابقه ندادی!")
            kb.add(types.InlineKeyboardButton("⚔️ مسابقه با NPC", callback_data="league:choose_horse"))

    lines.append(f"\n📊 رتبه‌ی فعلی تیم: {rank}ام از {len(LEAGUE_NPC_TEAMS)+1} (امتیاز: {our_score})")

    kb.add(types.InlineKeyboardButton("📊 جدول لیگ", callback_data="league:table"))
    kb.add(types.InlineKeyboardButton("📜 تاریخچه‌ی هفته‌های قبل", callback_data="league:history"))
    kb.add(types.InlineKeyboardButton("🔙 برگشت به منو", callback_data="menu:main"))
    return "\n".join(lines), kb


def render_league_choose_horse(user_id):
    horses = get_horses(user_id)
    if not horses:
        return "هنوز اسبی نداری!", back_button()
    kb = types.InlineKeyboardMarkup(row_width=1)
    lines = ["🐴 کدوم اسب بره مسابقه‌ی لیگ؟\n"]
    for i, horse in enumerate(horses, start=1):
        horse = apply_energy_regen(horse)
        lines.append(format_horse_line(i, horse))
        kb.add(types.InlineKeyboardButton(f"⚔️ اسب شماره {i}", callback_data=f"league:race:{i}"))
    kb.add(types.InlineKeyboardButton("🔙 برگشت", callback_data="league:back"))
    return "\n".join(lines), kb


def render_league_table():
    week_start = get_league_week_start()
    leaderboard = league_get_leaderboard(week_start)
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    max_score = max((s for _, s, _ in leaderboard), default=1) or 1

    lines = ["🏆 جدول لیگ اسبی — هفته‌ی جاری\n", "━━━━━━━━━━━━━━━━━━"]
    for i, (name, score, is_us) in enumerate(leaderboard, start=1):
        bars_filled = round((score / max_score) * 10) if max_score else 0
        bar = "▓" * bars_filled + "░" * (10 - bars_filled)
        rank_display = medals.get(i, f"{i}.")
        star = " ⭐" if is_us else ""
        lines.append(f"{rank_display} {name}{star}  {bar} {score}")
    lines.append("━━━━━━━━━━━━━━━━━━")

    rank, _ = league_get_our_rank(week_start)
    reward = LEAGUE_REWARD_BY_RANK.get(rank, 0)
    lines.append(f"\n💰 اگه همینجوری بمونی: {reward} سکه به هرکی مسابقه داده می‌رسه")

    kb = back_button_to("league:main")
    return "\n".join(lines), kb


def render_league_history():
    with db_lock:
        conn = get_conn()
        rows = conn.execute(
            "SELECT * FROM league_history ORDER BY week_start DESC LIMIT 8"
        ).fetchall()
        conn.close()

    if not rows:
        lines = ["📜 هنوز هیچ هفته‌ای تموم نشده که تاریخچه داشته باشه."]
    else:
        lines = ["📜 تاریخچه‌ی لیگ اسبی\n"]
        for r in rows:
            r = dict(r)
            lines.append(
                f"📅 هفته‌ی {r['week_start']}: رتبه {r['rank']}ام، امتیاز {r['our_score']}"
                f" — {r['reward_per_person']} سکه به هرنفر ({r['participants']} نفر مسابقه دادن)"
            )

    kb = back_button_to("league:main")
    return "\n".join(lines), kb


def back_button_to(callback_data):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 برگشت", callback_data=callback_data))
    return kb


def league_finalize_week(week_start):
    """جایزه‌ی پایان هفته رو حساب و پخش می‌کنه، بعد تو تاریخچه ثبتش می‌کنه."""
    already = None
    with db_lock:
        conn = get_conn()
        already = conn.execute(
            "SELECT 1 FROM league_history WHERE week_start=?", (week_start,)
        ).fetchone()
        conn.close()
    if already:
        return

    rank, our_score = league_get_our_rank(week_start)
    reward = LEAGUE_REWARD_BY_RANK.get(rank, 0)
    participants = league_get_participants(week_start)

    if reward > 0:
        for uid in participants:
            adjust_coins(uid, reward)

    with db_lock:
        conn = get_conn()
        try:
            conn.execute(
                """INSERT INTO league_history (week_start, our_score, rank, reward_per_person, participants, finalized_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (week_start, our_score, rank, reward, len(participants), now().isoformat())
            )
            conn.commit()
        except Exception:
            conn.commit()
        conn.close()

    if participants:
        broadcast_to_all_chats(
            f"🏆 نتیجه‌ی لیگ اسبی هفته‌ی {week_start}:\n"
            f"📊 رتبه‌ی نهایی: {rank}ام از {len(LEAGUE_NPC_TEAMS)+1}\n"
            f"💰 جایزه: {reward} سکه به هرکدوم از {len(participants)} نفری که مسابقه دادن"
        )


def league_loop():
    while True:
        time.sleep(LEAGUE_CHECK_INTERVAL_SECONDS)
        try:
            current = iran_now()
            today = current.date().isoformat()
            week_start = get_league_week_start(current)
            phase = get_league_phase(current)

            # فینالایز کردن هفته‌ی قبل، همین که وارد بازه‌ی ثبت‌نام هفته‌ی جدید شدیم
            if phase == "registration":
                prev_week_start = (date.fromisoformat(week_start) - timedelta(days=7)).isoformat()
                league_finalize_week(prev_week_start)

            # هر روزِ بازه‌ی مسابقه، یه‌بار امتیاز باشگاه‌های رقیب رو کمی بالا می‌بریم
            # (تا جدول زنده باشه و روزبه‌روز عوض بشه، نه یهو کامل یکشنبه معلوم بشه)
            if phase == "racing" and get_setting(f"league_increment_date_{week_start}") != today:
                league_increment_npc_scores(week_start)
                set_setting(f"league_increment_date_{week_start}", today)

            # پیام اعلام ثبت‌نام جمعه صبح
            if (current.weekday() == 4 and current.hour == LEAGUE_ANNOUNCE_HOUR
                    and get_setting("league_announce_date") != today):
                broadcast_to_all_chats(
                    "🏆 لیگ اسبی این هفته باز شد!\n"
                    "چه کسانی این هفته می‌خوان تو لیگ اسبی مسابقه بدن؟\n"
                    "از /منو → 🏆 لیگ اسبی ثبت‌نام کن (تا آخر شنبه وقت داری)."
                )
                set_setting("league_announce_date", today)

            # یادآوری چهارشنبه شب برای ثبت‌نامی‌های بی‌مسابقه
            if (current.weekday() == LEAGUE_REMINDER_WEEKDAY and current.hour == LEAGUE_REMINDER_HOUR
                    and get_setting("league_reminder_date") != today):
                pending = league_get_registered_not_raced(week_start)
                if pending:
                    names = "، ".join(p["username"] or f"کاربر{p['user_id']}" for p in pending)
                    broadcast_to_all_chats(
                        f"⏰ یادآوری لیگ اسبی: {names} هنوز این هفته مسابقه ندادن!\n"
                        f"فردا (پنج‌شنبه) آخرین فرصته."
                    )
                set_setting("league_reminder_date", today)

        except Exception as e:
            print("خطا در لیگ اسبی:", e)






# =========================================================
#          🦖 سیستم دایناسور و جنگ شهر (اصطبل مشترک) 🦖
# =========================================================

# ---------- ثابت‌های بازی ----------
HUNT_HOURS = (0, 12)
HUNT_MAX_ATTEMPTS_PER_SLOT = 4
HUNT_SUCCESS_MIN_VALUE = 5  # دارت با مقدار ۵ یا ۶ (نه فقط بولزای خالص ۶) موفقیت حساب میشه
WAR_HOURS = (0, 3, 6, 9, 12, 15, 18, 21)
WAR_ROUND_LENGTH_HOURS = 3
# مهلت واقعی ثبت‌نام/اقدام تو هر دور جنگ: از لحظه‌ی اعلام واقعی حساب میشه،
# نه از روی ساعت کلاک (تا با تست دستی یا داون‌تایم به‌هم نریزه)
WAR_ROUND_DEADLINE_HOURS = 2.5
TREASURY_START_BALANCE = 100
TREASURY_STEAL_MIN_PCT = 0.07
TREASURY_STEAL_MAX_PCT = 0.10
TREASURY_INTEREST_PCT = 0.15
TREASURY_INTEREST_HOUR = 23
TREASURY_INTEREST_MINUTE = 55
CITY_KEY = "us"
OUR_DOOR_TOTAL = 8  # تعداد کل درهای شهر خودمون، همیشه ثابت (برخلاف قبل که با تعداد نگهبان زیاد می‌شد)
NPC_TARGET_DOOR_COUNT = 8  # باشگاه‌های حریف NPC هستن، نگهبان واقعی ندارن؛ پس برخلاف
                            # درهای شهر خودمون، نیازی نیست تعداد درشون به تعداد حمله‌کننده‌ها ربط داشته باشه
LOOP_INTERVAL_SECONDS = 30

# ---------- نقش‌های دایناسور ----------
# نقشی که هنگام شکار موفق (بولزای دارت) رندوم به کاربر داده میشه.
DINO_ROLES = ["thief", "guard", "spy", "hunter"]
DINO_ROLE_DISPLAY = {
    "thief": "🦹 دزد",
    "guard": "🛡️ نگهبان",
    "spy": "🔭 جاسوس",
    "hunter": "🏹 شکارچی",
}

# ---------- جاسوسی ----------
# از ۸ در باشگاه حریف، این‌قدرشون «پاک» (بدون نگهبان) به جاسوس نشون داده میشه؛
# بقیه (شامل خودِ در نگهبانی‌شده) نامشخص می‌مونن.
SPY_DOORS_REVEALED = 5

# ---------- شکار حریف (شکارچی) ----------
HUNTER_MAX_SHOTS = 3
HUNTER_SHOT_DELAY_SECONDS = 2
HUNTER_DIRECTIONS = ["↗️", "↖️", "↘️", "↙️"]


def _iso_hour(dt):
    return dt.strftime("%Y-%m-%dT%H:00:00")


def _today_str(dt):
    return dt.strftime("%Y-%m-%d")


def current_war_round_key(dt=None):
    """نزدیک‌ترین ساعت جنگیِ گذشته یا الان رو به‌صورت رشته برمی‌گردونه."""
    current = dt or iran_now()
    candidates = [h for h in WAR_HOURS if h <= current.hour]
    hour = max(candidates) if candidates else WAR_HOURS[-1]
    if not candidates:
        current = current - timedelta(days=1)
    return _iso_hour(current.replace(hour=hour, minute=0, second=0, microsecond=0))


def next_war_round_key(round_key):
    dt = datetime.fromisoformat(round_key)
    idx = WAR_HOURS.index(dt.hour)
    if idx + 1 < len(WAR_HOURS):
        next_dt = dt.replace(hour=WAR_HOURS[idx + 1])
    else:
        next_dt = (dt + timedelta(days=1)).replace(hour=WAR_HOURS[0])
    return _iso_hour(next_dt)


def current_hunt_slot_key(dt=None):
    current = dt or iran_now()
    candidates = [h for h in HUNT_HOURS if h <= current.hour]
    hour = max(candidates) if candidates else HUNT_HOURS[-1]
    if not candidates:
        current = current - timedelta(days=1)
    return f"{_today_str(current)}-{hour:02d}"


# =========================================================
#                    دیتابیس
# =========================================================

def init_dino_tables():
    with db_lock:
        conn = get_conn()
        c = conn

        c.execute(f"""
            CREATE TABLE IF NOT EXISTS dino_catches (
                id {PK_AUTOINCREMENT},
                user_id BIGINT,
                role TEXT,
                caught_date TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS dino_hunt_attempts (
                slot_key TEXT,
                user_id BIGINT,
                attempts INTEGER DEFAULT 0,
                caught INTEGER DEFAULT 0,
                PRIMARY KEY (slot_key, user_id)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS dino_hunt_messages (
                slot_key TEXT,
                chat_id BIGINT,
                message_id BIGINT,
                PRIMARY KEY (slot_key, chat_id)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS dino_treasury (
                team_key TEXT PRIMARY KEY,
                balance INTEGER
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS dino_war_rounds (
                round_key TEXT PRIMARY KEY,
                announced INTEGER DEFAULT 0,
                resolved INTEGER DEFAULT 0
            )
        """)
        c.execute(f"""
            CREATE TABLE IF NOT EXISTS dino_war_guards (
                id {PK_AUTOINCREMENT},
                round_key TEXT,
                user_id BIGINT,
                door_index INTEGER
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS dino_war_guard_doors (
                round_key TEXT,
                door_index INTEGER,
                user_id BIGINT,
                PRIMARY KEY (round_key, door_index)
            )
        """)
        c.execute(f"""
            CREATE TABLE IF NOT EXISTS dino_war_thieves (
                id {PK_AUTOINCREMENT},
                round_key TEXT,
                user_id BIGINT,
                target TEXT,
                door_index INTEGER
            )
        """)
        # --- مهاجرت: این دو جدول قبلاً با ساختار قدیمی (بدون ستون id، با کلید ترکیبی
        # round_key+user_id که اجازه‌ی بیش از یه ثبت‌نام به هر نفر رو نمی‌داد) ساخته شده
        # بودن. چون CREATE TABLE IF NOT EXISTS رو جدول موجود کاری نمی‌کنه، اینجا چک
        # می‌کنیم اگه ستون id وجود نداره، جدول قدیمی رو با ساختار جدید جایگزین می‌کنیم.
        # (این جدول‌ها فقط داده‌ی موقتِ همون دور جنگن، پس خالی کردنشون بی‌خطره.)
        for old_table, create_sql in [
            ("dino_war_guards", f"""
                CREATE TABLE dino_war_guards (
                    id {PK_AUTOINCREMENT},
                    round_key TEXT,
                    user_id BIGINT,
                    door_index INTEGER
                )
            """),
            ("dino_war_thieves", f"""
                CREATE TABLE dino_war_thieves (
                    id {PK_AUTOINCREMENT},
                    round_key TEXT,
                    user_id BIGINT,
                    target TEXT,
                    door_index INTEGER
                )
            """),
        ]:
            try:
                c.execute(f"SELECT id FROM {old_table} LIMIT 1")
            except Exception:
                # execute() خودش موقع خطا rollback می‌کنه، پس اتصال برای ادامه سالمه
                c.execute(f"DROP TABLE IF EXISTS {old_table}")
                c.execute(create_sql)
                conn.commit()
        # تعداد درهای شهرِ خودمون رو برای هر دور جنگ، همون یه‌بار که محاسبه شد قفل می‌کنیم
        # تا وسط ثبت‌نام نگهبان‌ها عوض نشه (نگهبانِ اول نباید بعداً منوی متفاوتی ببینه)
        c.execute("""
            CREATE TABLE IF NOT EXISTS dino_war_door_counts (
                round_key TEXT PRIMARY KEY,
                door_count INTEGER
            )
        """)
        # در نگهبانی‌شده‌ی هر باشگاه NPC هم، دقیقاً مثل بالا، یه‌بار برای کل دور قفل میشه
        # (وگرنه جاسوسی معنی نداره: نمی‌شه چیزی رو که هنوز تعیین نشده لو داد)
        c.execute("""
            CREATE TABLE IF NOT EXISTS dino_war_npc_guarded_doors (
                round_key TEXT,
                npc_key TEXT,
                door_index INTEGER,
                PRIMARY KEY (round_key, npc_key)
            )
        """)
        # اگه شکارچی موفق بشه، اون باشگاه NPC دیگه تو همین دور به شهر ما حمله نمی‌کنه
        c.execute("""
            CREATE TABLE IF NOT EXISTS dino_war_disabled_attack (
                round_key TEXT,
                npc_key TEXT,
                PRIMARY KEY (round_key, npc_key)
            )
        """)
        c.execute(f"""
            CREATE TABLE IF NOT EXISTS dino_war_spy_actions (
                id {PK_AUTOINCREMENT},
                round_key TEXT,
                user_id BIGINT,
                target TEXT
            )
        """)
        c.execute(f"""
            CREATE TABLE IF NOT EXISTS dino_war_hunts (
                id {PK_AUTOINCREMENT},
                round_key TEXT,
                user_id BIGINT,
                target TEXT,
                hidden_dir TEXT,
                shots_used INTEGER DEFAULT 0,
                resolved INTEGER DEFAULT 0,
                success INTEGER DEFAULT 0,
                chat_id BIGINT,
                message_id BIGINT
            )
        """)
        conn.commit()
        conn.close()

        # خزانه‌ی شهر خودمون + هر ۹ باشگاه NPC، اگه هنوز ساخته نشدن
        conn2 = get_conn()
        for key in [CITY_KEY] + list(LEAGUE_NPC_TEAMS.keys()):
            try:
                conn2.execute(
                    "INSERT INTO dino_treasury (team_key, balance) VALUES (?, ?)",
                    (key, TREASURY_START_BALANCE)
                )
            except Exception:
                pass
        conn2.commit()
        conn2.close()


# ---------- خزانه ----------

def get_treasury(team_key):
    with db_lock:
        conn = get_conn()
        row = conn.execute(
            "SELECT balance FROM dino_treasury WHERE team_key=?", (team_key,)
        ).fetchone()
        conn.close()
        return row["balance"] if row else TREASURY_START_BALANCE


def adjust_treasury(team_key, delta):
    with db_lock:
        conn = get_conn()
        conn.execute(
            "UPDATE dino_treasury SET balance = MAX(0, balance + ?) WHERE team_key=?",
            (delta, team_key)
        )
        conn.commit()
        conn.close()


def steal_from_treasury(from_key, to_key):
    """درصد تصادفی ۷-۱۰٪ از خزانه‌ی from_key می‌دزده و میده به to_key. مقدار دزدیده‌شده رو برمی‌گردونه."""
    balance = get_treasury(from_key)
    pct = random.uniform(TREASURY_STEAL_MIN_PCT, TREASURY_STEAL_MAX_PCT)
    amount = max(1, round(balance * pct))
    adjust_treasury(from_key, -amount)
    adjust_treasury(to_key, amount)
    return amount


# ---------- شکار دایناسور ----------

def register_hunt_message(slot_key, chat_id, message_id):
    with db_lock:
        conn = get_conn()
        try:
            conn.execute(
                "INSERT INTO dino_hunt_messages (slot_key, chat_id, message_id) VALUES (?, ?, ?)",
                (slot_key, chat_id, message_id)
            )
            conn.commit()
        except Exception:
            conn.commit()
        conn.close()


def is_hunt_message(slot_key, chat_id, message_id):
    with db_lock:
        conn = get_conn()
        row = conn.execute(
            "SELECT 1 FROM dino_hunt_messages WHERE slot_key=? AND chat_id=? AND message_id=?",
            (slot_key, chat_id, message_id)
        ).fetchone()
        conn.close()
        return row is not None


def get_hunt_attempt(slot_key, user_id):
    with db_lock:
        conn = get_conn()
        row = conn.execute(
            "SELECT attempts, caught FROM dino_hunt_attempts WHERE slot_key=? AND user_id=?",
            (slot_key, user_id)
        ).fetchone()
        conn.close()
        return dict(row) if row else {"attempts": 0, "caught": 0}


def record_hunt_attempt(slot_key, user_id, caught_now):
    with db_lock:
        conn = get_conn()
        existing = conn.execute(
            "SELECT attempts, caught FROM dino_hunt_attempts WHERE slot_key=? AND user_id=?",
            (slot_key, user_id)
        ).fetchone()
        if existing:
            new_attempts = existing["attempts"] + 1
            new_caught = 1 if (existing["caught"] or caught_now) else 0
            conn.execute(
                "UPDATE dino_hunt_attempts SET attempts=?, caught=? WHERE slot_key=? AND user_id=?",
                (new_attempts, new_caught, slot_key, user_id)
            )
        else:
            conn.execute(
                "INSERT INTO dino_hunt_attempts (slot_key, user_id, attempts, caught) VALUES (?, ?, ?, ?)",
                (slot_key, user_id, 1, 1 if caught_now else 0)
            )
        conn.commit()
        conn.close()


ROLE_DAILY_USE_CAP = 2  # هر نقش رو حداکثر ۲ بار در روز میشه زد (نه اینکه چندتا از اون نقش گرفته باشی)


def create_dino_catch(user_id):
    """یه دایناسور «خام» (بدون نقش) به کاربر میده. نقشش رو خودش موقع عملیات
    (نگهبانی/دزدی/جاسوسی/شکار) تعیین می‌کنه."""
    today = _today_str(iran_now())
    with db_lock:
        conn = get_conn()
        conn.execute(
            "INSERT INTO dino_catches (user_id, role, caught_date, used) VALUES (?, NULL, ?, 0)",
            (user_id, today)
        )
        conn.commit()
        conn.close()


def get_user_available_dino_count(user_id):
    """چندتا دایناسورِ خام (بدون نقش، استفاده‌نشده) امروز داره."""
    today = _today_str(iran_now())
    with db_lock:
        conn = get_conn()
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM dino_catches WHERE user_id=? AND caught_date=? AND used=0",
            (user_id, today)
        ).fetchone()
        conn.close()
        return row["cnt"] if row else 0


def get_user_role_uses_today(user_id, role):
    """چندبار امروز این نقش رو زده (نه چندتا از این نقش گرفته - چون دیگه گرفتن و
    زدن دو مرحله‌ی جداست). سقفش ROLE_DAILY_USE_CAP هست."""
    today = _today_str(iran_now())
    with db_lock:
        conn = get_conn()
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM dino_catches WHERE user_id=? AND caught_date=? AND role=? AND used=1",
            (user_id, today, role)
        ).fetchone()
        conn.close()
        return row["cnt"] if row else 0


def try_use_dino_for_role(user_id, role):
    """اگه کاربر یه دایناسورِ خام داشته باشه و امروز این نقش رو کمتر از
    ROLE_DAILY_USE_CAP بار زده باشه، یکی از دایناسوراش رو همین الان به این نقش
    تبدیل و مصرف می‌کنه. موفق -> True، ناموفق (سهمیه یا دایناسور کافی نیست) -> False.
    این کار همه‌چی رو تو یه قفل انجام میده تا دو کلیک هم‌زمان دوبار یه دایناسور رو مصرف نکنن."""
    today = _today_str(iran_now())
    with db_lock:
        conn = get_conn()
        used_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM dino_catches WHERE user_id=? AND caught_date=? AND role=? AND used=1",
            (user_id, today, role)
        ).fetchone()["cnt"]
        if used_count >= ROLE_DAILY_USE_CAP:
            conn.close()
            return False
        row = conn.execute(
            "SELECT id FROM dino_catches WHERE user_id=? AND caught_date=? AND used=0 ORDER BY id LIMIT 1",
            (user_id, today)
        ).fetchone()
        if not row:
            conn.close()
            return False
        conn.execute("UPDATE dino_catches SET role=?, used=1 WHERE id=?", (role, row["id"]))
        conn.commit()
        conn.close()
        return True


def get_user_dino_today(user_id):
    """آخرین نقشی که امروز گرفته رو برمی‌گردونه (برای نمایش‌های ساده)، وگرنه None.
    توجه: چون یه نفر می‌تونه تو یه روز هم نگهبان بگیره هم دزد (دو تا شکار جدا،
    ساعت ۰۰ و ۱۲)، برای چک کردن "آیا این نقش رو داره؟" باید از
    get_user_dino_roles_today استفاده کرد، نه این تابع."""
    today = _today_str(iran_now())
    with db_lock:
        conn = get_conn()
        row = conn.execute(
            "SELECT role FROM dino_catches WHERE user_id=? AND caught_date=? ORDER BY id DESC LIMIT 1",
            (user_id, today)
        ).fetchone()
        conn.close()
        return row["role"] if row else None


def get_user_dino_roles_today(user_id):
    """همه‌ی نقش‌هایی که امروز گرفته رو به‌صورت set برمی‌گردونه، مثلاً {"guard"} یا
    {"guard", "thief"} اگه هر دوتا رو داشته باشه (دو تا شکار مختلف امروز)."""
    today = _today_str(iran_now())
    with db_lock:
        conn = get_conn()
        rows = conn.execute(
            "SELECT DISTINCT role FROM dino_catches WHERE user_id=? AND caught_date=?",
            (user_id, today)
        ).fetchall()
        conn.close()
        return {r["role"] for r in rows}


def get_user_role_catch_count(user_id, role):
    """چندتا دایناسور از این نقش امروز گرفته (مثلاً چندتا نگهبان). این سقفِ سهمیه‌شه."""
    today = _today_str(iran_now())
    with db_lock:
        conn = get_conn()
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM dino_catches WHERE user_id=? AND caught_date=? AND role=?",
            (user_id, today, role)
        ).fetchone()
        conn.close()
        return row["cnt"] if row else 0


def get_users_with_available_dino():
    """کیا امروز حداقل یه دایناسورِ خامِ استفاده‌نشده دارن (نقشش هرچی می‌خواد باشه)."""
    today = _today_str(iran_now())
    with db_lock:
        conn = get_conn()
        rows = conn.execute(
            "SELECT DISTINCT user_id FROM dino_catches WHERE caught_date=? AND used=0",
            (today,)
        ).fetchall()
        conn.close()
        return [r["user_id"] for r in rows]


def reset_daily_dinos():
    """نیمه‌شب: دایناسورهای دیروز رو کاملاً پاک می‌کنه (شامل شکار)."""
    with db_lock:
        conn = get_conn()
        conn.execute("DELETE FROM dino_catches")
        conn.execute("DELETE FROM dino_hunt_attempts")
        conn.execute("DELETE FROM dino_hunt_messages")
        conn.commit()
        conn.close()


# ---------- جنگ: نگهبان‌گذاری ----------

def get_taken_doors(round_key):
    with db_lock:
        conn = get_conn()
        rows = conn.execute(
            "SELECT door_index FROM dino_war_guard_doors WHERE round_key=?", (round_key,)
        ).fetchall()
        conn.close()
        return {r["door_index"] for r in rows}


def get_locked_our_door_count(round_key):
    """تعداد درهای شهر خودمون همیشه ثابته (OUR_DOOR_TOTAL)."""
    return OUR_DOOR_TOTAL


def get_doors_per_guard(round_key, user_id=None):
    """هرچی نگهبان کمتری تو *همین دور* داشته باشیم، هرکدوم باید در بیشتری پوشش بده:
    ۱ نگهبان → ۴ در، ۲ نگهبان → ۲ در هرکدوم، ۴+ نگهبان → ۱ در هرکدوم.
    چون دیگه نقش موقع شکار مشخص نمیشه (بلکه موقع عملیات)، این عدد رو زنده و بر اساس
    نگهبانای همین دور که تا الان ثبت‌نام کردن حساب می‌کنیم؛ اگه user_id داده بشه و قبلاً
    تو لیست نباشه، خودش هم به‌عنوان نگهبان جدید حساب میشه (چون داره همین الان می‌پیوسته)."""
    with db_lock:
        conn = get_conn()
        rows = conn.execute(
            "SELECT DISTINCT user_id FROM dino_war_guards WHERE round_key=?", (round_key,)
        ).fetchall()
        conn.close()
    existing = {r["user_id"] for r in rows}
    if user_id is not None:
        existing.add(user_id)
    guard_count = max(1, len(existing))
    return max(1, math.ceil(OUR_DOOR_TOTAL / (2 * guard_count)))


def get_locked_npc_guarded_door(round_key, npc_key):
    """درِ نگهبانی‌شده‌ی یه باشگاه NPC رو برای این دور، فقط یه‌بار (اولین باری که لازم
    میشه) رندوم انتخاب و ذخیره می‌کنه؛ دفعات بعد همون عدد برمی‌گرده. این کار لازمه چون
    جاسوسی فقط وقتی معنی داره که این در از قبل (قبل از حمله‌ی دزدها) مشخص و ثابت باشه."""
    with db_lock:
        conn = get_conn()
        row = conn.execute(
            "SELECT door_index FROM dino_war_npc_guarded_doors WHERE round_key=? AND npc_key=?",
            (round_key, npc_key)
        ).fetchone()
        if row:
            conn.close()
            return row["door_index"]
        conn.close()

    door_index = random.randint(1, NPC_TARGET_DOOR_COUNT)
    with db_lock:
        conn = get_conn()
        try:
            conn.execute(
                "INSERT INTO dino_war_npc_guarded_doors (round_key, npc_key, door_index) VALUES (?, ?, ?)",
                (round_key, npc_key, door_index)
            )
            conn.commit()
        except Exception:
            # هم‌زمان یکی دیگه هم قفلش کرده؛ مقدار ذخیره‌شده رو بخون
            row = conn.execute(
                "SELECT door_index FROM dino_war_npc_guarded_doors WHERE round_key=? AND npc_key=?",
                (round_key, npc_key)
            ).fetchone()
            if row:
                door_index = row["door_index"]
        conn.close()
    return door_index


def is_attack_disabled(round_key, npc_key):
    """True یعنی شکارچی امروز موفق شده این باشگاه رو بزنه، پس این دور اصلاً به شهر ما حمله نمی‌کنه."""
    with db_lock:
        conn = get_conn()
        row = conn.execute(
            "SELECT 1 FROM dino_war_disabled_attack WHERE round_key=? AND npc_key=?",
            (round_key, npc_key)
        ).fetchone()
        conn.close()
        return row is not None


def disable_attack(round_key, npc_key):
    with db_lock:
        conn = get_conn()
        try:
            conn.execute(
                "INSERT INTO dino_war_disabled_attack (round_key, npc_key) VALUES (?, ?)",
                (round_key, npc_key)
            )
            conn.commit()
        except Exception:
            pass
        conn.close()


# ---------- جاسوسی ----------

def get_user_spy_actions_used(round_key, user_id):
    with db_lock:
        conn = get_conn()
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM dino_war_spy_actions WHERE round_key=? AND user_id=?",
            (round_key, user_id)
        ).fetchone()
        conn.close()
        return row["cnt"] if row else 0


def register_spy_action(round_key, user_id, target):
    with db_lock:
        conn = get_conn()
        conn.execute(
            "INSERT INTO dino_war_spy_actions (round_key, user_id, target) VALUES (?, ?, ?)",
            (round_key, user_id, target)
        )
        conn.commit()
        conn.close()


def render_spy_target_menu(round_key):
    kb = types.InlineKeyboardMarkup(row_width=1)
    for npc_key, (name, _) in LEAGUE_NPC_TEAMS.items():
        kb.add(types.InlineKeyboardButton(name, callback_data=f"dino:spy_target:{round_key}:{npc_key}"))
    return "🔭 کدوم باشگاه رو می‌خوای زیر نظر بگیری؟", kb


def spy_on_target(round_key, target):
    """درِ نگهبانی‌شده رو قفل می‌کنه (اگه نشده) و SPY_DOORS_REVEALED تا از درهای
    «پاک» (غیرنگهبانی‌شده) رو رندوم انتخاب می‌کنه تا به جاسوس نشون بده."""
    guarded_door = get_locked_npc_guarded_door(round_key, target)
    clean_doors = [d for d in range(1, NPC_TARGET_DOOR_COUNT + 1) if d != guarded_door]
    revealed = random.sample(clean_doors, min(SPY_DOORS_REVEALED, len(clean_doors)))
    suspicious = sorted(set(range(1, NPC_TARGET_DOOR_COUNT + 1)) - set(revealed))
    return sorted(revealed), suspicious


# ---------- شکارچی ----------

def render_hunter_target_menu(round_key):
    kb = types.InlineKeyboardMarkup(row_width=1)
    for npc_key, (name, _) in LEAGUE_NPC_TEAMS.items():
        kb.add(types.InlineKeyboardButton(name, callback_data=f"dino:hunter_target:{round_key}:{npc_key}"))
    return "🏹 دنبال دایناسور کدوم باشگاه می‌گردی؟", kb


def get_user_hunt_uses(round_key, user_id):
    """چندتا شکار (چه موفق چه ناموفق) این کاربر تو این دور شروع کرده."""
    with db_lock:
        conn = get_conn()
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM dino_war_hunts WHERE round_key=? AND user_id=?",
            (round_key, user_id)
        ).fetchone()
        conn.close()
        return row["cnt"] if row else 0


def get_active_hunt(round_key, user_id):
    with db_lock:
        conn = get_conn()
        row = conn.execute(
            "SELECT * FROM dino_war_hunts WHERE round_key=? AND user_id=? AND resolved=0 ORDER BY id DESC LIMIT 1",
            (round_key, user_id)
        ).fetchone()
        conn.close()
        return dict(row) if row else None


def start_hunt(round_key, user_id, target, chat_id, message_id):
    hidden_dir = random.choice(HUNTER_DIRECTIONS)
    with db_lock:
        conn = get_conn()
        cur = conn.execute(
            "INSERT INTO dino_war_hunts (round_key, user_id, target, hidden_dir, shots_used, resolved, success, chat_id, message_id) "
            "VALUES (?, ?, ?, ?, 0, 0, 0, ?, ?)",
            (round_key, user_id, target, hidden_dir, chat_id, message_id)
        )
        conn.commit()
        hunt_id = cur.lastrowid
        conn.close()
        return hunt_id


def render_hunter_shot_keyboard(round_key, hunt_id):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(*[
        types.InlineKeyboardButton(d, callback_data=f"dino:hunter_shoot:{round_key}:{hunt_id}:{d}")
        for d in HUNTER_DIRECTIONS
    ])
    return kb


def get_hunt_by_id(hunt_id):
    with db_lock:
        conn = get_conn()
        row = conn.execute("SELECT * FROM dino_war_hunts WHERE id=?", (hunt_id,)).fetchone()
        conn.close()
        return dict(row) if row else None


def update_hunt(hunt_id, **fields):
    keys = ", ".join(f"{k}=?" for k in fields)
    values = list(fields.values()) + [hunt_id]
    with db_lock:
        conn = get_conn()
        conn.execute(f"UPDATE dino_war_hunts SET {keys} WHERE id=?", values)
        conn.commit()
        conn.close()


def register_guard_intent(round_key, user_id, count=1):
    """count تا سهمیه‌ی نگهبانی جدید برای این کاربر تو این دور باز می‌کنه (درهاشون هنوز
    انتخاب نشده). این‌جوری یه دایناسور که چندتا در پوشش میده، همه‌ی سهمیه‌هاش یهو باز میشه."""
    with db_lock:
        conn = get_conn()
        for _ in range(count):
            conn.execute(
                "INSERT INTO dino_war_guards (round_key, user_id, door_index) VALUES (?, ?, NULL)",
                (round_key, user_id)
            )
        conn.commit()
        conn.close()


def get_next_open_guard_slot(round_key, user_id):
    """قدیمی‌ترین سهمیه‌ی این کاربر تو این دور که هنوز درش انتخاب نشده."""
    with db_lock:
        conn = get_conn()
        row = conn.execute(
            "SELECT id FROM dino_war_guards WHERE round_key=? AND user_id=? AND door_index IS NULL ORDER BY id LIMIT 1",
            (round_key, user_id)
        ).fetchone()
        conn.close()
        return row["id"] if row else None


def get_user_guard_slots_used(round_key, user_id):
    """چندتا سهمیه‌ی نگهبانی این کاربر همین الان تو این دور جنگ ثبت کرده (چه در گرفته باشه چه نه)."""
    with db_lock:
        conn = get_conn()
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM dino_war_guards WHERE round_key=? AND user_id=?",
            (round_key, user_id)
        ).fetchone()
        conn.close()
        return row["cnt"] if row else 0


def set_guard_door(round_key, user_id, slot_id, door_index):
    """یه سهمیه‌ی نگهبانیِ مشخص (slot_id) رو پشت یه در می‌ذاره. چون هر نفر می‌تونه چند سهمیه
    (چند دایناسور نگهبان) داشته باشه، هر سهمیه یه در جدا می‌گیره؛ درِ سهمیه‌های دیگه‌ی
    همین کاربر دست‌نخورده می‌مونه. برمی‌گردونه: True اگه موفق شد، False اگه در انتخابی
    همون لحظه توسط یکی دیگه گرفته شده بود."""
    with db_lock:
        conn = get_conn()
        try:
            conn.execute(
                "INSERT INTO dino_war_guard_doors (round_key, door_index, user_id) VALUES (?, ?, ?)",
                (round_key, door_index, user_id)
            )
        except Exception:
            conn.rollback() if hasattr(conn, "rollback") else None
            conn.close()
            return False

        conn.execute(
            "UPDATE dino_war_guards SET door_index=? WHERE id=?",
            (door_index, slot_id)
        )
        conn.commit()
        conn.close()
        return True


# ---------- جنگ: حمله ----------

def get_user_thief_attacks_used(round_key, user_id):
    """چندتا حمله این کاربر همین الان تو این دور جنگ ثبت کرده."""
    with db_lock:
        conn = get_conn()
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM dino_war_thieves WHERE round_key=? AND user_id=?",
            (round_key, user_id)
        ).fetchone()
        conn.close()
        return row["cnt"] if row else 0


def register_thief_attack(round_key, user_id, target, door_index):
    with db_lock:
        conn = get_conn()
        conn.execute(
            "INSERT INTO dino_war_thieves (round_key, user_id, target, door_index) VALUES (?, ?, ?, ?)",
            (round_key, user_id, target, door_index)
        )
        conn.commit()
        conn.close()


def get_round_thieves(round_key):
    with db_lock:
        conn = get_conn()
        rows = conn.execute(
            "SELECT user_id, target, door_index FROM dino_war_thieves WHERE round_key=?", (round_key,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]


def get_round_guards(round_key):
    with db_lock:
        conn = get_conn()
        rows = conn.execute(
            "SELECT user_id, door_index FROM dino_war_guards WHERE round_key=? AND door_index IS NOT NULL",
            (round_key,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]


# =========================================================
#                    منطق رزولوشن جنگ
# =========================================================

def resolve_war_round(round_key):
    """درهای همه‌ی حمله‌ها و دفاع‌های این دور رو مقایسه می‌کنه، خزانه‌ها رو آپدیت
    می‌کنه، و یه گزارش برای پخش تو گروه‌ها برمی‌گردونه."""
    thieves = get_round_thieves(round_key)
    guards = get_round_guards(round_key)
    our_door_count = get_locked_our_door_count(round_key)
    # نکته: یه نفر می‌تونه چند در همزمان داشته باشه (چند دایناسور نگهبان)، پس مپینگ
    # واقعی که باید استفاده کنیم "در -> کاربر" ـه، نه "کاربر -> در" (که فقط آخری رو نگه می‌داشت)
    door_owner = {g["door_index"]: g["user_id"] for g in guards}
    our_guard_doors = set(door_owner.keys())

    lines = [f"⚔️ نتیجه‌ی جنگ ساعت {round_key[11:16]}:\n"]
    any_activity = False

    # --- حمله‌های ما به باشگاه‌های NPC ---
    thieves_per_target = {}
    for t in thieves:
        thieves_per_target.setdefault(t["target"], []).append(t)

    for target, atk_list in thieves_per_target.items():
        target_name = LEAGUE_NPC_TEAMS.get(target, (target,))[0]
        # نگهبانی NPC از اول دور قفل شده (نه اینجا رندوم)، تا جاسوسی معنی داشته باشه
        guarded_door = get_locked_npc_guarded_door(round_key, target)
        for atk in atk_list:
            any_activity = True
            if atk["door_index"] == guarded_door:
                lines.append(f"🚨 {name_of(atk['user_id'])} تو حمله به {target_name} لو رفت و دست‌خالی برگشت!")
            else:
                amount = steal_from_treasury(target, CITY_KEY)
                lines.append(f"🎉 {name_of(atk['user_id'])} از {target_name} دزدید! (+{amount} به خزانه‌ی ما)")

    # --- حمله‌ی خودکار باشگاه‌های NPC به شهر ما ---
    # اگه امروز هیچ‌کس تو این دور نه نگهبان ثبت کرده نه دزد فرستاده، یعنی کلاً کسی
    # بازی نکرده -> NPCها هم اصلاً حمله نمی‌کنن (بدون فعالیت، بدون ریسک از دست دادن خزانه)
    if thieves or guards:
        for npc_key in LEAGUE_NPC_TEAMS:
            if is_attack_disabled(round_key, npc_key):
                lines.append(f"🏹 {LEAGUE_NPC_TEAMS[npc_key][0]} امروز توسط یه شکارچی زمین‌گیر شده بود و اصلاً حمله نکرد!")
                any_activity = True
                continue
            any_activity = True
            chosen_door = random.randint(1, our_door_count)  # NPC هم شانسی حمله می‌کنه
            if chosen_door in our_guard_doors:
                guard_uid = door_owner[chosen_door]
                lines.append(f"🛡️ {LEAGUE_NPC_TEAMS[npc_key][0]} حمله کرد ولی {name_of(guard_uid)} جلوی در {chosen_door} گرفتش!")
            else:
                amount = steal_from_treasury(CITY_KEY, npc_key)
                lines.append(f"💸 {LEAGUE_NPC_TEAMS[npc_key][0]} از در {chosen_door} وارد شد و {amount} سکه از خزانه‌ی ما دزدید!")

    if not any_activity:
        lines.append("این دور هیچ‌کس حمله یا دفاع نکرد، خبری نبود.")

    lines.append(f"\n🏦 موجودی فعلی خزانه‌ی شهر ما: {get_treasury(CITY_KEY)} سکه")

    return "\n".join(lines)


def name_of(user_id):
    user = get_user_row(user_id)
    if user and user.get("username"):
        return user["username"]
    return f"کاربر{user_id}"


def distribute_treasury_interest():
    balance = get_treasury(CITY_KEY)
    interest = round(balance * TREASURY_INTEREST_PCT)
    if interest <= 0:
        return None
    eligible = []
    for uid in get_all_user_ids():
        user = get_user_row(uid)
        if user and compute_level(user) >= CITY_UNLOCK_LEVEL:
            eligible.append(uid)
    if not eligible:
        return None
    share = interest // len(eligible)
    if share <= 0:
        return None
    for uid in eligible:
        adjust_coins(uid, share)
    adjust_treasury(CITY_KEY, -interest)  # سود از خودِ خزانه پرداخت می‌شه (کم می‌شه)، بین بازیکنا پخش می‌شه
    return (
        f"🏦 گزارش خزانه‌ی امروز شهر:\n\n"
        f"💰 موجودی خزانه: {balance} سکه\n"
        f"📈 سود امروز ({int(TREASURY_INTEREST_PCT*100)}٪): {interest} سکه بین {len(eligible)} نفر بازیکن لول۲+ تقسیم شد\n"
        f"👤 سهم هرکس: {share} سکه\n\n"
        f"شب همگی بخیر! 🌙"
    )


# =========================================================
#                    پیام‌ها و دکمه‌ها
# =========================================================

def send_hunt_message():
    slot_key = current_hunt_slot_key()
    text = (
        "🦖 یه گله‌ی بزرگ دایناسور داره از کنار شهر رد می‌شه!\n\n"
        "همین‌جا تو گروه 🎯 بفرست (نیازی به ریپلای نیست) —\n"
        "اگه ۵ یا ۶ بیاری، یکیشونو رام می‌کنی!\n"
        f"(هر نفر حداکثر {HUNT_MAX_ATTEMPTS_PER_SLOT} تیر داره)"
    )
    for chat_id in _get_active_chats():
        try:
            sent = bot.send_message(chat_id, text)
            register_hunt_message(slot_key, chat_id, sent.message_id)
        except Exception:
            pass


def _get_active_chats():
    with db_lock:
        conn = get_conn()
        rows = conn.execute("SELECT chat_id FROM active_chats").fetchall()
        conn.close()
        return [r["chat_id"] for r in rows]


def handle_dart_reply(message):
    """باید از stable_bot.py برای content_types=['dice'] صدا زده بشه."""
    if not is_group(message):
        return
    if not message.dice or message.dice.emoji != "🎯":
        return
    mark_chat_active(message.chat.id)

    slot_key = current_hunt_slot_key()

    user_id = message.from_user.id
    attempt_info = get_hunt_attempt(slot_key, user_id)
    if attempt_info["caught"]:
        return  # همین امروز/این گله قبلاً گرفته
    if attempt_info["attempts"] >= HUNT_MAX_ATTEMPTS_PER_SLOT:
        return  # تیرش تموم شده

    is_bullseye = (message.dice.value >= HUNT_SUCCESS_MIN_VALUE)
    record_hunt_attempt(slot_key, user_id, caught_now=is_bullseye)

    if is_bullseye:
        create_dino_catch(user_id)
        bot.reply_to(
            message,
            "🎯 آفرین! یه دایناسور رام کردی!\n\n"
            "نقشش هنوز مشخص نیست — موقع جنگ، خودت تعیین می‌کنی می‌خوای نگهبان، دزد، جاسوس یا شکارچی باشه.\n"
            f"(هر نقش رو حداکثر {ROLE_DAILY_USE_CAP} بار در روز می‌تونی بزنی)"
        )
    else:
        remaining = HUNT_MAX_ATTEMPTS_PER_SLOT - (attempt_info["attempts"] + 1)
        if remaining > 0:
            bot.reply_to(message, f"🎯 این یکی خطا رفت... {remaining} تیر دیگه داری.")


def _new_war_round_key():
    """یه شناسه‌ی کاملاً یکتا برای یه دور جنگ جدید می‌سازه (بر پایه‌ی لحظه‌ی دقیق
    اعلام، نه ساعت گرد شده‌ی کلاک). قبلاً round_key فقط «نزدیک‌ترین ساعت جنگی روی
    کلاک» بود، پس هر دور جدیدی که تو همون بازه‌ی ۳ساعته اعلام می‌شد (مثلاً با
    /تست_دایناسور) دقیقاً همون ردیف دیتابیسِ دور قبلی رو به اشتراک می‌ذاشت -- اگه
    اون دور قبلی already resolved بود، دور «جدید» هم فوراً resolved به‌حساب میومد
    و دکمه‌هاش بلافاصله با پیام «این دور به پایان رسیده» رد می‌شدن."""
    return iran_now().isoformat()


def send_war_announcement():
    round_key = _new_war_round_key()
    with db_lock:
        conn = get_conn()
        try:
            conn.execute(
                "INSERT INTO dino_war_rounds (round_key, announced, resolved, announced_at) VALUES (?, 1, 0, ?)",
                (round_key, round_key)
            )
        except Exception:
            pass
        conn.commit()
        conn.close()

    users_with_dino = get_users_with_available_dino()

    for chat_id in _get_active_chats():
        try:
            if users_with_dino:
                kb = types.InlineKeyboardMarkup(row_width=2)
                kb.add(
                    types.InlineKeyboardButton("🛡️ نگهبانی", callback_data=f"dino:guard_in:{round_key}"),
                    types.InlineKeyboardButton("🦹 دزدی", callback_data=f"dino:thief_in:{round_key}"),
                    types.InlineKeyboardButton("🔭 جاسوسی", callback_data=f"dino:spy_in:{round_key}"),
                    types.InlineKeyboardButton("🏹 شکار", callback_data=f"dino:hunter_in:{round_key}"),
                )
                bot.send_message(
                    chat_id,
                    "⚔️ جنگ شروع شد! اگه دایناسورِ خامِ استفاده‌نشده داری، انتخاب کن این دفعه می‌خوای چیکار کنه:",
                    reply_markup=kb
                )
        except Exception:
            pass


# ---------- ابزار تست دستی (فقط برای @shay_hay) ----------

DINO_TEST_ADMIN_USERNAME = "shay_hay"  # بدون @


def _is_dino_test_admin(message):
    username = (message.from_user.username or "")
    return username.lower() == DINO_TEST_ADMIN_USERNAME.lower()


def force_send_war_announcement():
    """مثل send_war_announcement ولی برای تست دستیه؛ همیشه یه round_key کاملاً
    یکتای جدید می‌سازه (نه بر پایه‌ی ساعت کلاک) تا هیچ‌وقت با یه دور قبلی که
    ممکنه از قبل resolved شده باشه تداخل نکنه."""
    round_key = _new_war_round_key()
    with db_lock:
        conn = get_conn()
        try:
            conn.execute(
                "INSERT INTO dino_war_rounds (round_key, announced, resolved, announced_at) VALUES (?, 1, 0, ?)",
                (round_key, round_key)
            )
            conn.commit()
        except Exception:
            pass
        conn.close()

    users_with_dino = get_users_with_available_dino()

    for chat_id in _get_active_chats():
        try:
            if users_with_dino:
                kb = types.InlineKeyboardMarkup(row_width=2)
                kb.add(
                    types.InlineKeyboardButton("🛡️ نگهبانی", callback_data=f"dino:guard_in:{round_key}"),
                    types.InlineKeyboardButton("🦹 دزدی", callback_data=f"dino:thief_in:{round_key}"),
                    types.InlineKeyboardButton("🔭 جاسوسی", callback_data=f"dino:spy_in:{round_key}"),
                    types.InlineKeyboardButton("🏹 شکار", callback_data=f"dino:hunter_in:{round_key}"),
                )
                bot.send_message(
                    chat_id,
                    "⚔️ (تست دستی) جنگ شروع شد! اگه دایناسورِ خام داری، انتخاب کن چیکار کنه:",
                    reply_markup=kb
                )
            else:
                bot.send_message(chat_id, "⚔️ (تست دستی) دور جنگ شروع شد، ولی هیچ‌کس دایناسورِ خامِ استفاده‌نشده نداره.")
        except Exception:
            pass


@bot.message_handler(commands=["تست_دایناسور"])
def handle_dino_test_command(message):
    if not _is_dino_test_admin(message):
        return  # سکوت کامل؛ کس دیگه‌ای نباید حتی بفهمه این دستور وجود داره
    send_hunt_message()
    force_send_war_announcement()
    bot.reply_to(message, "✅ هم پیام گله‌ی دایناسور، هم اعلام جنگ، همین الان دستی فرستاده شد.")


def render_guard_door_menu(round_key):
    door_count = get_locked_our_door_count(round_key)
    filled = {g["door_index"]: g["user_id"] for g in get_round_guards(round_key)}
    kb = types.InlineKeyboardMarkup(row_width=4)
    buttons = []
    lines = ["🛡️ کدوم در می‌خوای وایستی؟ (وضعیت فعلی درای شهر:)"]
    for i in range(1, door_count + 1):
        if i in filled:
            lines.append(f"🔒 در {i} — {name_of(filled[i])} نگهبانشه")
        else:
            buttons.append(types.InlineKeyboardButton(f"🚪 {i}", callback_data=f"dino:guard_door:{round_key}:{i}"))
    kb.add(*buttons)
    return "\n".join(lines), kb


def render_thief_target_menu(round_key):
    kb = types.InlineKeyboardMarkup(row_width=1)
    for npc_key, (name, _) in LEAGUE_NPC_TEAMS.items():
        kb.add(types.InlineKeyboardButton(name, callback_data=f"dino:thief_target:{round_key}:{npc_key}"))
    return "🦹 دایناسور دزدت آماده‌ست! کدوم باشگاه رو می‌زنی؟", kb


def render_thief_door_menu(round_key, target):
    door_count = NPC_TARGET_DOOR_COUNT
    name = LEAGUE_NPC_TEAMS.get(target, (target,))[0]
    kb = types.InlineKeyboardMarkup(row_width=4)
    buttons = [
        types.InlineKeyboardButton(f"{i}", callback_data=f"dino:thief_door:{round_key}:{target}:{i}")
        for i in range(1, door_count + 1)
    ]
    kb.add(*buttons)
    return f"🚪 شهر {name} {door_count} تا در داره. کدومو می‌زنی؟\n(نمی‌دونی نگهبانش پشت کدومه...)", kb


# =========================================================
#                    callback dispatcher
# =========================================================

def is_round_still_open(round_key):
    """True فقط اگه این دور جنگ هنوز باز باشه: یعنی هم رزولو نشده باشه، هم هنوز از
    زمان اعلامش (announced_at) کمتر از WAR_ROUND_DEADLINE_HOURS نگذشته باشه.
    قبلاً این چک با current_war_round_key() (بر پایه ساعت کلاک) مقایسه می‌شد که با
    مهلت واقعی ۲.۵ ساعته هماهنگ نبود و باعث می‌شد دکمه‌ها زودتر از موعد «منقضی» بشن."""
    with db_lock:
        conn = get_conn()
        row = conn.execute(
            "SELECT resolved, announced_at FROM dino_war_rounds WHERE round_key=?",
            (round_key,)
        ).fetchone()
        conn.close()
    if row is None:
        return False
    if row["resolved"]:
        return False
    if row["announced_at"]:
        announced_at = datetime.fromisoformat(row["announced_at"])
        if iran_now() >= announced_at + timedelta(hours=WAR_ROUND_DEADLINE_HOURS):
            return False
    return True


def handle_dino_callback(call):
    """باید از دیسپچر callback اصلی تو stable_bot.py صدا زده بشه وقتی data با dino: شروع میشه."""
    data = call.data
    user_id = call.from_user.id
    parts = data.split(":")
    action = parts[1]

    # همه‌ی اکشن‌های دایناسور، round_key رو تو parts[2] دارن؛ اگه اون دور دیگه دور جاری نیست،
    # یعنی جنگ تموم شده و این دکمه‌ی قدیمیه -> اجازه‌ی هیچ عملی روش نده
    if len(parts) > 2 and not is_round_still_open(parts[2]):
        bot.answer_callback_query(call.id, "❌ این دور به پایان رسیده و دیگه نمی‌تونی روش کاری انجام بدی.", show_alert=True)
        return

    if action == "guard_in":
        round_key = parts[2]
        doors_per_guard = get_doors_per_guard(round_key, user_id)
        if not try_use_dino_for_role(user_id, "guard"):
            uses_today = get_user_role_uses_today(user_id, "guard")
            if uses_today >= ROLE_DAILY_USE_CAP:
                msg = f"سهمیه‌ی امروزت برای نگهبانی تموم شده (حداکثر {ROLE_DAILY_USE_CAP} بار در روز)."
            else:
                msg = "دایناسور خامِ استفاده‌نشده نداری! اول باید یکی شکار کنی."
            bot.answer_callback_query(call.id, msg, show_alert=True)
            return
        register_guard_intent(round_key, user_id, doors_per_guard)
        text, kb = render_guard_door_menu(round_key)
        bot.send_message(call.message.chat.id, f"🛡️ این دایناسورت رو نگهبان کردی! می‌تونه {doors_per_guard} در رو پوشش بده.\n\n{text}", reply_markup=kb)
        bot.answer_callback_query(call.id)

    elif action == "guard_door":
        round_key, door_str = parts[2], parts[3]
        door_index = int(door_str)
        slot_id = get_next_open_guard_slot(round_key, user_id)
        if slot_id is None:
            bot.answer_callback_query(call.id, "سهمیه‌ی این دایناسورت تموم شده!", show_alert=True)
            return
        if door_index in get_taken_doors(round_key):
            bot.answer_callback_query(call.id, "این در همین الان گرفته شد، یکی دیگه رو انتخاب کن!", show_alert=True)
            text, kb = render_guard_door_menu(round_key)
            bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=kb)
            return
        success = set_guard_door(round_key, user_id, slot_id, door_index)
        if not success:
            bot.answer_callback_query(call.id, "این در همین لحظه توسط یکی دیگه گرفته شد، دوباره امتحان کن!", show_alert=True)
            text, kb = render_guard_door_menu(round_key)
            bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=kb)
            return
        next_slot = get_next_open_guard_slot(round_key, user_id)
        if next_slot is not None:
            text, kb = render_guard_door_menu(round_key)
            bot.edit_message_text(f"✅ پشت در {door_index} وایستادی!\nهمین دایناسورت باید یه در دیگه هم پوشش بده:\n\n{text}", call.message.chat.id, call.message.message_id, reply_markup=kb)
        else:
            bot.edit_message_text(f"✅ پشت در {door_index} وایستادی. موفق باشی!", call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id)

    elif action == "thief_in":
        round_key = parts[2]
        if not try_use_dino_for_role(user_id, "thief"):
            uses_today = get_user_role_uses_today(user_id, "thief")
            if uses_today >= ROLE_DAILY_USE_CAP:
                msg = f"سهمیه‌ی امروزت برای دزدی تموم شده (حداکثر {ROLE_DAILY_USE_CAP} بار در روز)."
            else:
                msg = "دایناسور خامِ استفاده‌نشده نداری! اول باید یکی شکار کنی."
            bot.answer_callback_query(call.id, msg, show_alert=True)
            return
        text, kb = render_thief_target_menu(round_key)
        bot.send_message(call.message.chat.id, f"🦹 این دایناسورت رو دزد کردی! حالا هدف رو انتخاب کن:\n\n{text}", reply_markup=kb)
        bot.answer_callback_query(call.id)

    elif action == "thief_target":
        round_key, target = parts[2], parts[3]
        text, kb = render_thief_door_menu(round_key, target)
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=kb)
        bot.answer_callback_query(call.id)

    elif action == "thief_door":
        round_key, target, door_str = parts[2], parts[3], parts[4]
        register_thief_attack(round_key, user_id, target, int(door_str))
        remaining = ROLE_DAILY_USE_CAP - get_user_role_uses_today(user_id, "thief")
        extra = f"\n(هنوز {remaining} بار دیگه می‌تونی امروز دزدی کنی؛ اگه دایناسورِ خام داری، دوباره از دکمه‌ی «حمله با دایناسور دزد» استفاده کن.)" if remaining > 0 else ""
        bot.edit_message_text(
            f"✅ حمله ثبت شد! نتیجه‌ی این دور، نیم‌ساعت قبل از جنگ بعدی اعلام می‌شه.{extra}",
            call.message.chat.id, call.message.message_id
        )
        bot.answer_callback_query(call.id)

    elif action == "spy_in":
        round_key = parts[2]
        if not try_use_dino_for_role(user_id, "spy"):
            uses_today = get_user_role_uses_today(user_id, "spy")
            if uses_today >= ROLE_DAILY_USE_CAP:
                msg = f"سهمیه‌ی امروزت برای جاسوسی تموم شده (حداکثر {ROLE_DAILY_USE_CAP} بار در روز)."
            else:
                msg = "دایناسور خامِ استفاده‌نشده نداری! اول باید یکی شکار کنی."
            bot.answer_callback_query(call.id, msg, show_alert=True)
            return
        text, kb = render_spy_target_menu(round_key)
        bot.send_message(call.message.chat.id, f"🔭 این دایناسورت رو جاسوس کردی! حالا هدف رو انتخاب کن:\n\n{text}", reply_markup=kb)
        bot.answer_callback_query(call.id)

    elif action == "spy_target":
        round_key, target = parts[2], parts[3]
        revealed, suspicious = spy_on_target(round_key, target)
        register_spy_action(round_key, user_id, target)
        target_name = LEAGUE_NPC_TEAMS.get(target, (target,))[0]
        revealed_str = "، ".join(str(d) for d in revealed)
        suspicious_str = "، ".join(str(d) for d in suspicious)
        remaining = ROLE_DAILY_USE_CAP - get_user_role_uses_today(user_id, "spy")
        extra = f"\n(هنوز {remaining} بار دیگه می‌تونی امروز جاسوسی کنی.)" if remaining > 0 else ""
        bot.answer_callback_query(
            call.id,
            f"🔭 گزارش محرمانه درباره‌ی {target_name}:\n"
            f"این درا مطمئناً خالی‌ان: {revealed_str}\n"
            f"نگهبان یکی از این درای مشکوکه: {suspicious_str}\n"
            f"(این پیام فقط به خودت نشون داده شد، خودت باید به دزدای تیم بگی!){extra}",
            show_alert=True
        )

    elif action == "hunter_in":
        round_key = parts[2]
        if get_active_hunt(round_key, user_id):
            bot.answer_callback_query(call.id, "همین الان یه شکار نیمه‌کاره داری! اول اونو تموم کن.", show_alert=True)
            return
        if not try_use_dino_for_role(user_id, "hunter"):
            uses_today = get_user_role_uses_today(user_id, "hunter")
            if uses_today >= ROLE_DAILY_USE_CAP:
                msg = f"سهمیه‌ی امروزت برای شکار تموم شده (حداکثر {ROLE_DAILY_USE_CAP} بار در روز)."
            else:
                msg = "دایناسور خامِ استفاده‌نشده نداری! اول باید یکی شکار کنی."
            bot.answer_callback_query(call.id, msg, show_alert=True)
            return
        text, kb = render_hunter_target_menu(round_key)
        bot.send_message(call.message.chat.id, f"🏹 این دایناسورت رو شکارچی کردی! حالا هدف رو انتخاب کن:\n\n{text}", reply_markup=kb)
        bot.answer_callback_query(call.id)

    elif action == "hunter_target":
        round_key, target = parts[2], parts[3]
        target_name = LEAGUE_NPC_TEAMS.get(target, (target,))[0]
        sent = bot.send_message(
            call.message.chat.id,
            f"🦖 دایناسورِ {target_name} تو جنگل پیدا شده!\n"
            f"یه جهت رو انتخاب کن و شکارش کن ({HUNTER_MAX_SHOTS} تیر داری):"
        )
        hunt_id = start_hunt(round_key, user_id, target, call.message.chat.id, sent.message_id)
        kb = render_hunter_shot_keyboard(round_key, hunt_id)
        bot.edit_message_reply_markup(call.message.chat.id, sent.message_id, reply_markup=kb)
        bot.answer_callback_query(call.id)

    elif action == "hunter_shoot":
        round_key, hunt_id_str, chosen_dir = parts[2], parts[3], parts[4]
        hunt_id = int(hunt_id_str)
        hunt = get_hunt_by_id(hunt_id)
        if hunt is None or hunt["resolved"] or hunt["user_id"] != user_id:
            bot.answer_callback_query(call.id, "این شکار مال تو نیست یا قبلاً تموم شده!", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "🏹 تیر در حال طی شدن است... ⌛",
            hunt["chat_id"], hunt["message_id"]
        )
        time.sleep(HUNTER_SHOT_DELAY_SECONDS)

        # دوباره از دیتابیس می‌خونیم چون ممکنه بین این‌همه، وضعیتش عوض شده باشه
        hunt = get_hunt_by_id(hunt_id)
        target_name = LEAGUE_NPC_TEAMS.get(hunt["target"], (hunt["target"],))[0]

        if chosen_dir == hunt["hidden_dir"]:
            update_hunt(hunt_id, resolved=1, success=1)
            disable_attack(round_key, hunt["target"])
            bot.edit_message_text(
                f"🎯 خورد! دایناسورِ {target_name} اسیر شد.\n"
                f"دیگه این دور اصلاً به شهر ما حمله نمی‌کنن 🏹🛡️",
                hunt["chat_id"], hunt["message_id"]
            )
            return

        new_shots = hunt["shots_used"] + 1
        if new_shots >= HUNTER_MAX_SHOTS:
            update_hunt(hunt_id, resolved=1, success=0, shots_used=new_shots)
            bot.edit_message_text(
                f"💨 هر {HUNTER_MAX_SHOTS} تیرت خطا رفت، دایناسورِ {target_name} فرار کرد.",
                hunt["chat_id"], hunt["message_id"]
            )
            return

        # فرار کرد و رفت یه جهت دیگه؛ باید دوباره حدس زده بشه
        other_dirs = [d for d in HUNTER_DIRECTIONS if d != hunt["hidden_dir"]]
        new_hidden = random.choice(other_dirs)
        update_hunt(hunt_id, shots_used=new_shots, hidden_dir=new_hidden)
        remaining = HUNTER_MAX_SHOTS - new_shots
        kb = render_hunter_shot_keyboard(round_key, hunt_id)
        bot.edit_message_text(
            f"💨 نخورد! دایناسورِ {target_name} جابه‌جا شد. {remaining} تیر دیگه داری:",
            hunt["chat_id"], hunt["message_id"], reply_markup=kb
        )


@bot.message_handler(content_types=["dice"])
def _dino_dart_handler(message):
    if message.dice and message.dice.emoji == "🎯":
        handle_dart_reply(message)


# =========================================================
#                    حلقه‌ی زمان‌بندی
# =========================================================

def dino_loop():
    while True:
        time.sleep(LOOP_INTERVAL_SECONDS)
        try:
            current = iran_now()
            today = _today_str(current)

            # ریست نیمه‌شب
            if current.hour == 0 and current.minute < 1 and _get_flag("dino_reset_date") != today:
                reset_daily_dinos()
                _set_flag("dino_reset_date", today)

            # اعلام شکار
            if current.hour in HUNT_HOURS and current.minute < 1:
                slot_key = current_hunt_slot_key(current)
                if _get_flag(f"dino_hunt_sent_{slot_key}") != "1":
                    send_hunt_message()
                    _set_flag(f"dino_hunt_sent_{slot_key}", "1")

            # اعلام جنگ (window_key فقط برای اینه که تو یه بازه‌ی ۳ساعته دوبار
            # اعلام خودکار نفرسته؛ round_key واقعیِ هر دور داخل خودِ
            # send_war_announcement به‌صورت یکتا ساخته می‌شه)
            if current.hour in WAR_HOURS and current.minute < 1:
                window_key = current_war_round_key(current)
                if _get_flag(f"dino_war_announced_{window_key}") != "1":
                    send_war_announcement()
                    _set_flag(f"dino_war_announced_{window_key}", "1")

            # رزولوشن جنگ (۲.۵ ساعت بعد از لحظه‌ی واقعیِ اعلام، نه بر اساس ساعت کلاک؛
            # قبلاً بر اساس «نیم‌ساعت قبل از دور بعدی روی کلاک» حساب می‌شد که با تست
            # دستی یا داون‌تایم به‌هم می‌ریخت و باعث می‌شد جنگ همون لحظه‌ی شروع تموم بشه)
            with db_lock:
                conn = get_conn()
                row = conn.execute(
                    "SELECT round_key, announced_at FROM dino_war_rounds "
                    "WHERE announced=1 AND resolved=0 AND announced_at IS NOT NULL"
                ).fetchall()
                conn.close()
            for r in row:
                round_key = r["round_key"]
                announced_at = datetime.fromisoformat(r["announced_at"])
                resolve_time = announced_at + timedelta(hours=WAR_ROUND_DEADLINE_HOURS)
                if current >= resolve_time and _get_flag(f"dino_war_resolved_{round_key}") != "1":
                    report = resolve_war_round(round_key)
                    broadcast_to_all_chats(report)
                    _set_flag(f"dino_war_resolved_{round_key}", "1")
                    with db_lock:
                        conn = get_conn()
                        conn.execute(
                            "UPDATE dino_war_rounds SET resolved=1 WHERE round_key=?", (round_key,)
                        )
                        conn.commit()
                        conn.close()

            # سود شبانه‌ی خزانه
            if (current.hour == TREASURY_INTEREST_HOUR and current.minute >= TREASURY_INTEREST_MINUTE
                    and _get_flag("dino_interest_date") != today):
                report = distribute_treasury_interest()
                if report:
                    broadcast_to_all_chats(report)
                _set_flag("dino_interest_date", today)

        except Exception as e:
            print("خطا در سیستم دایناسور:", e)


def _get_flag(key):
    with db_lock:
        conn = get_conn()
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        conn.close()
        return row["value"] if row else None


def _set_flag(key, value):
    with db_lock:
        conn = get_conn()
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value))
        )
        conn.commit()


def run_dummy_web_server():
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Stable bot is running!")

        def log_message(self, format, *args):
            pass

    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()


# =========================================================
#                    🚀 اجرا 🚀
# =========================================================

def fix_legacy_zero_audience():
    """اصلاح یک‌باره: کاربرای قدیمی که به‌خاطر باگ قبلی تماشاچی‌شون صفر مونده بود
    (و هیچ رکورد فراری هم در انتظار برگشت ندارن، یعنی واقعاً هیچ‌وقت تماشاچی نگرفتن)
    رو به ظرفیت کامل برمی‌گردونه."""
    with db_lock:
        conn = get_conn()
        users = conn.execute(
            "SELECT user_id, track_capacity FROM users WHERE track_audience = 0"
        ).fetchall()
        for u in users:
            pending = conn.execute(
                "SELECT COUNT(*) as cnt FROM audience_returns WHERE user_id=?",
                (u["user_id"],)
            ).fetchone()
            if pending["cnt"] == 0:
                conn.execute(
                    "UPDATE users SET track_audience=? WHERE user_id=?",
                    (u["track_capacity"], u["user_id"])
                )
        conn.commit()
        conn.close()


def recover_pending_races():
    """موقع بالا اومدن ربات صدا زده میشه. دو حالت رو چک می‌کنه:
    ۱) مسابقه‌ای که زمانش قبل از ری‌استارت تموم شده بود ولی چون تایمرش تو حافظه
       بود از بین رفت -> همین الان تسویه‌ش می‌کنیم (سکه واریز + پیام نتیجه).
    ۲) مسابقه‌ای که هنوز در جریانه (racing_until تو آینده‌ست) -> یه تایمر جدید
       براش می‌سازیم که با زمان باقی‌مونده‌ی واقعی کار کنه، نه از اول.
    این‌جوری دیگه هیچ مسابقه‌ای با ری‌استارت Render گم نمیشه."""
    with db_lock:
        conn = get_conn()
        rows = conn.execute(
            "SELECT * FROM horses WHERE race_settled=0 AND racing_until IS NOT NULL"
        ).fetchall()
        conn.close()

    recovered = 0
    rearmed = 0
    for row in rows:
        horse = dict(row)
        racing_until = parse_time(horse.get("racing_until"))
        if racing_until is None:
            continue

        # اسبِ چندمِ این کاربره؟ finish_race با ایندکس نمایشی کار می‌کنه نه id خام
        user_horses = get_horses(horse["user_id"])
        horse_index = next((i + 1 for i, h in enumerate(user_horses) if h["id"] == horse["id"]), None)
        if horse_index is None:
            continue

        chat_id = horse.get("race_chat_id")
        coins_earned = horse.get("race_coins_earned")
        performance = horse.get("race_performance")
        if chat_id is None or coins_earned is None or performance is None:
            # اطلاعات لازم برای تسویه رو نداریم (مسابقه‌ی خیلی قدیمی‌تر از این فیکس)؛
            # فقط پرچمش رو تسویه‌شده می‌زنیم که اسب برای همیشه گیر نکنه
            update_horse(horse["id"], race_settled=1)
            continue

        remaining = (racing_until - now()).total_seconds()
        if remaining <= 0:
            finish_race(horse["user_id"], chat_id, coins_earned, performance, horse_index)
            recovered += 1
        else:
            timer = threading.Timer(
                remaining, finish_race,
                args=(horse["user_id"], chat_id, coins_earned, performance, horse_index)
            )
            timer.daemon = True
            timer.start()
            rearmed += 1

    if recovered or rearmed:
        print(f"بازیابی مسابقه‌ها: {recovered} تا تسویه شد، {rearmed} تا دوباره تایمرش ست شد.")


if __name__ == "__main__":
    init_db()
    print("دیتابیس آماده شد.")
    if DATABASE_URL:
        print("✅ در حال استفاده از Supabase (دائمی)")
    else:
        print("⚠️ هشدار: DATABASE_URL تنظیم نشده! داره از فایل موقت SQLite استفاده می‌کنه و اطلاعات با هر ری‌استارت پاک میشه.")

    fix_legacy_zero_audience()
    print("اصلاح حساب‌های قدیمی (تماشاچی صفر) انجام شد.")

    init_dino_tables()
    print("جداول سیستم دایناسور آماده شد.")

    recover_pending_races()
    print("بازیابی مسابقه‌های ناتموم انجام شد.")

    lottery_thread = threading.Thread(target=lottery_loop, daemon=True)
    lottery_thread.start()

    emotion_thread = threading.Thread(target=emotion_check_loop, daemon=True)
    emotion_thread.start()

    newspaper_thread = threading.Thread(target=newspaper_loop, daemon=True)
    newspaper_thread.start()

    beauty_thread = threading.Thread(target=beauty_contest_loop, daemon=True)
    beauty_thread.start()

    league_thread = threading.Thread(target=league_loop, daemon=True)
    league_thread.start()

    dino_thread = threading.Thread(target=dino_loop, daemon=True)
    dino_thread.start()
    print("سیستم دایناسور و جنگ شهر فعال شد.")

    web_thread = threading.Thread(target=run_dummy_web_server, daemon=True)
    web_thread.start()

    print("ربات در حال اجراست... (برای توقف Ctrl+C بزن)")

    bot.infinity_polling()
