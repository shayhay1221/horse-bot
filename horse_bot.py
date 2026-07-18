# -*- coding: utf-8 -*-
"""
ربات بازی اسب‌سواری تلگرام
"""

import telebot
import sqlite3
import random
import threading
import time
import os
from datetime import datetime, timedelta

TOKEN = "8974177847:AAFd7ZC4aO74DdJ3PlpcngIDGHeyMvr24Qc"

DB_PATH = "horse_game.db"

NEIGH_COOLDOWN_MINUTES = 30
NEIGH_MIN_POINTS = 1
NEIGH_MAX_POINTS = 10
GOLDEN_NEIGH_CHANCE = 0.05
GOLDEN_NEIGH_POINTS = 50

LEVELS = [
    (0,    "🐴 کره‌اسب"),
    (400,  "🐎 اسب جوان"),
    (600,  "🏇 اسب مسابقه‌ای"),
    (1000, "👑 اسب افسانه‌ای"),
]

SICKNESS_CHECK_INTERVAL_HOURS = 6
SICKNESS_CHANCE_PER_CHECK = 0.05
TREATMENT_COST = 40

VACCINE_PRICE = 60
VACCINE_DURATION_DAYS = 3

SHOP_ITEMS = {
    "vaccine": ("🩹 واکسن", VACCINE_PRICE, "vaccine"),
    "title_champion": ("👑 عنوان: قهرمان اصطبل", 150, "title"),
    "title_legend": ("👑 عنوان: افسانه دشت", 300, "title"),
    "badge_star": ("🖼️ بج: ستاره طلایی", 100, "badge"),
    "badge_fire": ("🖼️ بج: شعله سرکش", 100, "badge"),
}

RACE_JOIN_SECONDS = 60
RACE_MIN_PLAYERS = 2

DAILY_REWARD = 25
DAILY_COOLDOWN_HOURS = 24

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
                balance INTEGER DEFAULT 0,
                total_earned INTEGER DEFAULT 0,
                last_neigh TEXT,
                sick INTEGER DEFAULT 0,
                vaccine_until TEXT,
                last_daily TEXT,
                title TEXT,
                badge TEXT
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


def get_user(user_id, username=None):
    with db_lock:
        conn = get_conn()
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO users (user_id, username) VALUES (?, ?)",
                (user_id, username or "")
            )
            conn.commit()
            row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        elif username and row["username"] != username:
            conn.execute("UPDATE users SET username=? WHERE user_id=?", (username, user_id))
            conn.commit()
        conn.close()
        return dict(row)


def update_user(user_id, **fields):
    if not fields:
        return
    with db_lock:
        conn = get_conn()
        cols = ", ".join(f"{k}=?" for k in fields)
        values = list(fields.values()) + [user_id]
        conn.execute(f"UPDATE users SET {cols} WHERE user_id=?", values)
        conn.commit()
        conn.close()


def add_balance(user_id, amount, count_as_earned=True):
    user = get_user(user_id)
    new_balance = user["balance"] + amount
    fields = {"balance": new_balance}
    if count_as_earned and amount > 0:
        fields["total_earned"] = user["total_earned"] + amount
    update_user(user_id, **fields)
    return new_balance


def get_all_users():
    with db_lock:
        conn = get_conn()
        rows = conn.execute("SELECT * FROM users").fetchall()
        conn.close()
        return [dict(r) for r in rows]


def now():
    return datetime.now()


