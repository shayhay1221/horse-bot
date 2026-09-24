"""
restaurant_job.py — شغل «رستوران» برای طویله (Stable)

این فایل هم مثل crime_gang.py کاملاً جداست و به stable_bot.py «لینک» می‌شه.

────────────────────────────────────────────────────────────
سرعت — چرا این‌جوری طراحی شده:
هیچ inline keyboard‌ای تو مسیر اصلی بازی نیست. مشتری سفارش می‌ده،
بازیکن باید ترکیب مواد رو از حفظ (یا از /دستورپخت) به‌صورت یه پیام
متنی واحد بفرسته (مثلاً 🍞🐔🧀🍅🥬🥒🍞). یعنی هر سفارش دقیقاً
یک رفت‌وبرگشت به تلگرام داره: نه callback_query، نه edit_message،
نه چندتا دکمه‌ی پشت‌سرهم. کل چک‌کردن و پرداخت هم توی حافظه انجام
می‌شه و فقط در پایان یک بار bot.reply_to صدا زده می‌شه.

نحوه‌ی اتصال به stable_bot.py (۳ تغییر، دقیقاً مثل crime_gang.py):

۱) بالای فایل:
       import restaurant_job

۲) بعد از ساخت `bot` (بعد از crime_gang.register اگه از قبل هست):
       restaurant_job.register(bot, get_conn, db_lock, adjust_coins,
                                PK_AUTOINCREMENT, ensure_user)

۳) این فایل برای منوی دکمه‌ای (نه خودِ بازی) از callback_data استفاده می‌کنه،
   پس باید تو handle_callback هوک بشه — دقیقاً مثل crime_gang:
       if data == "menu:restaurant":
           restaurant_job.open_menu_from_main(call, user_id, call.message.chat.id, call.message.message_id)
           return
       if data.startswith("restaurant:"):
           restaurant_job.handle_restaurant_callback(call)
           return
   (این دو خط رو هم الان تو خودِ stable_bot.py زدیم.)
   خودِ جواب‌دادن به سفارش مشتری (ترکیب مواد) هنوز کاملاً پیام متنیه، نه دکمه —
   طبق همون تصمیم سرعت بالا.

اگه بعداً خواستی «ارتقا»‌ی رستوران رو مثل بقیه‌ی ارتقاها با یه دکمه‌ی
داخل منوی اصلی هم قابل‌دسترس کنی، کافیه از restaurant_job.upgrade_price_now(user_id)
و restaurant_job.do_upgrade(user_id) تو منوی خودت صدا بزنی.
────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import random
import threading
import time
from datetime import datetime, timezone

from telebot import types

bot = None
get_conn = None
db_lock: threading.Lock | None = None
adjust_coins = None
PK_AUTOINCREMENT = "SERIAL PRIMARY KEY"
ensure_user = None

_state_lock = threading.Lock()
# user_id -> {chat_id, message_id?, recipe_key, expected(list), started_at,
#             orders_left, shift_earned, timer(Timer)}
_active_orders: dict[int, dict] = {}


def register(bot_, get_conn_, db_lock_, adjust_coins_, pk_autoincrement_, ensure_user_):
    global bot, get_conn, db_lock, adjust_coins, PK_AUTOINCREMENT, ensure_user
    bot = bot_
    get_conn = get_conn_
    db_lock = db_lock_
    adjust_coins = adjust_coins_
    PK_AUTOINCREMENT = pk_autoincrement_
    ensure_user = ensure_user_
    init_restaurant_tables()
    _register_handlers()


def _now():
    return datetime.now(timezone.utc)


# ============================================================
# دیتا — مواد اولیه
# ============================================================

INGREDIENTS = {
    "🍞": "نان", "🥩": "گوشت", "🐔": "مرغ", "🧀": "پنیر", "🍅": "گوجه",
    "🥬": "کاهو", "🥒": "خیار", "🌶️": "فلفل‌تند", "🧅": "پیاز", "🍄": "قارچ",
    "🥓": "بیکن", "🥚": "تخم‌مرغ", "🍚": "برنج", "🫘": "لوبیا", "🌯": "لواش",
    "🥔": "سیب‌زمینی", "🍤": "میگو", "🐟": "ماهی", "🥑": "آووکادو", "🫒": "زیتون",
    "🥛": "سس‌مخصوص", "🍋": "لیمو", "🌽": "ذرت", "🧂": "نمک",
}
# برای پارس‌کردن سریع، از بلندترین کد به کوتاه‌ترین مرتب می‌کنیم
_INGREDIENT_KEYS_SORTED = sorted(INGREDIENTS.keys(), key=len, reverse=True)

# ============================================================
# دیتا — منوی غذاها، بر اساس سطح سختی (=سطح آشپزخونه لازم)
# هرچی ایموجی بیشتر و متنوع‌تر → سخت‌تر حفظ کردن → پول بیشتر
# ============================================================

RECIPES = [
    # ---- درجه ۱ — همیشه باز (۳-۴ ماده) ----
    dict(key="bread_cheese",  name="🥪 نون‌پنیر",             tier=1, emojis="🍞🧀🍞",         pay=(4, 7)),
    dict(key="fries",         name="🍟 سیب‌زمینی سرخ‌کرده",   tier=1, emojis="🥔🥔🧂🍋",       pay=(5, 8)),
    dict(key="egg_toast",     name="🍳 نون‌وتخم‌مرغ",          tier=1, emojis="🍞🥚🧂",         pay=(4, 7)),
    dict(key="simple_salad",  name="🥗 سالاد ساده",           tier=1, emojis="🥬🍅🥒🧂",       pay=(5, 9)),
    dict(key="corn_cup",      name="🌽 ذرت مکزیکی",           tier=1, emojis="🌽🧂🍋",         pay=(4, 7)),

    # ---- درجه ۲ — نیاز به ۲ ارتقا (۵-۶ ماده) ----
    dict(key="cold_cut",      name="🥪 ساندویچ کالباس‌پنیر",  tier=2, emojis="🍞🥓🧀🍅🍞",     pay=(9, 15)),
    dict(key="plain_burger",  name="🍔 برگر ساده",            tier=2, emojis="🍞🥩🧅🧀🍞",     pay=(10, 16)),
    dict(key="chicken_wrap",  name="🌯 رول مرغ",              tier=2, emojis="🌯🐔🥬🧀🥛",     pay=(10, 16)),
    dict(key="tuna_sandwich", name="🥪 ساندویچ تن‌ماهی",      tier=2, emojis="🍞🐟🧅🥒🍞🧂",   pay=(11, 18)),
    dict(key="chicken_salad", name="🥗 سالاد مرغ",            tier=2, emojis="🐔🥬🍅🧀🥑🧂",   pay=(11, 18)),

    # ---- درجه ۳ — نیاز به ۴ ارتقا (۷-۸ ماده) ----
    dict(key="special_chicken_sandwich", name="🥪 ساندویچ مرغ ویژه", tier=3, emojis="🍞🐔🧀🍅🥬🥒🍞", pay=(18, 28)),
    dict(key="special_burger", name="🍔 برگر مخصوص",          tier=3, emojis="🍞🥩🧀🍅🧅🍄🥬🍞", pay=(20, 32)),
    dict(key="full_burrito",  name="🌯 بوریتو کامل",           tier=3, emojis="🌯🫘🧀🌶️🍚🧅🥑",  pay=(19, 30)),
    dict(key="special_pizza", name="🍕 پیتزای مخصوص",         tier=3, emojis="🍞🧀🍄🧅🌶️🥓🫒🍅", pay=(20, 32)),
    dict(key="shrimp_roll",   name="🌯 رول میگو",              tier=3, emojis="🌯🍤🥬🥒🧀🥛🍋",  pay=(19, 30)),

    # ---- درجه ۴ — نیاز به ۶ ارتقا (۹-۱۰ ماده، سرآشپز واقعی) ----
    dict(key="double_burger", name="🍔 دوبل‌برگر مخصوص",      tier=4, emojis="🍞🥩🧀🥩🧀🧅🍄🥬🍅🍞", pay=(32, 48)),
    dict(key="seafood_mix",   name="🍚 غذای دریایی مخلوط",     tier=4, emojis="🍚🍤🐟🧅🌶️🍋🫒🥑🧂", pay=(30, 46)),
    dict(key="combo_sandwich", name="🥪 ساندویچ ترکیبی رستوران", tier=4, emojis="🍞🥩🐔🧀🥓🍅🥬🥒🧅🍞", pay=(34, 50)),
]

TIER_UNLOCK_UPGRADES = {1: 0, 2: 2, 3: 4, 4: 6}
TIER_TIME_LIMIT_SEC = {1: 20, 2: 30, 3: 45, 4: 60}
UPGRADE_BASE_PRICE = 90
ORDERS_PER_SHIFT_BASE = 4
ORDERS_PER_SHIFT_PER_UPGRADE = 1  # هر ۲ ارتقا یه مشتری بیشتر تو شیفت (پایین محاسبه می‌شه)
STREAK_BONUS_STEP = 0.08   # هر سفارش درستِ پشت‌سرهم ۸٪ به پاداش اضافه می‌کنه
STREAK_BONUS_MAX = 0.50    # سقف ۵۰٪ بونوس


def unlocked_tiers(upgrades: int) -> list[int]:
    return [t for t, need in TIER_UNLOCK_UPGRADES.items() if upgrades >= need]


def unlocked_recipes(upgrades: int) -> list[dict]:
    tiers = set(unlocked_tiers(upgrades))
    return [r for r in RECIPES if r["tier"] in tiers]


def orders_per_shift(upgrades: int) -> int:
    return ORDERS_PER_SHIFT_BASE + upgrades // 2


def upgrade_price(upgrades_done: int) -> int:
    return int(UPGRADE_BASE_PRICE * (1.28 ** upgrades_done))


# ============================================================
# دیتابیس
# ============================================================

def init_restaurant_tables():
    with db_lock:
        conn = get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS restaurant_state (
                user_id BIGINT PRIMARY KEY,
                upgrades INTEGER DEFAULT 0,
                streak INTEGER DEFAULT 0,
                best_streak INTEGER DEFAULT 0,
                orders_served INTEGER DEFAULT 0
            )
        """)
        conn.commit()
        conn.close()


