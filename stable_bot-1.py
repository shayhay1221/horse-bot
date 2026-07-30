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
ENERGY_REGEN_MINUTES = 60      # هر ۱ ساعت، ۱ واحد انرژی خودکار برمی‌گرده
HAY_PER_FEED_UNIT = 5          # هر واحد گشنگی با ۵ یونجه پر میشه

# ---------- مزرعه ----------
PLOT_BUSHES = 10               # هر قطعه چند بوته داره (فقط جنبه‌ی نمایشی)
PLOT_PLANT_COST = 10           # هزینه‌ی کاشتن یه قطعه‌ی کامل
PLOT_GROW_MINUTES = 60         # زمان رشد
HAY_PER_HARVEST = 20           # یونجه‌ی هر برداشت کامل

# ---------- پیست و تماشاچی ----------
INITIAL_AUDIENCE_CAPACITY = 5
TICKET_PRICE = 2
AUDIENCE_FLEE_PERCENT = 0.10
AUDIENCE_RETURN_HOURS = 24

# ---------- ارتقاها (قیمت پایه + رشد ۲۰٪ بعد از هر خرید) ----------
UPGRADE_BASE_PRICES = {"stable": 120, "track": 96, "farm": 72}
UPGRADE_GROWTH_RATE = 1.20

# ---------- فروشگاه ----------
SHOP_HAY_BUY_PER_10 = 5
SHOP_HAY_SELL_PER_10 = 3
SHOP_ENERGY_POTION_PRICE = 20
SHOP_HORSESHOE_GOOD_PRICE = 100    # ۱۵٪ سریع‌تر
SHOP_HORSESHOE_GREAT_PRICE = 300   # ۳۰٪ سریع‌تر
HORSESHOE_GOOD_REDUCTION = 0.15
HORSESHOE_GREAT_REDUCTION = 0.30

# ---------- قرعه‌کشی روزانه ----------
LOTTERY_PRIZE = 15
LOTTERY_CHECK_INTERVAL_SECONDS = 3600  # هر ساعت چک می‌کنیم که آیا امروز قرعه‌کشی انجام شده یا نه

# =========================================================
#                    🗄️  دیتابیس  🗄️
# =========================================================