def parse_time(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def compute_level(total_earned):
    level_name = LEVELS[0][1]
    for threshold, name in LEVELS:
        if total_earned >= threshold:
            level_name = name
        else:
            break
    return level_name


def display_name(user_row, tg_username=None, first_name=None):
    base = first_name or tg_username or f"کاربر{user_row['user_id']}"
    extras = ""
    if user_row.get("badge"):
        extras += f" {user_row['badge']}"
    if user_row.get("title"):
        extras += f" | {user_row['title']}"
    return f"{base}{extras}"


def is_vaccinated(user_row):
    until = parse_time(user_row.get("vaccine_until"))
    return until is not None and until > now()


bot = telebot.TeleBot(TOKEN, parse_mode=None)

_proxy = os.environ.get("https_proxy") or os.environ.get("http_proxy")
if _proxy:
    telebot.apihelper.proxy = {"https": _proxy}

current_race = {
    "active": False,
    "chat_id": None,
    "bet": None,
    "players": {},
    "timer": None,
}
race_lock = threading.Lock()


def is_group(message):
    return message.chat.type in ("group", "supergroup")


def group_only(func):
    def wrapper(message):
        if not is_group(message):
            bot.reply_to(message, "این بازی فقط توی گروه قابل بازیه 🐴")
            return
        set_setting("last_chat_id", message.chat.id)
        return func(message)
    return wrapper


@bot.message_handler(commands=["shihe", "neigh", "شیهه"])
@group_only
def handle_neigh(message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    user = get_user(user_id, username)

    if user["sick"]:
        bot.reply_to(message, "🤒 اسبت مریضه و نمی‌تونه شیهه بزنه! اول درمانش کن: /darou")
        return

    last_neigh = parse_time(user["last_neigh"])
    if last_neigh:
        remaining = last_neigh + timedelta(minutes=NEIGH_COOLDOWN_MINUTES) - now()
        if remaining.total_seconds() > 0:
            minutes = int(remaining.total_seconds() // 60) + 1
            bot.reply_to(message, f"⏳ اسبت خسته‌ست، {minutes} دقیقه‌ی دیگه دوباره امتحان کن.")
            return

    is_golden = random.random() < GOLDEN_NEIGH_CHANCE
    points = GOLDEN_NEIGH_POINTS if is_golden else random.randint(NEIGH_MIN_POINTS, NEIGH_MAX_POINTS)

    add_balance(user_id, points)
    update_user(user_id, last_neigh=now().isoformat())

    if is_golden:
        bot.reply_to(message, f"✨ شیهه طلایی! {points} یونجه گرفتی! 🌾")
    else:
        bot.reply_to(message, f"🐴 شیهه زدی و {points} یونجه گرفتی! 🌾")


@bot.message_handler(commands=["darou", "درمان", "دارو"])
@group_only
def handle_treatment(message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    user = get_user(user_id, username)

    if not user["sick"]:
        bot.reply_to(message, "اسبت سالمه، نیازی به درمان نداره 🐴")
        return

    if user["balance"] < TREATMENT_COST:
        bot.reply_to(message, f"یونجه کافی نداری! درمان {TREATMENT_COST} یونجه هزینه داره و تو {user['balance']} تا داری.")
        return

    add_balance(user_id, -TREATMENT_COST, count_as_earned=False)
    update_user(user_id, sick=0)
    bot.reply_to(message, f"💊 اسبت درمان شد! ({TREATMENT_COST} یونجه کم شد) حالا می‌تونه دوباره شیهه بزنه.")


def sickness_checker_loop():
    while True:
        time.sleep(SICKNESS_CHECK_INTERVAL_HOURS * 3600)
        try:
            users = get_all_users()
            chat_id = get_setting("last_chat_id")
            for user in users:
                if user["sick"]:
                    continue
                if is_vaccinated(user):
                    continue
                if random.random() < SICKNESS_CHANCE_PER_CHECK:
                    update_user(user["user_id"], sick=1)
                    if chat_id:
                        name = user["username"] or f"کاربر{user['user_id']}"
                        try:
                            bot.send_message(
                                int(chat_id),
                                f"🤒 اسب {name} مریض شد! تا درمان نکنه نمی‌تونه شیهه بزنه.\n"
                                f"درمان با دستور /darou"
                            )
                        except Exception:
                            pass
        except Exception as e:
            print("خطا در چک مریضی:", e)


@bot.message_handler(commands=["shop", "فروشگاه"])
@group_only
def handle_shop(message):
    lines = ["🛒 فروشگاه:\n"]
    for key, (name, price, _type) in SHOP_ITEMS.items():
        lines.append(f"• {name} — {price} یونجه   (خرید: /buy {key})")
    bot.reply_to(message, "\n".join(lines))


@bot.message_handler(commands=["buy", "خرید"])
@group_only
def handle_buy(message):
    parts = message.text.strip().split()
    if len(parts) < 2:
        bot.reply_to(message, "طرز استفاده: /buy <اسم آیتم>\nبرای دیدن لیست آیتم‌ها: /shop")
        return

    item_key = parts[1].lower()
    if item_key not in SHOP_ITEMS:
        bot.reply_to(message, "همچین آیتمی توی فروشگاه نیست. لیست آیتم‌ها: /shop")
        return

    name, price, item_type = SHOP_ITEMS[item_key]

    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    user = get_user(user_id, username)

    if user["balance"] < price:
        bot.reply_to(message, f"یونجه کافی نداری! {name} قیمتش {price} تاست و تو {user['balance']} تا داری.")
        return

    add_balance(user_id, -price, count_as_earned=False)

    if item_type == "vaccine":
        until = now() + timedelta(days=VACCINE_DURATION_DAYS)
        update_user(user_id, vaccine_until=until.isoformat())
        bot.reply_to(message, f"✅ {name} خریدی! تا {VACCINE_DURATION_DAYS} روز اسبت مریض نمیشه.")
    elif item_type == "title":
        update_user(user_id, title=name.replace("👑 عنوان: ", ""))
        bot.reply_to(message, f"✅ {name} خریدی! حالا این عنوان کنار اسمت نشون داده میشه.")
    elif item_type == "badge":
        update_user(user_id, badge=name.split(":")[0].strip())
        bot.reply_to(message, f"✅ {name} خریدی! حالا این بج کنار اسمت نشون داده میشه.")


@bot.message_handler(commands=["profile", "پروفایل", "من"])
@group_only
def handle_profile(message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    user = get_user(user_id, username)

    level = compute_level(user["total_earned"])
    status = "🤒 مریض" if user["sick"] else "😊 سالم"
    vaccine_txt = ""
    if is_vaccinated(user):
        until = parse_time(user["vaccine_until"])
        vaccine_txt = f"\n💉 واکسینه تا: {until.strftime('%Y-%m-%d %H:%M')}"

    text = (
        f"👤 پروفایل {display_name(user, username, message.from_user.first_name)}\n\n"
        f"🌾 یونجه: {user['balance']}\n"
        f"📈 کل یونجه کسب‌شده: {user['total_earned']}\n"
        f"🐎 سطح: {level}\n"
        f"❤️ وضعیت: {status}{vaccine_txt}"
    )
    bot.reply_to(message, text)


@bot.message_handler(commands=["top", "برترین‌ها"])
@group_only
def handle_top(message):
    users = get_all_users()
    users.sort(key=lambda u: u["total_earned"], reverse=True)
    top_users = users[:10]

    if not top_users:
        bot.reply_to(message, "هنوز کسی امتیازی نداره!")
        return

    lines = ["🏆 جدول برترین‌ها:\n"]
    medals = ["🥇", "🥈", "🥉"]
    for i, user in enumerate(top_users):
        medal = medals[i] if i < 3 else f"{i+1}."
        name = user["username"] or f"کاربر{user['user_id']}"
        level = compute_level(user["total_earned"])
        lines.append(f"{medal} {name} — {user['total_earned']} یونجه ({level})")

    bot.reply_to(message, "\n".join(lines))


@bot.message_handler(commands=["daily", "جایزه"])
@group_only
def handle_daily(message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    user = get_user(user_id, username)

    last_daily = parse_time(user["last_daily"])
    if last_daily:
        remaining = last_daily + timedelta(hours=DAILY_COOLDOWN_HOURS) - now()
        if remaining.total_seconds() > 0:
            hours = int(remaining.total_seconds() // 3600) + 1
            bot.reply_to(message, f"⏳ جایزه‌ی روزانه‌ت رو گرفتی، {hours} ساعت دیگه دوباره بیا.")
            return

    add_balance(user_id, DAILY_REWARD)
    update_user(user_id, last_daily=now().isoformat())
    bot.reply_to(message, f"🎁 جایزه‌ی روزانه گرفتی: {DAILY_REWARD} یونجه!")


@bot.message_handler(commands=["race", "مسابقه"])
@group_only
def handle_race(message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    user = get_user(user_id, username)

    parts = message.text.strip().split()
    amount_given = None
    if len(parts) > 1:
        try:
            amount_given = int(parts[1])
            if amount_given <= 0:
                raise ValueError
        except ValueError:
            bot.reply_to(message, "مبلغ شرط باید یه عدد مثبت باشه. مثال: /race 30")
            return

    with race_lock:
        if not current_race["active"]:
            if amount_given is None:
                bot.reply_to(message, "برای شروع مسابقه‌ی جدید باید مبلغ شرط رو مشخص کنی.\nمثال: /race 30")
                return

            if user["balance"] < amount_given:
                bot.reply_to(message, f"یونجه کافی نداری! تو {user['balance']} تا داری.")
                return

            add_balance(user_id, -amount_given, count_as_earned=False)

            current_race["active"] = True
            current_race["chat_id"] = message.chat.id
            current_race["bet"] = amount_given
            current_race["players"] = {user_id: (username or str(user_id))}

            bot.reply_to(
                message,
                f"🎲 مسابقه شروع شد! شرط این مسابقه: {amount_given} یونجه\n"
                f"تا {RACE_JOIN_SECONDS} ثانیه‌ی دیگه با /race بپیوندید!"
            )

            timer = threading.Timer(RACE_JOIN_SECONDS, resolve_race)
            current_race["timer"] = timer
            timer.start()
            return

        else:
            if amount_given is not None and amount_given != current_race["bet"]:
                bot.reply_to(
                    message,
                    f"مسابقه‌ای در حال برگزاریه با شرط {current_race['bet']} یونجه. "
                    f"فقط بنویس /race تا با همون مبلغ بپیوندی."
                )
                return

            if user_id in current_race["players"]:
                bot.reply_to(message, "تو همین الانشم توی این مسابقه هستی!")
                return

            bet = current_race["bet"]
            if user["balance"] < bet:
                bot.reply_to(message, f"یونجه کافی نداری! این مسابقه شرطش {bet} یونجه‌ست.")
                return

            add_balance(user_id, -bet, count_as_earned=False)
            current_race["players"][user_id] = username or str(user_id)

            bot.reply_to(message, f"✅ به مسابقه پیوستی! تعداد نفرات الان: {len(current_race['players'])}")


def resolve_race():
    with race_lock:
        chat_id = current_race["chat_id"]
        players = dict(current_race["players"])
        bet = current_race["bet"]

        if len(players) < RACE_MIN_PLAYERS:
            for uid in players:
                add_balance(uid, bet, count_as_earned=False)
            try:
                bot.send_message(
                    chat_id,
                    f"❌ مسابقه لغو شد چون کمتر از {RACE_MIN_PLAYERS} نفر بودن. یونجه‌ها برگشت داده شد."
                )
            except Exception:
                pass
        else:
            user_ids = list(players.keys())
            weights = [bet for _ in user_ids]
            winner_id = random.choices(user_ids, weights=weights, k=1)[0]

            prize = bet * len(players)
            add_balance(winner_id, prize)

            winner_name = players[winner_id]
            try:
                bot.send_message(
                    chat_id,
                    f"🏁 مسابقه تموم شد!\n"
                    f"👑 برنده: {winner_name}\n"
                    f"🌾 جایزه: {prize} یونجه"
                )
            except Exception:
                pass

        current_race["active"] = False
        current_race["chat_id"] = None
        current_race["bet"] = None
        current_race["players"] = {}
        current_race["timer"] = None


@bot.message_handler(commands=["start", "help", "راهنما"])
@group_only
def handle_help(message):
    text = (
        "🐴 به بازی اسب‌سواری خوش اومدی!\n\n"
        "دستورات:\n"
        "🐴 /shihe یا /شیهه — شیهه بزن و یونجه بگیر\n"
        "👤 /profile — پروفایلت رو ببین\n"
        "🏆 /top — جدول برترین‌ها\n"
        "🎁 /daily — جایزه‌ی روزانه\n"
        "🩹 /darou — درمان اسب مریض\n"
        "🛒 /shop — فروشگاه\n"
        "🛍️ /buy <آیتم> — خرید آیتم\n"
        "🎲 /race <مبلغ> — شروع یا پیوستن به مسابقه"
    )
    bot.reply_to(message, text)


def run_dummy_web_server():
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Horse bot is running!")

        def log_message(self, format, *args):
            pass

    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()


if __name__ == "__main__":
    init_db()
    print("دیتابیس آماده شد.")

    sickness_thread = threading.Thread(target=sickness_checker_loop, daemon=True)
    sickness_thread.start()

    web_thread = threading.Thread(target=run_dummy_web_server, daemon=True)
    web_thread.start()

    print("ربات در حال اجراست... (برای توقف Ctrl+C بزن)")

    bot.infinity_polling()