def _get_state(user_id) -> dict:
    with db_lock:
        conn = get_conn()
        row = conn.execute(
            "SELECT * FROM restaurant_state WHERE user_id=?", (user_id,)
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO restaurant_state (user_id) VALUES (?)", (user_id,)
            )
            conn.commit()
            conn.close()
            return dict(user_id=user_id, upgrades=0, streak=0, best_streak=0, orders_served=0)
        conn.close()
        return dict(row)


def _update_state(user_id, **fields):
    with db_lock:
        conn = get_conn()
        cols = ", ".join(f"{k}=?" for k in fields)
        values = list(fields.values()) + [user_id]
        conn.execute(f"UPDATE restaurant_state SET {cols} WHERE user_id=?", values)
        conn.commit()
        conn.close()


def do_upgrade(user_id):
    """برای استفاده‌ی اختیاری از منوی اصلی خودِ ربات هم قابل صدا زدنه."""
    state = _get_state(user_id)
    price = upgrade_price(state["upgrades"])
    ok, balance = adjust_coins(user_id, -price)
    if not ok:
        return False, f"سکه‌ت کافی نیست. قیمت ارتقا: {price} سکه."
    _update_state(user_id, upgrades=state["upgrades"] + 1)
    return True, f"👨‍🍳 آشپزخونه ارتقا پیدا کرد! (ارتقای {state['upgrades'] + 1})"


