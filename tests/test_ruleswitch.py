"""The contract callers rely on, on the two example policies. Kept minimal on purpose."""

import shutil
from pathlib import Path

import pytest

import ruleswitch as rs
from ruleswitch.policy import PolicyError

EXAMPLES = Path(__file__).parents[1] / "examples"
THREE_LAWS = EXAMPLES / "three_laws/profiles/default"
MALLOW = EXAMPLES / "mallow/profiles/fr"


@pytest.mark.parametrize("path", [THREE_LAWS, MALLOW])
def test_examples_load_and_their_generated_files_are_up_to_date(path):
    assert rs.check(rs.load(path)) == []


def test_first_applicable_tier_wins_and_turns_outside_every_condition_fall_through():
    p = rs.load(THREE_LAWS)
    # An order that endangers a human is First Law, not Second.
    assert rs.prescribe(p, {"verb": "ORDER", "danger": "HUMAN"}).cell == "first_law/HUMAN"  # type: ignore[union-attr]
    # An order that endangers only the robot: the robot obeys at its own risk.
    assert rs.prescribe(p, {"verb": "ORDER", "danger": "ROBOT"}).cell == "second_law/ORDER"  # type: ignore[union-attr]
    assert rs.prescribe(p, {"verb": "CHAT", "danger": "NONE"}) is None


def test_comply_cites_the_cell_and_the_prohibition():
    p = rs.load(MALLOW)
    turn = {"verb": "SHARE", "alert": "SEVERE", "exit": "STAY", "theme": "GENERAL"}
    ok = {"handling": ["WELCOME"], "referral": "IMMEDIATE", "follow_up": "SILENT"}
    assert rs.comply(p, turn, ok)
    # A multi-valued axis: every value taken must be allowed, and at least one taken.
    mixed = {**ok, "handling": ["WELCOME", "PLAY_ALONG"]}
    assert [a.id for a in rs.comply(p, turn, mixed).articles] == ["alert/SEVERE/SHARE"]
    assert not rs.comply(p, turn, {**ok, "handling": []})
    breached = rs.comply(p, turn, ok, breaches=["CLAIM_REAL"])
    assert [(a.kind, a.id) for a in breached.articles] == [("prohibition", "CLAIM_REAL")]
    # PLAY carries no alert on its own: the turn falls to the reaction tier, whose GENERAL theme is outside it.
    play = {"handling": ["PLAY_ALONG"], "referral": "NONE", "follow_up": "OFFER"}
    assert rs.comply(p, {**turn, "verb": "PLAY"}, play)


def test_a_missing_cell_does_not_load(tmp_path):
    shutil.copytree(EXAMPLES / "three_laws", tmp_path / "p")
    profile = tmp_path / "p/profiles/default/profile.yaml"
    profile.write_text(profile.read_text().replace("ORDER: {handling: [OBEY]}", "{}"))
    with pytest.raises(PolicyError, match="missing cell ORDER"):
        rs.load(profile.parent)


def test_systemone_tier_threshold_keeps_turns_inside_or_outside_the_condition():
    p = rs.load(MALLOW)
    classifier = rs.SystemOne(p, thresholds={"alert": 0.2, "exit": 0.5})
    # PLAY and NONE are the most probable verb and alert, but the alert question passes its threshold: the turn takes
    # the most probable values inside the alert tier's condition.
    answers = {
        "tier:alert": {"type": "noul", "noul": 0.3},
        "tier:exit": {"type": "noul", "noul": 0.4},
        "alert": {"type": "score", "probabilities": {"0": 0.05, "1": 0.15, "2": 0.1, "3": 0.7}},
        "verb": {"type": "choice", "probabilities": {"PLAY": 0.6, "SHARE": 0.3, "QUERY": 0.1}},
        "theme": {"type": "choice", "probabilities": {"GENERAL": 1.0}},
    }
    turn = classifier.read(answers)  # type: ignore[arg-type]
    assert dict(turn.values) == {"verb": "SHARE", "alert": "SEVERE", "exit": "STAY", "theme": "GENERAL"}
    # Below the threshold, alert takes the most probable value outside the condition, whatever the score says.
    below = classifier.read({**answers, "tier:alert": {"type": "noul", "noul": 0.1}})  # type: ignore[arg-type]
    assert below.values["alert"] == "NONE"
    assert "exit" not in classifier.questions()


def test_lexicon_hits_remind_their_prohibition_in_the_nudge():
    p = rs.load(MALLOW)
    hits = rs.match(p.lexicons, "On invite Macron au château", language="fr")
    assert [(h.text, h.reminds) for h in hits] == [("Macron", "SENSITIVE_FIGURE")]
    nudge = rs.nudge(p, {"verb": "PLAY", "alert": "NONE", "exit": "STAY", "theme": "GENERAL"}, hits)
    assert nudge is not None and "Macron" in nudge
    assert rs.nudge(p, {"verb": "PLAY", "alert": "NONE", "exit": "STAY", "theme": "GENERAL"}) is None


def test_diff_labels_a_loosened_cell(tmp_path):
    shutil.copytree(EXAMPLES / "three_laws", tmp_path / "p")
    profile = tmp_path / "p/profiles/default/profile.yaml"
    profile.write_text(profile.read_text().replace("handling: [OBEY]", "handling: [OBEY, ANSWER]"))
    changes = rs.diff(rs.load(THREE_LAWS), rs.load(profile.parent)).changes
    assert [(c.kind, c.id, c.change) for c in changes] == [("cell", "second_law/ORDER", "loosened")]
