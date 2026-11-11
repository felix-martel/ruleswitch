"""ruleswitch: behavior policies as code.

A policy classifies a user's turn on its turn axes; its tiers, tried in order, prescribe the values a response may take
on each response axis; a response complies when it takes allowed values and breaches no prohibition.
"""

from ruleswitch.lexicon import Lexicon, match
from ruleswitch.policy import Policy, load
from ruleswitch.render import nudge, render
from ruleswitch.rules import comply, prescribe
from ruleswitch.types import Article, Breach, Classification, Compliance, Hit, Message, Prescription, Problem

__all__ = [
    "Article",
    "Breach",
    "Classification",
    "Compliance",
    "Hit",
    "Lexicon",
    "Message",
    "Policy",
    "Prescription",
    "Problem",
    "comply",
    "load",
    "match",
    "nudge",
    "prescribe",
    "render",
]