def upgrade_price_now(user_id):
    return upgrade_price(_get_state(user_id)["upgrades"])


# ============================================================
# پارس‌کردن پاسخ بازیکن
# ============================================================

def _parse_emoji_sequence(text: str) -> list[str] | None:
    """رشته‌ی ورودی رو به لیست ایموجی‌های مواد تبدیل می‌کنه.
    اگه یه کاراکتر ناشناس (غیر مواد، غیر فاصله) توش باشه، None برمی‌گردونه."""
    text = text.strip()
    if not text:
        return None
    result = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        matched = None
        for key in _INGREDIENT_KEYS_SORTED:
            if text.startswith(key, i):
                matched = key
                break
        if matched is None:
            return None
        result.append(matched)
        i += len(matched)
    return result


# ============================================================
# منطق شیفت / سفارش
# ============================================================

def _recipe_book_text(user_id) -> str:
    state = _get_state(user_id)
    recipes = unlocked_recipes(state["upgrades"])
    recipes.sort(key=lambda r: (r["tier"], r["name"]))
    lines = ["📖 دستورپخت‌های باز:\n"]
    cur_tier = None
    for r in recipes:
        if r["tier"] != cur_tier:
            cur_tier = r["tier"]
            lines.append(f"\n— درجه {cur_tier} —")
        lines.append(f"{r['name']}: {r['emojis']}")
    next_tier = next((t for t in (1, 2, 3, 4) if t not in unlocked_tiers(state["upgrades"])), None)
    if next_tier:
        need = TIER_UNLOCK_UPGRADES[next_tier] - state["upgrades"]
        lines.append(f"\n🔒 درجه {next_tier} با {need} ارتقای دیگه باز می‌شه. (/ارتقا_رستوران)")
    return "\n".join(lines)


