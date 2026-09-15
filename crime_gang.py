"""
crime_gang.py — سیستم خلافکاری و گنگ برای طویله (Stable)

این فایل کاملاً جداست و به stable_bot.py «لینک» می‌شه، نه داخلش قاطی می‌شه.
چون تو stable_bot.py همه‌ی دکمه‌ها از یه دیسپچر مرکزی واحد رد می‌شن
(@bot.callback_query_handler(func=lambda call: True) با زنجیره‌ی
if data.startswith("dino:") / "hokm:" / ...)، برای این‌که دکمه‌های این
سیستم هم کار کنن، باید یه هوک کوچیک به همون زنجیره اضافه بشه.

────────────────────────────────────────────────────────────
نحوه‌ی اتصال به stable_bot.py (۳ تغییر — الان همه‌ش تو stable_bot.py هم زده شده):

۱) بالای فایل: import crime_gang
۲) بعد از ساخت `bot`:
       crime_gang.register(bot, get_conn, db_lock, adjust_coins,
                            PK_AUTOINCREMENT, ensure_user)
۳) توی handle_callback(call)، قبل از بقیه‌ی شرط‌ها:
       if data.startswith("gang:") or data.startswith("newgang:"):
           crime_gang.handle_gang_callback(call)
           return
────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import random
import threading
import time
from datetime import datetime, timedelta, timezone

from telebot import types

bot = None
get_conn = None
db_lock: threading.Lock | None = None
adjust_coins = None
PK_AUTOINCREMENT = "SERIAL PRIMARY KEY"
ensure_user = None
find_user_by_username = None

_flow_lock = threading.Lock()
_pending_gang_creation: dict[int, dict] = {}   # user_id -> {stage, ...}


def register(bot_, get_conn_, db_lock_, adjust_coins_, pk_autoincrement_, ensure_user_, find_user_by_username_=None):
    global bot, get_conn, db_lock, adjust_coins, PK_AUTOINCREMENT, ensure_user, find_user_by_username
    bot = bot_
    get_conn = get_conn_
    db_lock = db_lock_
    adjust_coins = adjust_coins_
    PK_AUTOINCREMENT = pk_autoincrement_
    ensure_user = ensure_user_
    find_user_by_username = find_user_by_username_
    _register_handlers()


# ============================================================
# دیتای پایه — دیتا-محور. اعداد سکه با اقتصاد فعلی ربات (نعل عالی=۳۰۰،
# ارتقاهای پایه ۷۲-۱۲۰) هم‌مقیاس شدن، نه با ده‌ها هزار.
# ============================================================

CRIME_LADDER = [
    # سطح ۱ — خرده‌خلاف
    dict(key="pickpocket",    name="🧤 جیب‌بری",                tier=1, xp_req=0,
         base_success=0.90, coin_min=5,   coin_max=15,   cooldown_h=4,  catch_fine=5,   xp_gain=8),
    dict(key="bike_theft",    name="🏍️ دزدی موتور/دوچرخه",     tier=1, xp_req=60,
         base_success=0.85, coin_min=10,  coin_max=25,   cooldown_h=5,  catch_fine=8,   xp_gain=12),
    dict(key="shoplifting",   name="🛍️ کش رفتن از مغازه",       tier=1, xp_req=120,
         base_success=0.85, coin_min=12,  coin_max=30,   cooldown_h=5,  catch_fine=10,  xp_gain=14),

    # سطح ۲ — محله‌ای
    dict(key="burglary",      name="🏠 دزدی خونه",              tier=2, xp_req=220,
         base_success=0.75, coin_min=25,  coin_max=60,   cooldown_h=8,  catch_fine=20,  xp_gain=25),
    dict(key="extortion",     name="💢 باج‌گیری از مغازه‌دار",   tier=2, xp_req=320,
         base_success=0.72, coin_min=30,  coin_max=70,   cooldown_h=8,  catch_fine=25,  xp_gain=28),
    dict(key="phone_scam",    name="☎️ کلاهبرداری تلفنی",       tier=2, xp_req=420,
         base_success=0.78, coin_min=20,  coin_max=55,   cooldown_h=6,  catch_fine=18,  xp_gain=26),

    # سطح ۳ — سازمان‌یافته‌ی سبک
    dict(key="car_theft",     name="🚗 دزدی ماشین",             tier=3, xp_req=650,
         base_success=0.65, coin_min=55,  coin_max=130,  cooldown_h=10, catch_fine=45,  xp_gain=45),
    dict(key="smuggling",     name="📦 قاچاق خرد کالا",          tier=3, xp_req=850,
         base_success=0.65, coin_min=65,  coin_max=150,  cooldown_h=10, catch_fine=50,  xp_gain=50),
    dict(key="home_lab",      name="🧪 آزمایشگاه خانگی مواد",    tier=3, xp_req=1050,
         base_success=0.60, coin_min=75,  coin_max=175,  cooldown_h=12, catch_fine=60,  xp_gain=58),

    # سطح ۴ — سنگین
    dict(key="jewelry",       name="💍 سرقت طلافروشی",          tier=4, xp_req=1450,
         base_success=0.55, coin_min=140, coin_max=300,  cooldown_h=14, catch_fine=110, xp_gain=90),
    dict(key="bank_branch",   name="🏦 سرقت شعبه‌ی بانک",        tier=4, xp_req=1850,
         base_success=0.50, coin_min=190, coin_max=400,  cooldown_h=16, catch_fine=150, xp_gain=105),
    dict(key="distribution",  name="🚚 توزیع مواد در سطح شهر",   tier=4, xp_req=2200,
         base_success=0.52, coin_min=170, coin_max=380,  cooldown_h=14, catch_fine=130, xp_gain=100),

    # سطح ۵ — کلان (تیمی — حداقل ۲ نیرو لازم داره)
    dict(key="central_bank",  name="🏛️ هایست بانک مرکزی",       tier=5, xp_req=3200,
         base_success=0.40, coin_min=400, coin_max=850,  cooldown_h=24, catch_fine=320, xp_gain=170),
    dict(key="int_smuggling", name="✈️ قاچاق بین‌المللی",        tier=5, xp_req=4000,
         base_success=0.38, coin_min=450, coin_max=950,  cooldown_h=24, catch_fine=360, xp_gain=185),
    dict(key="territory",     name="🏙️ تصرف قلمرو",              tier=5, xp_req=4800,
         base_success=0.45, coin_min=300, coin_max=650,  cooldown_h=20, catch_fine=240, xp_gain=160),

    # سطح ۶ — افسانه‌ای
    dict(key="heist_century", name="👑 سرقت قرن",                tier=6, xp_req=6500,
         base_success=0.30, coin_min=1000, coin_max=2200, cooldown_h=48, catch_fine=800, xp_gain=320),
    dict(key="mafia_boss",    name="🕴️ رئیس مافیا شدن",          tier=6, xp_req=8500,
         base_success=0.25, coin_min=1600, coin_max=3500, cooldown_h=48, catch_fine=1300, xp_gain=600),
]
CRIME_BY_KEY = {c["key"]: c for c in CRIME_LADDER}

# اسم‌های خارجی برای کارگرها
WORKER_NAME_POOL = [
    "James", "Carlos", "Marco", "Viktor", "Dmitri", "Diego", "Mateo",
    "Leon", "Ivan", "Bruno", "Nadia", "Elena", "Sofia", "Katya", "Rico", "Hugo",
]

HIRE_COST_BASE = 35     # قیمت پایه‌ی استخدام کارگر بعدی — هم‌مقیاس با بقیه‌ی فروشگاه
HIRE_COST_PER_WORKER = 25

JAIL_HOURS_MIN = 3      # حداقل زندان برای خلاف‌های سبک؛ برای خلاف‌های سنگین‌تر بیشتر می‌شه (پایین‌تر از کول‌داون نمی‌افته)


def _stat_bar(value: int) -> str:
    filled = round(value / 10)
    return "▰" * filled + "▱" * (10 - filled)


def _roll_worker() -> dict:
    return dict(
        name=random.choice(WORKER_NAME_POOL),
        speed=random.randint(30, 95),
        strength=random.randint(30, 95),
        trust=random.randint(40, 90),
    )


def _worker_profile_text(w: dict) -> str:
    return (
        f"👤 {w['name']}\n"
        f"⚡ سرعت: {_stat_bar(w['speed'])} ({w['speed']})\n"
        f"💪 قدرت: {_stat_bar(w['strength'])} ({w['strength']})\n"
        f"🤝 اعتماد: {_stat_bar(w['trust'])} ({w['trust']})"
    )


def _unlocked_crimes(xp: int) -> list[dict]:
    return [c for c in CRIME_LADDER if c["xp_req"] <= xp]


# ============================================================
# دیتابیس
# ============================================================

def init_crime_tables():
    with db_lock:
        conn = get_conn()
        c = conn.cursor()
        c.execute(f"""
            CREATE TABLE IF NOT EXISTS crime_gangs (
                gang_id {PK_AUTOINCREMENT},
                name TEXT UNIQUE NOT NULL,
                leader_id BIGINT UNIQUE NOT NULL,
                xp INTEGER DEFAULT 0,
                reputation INTEGER DEFAULT 0,
                fear INTEGER DEFAULT 0,
                created_at TEXT
            )
        """)
        c.execute(f"""
            CREATE TABLE IF NOT EXISTS crime_workers (
                worker_id {PK_AUTOINCREMENT},
                gang_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                speed INTEGER NOT NULL,
                strength INTEGER NOT NULL,
                trust INTEGER NOT NULL,
                satisfaction INTEGER DEFAULT 70,
                assigned_crime TEXT,
                busy_until TEXT,
                last_paid_at TEXT,
                hired_at TEXT,
                custom_salary INTEGER,
                last_reminder_at TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS crime_gang_relations (
                gang_a INTEGER NOT NULL,
                gang_b INTEGER NOT NULL,
                status TEXT NOT NULL,
                last_attack_at TEXT,
                updated_at TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS crime_heist_allies (
                gang_a INTEGER NOT NULL,
                gang_b INTEGER NOT NULL,
                expires_at TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close()

    # مهاجرت برای دیتابیس‌هایی که از قبل این جدول رو داشتن (بدون این دو ستون جدید)
    for col, coltype in [("custom_salary", "INTEGER"), ("last_reminder_at", "TEXT")]:
        try:
            with db_lock:
                conn = get_conn()
                conn.execute(f"ALTER TABLE crime_workers ADD COLUMN {col} {coltype}")
                conn.commit()
                conn.close()
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
    try:
        with db_lock:
            conn = get_conn()
            conn.execute("ALTER TABLE crime_heist_allies ADD COLUMN crime_key TEXT")
            conn.commit()
            conn.close()
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
    print("جداول سیستم خلافکاری/گنگ آماده شد.")


def _now():
    return datetime.now(timezone.utc)


def _now_str():
    return _now().isoformat()


def _parse_dt(s):
    if not s:
        return None
    return datetime.fromisoformat(s)


def get_gang_by_leader(user_id):
    with db_lock:
        conn = get_conn()
        row = conn.execute("SELECT * FROM crime_gangs WHERE leader_id=?", (user_id,)).fetchone()
        conn.close()
        return dict(row) if row else None


def get_gang_by_id(gang_id):
    with db_lock:
        conn = get_conn()
        row = conn.execute("SELECT * FROM crime_gangs WHERE gang_id=?", (gang_id,)).fetchone()
        conn.close()
        return dict(row) if row else None


def get_gang_by_name(name):
    with db_lock:
        conn = get_conn()
        row = conn.execute("SELECT * FROM crime_gangs WHERE name=?", (name,)).fetchone()
        conn.close()
        return dict(row) if row else None


def get_workers(gang_id):
    with db_lock:
        conn = get_conn()
        rows = conn.execute(
            "SELECT * FROM crime_workers WHERE gang_id=? ORDER BY worker_id", (gang_id,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]


def create_gang(name, leader_id):
    with db_lock:
        conn = get_conn()
        conn.execute(
            "INSERT INTO crime_gangs (name, leader_id, xp, reputation, fear, created_at) VALUES (?,?,?,?,?,?)",
            (name, leader_id, 0, 0, 0, _now_str()),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM crime_gangs WHERE leader_id=?", (leader_id,)).fetchone()
        conn.close()
        return dict(row)


def hire_worker(gang_id, worker: dict, assigned_crime: str):
    with db_lock:
        conn = get_conn()
        conn.execute(
            """INSERT INTO crime_workers
               (gang_id, name, speed, strength, trust, satisfaction, assigned_crime, busy_until, last_paid_at, hired_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (gang_id, worker["name"], worker["speed"], worker["strength"], worker["trust"],
             70, assigned_crime, None, _now_str(), _now_str()),
        )
        conn.commit()
        conn.close()


def remove_worker(worker_id):
    with db_lock:
        conn = get_conn()
        conn.execute("DELETE FROM crime_workers WHERE worker_id=?", (worker_id,))
        conn.commit()
        conn.close()


def update_worker(worker_id, **fields):
    if not fields:
        return
    with db_lock:
        conn = get_conn()
        sets = ", ".join(f"{k}=?" for k in fields)
        conn.execute(f"UPDATE crime_workers SET {sets} WHERE worker_id=?",
                     (*fields.values(), worker_id))
        conn.commit()
        conn.close()


def add_gang_xp(gang_id, delta):
    with db_lock:
        conn = get_conn()
        conn.execute("UPDATE crime_gangs SET xp = xp + ? WHERE gang_id=?", (delta, gang_id))
        conn.commit()
        conn.close()


def add_gang_reputation(gang_id, delta):
    with db_lock:
        conn = get_conn()
        conn.execute("UPDATE crime_gangs SET reputation = reputation + ? WHERE gang_id=?", (delta, gang_id))
        conn.commit()
        conn.close()


def add_gang_fear(gang_id, delta):
    with db_lock:
        conn = get_conn()
        conn.execute("UPDATE crime_gangs SET fear = MAX(0, fear + ?) WHERE gang_id=?", (delta, gang_id))
        conn.commit()
        conn.close()


def _canon(gang_a, gang_b):
    return (gang_a, gang_b) if gang_a < gang_b else (gang_b, gang_a)


def get_relation_row(gang_a, gang_b):
    a, b = _canon(gang_a, gang_b)
    with db_lock:
        conn = get_conn()
        row = conn.execute(
            "SELECT * FROM crime_gang_relations WHERE gang_a=? AND gang_b=?", (a, b)
        ).fetchone()
        conn.close()
        return dict(row) if row else None


def get_relation_status(gang_a, gang_b):
    row = get_relation_row(gang_a, gang_b)
    return row["status"] if row else "neutral"


def set_relation(gang_a, gang_b, status):
    a, b = _canon(gang_a, gang_b)
    with db_lock:
        conn = get_conn()
        existing = conn.execute(
            "SELECT * FROM crime_gang_relations WHERE gang_a=? AND gang_b=?", (a, b)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE crime_gang_relations SET status=?, updated_at=? WHERE gang_a=? AND gang_b=?",
                (status, _now_str(), a, b),
            )
        else:
            conn.execute(
                "INSERT INTO crime_gang_relations (gang_a, gang_b, status, last_attack_at, updated_at) VALUES (?,?,?,?,?)",
                (a, b, status, None, _now_str()),
            )
        conn.commit()
        conn.close()


def clear_relation(gang_a, gang_b):
    a, b = _canon(gang_a, gang_b)
    with db_lock:
        conn = get_conn()
        conn.execute("DELETE FROM crime_gang_relations WHERE gang_a=? AND gang_b=?", (a, b))
        conn.commit()
        conn.close()


def set_last_attack(gang_a, gang_b):
    a, b = _canon(gang_a, gang_b)
    with db_lock:
        conn = get_conn()
        conn.execute(
            "UPDATE crime_gang_relations SET last_attack_at=? WHERE gang_a=? AND gang_b=?",
            (_now_str(), a, b),
        )
        conn.commit()
        conn.close()


def list_relations(gang_id):
    with db_lock:
        conn = get_conn()
        rows = conn.execute(
            "SELECT * FROM crime_gang_relations WHERE gang_a=? OR gang_b=?", (gang_id, gang_id)
        ).fetchall()
        conn.close()
    out = []
    for r in rows:
        r = dict(r)
        other_id = r["gang_b"] if r["gang_a"] == gang_id else r["gang_a"]
        other = get_gang_by_id(other_id)
        if other:
            out.append((other, r["status"], r.get("last_attack_at")))
    return out


# ============================================================
# حقوق و رضایت
# ============================================================

SALARY_CYCLE_HOURS = 48
SALARY_STEP = 5           # هر بار با دکمه‌ی +/- چقدر تغییر می‌کنه
SALARY_MAX_MULTIPLIER = 3  # سقف حقوق دستی: ۳ برابر انتظار کارگر
SALARY_REMINDER_CHECK_SECONDS = 30 * 60  # هر نیم ساعت چک کن کسی حقوق عقب‌افتاده داره یا نه


def expected_salary(worker: dict) -> int:
    """حقوقی که کارگر متناسب با آمارش انتظار داره — هم‌مقیاس با بقیه‌ی اقتصاد بازی.
    این عدد فقط یه «پیشنهاد/مرجع» برای رهبره؛ رقم واقعی پرداختی رو خودِ رهبر
    با دکمه‌های +/- تنظیم می‌کنه (custom_salary)."""
    return int(6 + (worker["speed"] + worker["strength"]) * 0.15)


def effective_salary(worker: dict) -> int:
    """حقوقی که رهبر واقعاً برای این کارگر تنظیم کرده؛ اگه هنوز دست نزده، پیش‌فرض = انتظار کارگره."""
    cs = worker.get("custom_salary")
    return int(cs) if cs is not None else expected_salary(worker)


def set_worker_salary(worker_id, amount):
    amount = max(0, int(amount))
    update_worker(worker_id, custom_salary=amount)
    return amount


def adjust_worker_salary(worker: dict, delta: int) -> int:
    cap = expected_salary(worker) * SALARY_MAX_MULTIPLIER
    new_amount = max(0, min(cap, effective_salary(worker) + delta))
    return set_worker_salary(worker["worker_id"], new_amount)


def _hours_overdue(worker: dict) -> float:
    last_paid = _parse_dt(worker.get("last_paid_at"))
    if last_paid is None:
        return SALARY_CYCLE_HOURS
    hours_since = (_now() - last_paid).total_seconds() / 3600
    return max(0.0, hours_since - SALARY_CYCLE_HOURS)


def _check_betrayal_and_apply(worker: dict) -> tuple[bool, int]:
    last_paid = _parse_dt(worker.get("last_paid_at"))
    if last_paid is None:
        overdue_cycles = 1
    else:
        hours_since = (_now() - last_paid).total_seconds() / 3600
        overdue_cycles = max(0, int(hours_since // SALARY_CYCLE_HOURS))

    satisfaction = worker["satisfaction"]
    if overdue_cycles == 0 and satisfaction >= 40:
        return False, 0

    betrayal_chance = max(0.0, (60 - satisfaction) / 200) + overdue_cycles * 0.08
    betrayal_chance = min(betrayal_chance, 0.6)

    if random.random() < betrayal_chance:
        stolen = random.randint(10, 60)
        return True, stolen
    return False, 0


def _satisfaction_gain_for_payment(worker: dict, paid: int) -> int:
    """رضایت بر اساس نسبت پرداختی به انتظار کارگر تغییر می‌کنه، نه یه عدد ثابت."""
    expected = max(1, expected_salary(worker))
    ratio = paid / expected
    if ratio >= 1.5:
        return 28
    if ratio >= 1.0:
        return 20
    if ratio >= 0.6:
        return 8
    if ratio > 0:
        return 2
    return -10  # حقوق صفر گذاشتی و بازم "پرداخت" زدی — طبیعتاً ناراضی‌تر می‌شه


def pay_single_worker(worker_id, leader_id):
    with db_lock:
        conn = get_conn()
        row = conn.execute("SELECT * FROM crime_workers WHERE worker_id=?", (worker_id,)).fetchone()
        conn.close()
    if not row:
        return False, "این نیرو دیگه وجود نداره."
    worker = dict(row)
    amount = effective_salary(worker)

    if amount > 0:
        ok, balance = adjust_coins(leader_id, -amount)
        if not ok:
            return False, f"موجودیت کافی نیست. حقوق {worker['name']} {amount} سکه‌ست."

    gain = _satisfaction_gain_for_payment(worker, amount)
    new_satisfaction = max(0, min(100, worker["satisfaction"] + gain))
    update_worker(worker_id, satisfaction=new_satisfaction, last_paid_at=_now_str(), last_reminder_at=None)
    return True, f"💰 {amount} سکه به {worker['name']} دادی. رضایتش الان {new_satisfaction}%."


def pay_salaries(gang_id, leader_id):
    """پرداخت یک‌جا به همه‌ی نیروها — هرکدوم با رقمی که رهبر برای خودش تنظیم کرده."""
    workers = get_workers(gang_id)
    if not workers:
        return False, "هنوز کارگری استخدام نکردی."

    total = sum(effective_salary(w) for w in workers)
    if total > 0:
        ok, balance = adjust_coins(leader_id, -total)
        if not ok:
            return False, f"موجودیت کافی نیست. برای پرداخت حقوق همه‌ی نیروها {total} سکه لازمه."

    for w in workers:
        amount = effective_salary(w)
        gain = _satisfaction_gain_for_payment(w, amount)
        new_satisfaction = max(0, min(100, w["satisfaction"] + gain))
        update_worker(w["worker_id"], satisfaction=new_satisfaction, last_paid_at=_now_str(), last_reminder_at=None)

    return True, f"💰 حقوق {len(workers)} نفر پرداخت شد (جمعاً {total} سکه)."


def salary_reminder_loop():
    """هر نیم ساعت چک می‌کنه: کدوم نیروها بیش از ۴۸ ساعته حقوق نگرفتن،
    و اگه هنوز برای این دوره‌ی عقب‌افتادگی یادآوری نفرستاده، یه پیام به رهبر می‌ده."""
    while True:
        time.sleep(SALARY_REMINDER_CHECK_SECONDS)
        try:
            with db_lock:
                conn = get_conn()
                rows = conn.execute("SELECT * FROM crime_workers").fetchall()
                conn.close()

            by_gang: dict[int, list[dict]] = {}
            for r in rows:
                w = dict(r)
                if _hours_overdue(w) <= 0:
                    continue
                last_reminder = _parse_dt(w.get("last_reminder_at"))
                if last_reminder and (_now() - last_reminder).total_seconds() < SALARY_CYCLE_HOURS * 3600:
                    continue
                by_gang.setdefault(w["gang_id"], []).append(w)

            for gang_id, overdue_workers in by_gang.items():
                gang = get_gang_by_id(gang_id)
                if not gang:
                    continue
                names = "، ".join(w["name"] for w in overdue_workers)
                try:
                    bot.send_message(
                        gang["leader_id"],
                        f"⏰ یادآوری حقوق گنگ «{gang['name']}»: {names} بیش از {SALARY_CYCLE_HOURS} ساعته حقوق نگرفتن. "
                        f"اگه ندی، رضایتشون میفته و ممکنه خیانت کنن. با /خلافکاری برو تو «💰 حقوق‌ها».",
                    )
                    for w in overdue_workers:
                        update_worker(w["worker_id"], last_reminder_at=_now_str())
                except Exception:
                    pass
        except Exception as e:
            print("خطا در یادآوری حقوق گنگ:", e)


# ============================================================
# اجرای کار — کول‌داون، تیر خوردن (قدرت = ریکاوری سریع‌تر)،
# تعقیب پلیس (سرعت = شانس فرار)، دستگیری (همیشه ۳ ساعت زندان)
# ============================================================

ALLY_REWARD_MULTIPLIER = 1.6
ALLY_TIME_MULTIPLIER = 1.7

# سرعت زمانِ کار رو کم/زیاد می‌کنه: سرعت ۹۵ ≈ ۳۰٪ سریع‌تر، سرعت ۳۰ ≈ ۱۵٪ کندتر
SPEED_TIME_MIN_FACTOR = 0.7
SPEED_TIME_MAX_FACTOR = 1.15
# قدرت پاداش پولی رو زیاد می‌کنه: قدرت ۹۵ ≈ ۴۰٪ بیشتر، قدرت ۳۰ ≈ ۱۰٪ کمتر
STRENGTH_REWARD_MIN_FACTOR = 0.9
STRENGTH_REWARD_MAX_FACTOR = 1.4

INJURY_REASONS = [
    ("🔫 تیر خورد", "تیر خورد"),
    ("🚓 تو فرار تصادف کرد", "تصادف کرد"),
    ("🥊 سر کار درگیر شد و کتک خورد", "تو دعوا زخمی شد"),
    ("🦴 موقع فرار از دیوار افتاد و پاش پیچ خورد", "پاش پیچ خورد"),
]


def _speed_time_factor(speed: int) -> float:
    # speed=30 -> ~1.15 ، speed=95 -> ~0.7 (خطی)
    frac = (speed - 30) / (95 - 30)
    frac = max(0.0, min(1.0, frac))
    return SPEED_TIME_MIN_FACTOR + (1 - frac) * (SPEED_TIME_MAX_FACTOR - SPEED_TIME_MIN_FACTOR)


def _strength_reward_factor(strength: int) -> float:
    frac = (strength - 30) / (95 - 30)
    frac = max(0.0, min(1.0, frac))
    return STRENGTH_REWARD_MIN_FACTOR + frac * (STRENGTH_REWARD_MAX_FACTOR - STRENGTH_REWARD_MIN_FACTOR)


def run_crime_job(worker: dict, gang: dict, with_ally: bool = False):
    crime = CRIME_BY_KEY.get(worker["assigned_crime"])
    if crime is None:
        return {"status": "error", "message": "این نیرو هنوز خلاف مشخصی نداره."}

    busy_until = _parse_dt(worker.get("busy_until"))
    if busy_until and busy_until > _now():
        remaining = busy_until - _now()
        hrs = int(remaining.total_seconds() // 3600)
        mins = int((remaining.total_seconds() % 3600) // 60)
        return {"status": "busy", "message": f"⏳ {worker['name']} هنوز آماده نیست، {hrs} ساعت و {mins} دقیقه‌ی دیگه صبر کن."}

    betrayed, stolen = _check_betrayal_and_apply(worker)
    if betrayed:
        remove_worker(worker["worker_id"])
        return {
            "status": "betrayed",
            "message": f"💔 {worker['name']} بهت خیانت کرد! {stolen} سکه از خزانه‌ت برداشت و غیب شد.",
        }

    # سرعت = چقدر زود کارش تموم می‌شه و دوباره آماده می‌شه
    cooldown_h = crime["cooldown_h"] * _speed_time_factor(worker["speed"])
    cooldown_h *= (ALLY_TIME_MULTIPLIER if with_ally else 1)
    cooldown_h = max(1, round(cooldown_h))
    tag = " (با کمک گنگ متحد)" if with_ally else ""

    skill_bonus = ((worker["speed"] + worker["strength"]) / 2 - 50) / 250
    satisfaction_penalty = max(0.0, (50 - worker["satisfaction"]) / 200)
    success_chance = max(0.05, min(0.95, crime["base_success"] + skill_bonus - satisfaction_penalty))

    if random.random() < success_chance:
        # قدرت = چقدر پول بیشتر گیرش میاد
        reward = random.randint(crime["coin_min"], crime["coin_max"])
        reward = round(reward * _strength_reward_factor(worker["strength"]))
        if with_ally:
            reward = round(reward * ALLY_REWARD_MULTIPLIER)
        if worker["satisfaction"] < 50:
            reward = int(reward * 0.7)
        adjust_coins(worker["_leader_id"], reward)
        add_gang_xp(gang["gang_id"], crime["xp_gain"])
        add_gang_reputation(gang["gang_id"], max(1, crime["xp_gain"] // 15))
        update_worker(worker["worker_id"], busy_until=(_now() + timedelta(hours=cooldown_h)).isoformat())
        return {"status": "success", "message": f"✅ {worker['name']} تو «{crime['name']}»{tag} موفق شد! {reward} سکه گیر گنگت اومد."}

    # کار خراب شد — یا مصدوم می‌شه (چند علت مختلف)، یا پلیس میفته دنبالش
    if random.random() < 0.5:
        emoji_text, verb = random.choice(INJURY_REASONS)
        # حدوداً ۳ ساعت استراحت؛ قدرت بالا کمی زودتر رو پا می‌کنتش
        injury_hours = random.randint(2, 4)
        if worker["strength"] >= 70:
            injury_hours = max(2, injury_hours - 1)
        total_hours = cooldown_h + injury_hours
        update_worker(worker["worker_id"], busy_until=(_now() + timedelta(hours=total_hours)).isoformat())
        return {
            "status": "injured",
            "message": f"{emoji_text} — {worker['name']} تو «{crime['name']}»{tag} {verb}! {injury_hours} ساعت استراحت لازم داره ({total_hours} ساعت تا آماده‌ی کار بعدی).",
        }
    else:
        # پلیس افتاد دنبالش — سرعتش تعیین می‌کنه فرار کنه یا نه
        escape_chance = min(0.9, 0.25 + worker["speed"] / 140)
        if random.random() < escape_chance:
            update_worker(worker["worker_id"], busy_until=(_now() + timedelta(hours=cooldown_h)).isoformat())
            return {
                "status": "escaped",
                "message": f"👮 پلیس افتاد دنبال {worker['name']}، ولی چون سریعه در رفت! فقط {cooldown_h} ساعت لازمه خودشو جمع‌وجور کنه.",
            }
        else:
            fine = crime["catch_fine"]
            adjust_coins(worker["_leader_id"], -fine)
            jail_hours = max(JAIL_HOURS_MIN, cooldown_h + 2)
            update_worker(worker["worker_id"], busy_until=(_now() + timedelta(hours=jail_hours)).isoformat())
            return {
                "status": "caught",
                "message": f"🚨 پلیس {worker['name']} رو گرفت! {jail_hours} ساعت زندانه و {fine} سکه جریمه شدی.",
            }


# ============================================================
# روابط بین گنگ‌ها — اتحاد/جنگ/صلح + حمله
# ============================================================

ATTACK_COOLDOWN_HOURS = 12
HEIST_ALLY_HOURS = 24   # اتحاد برای یه سرقت گروهی چقدر دووم داره

# پیشنهادهای در انتظار (اتحاد/صلح که نیاز به تایید طرف مقابل دارن)
_pending_relation_proposals: dict[str, dict] = {}
_pending_heist_ally_invites: dict[str, dict] = {}  # key -> {from_gang, to_gang, crime_key}
_pending_ally_flow: dict[int, dict] = {}  # user_id -> {stage, from_gang, target_prompt_id, to_gang}


def has_heist_ally(gang_id, crime_key=None) -> bool:
    """اگه crime_key داده بشه، فقط اتحاد مختص همون خلاف رو چک می‌کنه."""
    with db_lock:
        conn = get_conn()
        if crime_key is not None:
            row = conn.execute(
                "SELECT 1 FROM crime_heist_allies WHERE (gang_a=? OR gang_b=?) AND expires_at > ? AND crime_key = ?",
                (gang_id, gang_id, _now_str(), crime_key),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT 1 FROM crime_heist_allies WHERE (gang_a=? OR gang_b=?) AND expires_at > ?",
                (gang_id, gang_id, _now_str()),
            ).fetchone()
        conn.close()
    return bool(row)


def create_heist_ally(gang_a, gang_b, crime_key):
    a, b = _canon(gang_a, gang_b)
    expires = (_now() + timedelta(hours=HEIST_ALLY_HOURS)).isoformat()
    with db_lock:
        conn = get_conn()
        conn.execute(
            "INSERT INTO crime_heist_allies (gang_a, gang_b, expires_at, crime_key) VALUES (?,?,?,?)",
            (a, b, expires, crime_key),
        )
        conn.commit()
        conn.close()


def gang_power(gang_id) -> int:
    workers = get_workers(gang_id)
    return sum(w["speed"] + w["strength"] for w in workers) or 1


def _proposal_key(kind, from_gang, to_gang):
    return f"{kind}:{from_gang}:{to_gang}"


def declare_war(from_gang_id, to_gang_id):
    """اعلام جنگ یک‌طرفه‌ست — نیازی به تایید طرف مقابل نیست."""
    set_relation(from_gang_id, to_gang_id, "war")


def propose_relation(kind, from_gang_id, to_gang_id):
    """kind: 'alliance' یا 'peace' — این‌ها نیاز به تایید طرف مقابل دارن."""
    key = _proposal_key(kind, from_gang_id, to_gang_id)
    with _flow_lock:
        _pending_relation_proposals[key] = {"from": from_gang_id, "to": to_gang_id, "kind": kind}
    return key


def resolve_relation_proposal(kind, from_gang_id, to_gang_id, accepted):
    key = _proposal_key(kind, from_gang_id, to_gang_id)
    with _flow_lock:
        existed = _pending_relation_proposals.pop(key, None)
    if not existed:
        return False
    if accepted:
        if kind == "alliance":
            set_relation(from_gang_id, to_gang_id, "alliance")
        elif kind == "peace":
            clear_relation(from_gang_id, to_gang_id)
    return True


def attack_gang(attacker_gang_id, defender_gang_id):
    status = get_relation_status(attacker_gang_id, defender_gang_id)
    if status != "war":
        return {"ok": False, "message": "با این گنگ در جنگ نیستی."}

    row = get_relation_row(attacker_gang_id, defender_gang_id)
    last_attack = _parse_dt(row.get("last_attack_at")) if row else None
    if last_attack:
        remaining = timedelta(hours=ATTACK_COOLDOWN_HOURS) - (_now() - last_attack)
        if remaining.total_seconds() > 0:
            hrs = int(remaining.total_seconds() // 3600)
            mins = int((remaining.total_seconds() % 3600) // 60)
            return {"ok": False, "message": f"⏳ نیروهات هنوز آماده‌ی حمله‌ی بعدی نیستن، {hrs} ساعت و {mins} دقیقه‌ی دیگه صبر کن."}

    attacker = get_gang_by_id(attacker_gang_id)
    defender = get_gang_by_id(defender_gang_id)
    p_a = gang_power(attacker_gang_id)
    p_d = gang_power(defender_gang_id)
    win_chance = p_a / (p_a + p_d)
    set_last_attack(attacker_gang_id, defender_gang_id)

    if random.random() < win_chance:
        loot = random.randint(15, 60)
        adjust_coins(defender["leader_id"], -loot)
        adjust_coins(attacker["leader_id"], loot)
        add_gang_reputation(attacker_gang_id, 10)
        add_gang_fear(attacker_gang_id, 3)
        add_gang_fear(defender_gang_id, -2)
        return {"ok": True, "message": f"⚔️ گنگ «{attacker['name']}» به «{defender['name']}» حمله کرد و برد! {loot} سکه غارت شد."}
    else:
        loss = random.randint(10, 40)
        adjust_coins(attacker["leader_id"], -loss)
        add_gang_reputation(defender_gang_id, 6)
        add_gang_fear(defender_gang_id, 2)
        return {"ok": True, "message": f"🛡️ گنگ «{defender['name']}» حمله‌ی «{attacker['name']}» رو دفع کرد! {loss} سکه از دستشون رفت."}


# ============================================================
# کیبوردها
# ============================================================

def _tier_progress_bar(gang) -> str:
    next_up = next((c for c in CRIME_LADDER if c["xp_req"] > gang["xp"]), None)
    if not next_up:
        return "🏆 همه‌ی سطح‌ها باز شدن!"
    prev_req = 0
    for c in CRIME_LADDER:
        if c["xp_req"] >= next_up["xp_req"]:
            break
        prev_req = c["xp_req"]
    span = max(1, next_up["xp_req"] - prev_req)
    done = max(0, gang["xp"] - prev_req)
    filled = round(min(1.0, done / span) * 10)
    bar = "▰" * filled + "▱" * (10 - filled)
    remaining = next_up["xp_req"] - gang["xp"]
    return f"{bar}\nتا «{next_up['name']}»: {remaining} XP مونده"


def _main_menu_kb(gang):
    gang_id = gang["gang_id"]
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("👥 نیروهام", callback_data=f"gang:workers:{gang_id}"),
        types.InlineKeyboardButton("➕ استخدام", callback_data=f"gang:hire:{gang_id}"),
    )
    kb.add(
        types.InlineKeyboardButton("💰 حقوق‌ها", callback_data=f"gang:salarymenu:{gang_id}"),
        types.InlineKeyboardButton("⚔️ روابط گنگ‌ها", callback_data=f"gang:relations:{gang_id}"),
    )
    kb.add(types.InlineKeyboardButton("🤝 اتحاد سرقت", callback_data=f"gang:allystart:{gang_id}"))
    kb.add(types.InlineKeyboardButton("🔙 برگشت به منو", callback_data="menu:main"))
    return kb


def _gang_status_text(gang):
    workers = get_workers(gang["gang_id"])
    overdue = [w for w in workers if _hours_overdue(w) > 0]
    lines = [
        f"🏴 گنگ «{gang['name']}»",
        f"🎖️ اعتبار: {gang['reputation']}   😱 ترسناکی: {gang['fear']}",
        f"👥 نیرو: {len(workers)} نفر" + (f"   ⚠️ {len(overdue)} نفر حقوق عقب‌افتاده دارن" if overdue else ""),
        "",
        f"امتیاز خلاف (XP): {gang['xp']}",
        _tier_progress_bar(gang),
    ]
    return "\n".join(lines)


def _worker_status_line(w) -> str:
    crime = CRIME_BY_KEY.get(w["assigned_crime"])
    crime_name = crime["name"] if crime else "بدون کار"

    busy_until = _parse_dt(w.get("busy_until"))
    if busy_until and busy_until > _now():
        remaining = busy_until - _now()
        hrs = int(remaining.total_seconds() // 3600)
        mins = int((remaining.total_seconds() % 3600) // 60)
        status = f"⏳ {hrs}س {mins}د دیگه آزاد می‌شه"
    else:
        status = "✅ آماده"

    sat = w["satisfaction"]
    sat_emoji = "😊" if sat >= 70 else ("😐" if sat >= 40 else "😠")
    overdue_tag = " 🔴 حقوق عقب‌افتاده" if _hours_overdue(w) > 0 else ""

    return f"• {w['name']} — {crime_name}\n   {status} | {sat_emoji} رضایت {sat}%{overdue_tag}"


def _workers_kb(gang_id, workers):
    kb = types.InlineKeyboardMarkup(row_width=1)
    for w in workers:
        busy_until = _parse_dt(w.get("busy_until"))
        ready = not (busy_until and busy_until > _now())
        icon = "🎯" if ready else "⏳"
        label = f"{icon} {w['name']}"
        kb.add(types.InlineKeyboardButton(label, callback_data=f"gang:run:{w['worker_id']}"))
    kb.add(types.InlineKeyboardButton("💰 حقوق‌ها", callback_data=f"gang:salarymenu:{gang_id}"))
    kb.add(types.InlineKeyboardButton("🔙 برگشت", callback_data=f"gang:menu:{gang_id}"))
    return kb


def _salary_menu_text(gang):
    workers = get_workers(gang["gang_id"])
    if not workers:
        return "هیچ نیرویی نداری."
    total = sum(effective_salary(w) for w in workers)
    lines = [
        f"💰 حقوق نیروهای «{gang['name']}»",
        "خودت تعیین می‌کنی هرکدوم چقدر بگیره — هر ۴۸ ساعت باید پرداخت کنی، وگرنه ناراضی می‌شن و ممکنه خیانت کنن.\n",
    ]
    for w in workers:
        expected = expected_salary(w)
        pay = effective_salary(w)
        tag = " (کمتر از انتظارش)" if pay < expected else ("" if pay == expected else " (بیشتر از انتظارش)")
        overdue_tag = " 🔴 عقب‌افتاده" if _hours_overdue(w) > 0 else ""
        lines.append(f"• {w['name']}: {pay} سکه{tag} — انتظارش ~{expected} سکه{overdue_tag}")
    lines.append(f"\nجمع پرداخت همه: {total} سکه")
    return "\n".join(lines)


def _salary_menu_kb(gang_id, workers):
    kb = types.InlineKeyboardMarkup(row_width=1)
    for w in workers:
        wid = w["worker_id"]
        kb.row(
            types.InlineKeyboardButton(f"➖ {w['name']}", callback_data=f"gang:salaryadj:{wid}:-{SALARY_STEP}"),
            types.InlineKeyboardButton(f"{effective_salary(w)} سکه", callback_data="gang:noop"),
            types.InlineKeyboardButton("➕", callback_data=f"gang:salaryadj:{wid}:{SALARY_STEP}"),
            types.InlineKeyboardButton("💸 پرداخت", callback_data=f"gang:salarypay1:{wid}"),
        )
    kb.add(types.InlineKeyboardButton("💰 پرداخت به همه", callback_data=f"gang:pay:{gang_id}"))
    kb.add(types.InlineKeyboardButton("🔙 برگشت", callback_data=f"gang:menu:{gang_id}"))
    return kb


def _open_salary_menu(call, gang_id, chat_id, message_id):
    gang = get_gang_by_id(gang_id)
    workers = get_workers(gang_id)
    if not workers:
        bot.answer_callback_query(call.id, "هنوز کارگری استخدام نکردی.")
        return
    bot.edit_message_text(_salary_menu_text(gang), chat_id, message_id, reply_markup=_salary_menu_kb(gang_id, workers))


def _crime_choice_kb(prefix, xp):
    kb = types.InlineKeyboardMarkup(row_width=1)
    for c in _unlocked_crimes(xp):
        kb.add(types.InlineKeyboardButton(c["name"], callback_data=f"{prefix}:{c['key']}"))
    return kb


# ============================================================
# فلو ساخت گنگ (/ساختن_گنگ) — اسم → خلاف اول → انتخاب کارگر
# ============================================================

def _start_gang_creation(message):
    user_id = message.from_user.id
    if get_gang_by_leader(user_id):
        bot.reply_to(message, "تو همین الان یه گنگ داری! برای دیدنش /خلافکاری رو بزن.")
        return
    with _flow_lock:
        _pending_gang_creation[user_id] = {"stage": "await_name"}
    sent = bot.send_message(
        message.chat.id,
        "🏴 وقتشه یه گنگ راه بندازی. اسم گنگت چیه؟\n(با ریپلای به همین پیام جواب بده)",
        reply_markup=types.ForceReply(selective=True),
    )
    with _flow_lock:
        _pending_gang_creation[user_id]["name_prompt_id"] = sent.message_id


def _is_gang_name_reply(message) -> bool:
    if message.reply_to_message is None or not message.text:
        return False
    user_id = message.from_user.id
    with _flow_lock:
        flow = _pending_gang_creation.get(user_id)
    return bool(flow and flow.get("stage") == "await_name"
                and flow.get("name_prompt_id") == message.reply_to_message.message_id)


def _handle_gang_name_reply(message):
    user_id = message.from_user.id
    name = message.text.strip()
    if len(name) < 2 or len(name) > 30:
        bot.reply_to(message, "اسم باید بین ۲ تا ۳۰ کاراکتر باشه. دوباره امتحان کن.")
        return
    if get_gang_by_name(name):
        bot.reply_to(message, "این اسم قبلاً گرفته شده. یه اسم دیگه انتخاب کن.")
        return

    with _flow_lock:
        _pending_gang_creation[user_id] = {"stage": "await_crime", "name": name}

    text = (
        f"اسم گنگت شد «{name}» 🏴\n\n"
        "تازه شروع کردی، فقط یه نیرو داری. برای چه کاری می‌خوای اول ازش استفاده کنی؟"
    )
    kb = _crime_choice_kb("newgang:crime", xp=0)
    bot.reply_to(message, text, reply_markup=kb)


def _handle_new_gang_crime_choice(call, crime_key):
    user_id = call.from_user.id
    with _flow_lock:
        flow = _pending_gang_creation.get(user_id)
    if not flow or flow.get("stage") != "await_crime":
        bot.answer_callback_query(call.id, "این مرحله دیگه معتبر نیست.")
        return

    candidates = [_roll_worker() for _ in range(3)]
    with _flow_lock:
        _pending_gang_creation[user_id] = {
            "stage": "await_worker",
            "name": flow["name"],
            "crime_key": crime_key,
            "candidates": candidates,
        }

    crime = CRIME_BY_KEY[crime_key]
    text = f"باشه، اولین کارت می‌شه «{crime['name']}». حالا کی رو استخدام می‌کنی؟\n\n"
    text += "\n\n".join(_worker_profile_text(w) for w in candidates)

    kb = types.InlineKeyboardMarkup(row_width=1)
    for i, w in enumerate(candidates):
        kb.add(types.InlineKeyboardButton(f"✅ {w['name']} رو استخدام کن", callback_data=f"newgang:worker:{i}"))
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=kb)


def _handle_new_gang_worker_choice(call, idx: int):
    user_id = call.from_user.id
    with _flow_lock:
        flow = _pending_gang_creation.get(user_id)
    if not flow or flow.get("stage") != "await_worker":
        bot.answer_callback_query(call.id, "این مرحله دیگه معتبر نیست.")
        return

    worker = flow["candidates"][idx]
    gang = create_gang(flow["name"], user_id)
    hire_worker(gang["gang_id"], worker, flow["crime_key"])

    with _flow_lock:
        _pending_gang_creation.pop(user_id, None)

    crime = CRIME_BY_KEY[flow["crime_key"]]
    text = (
        f"🏴 گنگ «{gang['name']}» تأسیس شد!\n"
        f"{worker['name']} به‌عنوان اولین نیروت، مشغول «{crime['name']}» شد.\n\n"
        "هر ۴۸ ساعت یادت نره حقوقشو بدی وگرنه ناراضی می‌شه و ممکنه بهت خیانت کنه — "
        "از «💰 حقوق‌ها» تو منوی گنگ می‌تونی خودت تعیین کنی چقدر بهش بدی.\n"
        "با /خلافکاری هر وقت خواستی وضعیت گنگتو ببین."
    )
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id)


# ============================================================
# استخدام نیروی جدید (بعد از ساخت گنگ) — اول کارگر، بعد خلاف
# ============================================================

def _start_hire_flow(user_id, gang_id, chat_id, message_id):
    gang = get_gang_by_id(gang_id)
    workers = get_workers(gang_id)
    cost = HIRE_COST_BASE + HIRE_COST_PER_WORKER * len(workers)
    candidates = [_roll_worker() for _ in range(3)]
    with _flow_lock:
        _pending_gang_creation[user_id] = {
            "stage": "await_hire_worker",
            "gang_id": gang_id,
            "candidates": candidates,
            "cost": cost,
        }
    text = f"استخدام نیروی جدید {cost} سکه هزینه داره. کدومو می‌خوای؟\n\n"
    text += "\n\n".join(_worker_profile_text(w) for w in candidates)
    kb = types.InlineKeyboardMarkup(row_width=1)
    for i, w in enumerate(candidates):
        kb.add(types.InlineKeyboardButton(f"✅ {w['name']}", callback_data=f"gang:hireconfirm:{i}"))
    kb.add(types.InlineKeyboardButton("🔙 انصراف", callback_data=f"gang:menu:{gang_id}"))
    bot.edit_message_text(text, chat_id, message_id, reply_markup=kb)


def _confirm_hire_worker(call, idx, user_id, chat_id, message_id):
    with _flow_lock:
        flow = _pending_gang_creation.get(user_id)
    if not flow or flow.get("stage") != "await_hire_worker":
        bot.answer_callback_query(call.id, "این مرحله دیگه معتبر نیست.")
        return
    gang_id = flow["gang_id"]
    ok, balance = adjust_coins(user_id, -flow["cost"])
    if not ok:
        bot.answer_callback_query(call.id, "موجودیت کافی نیست!", show_alert=True)
        return

    worker = flow["candidates"][idx]
    gang = get_gang_by_id(gang_id)
    with _flow_lock:
        _pending_gang_creation[user_id] = {
            "stage": "await_hire_crime",
            "gang_id": gang_id,
            "worker": worker,
        }

    unlocked = _unlocked_crimes(gang["xp"])
    text = f"{worker['name']} استخدام شد 🎉\nحالا بفرستش تو کدوم خلاف؟"
    kb = types.InlineKeyboardMarkup(row_width=1)
    for c in unlocked:
        kb.add(types.InlineKeyboardButton(c["name"], callback_data=f"gang:hirecrime:{c['key']}"))
    bot.edit_message_text(text, chat_id, message_id, reply_markup=kb)


def _assign_new_hire_crime(call, crime_key, user_id, chat_id, message_id):
    with _flow_lock:
        flow = _pending_gang_creation.get(user_id)
    if not flow or flow.get("stage") != "await_hire_crime":
        bot.answer_callback_query(call.id, "این مرحله دیگه معتبر نیست.")
        return
    gang_id = flow["gang_id"]
    worker = flow["worker"]
    hire_worker(gang_id, worker, crime_key)
    with _flow_lock:
        _pending_gang_creation.pop(user_id, None)
    bot.answer_callback_query(call.id, f"{worker['name']} رفت سر کار «{CRIME_BY_KEY[crime_key]['name']}»! 🎉", show_alert=True)
    _open_crime_menu(call, user_id, chat_id, edit=True, message_id=message_id)


# ============================================================
# منوی اصلی /خلافکاری و دکمه‌ها
# ============================================================

def _open_crime_menu(message_or_call, user_id, chat_id, edit=False, message_id=None):
    gang = get_gang_by_leader(user_id)
    if not gang:
        text = "هنوز گنگی نداری. با /ساختن_گنگ شروع کن."
        if edit:
            bot.edit_message_text(text, chat_id, message_id)
        else:
            bot.send_message(chat_id, text)
        return
    text = _gang_status_text(gang)
    kb = _main_menu_kb(gang)
    if edit:
        bot.edit_message_text(text, chat_id, message_id, reply_markup=kb)
    else:
        bot.send_message(chat_id, text, reply_markup=kb)


def open_menu_from_main(call, user_id, chat_id, message_id):
    """برای دکمه‌ی «🏴 خلافکاری» تو /منوی اصلی ربات — همون منوی /خلافکاری رو باز می‌کنه."""
    _open_crime_menu(call, user_id, chat_id, edit=True, message_id=message_id)


def handle_gang_callback(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    data = call.data

    if data.startswith("newgang:crime:"):
        _handle_new_gang_crime_choice(call, data.split(":", 2)[2])
        return
    if data.startswith("newgang:worker:"):
        _handle_new_gang_worker_choice(call, int(data.split(":", 2)[2]))
        return

    if data.startswith("gang:menu:"):
        _open_crime_menu(call, user_id, chat_id, edit=True, message_id=message_id)
        return

    if data.startswith("gang:workers:"):
        gang_id = int(data.split(":")[2])
        workers = get_workers(gang_id)
        if not workers:
            bot.answer_callback_query(call.id, "هیچ نیرویی نداری.")
            return
        lines = ["👥 نیروهای گنگت — برای فرستادنش سر کار دکمه‌شو بزن:\n"]
        lines.extend(_worker_status_line(w) for w in workers)
        bot.edit_message_text("\n\n".join(lines), chat_id, message_id, reply_markup=_workers_kb(gang_id, workers))
        return

    if data.startswith("gang:run:"):
        worker_id = int(data.split(":")[2])
        with db_lock:
            conn = get_conn()
            row = conn.execute("SELECT * FROM crime_workers WHERE worker_id=?", (worker_id,)).fetchone()
            conn.close()
        if not row:
            bot.answer_callback_query(call.id, "این نیرو دیگه وجود نداره.")
            return
        worker = dict(row)
        gang = get_gang_by_id(worker["gang_id"])

        if has_heist_ally(gang["gang_id"], worker["assigned_crime"]):
            crime = CRIME_BY_KEY.get(worker["assigned_crime"])
            kb = types.InlineKeyboardMarkup(row_width=1)
            kb.add(types.InlineKeyboardButton("🎯 تنها انجام بده", callback_data=f"gang:runchoice:solo:{worker_id}"))
            kb.add(types.InlineKeyboardButton("🤝 با متحدت انجام بده (سود بیشتر، زمان بیشتر)", callback_data=f"gang:runchoice:ally:{worker_id}"))
            kb.add(types.InlineKeyboardButton("🔙 برگشت", callback_data=f"gang:workers:{gang['gang_id']}"))
            bot.edit_message_text(
                f"{worker['name']} رو برای «{crime['name'] if crime else ''}» چجوری بفرستم؟",
                chat_id, message_id, reply_markup=kb,
            )
            return

        worker["_leader_id"] = gang["leader_id"]
        result = run_crime_job(worker, gang)
        bot.answer_callback_query(call.id, result["message"][:200], show_alert=True)
        _open_crime_menu(call, user_id, chat_id, edit=True, message_id=message_id)
        return

    if data.startswith("gang:runchoice:"):
        parts = data.split(":")
        choice = parts[2]
        worker_id = int(parts[3])
        with db_lock:
            conn = get_conn()
            row = conn.execute("SELECT * FROM crime_workers WHERE worker_id=?", (worker_id,)).fetchone()
            conn.close()
        if not row:
            bot.answer_callback_query(call.id, "این نیرو دیگه وجود نداره.")
            return
        worker = dict(row)
        gang = get_gang_by_id(worker["gang_id"])
        worker["_leader_id"] = gang["leader_id"]
        result = run_crime_job(worker, gang, with_ally=(choice == "ally"))
        bot.answer_callback_query(call.id, result["message"][:200], show_alert=True)
        _open_crime_menu(call, user_id, chat_id, edit=True, message_id=message_id)
        return

    if data.startswith("gang:noop"):
        bot.answer_callback_query(call.id)
        return

    if data.startswith("gang:salarymenu:"):
        gang_id = int(data.split(":")[2])
        _open_salary_menu(call, gang_id, chat_id, message_id)
        return

    if data.startswith("gang:salaryadj:"):
        parts = data.split(":")
        worker_id = int(parts[2])
        delta = int(parts[3])
        with db_lock:
            conn = get_conn()
            row = conn.execute("SELECT * FROM crime_workers WHERE worker_id=?", (worker_id,)).fetchone()
            conn.close()
        if not row:
            bot.answer_callback_query(call.id, "این نیرو دیگه وجود نداره.")
            return
        worker = dict(row)
        gang = get_gang_by_id(worker["gang_id"])
        if not gang or gang["leader_id"] != user_id:
            bot.answer_callback_query(call.id, "این نیروی تو نیست.")
            return
        adjust_worker_salary(worker, delta)
        bot.answer_callback_query(call.id)
        _open_salary_menu(call, gang["gang_id"], chat_id, message_id)
        return

    if data.startswith("gang:salarypay1:"):
        worker_id = int(data.split(":")[2])
        with db_lock:
            conn = get_conn()
            row = conn.execute("SELECT * FROM crime_workers WHERE worker_id=?", (worker_id,)).fetchone()
            conn.close()
        if not row:
            bot.answer_callback_query(call.id, "این نیرو دیگه وجود نداره.")
            return
        worker = dict(row)
        gang = get_gang_by_id(worker["gang_id"])
        if not gang or gang["leader_id"] != user_id:
            bot.answer_callback_query(call.id, "این نیروی تو نیست.")
            return
        ok, msg = pay_single_worker(worker_id, user_id)
        bot.answer_callback_query(call.id, msg[:200], show_alert=True)
        _open_salary_menu(call, gang["gang_id"], chat_id, message_id)
        return

    if data.startswith("gang:pay:"):
        gang_id = int(data.split(":")[2])
        gang = get_gang_by_id(gang_id)
        ok, msg = pay_salaries(gang_id, gang["leader_id"])
        bot.answer_callback_query(call.id, msg[:200], show_alert=True)
        _open_salary_menu(call, gang_id, chat_id, message_id)
        return

    if data.startswith("gang:hire:"):
        gang_id = int(data.split(":")[2])
        _start_hire_flow(user_id, gang_id, chat_id, message_id)
        return

    if data.startswith("gang:hireconfirm:"):
        idx = int(data.split(":")[2])
        _confirm_hire_worker(call, idx, user_id, chat_id, message_id)
        return

    if data.startswith("gang:hirecrime:"):
        crime_key = data.split(":", 2)[2]
        _assign_new_hire_crime(call, crime_key, user_id, chat_id, message_id)
        return

    if data.startswith("gang:relations:"):
        gang_id = int(data.split(":")[2])
        relations = list_relations(gang_id)
        if not relations:
            text = "هنوز با هیچ گنگی رابطه‌ای نداری.\nبرای شروع: /گنگ_رابطه <اسم گنگ>"
        else:
            status_fa = {"alliance": "متحد 🤝", "war": "در جنگ ⚔️"}
            lines = ["روابط گنگت:\n"] + [
                f"• {other['name']} — {status_fa.get(status, status)}" for other, status, _ in relations
            ]
            lines.append("\nبرای تغییر رابطه با یه گنگ خاص: /گنگ_رابطه <اسم گنگ>")
            text = "\n".join(lines)
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(types.InlineKeyboardButton("🔙 برگشت", callback_data=f"gang:menu:{gang_id}"))
        bot.edit_message_text(text, chat_id, message_id, reply_markup=kb)
        return

    if data.startswith("gang:rel:"):
        _handle_relation_callback(call, data, user_id, chat_id)
        return

    if data.startswith("gang:heistally:"):
        _handle_heist_ally_callback(call, data, user_id, chat_id)
        return

    if data.startswith("gang:allystart:"):
        my_gang = get_gang_by_leader(user_id)
        if not my_gang:
            bot.answer_callback_query(call.id, "اول باید خودت یه گنگ داشته باشی.")
            return
        bot.answer_callback_query(call.id)
        _start_ally_flow(user_id, chat_id, my_gang)
        return

    if data.startswith("gang:allycrime:"):
        crime_key = data.split(":", 2)[2]
        _handle_ally_crime_choice(call, crime_key, user_id, chat_id, message_id)
        return


# ============================================================
# ثبت دستورات و هندلرها
# ============================================================

def _relation_kb(my_id, target_id, status):
    kb = types.InlineKeyboardMarkup(row_width=1)
    if status == "neutral":
        kb.add(types.InlineKeyboardButton("⚔️ اعلام جنگ", callback_data=f"gang:rel:war:{my_id}:{target_id}"))
        kb.add(types.InlineKeyboardButton("🤝 پیشنهاد اتحاد", callback_data=f"gang:rel:allyreq:{my_id}:{target_id}"))
    elif status == "alliance":
        kb.add(types.InlineKeyboardButton("⚔️ اعلام جنگ (شکستن اتحاد)", callback_data=f"gang:rel:war:{my_id}:{target_id}"))
    elif status == "war":
        kb.add(types.InlineKeyboardButton("🕊️ پیشنهاد صلح", callback_data=f"gang:rel:peacereq:{my_id}:{target_id}"))
        kb.add(types.InlineKeyboardButton("💥 حمله", callback_data=f"gang:rel:attack:{my_id}:{target_id}"))
    return kb


_RELATION_STATUS_FA = {"neutral": "خنثی", "alliance": "متحد 🤝", "war": "در جنگ ⚔️"}


def _cmd_gang_relation(message):
    ensure_user(message.from_user.id, message.from_user.username or message.from_user.first_name or "")
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "استفاده: /گنگ_رابطه <اسم گنگ>")
        return
    target_name = parts[1].strip()
    my_gang = get_gang_by_leader(message.from_user.id)
    if not my_gang:
        bot.reply_to(message, "اول باید خودت یه گنگ داشته باشی. با /ساختن_گنگ شروع کن.")
        return
    target = get_gang_by_name(target_name)
    if not target:
        bot.reply_to(message, "گنگی به این اسم پیدا نکردم.")
        return
    if target["gang_id"] == my_gang["gang_id"]:
        bot.reply_to(message, "این که خودتی 😄")
        return
    status = get_relation_status(my_gang["gang_id"], target["gang_id"])
    text = f"رابطه‌ی گنگ «{my_gang['name']}» با «{target['name']}»: {_RELATION_STATUS_FA[status]}"
    bot.reply_to(message, text, reply_markup=_relation_kb(my_gang["gang_id"], target["gang_id"], status))


def _handle_relation_callback(call, data, user_id, chat_id):
    parts = data.split(":")
    action = parts[2]
    a = int(parts[3])
    b = int(parts[4])
    my_gang = get_gang_by_leader(user_id)

    if action == "war":
        if not my_gang or my_gang["gang_id"] != a:
            bot.answer_callback_query(call.id, "این دکمه مال گنگ تو نیست.")
            return
        declare_war(a, b)
        defender = get_gang_by_id(b)
        attacker = get_gang_by_id(a)
        bot.answer_callback_query(call.id, f"⚔️ رسماً به «{defender['name']}» اعلام جنگ کردی!", show_alert=True)
        try:
            bot.send_message(defender["leader_id"], f"🚨 گنگ «{attacker['name']}» بهت اعلام جنگ کرد! با /گنگ_رابطه {attacker['name']} می‌تونی وضعیت رو ببینی.")
        except Exception:
            pass
        return

    if action == "attack":
        if not my_gang or my_gang["gang_id"] != a:
            bot.answer_callback_query(call.id, "این دکمه مال گنگ تو نیست.")
            return
        result = attack_gang(a, b)
        bot.answer_callback_query(call.id, result["message"][:200], show_alert=True)
        return

    if action in ("allyreq", "peacereq"):
        if not my_gang or my_gang["gang_id"] != a:
            bot.answer_callback_query(call.id, "این دکمه مال گنگ تو نیست.")
            return
        kind = "alliance" if action == "allyreq" else "peace"
        propose_relation(kind, a, b)
        proposer = get_gang_by_id(a)
        target = get_gang_by_id(b)
        label = "اتحاد 🤝" if kind == "alliance" else "صلح 🕊️"
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton("✅ قبول", callback_data=f"gang:rel:{'allyack' if kind == 'alliance' else 'peaceack'}:{a}:{b}"),
            types.InlineKeyboardButton("❌ رد", callback_data=f"gang:rel:{'allyrej' if kind == 'alliance' else 'peacerej'}:{a}:{b}"),
        )
        try:
            bot.send_message(target["leader_id"], f"گنگ «{proposer['name']}» پیشنهاد {label} داده. قبول می‌کنی؟", reply_markup=kb)
            bot.answer_callback_query(call.id, "پیشنهادت فرستاده شد، منتظر جواب بمون.", show_alert=True)
        except Exception:
            bot.answer_callback_query(call.id, "نشد پیام بفرستم، شاید هنوز با ربات چت نکرده.", show_alert=True)
        return

    if action in ("allyack", "allyrej", "peaceack", "peacerej"):
        if not my_gang or my_gang["gang_id"] != b:
            bot.answer_callback_query(call.id, "این پیشنهاد برای گنگ تو نیست.")
            return
        kind = "alliance" if action.startswith("ally") else "peace"
        accepted = action.endswith("ack")
        ok = resolve_relation_proposal(kind, a, b, accepted)
        if not ok:
            bot.answer_callback_query(call.id, "این پیشنهاد منقضی شده.", show_alert=True)
            return
        proposer = get_gang_by_id(a)
        label = "اتحاد" if kind == "alliance" else "صلح"
        if accepted:
            bot.answer_callback_query(call.id, f"{label} با «{proposer['name']}» برقرار شد! 🎉", show_alert=True)
            try:
                bot.send_message(proposer["leader_id"], f"گنگت با «{my_gang['name']}» به {label} رسید! 🎉")
            except Exception:
                pass
        else:
            bot.answer_callback_query(call.id, "رد کردی.", show_alert=True)
            try:
                bot.send_message(proposer["leader_id"], f"پیشنهاد {label} با «{my_gang['name']}» رد شد.")
            except Exception:
                pass
        return


def _extract_username(text: str) -> str:
    text = text.strip()
    if text.startswith("@"):
        text = text[1:]
    return text.split()[0] if text else ""


def _start_ally_flow(user_id, chat_id, my_gang):
    with _flow_lock:
        _pending_ally_flow[user_id] = {"stage": "await_target", "from_gang": my_gang["gang_id"]}
    sent = bot.send_message(
        chat_id,
        "🤝 به کدوم بازیکن پیشنهاد اتحاد سرقت بدم؟\n"
        "با ریپلای به همین پیام، @یوزرنیمش رو بفرست (یا فقط ریپلای بزن روی یکی از پیام‌های خودش تو گروه و بنویس @یوزرنیمش).",
        reply_markup=types.ForceReply(selective=True),
    )
    with _flow_lock:
        if user_id in _pending_ally_flow:
            _pending_ally_flow[user_id]["prompt_id"] = sent.message_id


def _is_ally_target_reply(message) -> bool:
    if message.reply_to_message is None or not message.text:
        return False
    user_id = message.from_user.id
    with _flow_lock:
        flow = _pending_ally_flow.get(user_id)
    return bool(flow and flow.get("stage") == "await_target"
                and flow.get("prompt_id") == message.reply_to_message.message_id)


def _handle_ally_target_reply(message):
    _handle_ally_target_reply_for_message(message, message.text)


def _handle_ally_crime_choice(call, crime_key, user_id, chat_id, message_id):
    with _flow_lock:
        flow = _pending_ally_flow.get(user_id)
    if not flow or flow.get("stage") != "await_crime":
        bot.answer_callback_query(call.id, "این مرحله دیگه معتبر نیست. دوباره از «🤝 اتحاد سرقت» شروع کن.")
        return

    from_gang_id = flow["from_gang"]
    to_gang_id = flow["to_gang"]
    with _flow_lock:
        _pending_ally_flow.pop(user_id, None)

    my_gang = get_gang_by_id(from_gang_id)
    target_gang = get_gang_by_id(to_gang_id)
    crime = CRIME_BY_KEY[crime_key]

    key = f"{from_gang_id}:{to_gang_id}"
    with _flow_lock:
        _pending_heist_ally_invites[key] = {"from": from_gang_id, "to": to_gang_id, "crime_key": crime_key}

    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("✅ قبول", callback_data=f"gang:heistally:ack:{from_gang_id}:{to_gang_id}"),
        types.InlineKeyboardButton("❌ رد", callback_data=f"gang:heistally:rej:{from_gang_id}:{to_gang_id}"),
    )
    try:
        bot.send_message(
            target_gang["leader_id"],
            f"🤝 گنگ «{my_gang['name']}» می‌خواد باهات توی «{crime['name']}» متحد بشه "
            f"(فقط برای همین خلاف، تا {HEIST_ALLY_HOURS} ساعت). قبول می‌کنی؟",
            reply_markup=kb,
        )
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            f"درخواست اتحاد برای «{crime['name']}» به «{target_gang['name']}» فرستاده شد، منتظر جواب بمون.",
            chat_id, message_id,
        )
    except Exception:
        bot.answer_callback_query(call.id, "نتونستم پیام بفرستم — شاید طرف هنوز با ربات چت نکرده.", show_alert=True)


def _cmd_heist_ally_invite(message):
    """میانبر تایپی: /اتحاد <یوزرنیم> — همون فلو رو با یه مرحله‌ی کمتر شروع می‌کنه."""
    ensure_user(message.from_user.id, message.from_user.username or message.from_user.first_name or "")
    parts = message.text.split(maxsplit=1)
    my_gang = get_gang_by_leader(message.from_user.id)
    if not my_gang:
        bot.reply_to(message, "اول باید خودت یه گنگ داشته باشی. با /ساختن_گنگ شروع کن.")
        return
    if len(parts) < 2:
        _start_ally_flow(message.from_user.id, message.chat.id, my_gang)
        return
    _handle_ally_target_reply_for_message(message, parts[1])


def _handle_ally_target_reply_for_message(message, username_text):
    user_id = message.from_user.id
    if find_user_by_username is None:
        bot.reply_to(message, "این قابلیت الان در دسترس نیست.")
        return
    my_gang = get_gang_by_leader(user_id)
    username = _extract_username(username_text)
    target_user = find_user_by_username(username) if username else None
    if not target_user:
        bot.reply_to(message, "همچین کاربری پیدا نکردم. مطمئن شو یوزرنیمو درست نوشتی و طرف قبلاً با ربات چت کرده.")
        return
    if target_user["user_id"] == user_id:
        bot.reply_to(message, "با خودت که نمی‌شه متحد شد 😄")
        return
    target_gang = get_gang_by_leader(target_user["user_id"])
    if not target_gang:
        bot.reply_to(message, "این کاربر هنوز گنگی نداره، اول باید خودش /ساختن_گنگ رو بزنه.")
        return
    with _flow_lock:
        _pending_ally_flow[user_id] = {
            "stage": "await_crime",
            "from_gang": my_gang["gang_id"],
            "to_gang": target_gang["gang_id"],
        }
    kb = _crime_choice_kb("gang:allycrime", my_gang["xp"])
    bot.reply_to(message, f"با «{target_gang['name']}» می‌خواین رو کدوم خلاف متحد بشین؟", reply_markup=kb)


def _handle_heist_ally_callback(call, data, user_id, chat_id):
    # gang:heistally:<ack|rej>:<from_gang>:<to_gang>
    parts = data.split(":")
    decision = parts[2]
    from_gang = int(parts[3])
    to_gang = int(parts[4])
    key = f"{from_gang}:{to_gang}"

    my_gang = get_gang_by_leader(user_id)
    if not my_gang or my_gang["gang_id"] != to_gang:
        bot.answer_callback_query(call.id, "این پیشنهاد برای گنگ تو نیست.")
        return

    with _flow_lock:
        existed = _pending_heist_ally_invites.pop(key, None)
    if not existed:
        bot.answer_callback_query(call.id, "این پیشنهاد دیگه منقضی شده.", show_alert=True)
        return

    crime_key = existed.get("crime_key")
    crime_name = CRIME_BY_KEY[crime_key]["name"] if crime_key in CRIME_BY_KEY else "سرقت گروهی"
    proposer = get_gang_by_id(from_gang)
    if decision == "ack":
        create_heist_ally(from_gang, to_gang, crime_key)
        bot.answer_callback_query(call.id, f"اتحادتون برای «{crime_name}» برقرار شد! {HEIST_ALLY_HOURS} ساعت وقت دارید.", show_alert=True)
        try:
            bot.send_message(proposer["leader_id"], f"گنگ «{my_gang['name']}» پیشنهاد اتحادت برای «{crime_name}» رو قبول کرد! حالا هر دو می‌تونید این خلاف رو تیمی انجام بدید.")
        except Exception:
            pass
    else:
        bot.answer_callback_query(call.id, "رد کردی.", show_alert=True)
        try:
            bot.send_message(proposer["leader_id"], f"گنگ «{my_gang['name']}» پیشنهاد اتحادت رو رد کرد.")
        except Exception:
            pass


def _register_handlers():
    @bot.message_handler(commands=["ساختن_گنگ"])
    def _cmd_create_gang(message):
        ensure_user(message.from_user.id, message.from_user.username or message.from_user.first_name or "")
        _start_gang_creation(message)

    @bot.message_handler(commands=["خلافکاری"])
    def _cmd_crime_menu(message):
        ensure_user(message.from_user.id, message.from_user.username or message.from_user.first_name or "")
        _open_crime_menu(message, message.from_user.id, message.chat.id)

    @bot.message_handler(commands=["گنگ_رابطه"])
    def _cmd_relation(message):
        _cmd_gang_relation(message)

    @bot.message_handler(commands=["اتحاد"])
    def _cmd_ally(message):
        _cmd_heist_ally_invite(message)

    @bot.message_handler(func=_is_gang_name_reply)
    def _reply_gang_name(message):
        _handle_gang_name_reply(message)

    @bot.message_handler(func=_is_ally_target_reply)
    def _reply_ally_target(message):
        ensure_user(message.from_user.id, message.from_user.username or message.from_user.first_name or "")
        _handle_ally_target_reply(message)

    init_crime_tables()
