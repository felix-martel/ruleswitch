"""The `ruleswitch` command: create, check, generate, render, diff and evaluate policies, and serve the editor.

POLICY is a profile directory, such as `examples/mallow/profiles/fr`. The built-in classifiers read their endpoint and
key from the environment: `RULESWITCH_SYSTEMONE_URL` and `RULESWITCH_SYSTEMONE_KEY`, or `RULESWITCH_LLM_URL` and
`RULESWITCH_LLM_KEY`.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
import shutil
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from ruleswitch.check import check
from ruleswitch.diff import diff
from ruleswitch.editor import serve
from ruleswitch.evaluate import Dataset, evaluate
from ruleswitch.generate import generate
from ruleswitch.judge import Judge, openai_compatible
from ruleswitch.policy import Policy, PolicyError, load
from ruleswitch.render import render
from ruleswitch.systemone import SystemOne
from ruleswitch.types import Classifier

TOYS = ("three_laws", "rbr")


def _init(name: str, toy: str) -> int:
    """Copy a toy policy to the new directory `name`. The toys ship in the package, or sit in a checkout's examples."""
    here = Path(__file__).parent
    source = next(p for root in (here / "examples", here.parents[1] / "examples") if (p := root / toy).is_dir())
    try:
        shutil.copytree(source, name, ignore=shutil.ignore_patterns("__pycache__"))
    except FileExistsError:
        print(f"{name} already exists", file=sys.stderr)
        return 1
    profile = Path(name, "profiles", "default")
    print(f"wrote {name}, a copy of the {toy} policy. Edit its structure.yaml and {profile / 'profile.yaml'}, then:")
    print(f"  ruleswitch check {profile}")
    return 0


def _load_at(spec: str) -> Policy:
    """A profile directory, or `DIR@REV` for the same directory at a git revision, such as `profiles/fr@HEAD~1`."""
    if "@" not in spec:
        return load(spec)
    path, revision = spec.rsplit("@", 1)
    return load(path, revision=revision)


def _classifier(spec: str, thresholds: dict[str, float]) -> Callable[[Policy], Classifier]:
    """`systemone[:MODEL]`, `judge:MODEL`, or `module:attr`, a factory taking the policy."""
    kind, _, model = spec.partition(":")
    needed = {
        "systemone": ("RULESWITCH_SYSTEMONE_URL", "RULESWITCH_SYSTEMONE_KEY"),
        "judge": ("RULESWITCH_LLM_URL", "RULESWITCH_LLM_KEY"),
    }.get(kind, ())
    if missing := [name for name in needed if name not in os.environ]:
        raise SystemExit(f"--classifier {kind} needs {' and '.join(missing)} in the environment")
    if kind == "systemone":
        url, key = os.environ["RULESWITCH_SYSTEMONE_URL"], os.environ["RULESWITCH_SYSTEMONE_KEY"]
        return lambda p: SystemOne(p, url, key, model or None, thresholds=thresholds, breach=0.5)
    if kind == "judge":
        url, key = os.environ["RULESWITCH_LLM_URL"], os.environ["RULESWITCH_LLM_KEY"]
        return lambda p: Judge(p, openai_compatible(url, key, model))
    return getattr(importlib.import_module(kind), model)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ruleswitch", description=(__doc__ or "").split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    i = commands.add_parser("init", help="a new policy, copied from a toy policy")
    i.add_argument("name", help="the directory to create")
    i.add_argument("--from", dest="toy", choices=TOYS, default=TOYS[0])
    commands.add_parser("check", help="static checks; exit 1 on any problem").add_argument("policy")
    commands.add_parser(
        "generate", help="profile.schema.json and structure_types.py, from structure.yaml"
    ).add_argument("policy")
    r = commands.add_parser("render", help="the policy as text")
    r.add_argument("policy")
    r.add_argument("--rendering", choices=["document", "prompt", "judge"], default="document")
    r.add_argument("-o", "--output", help="a file, stdout by default")
    d = commands.add_parser("diff", help="what changed between two versions; DIR@REV reads a git revision")
    d.add_argument("old")
    d.add_argument("new")
    e = commands.add_parser("eval", help="a classifier on a dataset, the policy's own examples by default")
    e.add_argument("policy")
    e.add_argument("--data", help="a JSONL dataset")
    e.add_argument("--classifier", required=True, help="systemone[:MODEL], judge:MODEL or module:attr")
    e.add_argument("--json", action="store_true", help="the agreement per label as JSON")
    v = commands.add_parser("serve", help="the editor, on localhost")
    v.add_argument("policy")
    v.add_argument("--port", type=int, default=8765)
    v.add_argument("--classifier", help="the try panel's: systemone[:MODEL], judge:MODEL or module:attr")
    for command in (e, v):
        command.add_argument("--threshold", action="append", default=[], metavar="TIER=P", help="SystemOne tiers")
    args = parser.parse_args(argv)

    if args.command == "init":
        return _init(args.name, args.toy)
    thresholds = {t: float(p) for t, p in (t.split("=") for t in getattr(args, "threshold", []))}
    try:
        if args.command == "diff":
            print(diff(_load_at(args.old), _load_at(args.new)))
            return 0
        if args.command == "serve":
            serve(args.policy, args.port, args.classifier and _classifier(args.classifier, thresholds))
            return 0
        policy = load(args.policy)
    except PolicyError as error:
        print(error, file=sys.stderr)
        return 1
    if args.command == "check":
        problems = check(policy)
        for problem in problems:
            print(problem)
        return 1 if problems else 0
    if args.command == "generate":
        for name in generate(policy):
            print(f"wrote {policy.root / name}")
        return 0
    if args.command == "render":
        text = render(policy, args.rendering)
        if args.output:
            Path(args.output).write_text(text)
        else:
            print(text, end="")
        return 0
    data = Dataset.load(args.data) if args.data else Dataset.from_policy(policy)
    report = asyncio.run(evaluate(policy, data, _classifier(args.classifier, thresholds)(policy)))
    print(json.dumps(report.agreement()) if args.json else report.markdown(), end="")
    return 0 if all(r.ok for r in report.results) else 1


if __name__ == "__main__":
    sys.exit(main())