def _status_text(user_id) -> str:
    state = _get_state(user_id)
    price = upgrade_price(state["upgrades"])
    return (
        f"🍽️ رستوران\n\n"
        f"سطح آشپزخونه: {state['upgrades']}\n"
        f"رکورد استریک: {state['best_streak']}\n"
        f"تعداد سفارش‌های موفق تا الان: {state['orders_served']}\n"
        f"مشتری‌های هر شیفت: {orders_per_shift(state['upgrades'])}\n\n"
        f"دستورها:\n"
        f"/دستورپخت — لیست غذاها و ترکیبشون\n"
        f"/باز_رستوران — شروع شیفت کاری\n"
        f"/ارتقا_رستوران — ارتقای آشپزخونه ({price} سکه)"
    )


def _pick_order(upgrades: int) -> dict:
    return random.choice(unlocked_recipes(upgrades))


def _send_next_customer(user_id, chat_id):
    with _state_lock:
        session = _active_orders.get(user_id)
        if not session:
            return
        if session["orders_left"] <= 0:
            _end_shift(user_id, chat_id, timed_out=False)
            return
        state = _get_state(user_id)
        recipe = _pick_order(state["upgrades"])
        session["recipe"] = recipe
        session["started_at"] = time.monotonic()
        limit = TIER_TIME_LIMIT_SEC[recipe["tier"]]
        old_timer = session.get("timer")
        if old_timer:
            old_timer.cancel()
        timer = threading.Timer(limit, _order_timeout, args=(user_id, chat_id))
        timer.daemon = True
        session["timer"] = timer
        timer.start()

    bot.send_message(
        chat_id,
        f"🧑 مشتری: یه «{recipe['name']}» می‌خوام!\n"
        f"⏱ {limit} ثانیه وقت داری — ترکیب مواد رو به‌صورت یه پیام بفرست.\n"
        f"(مونده تو این شیفت: {session['orders_left']})"
    )


def _order_timeout(user_id, chat_id):
    with _state_lock:
        session = _active_orders.get(user_id)
        if not session:
            return
        recipe = session.get("recipe")
    if recipe:
        _update_state(user_id, streak=0)
        bot.send_message(chat_id, f"⏰ وقت تموم شد، مشتری رفت. (سفارش: {recipe['name']})")
    with _state_lock:
        session = _active_orders.get(user_id)
        if session:
            session["orders_left"] -= 1
    _send_next_customer(user_id, chat_id)


