"""Replace the dangling legacy Bedtime quips with complete good-night lines

The three seeded 'bedtime' quips were sentence prefixes ("Unless we are burning the midnight oil, ")
left over from an older two-part design. Spoken on their own, the speak service's LLM was asked to
rephrase a fragment and invented an unrelated line ("...maintaining a reasonable schedule, I
presume") instead of a good night. These are complete, warm-but-slightly-odd replacements.

Revision ID: 0047
Revises: 0046
Create Date: 2026-10-07
"""

import logging

import sqlalchemy as sa
from alembic import op

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.migration")

_LEGACY = (
    "Unless we are burning the midnight oil, ",
    "If you are going to invent something new tomorrow, ",
    "If you intend on being charming tomorrow",
)

_NEW = (
    "Unless you are burning the midnight oil, it is time for bed. Good night, everyone.",
    "Good night. Go and rest; tomorrow's inventions will keep until morning.",
    "Sleep well. Tomorrow you will be charming, and I will pretend to be surprised.",
    "Good night, everyone. I shall guard the thermostat with my life.",
    "Sleep well. The house and I will compare notes on your snoring in the morning.",
    "Good night. Should anything go bump, I am fairly sure it is the dishwasher.",
    "Rest now. Tomorrow's problems have been filed under tomorrow.",
    "Sweet dreams, all of you. I will keep the lights low and my opinions lower.",
)


def upgrade():
    bind = op.get_bind()
    for text in _LEGACY:
        bind.execute(
            sa.text("DELETE FROM quips WHERE type = 'bedtime' AND quips = :q"), {"q": text}
        )
    for text in _NEW:
        bind.execute(
            sa.text(
                "INSERT INTO quips (type, quips) SELECT 'bedtime', :q FROM DUAL "
                "WHERE NOT EXISTS (SELECT 1 FROM quips WHERE type = 'bedtime' AND quips = :q)"
            ),
            {"q": text},
        )


def downgrade():
    bind = op.get_bind()
    for text in _NEW:
        bind.execute(
            sa.text("DELETE FROM quips WHERE type = 'bedtime' AND quips = :q"), {"q": text}
        )
    for text in _LEGACY:
        bind.execute(sa.text("INSERT INTO quips (type, quips) VALUES ('bedtime', :q)"), {"q": text})
