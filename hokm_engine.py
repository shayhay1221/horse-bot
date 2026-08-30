# -*- coding: utf-8 -*-
"""
hokm_engine.py — موتور بازی حکم برای ربات طویله

طراحی: این ماژول کاملاً مستقل از تلگرام است. یک کلاس HokmGame داریم که
تمام state و قوانین بازی رو نگه می‌داره، و متدهایی که هندلرهای تلگرام
(python-telegram-bot) فقط صداشون می‌زنن و نتیجه رو نمایش می‌دن.

این جدایی مهمه چون:
1. تست کردن منطق بازی بدون نیاز به تلگرام راحت‌تره
2. می‌تونی state رو به راحتی به JSON تبدیل کنی و توی Supabase ذخیره کنی
   (دقیقاً مثل کاری که برای پرسیستنس تایمر مسابقه اسب کردی)

--------------------------------------------------------------------
قوانین پیاده‌سازی‌شده (نسخه پایه، رایج‌ترین قوانین حکم ایرانی):
- ۴ بازیکن، ۲ تیم (نفرات روبه‌رو = هم‌تیمی: صندلی ۰و۲ / ۱و۳)
- یک دست کامل = ۱۳ دست‌بازی (trick)؛ هر تیم که اول به ۷ ترick برسه، اون
  "دست" رو می‌بره
- بازیکنی که نوبتشه ابتدا ۵ کارت می‌گیره و حکم (خال برتر) رو انتخاب می‌کنه،
  بعد بقیه کارت‌ها (۸ تای دیگه به همون نفر، ۱۳ تا به بقیه) پخش می‌شه
- باید هم‌خال بازی کنی؛ اگه خال نداری، هر کارتی (از جمله حکم) می‌تونی بزنی
  برنده‌ی دست: بالاترین کارت هم‌خال با خال شروع‌کننده، مگر این‌که حکم
  زده شده باشه که در اون صورت بالاترین حکم برنده است
- برد مسابقه (match): اولین تیمی که به تعداد مشخصی "دست" برسه (پیش‌فرض ۷)
--------------------------------------------------------------------
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional
import random


# ---------------------------------------------------------------------------
# کارت‌ها
# ---------------------------------------------------------------------------

SUITS = ["♠", "♥", "♦", "♣"]  # پیک، دل، خشت، گشنیز
SUIT_NAMES_FA = {"♠": "پیک", "♥": "دل", "♦": "خشت", "♣": "گشنیز"}

RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
RANK_VALUE = {r: i for i, r in enumerate(RANKS)}  # 2 پایین‌ترین، A بالاترین


@dataclass(frozen=True)
class Card:
    suit: str
    rank: str

    def __str__(self) -> str:
        return f"{self.rank}{self.suit}"

    def to_str(self) -> str:
        return f"{self.rank}{self.suit}"

    @staticmethod
    def from_str(s: str) -> "Card":
        # فرمت ذخیره: "10♠", "A♥" و ...
        suit = s[-1]
        rank = s[:-1]
        return Card(suit=suit, rank=rank)

    @property
    def value(self) -> int:
        return RANK_VALUE[self.rank]


def make_deck() -> list[Card]:
    return [Card(s, r) for s in SUITS for r in RANKS]


# ---------------------------------------------------------------------------
# فازهای بازی
# ---------------------------------------------------------------------------

class Phase(str, Enum):
    WAITING_PLAYERS = "waiting_players"
    CHOOSING_HOKM = "choosing_hokm"
    PLAYING = "playing"
    HAND_OVER = "hand_over"      # یک دست (۱۳ ترick) تموم شد
    MATCH_OVER = "match_over"    # کل مسابقه تموم شد


class HokmError(Exception):
    """خطای منطقی بازی — این پیام مستقیم قابل نمایش به کاربره."""
    pass


# ---------------------------------------------------------------------------
# موتور اصلی بازی
# ---------------------------------------------------------------------------

@dataclass
class HokmGame:
    chat_id: int
    players: list[int] = field(default_factory=list)      # 4 user_id، به ترتیب نشستن
    player_names: dict[int, str] = field(default_factory=dict)

    phase: Phase = Phase.WAITING_PLAYERS
    dealer_index: int = 0          # کی این دست دیلر (کارت‌دهنده) است
    hakem_index: Optional[int] = None   # کی حکم رو انتخاب می‌کنه (نفر بعد از دیلر)
    hokm_suit: Optional[str] = None

    hands: dict[int, list[Card]] = field(default_factory=dict)   # user_id -> کارت‌های دستش
    current_trick: list[tuple[int, Card]] = field(default_factory=list)  # [(user_id, card), ...]
    trick_leader_index: int = 0     # ایندکس بازیکنی که این ترick رو شروع کرد
    turn_index: int = 0             # نوبت الان با کیه

    tricks_won: dict[int, int] = field(default_factory=lambda: {0: 0, 1: 0})  # team_id -> تعداد ترick
    hands_won: dict[int, int] = field(default_factory=lambda: {0: 0, 1: 0})   # team_id -> تعداد دست‌های برده‌شده
    target_hands: int = 7           # چند دست ببری، مسابقه رو بردی

    round_history: list[dict] = field(default_factory=list)  # لاگ هر ترick برای نمایش/دیباگ

    # -----------------------------------------------------------------
    # مدیریت بازیکن‌ها
    # -----------------------------------------------------------------

    def add_player(self, user_id: int, name: str) -> None:
        if self.phase != Phase.WAITING_PLAYERS:
            raise HokmError("بازی از قبل شروع شده، الان نمی‌تونی وارد بشی.")
        if user_id in self.players:
            raise HokmError("قبلاً وارد بازی شدی.")
        if len(self.players) >= 4:
            raise HokmError("میز پره (۴ نفر کامله).")
        self.players.append(user_id)
        self.player_names[user_id] = name

    def team_of(self, user_id: int) -> int:
        """صندلی ۰و۲ = تیم ۰، صندلی ۱و۳ = تیم ۱."""
        idx = self.players.index(user_id)
        return idx % 2

    # -----------------------------------------------------------------
    # شروع دست جدید (deal)
    # -----------------------------------------------------------------

    def start_hand(self) -> None:
        if len(self.players) != 4:
            raise HokmError("برای شروع بازی دقیقاً ۴ نفر لازمه.")

        deck = make_deck()
        random.shuffle(deck)

        self.hakem_index = (self.dealer_index + 1) % 4
        hakem_id = self.players[self.hakem_index]

        # مرحله ۱: ۵ کارت اول فقط به حاکم
        self.hands = {p: [] for p in self.players}
        self.hands[hakem_id] = deck[:5]
        self._pending_deck = deck[5:]  # بقیه کارت‌ها برای بعد از انتخاب حکم

        self.hokm_suit = None
        self.current_trick = []
        self.tricks_won = {0: 0, 1: 0}
        self.trick_leader_index = self.hakem_index
        self.turn_index = self.hakem_index
        self.phase = Phase.CHOOSING_HOKM

    def choose_hokm(self, user_id: int, suit: str) -> None:
        if self.phase != Phase.CHOOSING_HOKM:
            raise HokmError("الان وقت انتخاب حکم نیست.")
        if self.players[self.hakem_index] != user_id:
            raise HokmError("فقط حاکم می‌تونه خال حکم رو انتخاب کنه.")
        if suit not in SUITS:
            raise HokmError("خال نامعتبره.")

        self.hokm_suit = suit

        # مرحله ۲: پخش بقیه کارت‌ها — ۸ تا به حاکم، ۱۳ تا به بقیه
        deck = self._pending_deck
        i = 0
        for offset in range(4):
            idx = (self.hakem_index + offset) % 4
            pid = self.players[idx]
            n = 8 if idx == self.hakem_index else 13
            self.hands[pid].extend(deck[i:i + n])
            i += n

        for pid in self.players:
            self.hands[pid].sort(key=lambda c: (c.suit != self.hokm_suit, c.suit, c.value))

        self.phase = Phase.PLAYING

    # -----------------------------------------------------------------
    # بازی کردن کارت
    # -----------------------------------------------------------------

    def legal_cards(self, user_id: int) -> list[Card]:
        """کارت‌های مجازی که این بازیکن الان می‌تونه بزنه."""
        hand = self.hands[user_id]
        if not self.current_trick:
            return hand  # شروع‌کننده هر کارتی می‌تونه بزنه
        lead_suit = self.current_trick[0][1].suit
        same_suit = [c for c in hand if c.suit == lead_suit]
        return same_suit if same_suit else hand

    def play_card(self, user_id: int, card: Card) -> Optional[dict]:
        """
        یک کارت بازی می‌کنه. اگه ترick کامل بشه، نتیجه‌ی ترick رو برمی‌گردونه
        (dict شامل winner_id و team) وگرنه None.
        """
        if self.phase != Phase.PLAYING:
            raise HokmError("الان وقت بازی کردن نیست.")
        if self.players[self.turn_index] != user_id:
            raise HokmError("نوبت تو نیست.")
        if card not in self.hands[user_id]:
            raise HokmError("این کارت رو نداری.")
        if card not in self.legal_cards(user_id):
            lead_suit = self.current_trick[0][1].suit
            raise HokmError(f"باید {SUIT_NAMES_FA[lead_suit]} بزنی (اگه داری).")

        self.hands[user_id].remove(card)
        self.current_trick.append((user_id, card))
        self.turn_index = (self.turn_index + 1) % 4

        if len(self.current_trick) < 4:
            return None

        # ترick کامل شد -> برنده رو مشخص کن
        winner_id = self._resolve_trick()
        winner_team = self.team_of(winner_id)
        self.tricks_won[winner_team] += 1

        result = {
            "winner_id": winner_id,
            "team": winner_team,
            "trick": list(self.current_trick),
            "tricks_won": dict(self.tricks_won),
        }
        self.round_history.append(result)

        # آماده‌سازی ترick بعدی
        self.current_trick = []
        self.trick_leader_index = self.players.index(winner_id)
        self.turn_index = self.trick_leader_index

        # چک کن دست تموم شده یا نه (۷ ترick یا ۱۳ ترick بازی شده)
        if self.tricks_won[winner_team] >= 7 or sum(self.tricks_won.values()) == 13:
            self._end_hand(winner_team if self.tricks_won[winner_team] >= 7 else self._majority_team())

        return result

    def _resolve_trick(self) -> int:
        lead_suit = self.current_trick[0][1].suit
        trump_cards = [(pid, c) for pid, c in self.current_trick if c.suit == self.hokm_suit]
        if trump_cards:
            winner = max(trump_cards, key=lambda pc: pc[1].value)
        else:
            same_suit = [(pid, c) for pid, c in self.current_trick if c.suit == lead_suit]
            winner = max(same_suit, key=lambda pc: pc[1].value)
        return winner[0]

    def _majority_team(self) -> int:
        return 0 if self.tricks_won[0] > self.tricks_won[1] else 1

    def _end_hand(self, winning_team: int) -> None:
        self.hands_won[winning_team] += 1
        self.dealer_index = (self.dealer_index + 1) % 4  # نوبت دیلر می‌چرخه

        if self.hands_won[winning_team] >= self.target_hands:
            self.phase = Phase.MATCH_OVER
        else:
            self.phase = Phase.HAND_OVER  # منتظر دستور شروع دست بعدی

    # -----------------------------------------------------------------
    # سریالایز برای ذخیره توی Supabase (پرسیستنس بین ری‌استارت‌های Render)
    # -----------------------------------------------------------------

    def to_dict(self) -> dict:
        d = asdict(self)
        d["phase"] = self.phase.value
        d["hands"] = {pid: [c.to_str() for c in cards] for pid, cards in self.hands.items()}
        d["current_trick"] = [(pid, c.to_str()) for pid, c in self.current_trick]
        d.pop("round_history", None)  # اختیاری: می‌تونی نگه داری اگه لاگ می‌خوای
        return d

    @staticmethod
    def from_dict(d: dict) -> "HokmGame":
        game = HokmGame(chat_id=d["chat_id"])
        game.players = d["players"]
        game.player_names = {int(k): v for k, v in d["player_names"].items()}
        game.phase = Phase(d["phase"])
        game.dealer_index = d["dealer_index"]
        game.hakem_index = d["hakem_index"]
        game.hokm_suit = d["hokm_suit"]
        game.hands = {int(pid): [Card.from_str(s) for s in cards] for pid, cards in d["hands"].items()}
        game.current_trick = [(pid, Card.from_str(s)) for pid, s in d["current_trick"]]
        game.trick_leader_index = d["trick_leader_index"]
        game.turn_index = d["turn_index"]
        game.tricks_won = {int(k): v for k, v in d["tricks_won"].items()}
        game.hands_won = {int(k): v for k, v in d["hands_won"].items()}
        game.target_hands = d["target_hands"]
        return game


# ---------------------------------------------------------------------------
# مثال استفاده‌ی سریع (بدون تلگرام) — برای تست منطق بازی
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    g = HokmGame(chat_id=1)
    for i, name in enumerate(["امیر", "سارا", "رضا", "مریم"]):
        g.add_player(i, name)

    g.start_hand()
    print("حاکم:", g.player_names[g.players[g.hakem_index]])
    print("۵ کارت حاکم:", [str(c) for c in g.hands[g.players[g.hakem_index]]])

    g.choose_hokm(g.players[g.hakem_index], "♠")
    print("حکم شد: پیک")
    print("کارت‌های امیر:", [str(c) for c in g.hands[g.players[0]]])