def _end_shift(user_id, chat_id, timed_out=False):
    with _state_lock:
        session = _active_orders.pop(user_id, None)
    if not session:
        return
    timer = session.get("timer")
    if timer:
        timer.cancel()
    bot.send_message(
        chat_id,
        f"🔚 شیفت تموم شد! امروز {session['shift_earned']} سکه در آوردی.\n"
        f"دوباره با /باز_رستوران شروع کن."
    )


def _handle_order_reply(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    with _state_lock:
        session = _active_orders.get(user_id)
        if not session or "recipe" not in session:
            return
        recipe = session["recipe"]
        timer = session.get("timer")

    parsed = _parse_emoji_sequence(message.text or "")
    expected = list(recipe["emojis"])
    # emojis رشته‌ست ولی چون تک‌کاراکتری‌های ساده‌ن، iterate مستقیم هم کار می‌کنه؛
    # برای اطمینان از دیتای چندکاراکتری احتمالی از همون پارسر استفاده می‌کنیم:
    expected = _parse_emoji_sequence(recipe["emojis"])

    if timer:
        timer.cancel()

    if parsed is not None and parsed == expected:
        state = _get_state(user_id)
        new_streak = state["streak"] + 1
        bonus = min(STREAK_BONUS_MAX, (new_streak - 1) * STREAK_BONUS_STEP)
        base_pay = random.randint(*recipe["pay"])
        final_pay = int(round(base_pay * (1 + bonus)))
        adjust_coins(user_id, final_pay)
        _update_state(
            user_id,
            streak=new_streak,
            best_streak=max(state["best_streak"], new_streak),
            orders_served=state["orders_served"] + 1,
        )
        extra = f" (+{int(bonus*100)}٪ بونوس استریک)" if bonus > 0 else ""
        bot.reply_to(message, f"✅ عالی بود! +{final_pay} سکه{extra} — استریک: {new_streak}")
        with _state_lock:
            s = _active_orders.get(user_id)
            if s:
                s["shift_earned"] += final_pay
    else:
        _update_state(user_id, streak=0)
        bot.reply_to(message, f"❌ اشتباه بود. ترکیب درست: {recipe['emojis']}")

    with _state_lock:
        session = _active_orders.get(user_id)
        if session:
            session["orders_left"] -= 1
            session.pop("recipe", None)

    _send_next_customer(user_id, chat_id)


def _has_active_order(message) -> bool:
    if not message.text:
        return False
    with _state_lock:
        session = _active_orders.get(message.from_user.id)
        return bool(session and "recipe" in session and session.get("chat_id") == message.chat.id)


# ============================================================
# منوی دکمه‌ای (برای این‌که لازم نباشه کامند بزنن)
# فقط ناوبری (وضعیت/دستورپخت/باز‌وبسته‌کردن شیفت/ارتقا) دکمه‌ایه؛
# خودِ جواب‌دادن به سفارش عمداً پیام متنیه، همون‌طور که بالای فایل
# توضیح داده شده — برای سرعت.
# ============================================================

def _main_menu_kb(user_id):
    with _state_lock:
        has_shift = user_id in _active_orders
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("📖 دستورپخت", callback_data="restaurant:recipes"))
    if has_shift:
        kb.add(types.InlineKeyboardButton("🔚 بستن شیفت", callback_data="restaurant:close"))
    else:
        kb.add(types.InlineKeyboardButton("🍽️ باز کردن مغازه", callback_data="restaurant:open"))
    kb.add(types.InlineKeyboardButton("👨‍🍳 ارتقای آشپزخونه", callback_data="restaurant:upgrade"))
    kb.add(types.InlineKeyboardButton("🔙 برگشت به منو", callback_data="menu:main"))
    return kb


def open_menu_from_main(call, user_id, chat_id, message_id):
    """برای دکمه‌ی «🍽️ رستوران» تو /منوی اصلی ربات."""
    ensure_user(user_id, call.from_user.username or call.from_user.first_name or "")
    bot.edit_message_text(_status_text(user_id), chat_id, message_id, reply_markup=_main_menu_kb(user_id))


