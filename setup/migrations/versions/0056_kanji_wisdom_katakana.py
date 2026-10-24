"""Rewrite the seeded kanji_wisdom quotes in katakana

The daily wisdom quote is now shown in katakana rather than kanji. Rewrites the 30 seeded rows
in place (keeping ids, so the day rotation does not shift); rows edited or added through
/api/kanji, and rows already in katakana, are left alone.

Revision ID: 0056
Revises: 0055
Create Date: 2026-10-24
"""

import logging

from alembic import op

from run_sql import table_exists

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.migration")

# Seeded kanji phrase -> katakana (mirrors the Deck's built-in list, KanjiWisdom.kt).
_KATAKANA = (
    ("独り占め", "ヒトリジメ"),
    ("七転八起", "ナナコロビヤオキ"),
    ("一期一会", "イチゴイチエ"),
    ("猿も木から落ちる", "サルモキカラオチル"),
    ("石の上にも三年", "イシノウエニモサンネン"),
    ("継続は力なり", "ケイゾクワチカラナリ"),
    ("初心忘るべからず", "ショシンワスルベカラズ"),
    ("急がば回れ", "イソガバマワレ"),
    ("十人十色", "ジュウニントイロ"),
    ("以心伝心", "イシンデンシン"),
    ("温故知新", "オンコチシン"),
    ("自業自得", "ジゴウジトク"),
    ("一石二鳥", "イッセキニチョウ"),
    ("臥薪嘗胆", "ガシンショウタン"),
    ("不撓不屈", "フトウフクツ"),
    ("百聞は一見に如かず", "ヒャクブンワイッケンニシカズ"),
    ("塵も積もれば山となる", "チリモツモレバヤマトナル"),
    ("時は金なり", "トキワカネナリ"),
    ("雨降って地固まる", "アメフッテジカタマル"),
    ("沈黙は金", "チンモクワキン"),
    ("明鏡止水", "メイキョウシスイ"),
    ("縁の下の力持ち", "エンノシタノチカラモチ"),
    ("光陰矢の如し", "コウインヤノゴトシ"),
    ("千里の道も一歩から", "センリノミチモイッポカラ"),
    ("木漏れ日", "コモレビ"),
    ("侘寂", "ワビサビ"),
    ("初志貫徹", "ショシカンテツ"),
    ("守破離", "シュハリ"),
    ("一日一善", "イチニチイチゼン"),
    ("花鳥風月", "カチョウフウゲツ"),
)


def upgrade():
    if not table_exists(op, "kanji_wisdom"):
        return
    for kanji, katakana in _KATAKANA:
        op.execute(
            "UPDATE `kanji_wisdom` SET `kanji` = '%s' WHERE `kanji` = '%s';" % (katakana, kanji)
        )


def downgrade():
    if not table_exists(op, "kanji_wisdom"):
        return
    for kanji, katakana in _KATAKANA:
        op.execute(
            "UPDATE `kanji_wisdom` SET `kanji` = '%s' WHERE `kanji` = '%s';" % (kanji, katakana)
        )