db_lock = threading.Lock()


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
                user_id INTEGER PRIMARY KEY,
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
        c.execute("""
            CREATE TABLE IF NOT EXISTS horses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                breed_key TEXT,
                energy INTEGER,
                hunger INTEGER,
                last_energy_update TEXT,
                horseshoe TEXT DEFAULT 'none',
                racing_until TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS farm_plots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                status TEXT DEFAULT 'empty',
                planted_at TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS audience_returns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
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
        conn.commit()
        conn.close()


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
               VALUES (?, ?, ?, 0, 1, ?, 0)""",
            (user_id, username or "", STARTING_COINS, INITIAL_AUDIENCE_CAPACITY)
        )
        # اسب اولیه: خسته و گشنه (انرژی و گشنگی صفر)
        conn.execute(
            """INSERT INTO horses (user_id, breed_key, energy, hunger, last_energy_update, horseshoe)
               VALUES (?, ?, 0, 0, ?, 'none')""",
            (user_id, STARTER_BREED, now().isoformat())
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
    """این تابع اتمیک هست: تو یه قفل واحد چک و کم/زیاد می‌کنه، برای جلوگیری از باگ کسر نشدن موجودی."""
    with db_lock:
        conn = get_conn()
        row = conn.execute("SELECT coins FROM users WHERE user_id=?", (user_id,)).fetchone()
        if row is None:
            conn.close()
            return False, 0
        new_value = row["coins"] + delta
        if new_value < 0:
            conn.close()
            return False, row["coins"]
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
    with db_lock:
        conn = get_conn()
        conn.execute(
            """INSERT INTO horses (user_id, breed_key, energy, hunger, last_energy_update, horseshoe)
               VALUES (?, ?, ?, ?, ?, 'none')""",
            (user_id, breed_key, e, h, now().isoformat())
        )
        conn.commit()
        conn.close()


def apply_energy_regen(horse):
    """محاسبه‌ی تنبل (Lazy) انرژی: بر اساس زمان گذشته، انرژی رو آپدیت و ذخیره می‌کنه."""
    breed = HORSE_BREEDS[horse["breed_key"]]
    max_energy = breed["energy_max"]
    if horse["energy"] >= max_energy:
        return horse

    last_update = parse_time(horse["last_energy_update"]) or now()
    elapsed_minutes = (now() - last_update).total_seconds() / 60
    units_gained = int(elapsed_minutes // ENERGY_REGEN_MINUTES)

    if units_gained <= 0:
        return horse

    new_energy = min(max_energy, horse["energy"] + units_gained)
    # ساعتِ آخرین آپدیت رو به اندازه‌ی واحدهای مصرف‌شده جلو می‌بریم (نه به now کامل، تا واحد اضافه هدر نره)
    new_last_update = last_update + timedelta(minutes=units_gained * ENERGY_REGEN_MINUTES)

    update_horse(horse["id"], energy=new_energy, last_energy_update=new_last_update.isoformat())
    horse["energy"] = new_energy
    horse["last_energy_update"] = new_last_update.isoformat()
    return horse


def is_horse_racing(horse):
    racing_until = parse_time(horse.get("racing_until"))
    return racing_until is not None and racing_until > now()


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
        set_setting("last_chat_id", message.chat.id)
        user_id = message.from_user.id
        username = message.from_user.username or message.from_user.first_name or ""
        ensure_user(user_id, username)
        process_audience_returns(user_id)
        return func(message)
    return wrapper


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
    return (
        f"{index}. {breed['display']}{shoe}\n"
        f"   ⚡ انرژی: {horse['energy']}/{breed['energy_max']}   "
        f"🌾 گشنگی: {horse['hunger']}/{breed['hunger_max']}{status}"
    )


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
    horse = get_horse_by_index(user_id, index)
    if horse is None:
        bot.reply_to(message, "همچین اسبی نداری!")
        return

    if is_horse_racing(horse):
        bot.reply_to(message, "این اسب همین الان تو پیسته، صبر کن نتیجه بیاد!")
        return

    horse = apply_energy_regen(horse)
    breed = HORSE_BREEDS[horse["breed_key"]]

    if horse["energy"] < 1 or horse["hunger"] < 1:
        bot.reply_to(
            message,
            "این اسب خیلی خسته یا گشنه‌ست و نمی‌تونه بدوئه!\n"
            "با /غذا بهش یونجه بده یا صبر کن انرژیش برگرده."
        )
        return

    # تعیین عملکرد بر اساس وضعیت فعلی (قبل از کم شدن)
    energy_frac = horse["energy"] / breed["energy_max"]
    hunger_frac = horse["hunger"] / breed["hunger_max"]

    if energy_frac >= 1.0 and hunger_frac >= 1.0:
        performance = "excellent"
    elif energy_frac >= 0.5 and hunger_frac >= 0.5:
        performance = "average"
    else:
        performance = "poor"

    # کم کردن انرژی و گشنگی (حداقل صفر)
    new_energy = max(0, horse["energy"] - 1)
    new_hunger = max(0, horse["hunger"] - 1)
    update_horse(horse["id"], energy=new_energy, hunger=new_hunger)

    # محاسبه‌ی تماشاچی و سکه
    process_audience_returns(user_id)
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
            new_audience = audience - fled
            update_user_fields(user_id, track_audience=new_audience)
            schedule_audience_return(user_id, fled)

    # محاسبه‌ی زمان دویدن بر اساس نعل
    duration_minutes = breed["race_minutes"]
    if horse["horseshoe"] == "good":
        duration_minutes *= (1 - HORSESHOE_GOOD_REDUCTION)
    elif horse["horseshoe"] == "great":
        duration_minutes *= (1 - HORSESHOE_GREAT_REDUCTION)
    duration_seconds = duration_minutes * 60

    racing_until = now() + timedelta(seconds=duration_seconds)
    update_horse(horse["id"], racing_until=racing_until.isoformat())

    chat_id = message.chat.id
    timer = threading.Timer(
        duration_seconds, finish_race,
        args=(user_id, chat_id, coins_earned, performance, index)
    )
    timer.daemon = True
    timer.start()

    minutes_display = max(1, round(duration_minutes))
    bot.reply_to(
        message,
        f"🏁 اسب شماره {index} رفت تو پیست! {minutes_display} دقیقه‌ی دیگه نتیجه رو اعلام می‌کنم."
    )


def finish_race(user_id, chat_id, coins_earned, performance, horse_index):
    adjust_coins(user_id, coins_earned)

    performance_text = {
        "excellent": "🌟 عملکرد عالی",
        "average": "🙂 عملکرد متوسط",
        "poor": "😞 عملکرد ضعیف (چندتا تماشاچی ناراضی رفتن)",
    }[performance]

    try:
        bot.send_message(
            chat_id,
            f"🏁 نتیجه‌ی مسابقه‌ی اسب شماره {horse_index}:\n"
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

    total_hay = len(ready_plots) * HAY_PER_HARVEST
    for plot in ready_plots:
        set_plot(plot["id"], status="empty", planted_at=None)

    adjust_hay(user_id, total_hay)
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


# =========================================================
#                    💰 کیف پول و راهنما 💰
# =========================================================

@bot.message_handler(commands=["کیف_پول", "wallet"])
@group_only
def handle_wallet(message):
    user = get_user_row(message.from_user.id)
    bot.reply_to(message, f"💰 سکه: {user['coins']}\n🌾 یونجه: {user['hay']}")


HELP_TEXT = """🐴 به بازی «طویله» خوش اومدی!

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

━━━ 💰 عمومی ━━━
/کیف_پول — موجودی سکه و یونجه
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


def build_main_menu():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🐴 اسب‌ها", callback_data="menu:horses"),
        types.InlineKeyboardButton("🌾 مزرعه", callback_data="menu:farm"),
    )
    kb.add(
        types.InlineKeyboardButton("🎪 پیست", callback_data="menu:track"),
        types.InlineKeyboardButton("🏠 طویله", callback_data="menu:stable"),
    )
    kb.add(
        types.InlineKeyboardButton("🛒 فروشگاه", callback_data="menu:shop"),
        types.InlineKeyboardButton("💰 کیف پول", callback_data="menu:wallet"),
    )
    kb.add(
        types.InlineKeyboardButton("🐎 بازار اسب", callback_data="menu:horsemarket"),
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
    bot.reply_to(message, "🐴 منوی طویله — یکی رو انتخاب کن:", reply_markup=build_main_menu())


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
        f"🏠 طویله:\n"
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
    text = f"💰 سکه: {user['coins']}\n🌾 یونجه: {user['hay']}"
    return text, back_button()


@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = call.from_user.id
    username = call.from_user.username or call.from_user.first_name or ""
    ensure_user(user_id, username)
    process_audience_returns(user_id)

    data = call.data
    text, kb = None, None

    try:
        if data == "menu:main":
            text, kb = "🐴 منوی طویله — یکی رو انتخاب کن:", build_main_menu()

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

    if horse["energy"] < 1 or horse["hunger"] < 1:
        return "این اسب خیلی خسته یا گشنه‌ست و نمی‌تونه بدوئه!"

    energy_frac = horse["energy"] / breed["energy_max"]
    hunger_frac = horse["hunger"] / breed["hunger_max"]

    if energy_frac >= 1.0 and hunger_frac >= 1.0:
        performance = "excellent"
    elif energy_frac >= 0.5 and hunger_frac >= 0.5:
        performance = "average"
    else:
        performance = "poor"

    new_energy = max(0, horse["energy"] - 1)
    new_hunger = max(0, horse["hunger"] - 1)
    update_horse(horse["id"], energy=new_energy, hunger=new_hunger)

    process_audience_returns(user_id)
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
    if horse["horseshoe"] == "good":
        duration_minutes *= (1 - HORSESHOE_GOOD_REDUCTION)
    elif horse["horseshoe"] == "great":
        duration_minutes *= (1 - HORSESHOE_GREAT_REDUCTION)
    duration_seconds = duration_minutes * 60

    racing_until = now() + timedelta(seconds=duration_seconds)
    update_horse(horse["id"], racing_until=racing_until.isoformat())

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

    total_hay = len(ready_plots) * HAY_PER_HARVEST
    for plot in ready_plots:
        set_plot(plot["id"], status="empty", planted_at=None)
    adjust_hay(user_id, total_hay)
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
        ok, remaining = adjust_coins(user_id, -price)
        if not ok:
            return f"سکه‌ی کافی نداری! ({remaining} تا داری)"
        update_horse(horse["id"], horseshoe=item_type)
        return "🔨 نعل زده شد!"

    return "چیز نامعتبری بود."


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

            chat_id = get_setting("last_chat_id")
            if chat_id:
                winner = get_user_row(winner_id)
                name = winner["username"] or f"کاربر{winner_id}"
                try:
                    bot.send_message(
                        int(chat_id),
                        f"🎰 قرعه‌کشی امروز!\n🎉 برنده: {name}\n🎁 جایزه: {prize_text}"
                    )
                except Exception:
                    pass
        except Exception as e:
            print("خطا در قرعه‌کشی:", e)


# =========================================================
#                    🌐 وب‌سرور برای سازگاری با Render 🌐
# =========================================================

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

if __name__ == "__main__":
    init_db()
    print("دیتابیس آماده شد.")

    lottery_thread = threading.Thread(target=lottery_loop, daemon=True)
    lottery_thread.start()

    web_thread = threading.Thread(target=run_dummy_web_server, daemon=True)
    web_thread.start()

    print("ربات در حال اجراست... (برای توقف Ctrl+C بزن)")

    bot.infinity_polling()