def handle_restaurant_callback(call):
    """باید از stable_bot.py برای هر callback_data که با restaurant: شروع می‌شه صدا زده بشه."""
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    data = call.data

    if data == "restaurant:menu":
        bot.answer_callback_query(call.id)
        bot.edit_message_text(_status_text(user_id), chat_id, message_id, reply_markup=_main_menu_kb(user_id))
        return

    if data == "restaurant:recipes":
        bot.answer_callback_query(call.id)
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🔙 برگشت", callback_data="restaurant:menu"))
        bot.edit_message_text(_recipe_book_text(user_id), chat_id, message_id, reply_markup=kb)
        return

    if data == "restaurant:upgrade":
        ok, msg = do_upgrade(user_id)
        bot.answer_callback_query(call.id, msg, show_alert=True)
        if ok:
            bot.edit_message_text(_status_text(user_id), chat_id, message_id, reply_markup=_main_menu_kb(user_id))
        return

    if data == "restaurant:open":
        with _state_lock:
            if user_id in _active_orders:
                bot.answer_callback_query(call.id, "الان وسط یه شیفتی!")
                return
            state = _get_state(user_id)
            _active_orders[user_id] = dict(
                chat_id=chat_id,
                orders_left=orders_per_shift(state["upgrades"]),
                shift_earned=0,
                timer=None,
            )
        bot.answer_callback_query(call.id, "🍽️ مغازه باز شد!")
        bot.edit_message_text(
            "🍽️ مغازه بازه! سفارش مشتری تو پیام بعدی میاد — جوابش رو با یه پیام معمولی (ترکیب مواد) بده.",
            chat_id, message_id, reply_markup=_main_menu_kb(user_id),
        )
        _send_next_customer(user_id, chat_id)
        return

    if data == "restaurant:close":
        bot.answer_callback_query(call.id)
        _end_shift(user_id, chat_id)
        bot.edit_message_text(_status_text(user_id), chat_id, message_id, reply_markup=_main_menu_kb(user_id))
        return


# ============================================================
# دستورها
# ============================================================

def _register_handlers():
    @bot.message_handler(commands=["رستوران", "restaurant"])
    def _cmd_restaurant(message):
        ensure_user(message.from_user.id, message.from_user.username or message.from_user.first_name or "")
        bot.reply_to(message, _status_text(message.from_user.id), reply_markup=_main_menu_kb(message.from_user.id))

    @bot.message_handler(commands=["دستورپخت", "recipes"])
    def _cmd_recipes(message):
        ensure_user(message.from_user.id, message.from_user.username or message.from_user.first_name or "")
        bot.reply_to(message, _recipe_book_text(message.from_user.id))

    @bot.message_handler(commands=["ارتقا_رستوران"])
    def _cmd_upgrade(message):
        ensure_user(message.from_user.id, message.from_user.username or message.from_user.first_name or "")
        ok, msg = do_upgrade(message.from_user.id)
        bot.reply_to(message, msg)

    @bot.message_handler(commands=["باز_رستوران", "openrestaurant"])
    def _cmd_open(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        ensure_user(user_id, message.from_user.username or message.from_user.first_name or "")
        with _state_lock:
            if user_id in _active_orders:
                bot.reply_to(message, "الان وسط یه شیفتی! اول سفارش فعلی رو تموم کن.")
                return
            state = _get_state(user_id)
            _active_orders[user_id] = dict(
                chat_id=chat_id,
                orders_left=orders_per_shift(state["upgrades"]),
                shift_earned=0,
                timer=None,
            )
        bot.reply_to(message, "🍽️ مغازه باز شد! مشتری اول داره میاد...")
        _send_next_customer(user_id, chat_id)

    @bot.message_handler(commands=["بستن_رستوران", "closerestaurant"])
    def _cmd_close(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        with _state_lock:
            session = _active_orders.get(user_id)
            if not session:
                bot.reply_to(message, "شیفت بازی نداری.")
                return
        _end_shift(user_id, chat_id)

    @bot.message_handler(func=_has_active_order)
    def _reply_order(message):
        _handle_order_reply(message)
