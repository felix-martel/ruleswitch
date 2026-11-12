"""The editor behind `ruleswitch serve`: a stdlib web server over one profile, and one static page.

The page edits the policy's YAML files and shows what they make: each tier's grid, where a cell opens a form that
rewrites it in `profile.yaml` through yamlrocks' round trip, the `document` rendering, the static problems, the changes
against git `HEAD`, and a try panel that classifies a turn and a response and shows the prescription, the nudge and the
compliance. Every view runs on the page's unsaved text; saving writes the files in place, and git is the versioning.
It binds to localhost and has no auth.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
from collections.abc import Callable, Mapping
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files as package_files
from pathlib import Path
from typing import Any, Literal

import yamlrocks

from ruleswitch.check import check
from ruleswitch.diff import diff
from ruleswitch.lexicon import match
from ruleswitch.policy import PROFILE, STRUCTURE, Policy, PolicyError, load
from ruleswitch.render import nudge, template
from ruleswitch.rules import comply, prescribe
from ruleswitch.types import Classification, Classifier, Message


class _Workspace:
    """The policy's files on disk, and the policy they make with the page's unsaved text over them.

    Unsaved text is loaded from a mirror of the policy's folder, which the lock guards: a `Policy` reads its templates
    and generated files from its folder.
    """

    def __init__(self, path: Path, classifier: Callable[[Policy], Classifier] | None):
        policy = load(path)
        profile_dir = path.resolve()
        self.base = Path(os.path.commonpath([policy.root, profile_dir]))
        self.profile = profile_dir.relative_to(self.base)
        names = [policy.root / STRUCTURE, profile_dir / PROFILE, *sorted(profile_dir.glob("lexicons/*.yaml"))]
        self.names = [str(p.relative_to(self.base)) for p in names]
        self.classifier = classifier
        self.mirror = Path(tempfile.mkdtemp(prefix="ruleswitch-editor-")) / self.base.name
        self.lock = threading.Lock()
        self.head: tuple[str, Policy] | None = None

    def files(self) -> dict[str, str]:
        return {name: (self.base / name).read_text() for name in self.names}

    def _texts(self, texts: Mapping[str, str]) -> dict[str, str]:
        if unknown := [name for name in texts if name not in self.names]:
            raise ValueError(f"not a file of this policy: {', '.join(unknown)}")
        return dict(texts)

    def save(self, texts: Mapping[str, str]) -> None:
        for name, text in self._texts(texts).items():
            (self.base / name).write_text(text)

    def load(self, texts: Mapping[str, str]) -> Policy:
        """The policy with `texts` over the files on disk. Call it with the lock held."""
        texts = self._texts(texts)
        shutil.copytree(self.base, self.mirror, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".*", "__pycache__"))
        for name, text in texts.items():
            (self.mirror / name).write_text(text)
        return load(self.mirror / self.profile)

    def changes(self, policy: Policy) -> str:
        """What changed from git `HEAD`, article by article."""
        try:
            sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.base, text=True).strip()
            if self.head is None or self.head[0] != sha:
                self.head = sha, load(self.base / self.profile, revision=sha)
        except (subprocess.CalledProcessError, OSError, PolicyError):
            return "no version at git HEAD to compare with"
        return str(diff(self.head[1], policy))

    def view(self, texts: Mapping[str, str]) -> dict[str, Any]:
        with self.lock:
            try:
                policy = self.load(texts)
            except PolicyError as error:
                return {"problems": [str(p) for p in error.problems]}
            return {
                "problems": [str(p) for p in check(policy)],
                "policy": _outline(policy),
                "document": template(policy, "document.j2", note=False),
                "changes": self.changes(policy),
            }

    def set_cell(self, texts: Mapping[str, str], tier: str, position: list[str], allowed: dict[str, list[str]]) -> str:
        """`profile.yaml` with one cell's allowed values replaced; an axis with no value allows any."""
        name = str(self.profile / PROFILE)
        doc = yamlrocks.loads(texts.get(name) or (self.base / name).read_text(), option=yamlrocks.OPT_ROUND_TRIP)
        parent = doc["tiers"][tier]["cells"]
        for value in position[:-1]:
            parent = parent[value]
        if parent[position[-1]] is None:
            parent[position[-1]] = {}
        cell = parent[position[-1]]
        for axis, values in allowed.items():
            if values:
                cell[axis] = values
            elif axis in cell:
                del cell[axis]
        return yamlrocks.dumps(doc, option=yamlrocks.OPT_ROUND_TRIP).decode()

    def attempt(self, texts: Mapping[str, str], request: dict[str, Any]) -> dict[str, Any]:
        """Read a turn and maybe a response: classified from their text, or from the values the page sets."""
        turn_text, response_text = request.get("turn", ""), request.get("response", "")
        with self.lock:
            policy = self.load(texts)
            classifier = self.classifier(policy) if self.classifier else None
        hits = match(policy.lexicons, turn_text)
        convo = [Message("user", turn_text)]

        async def read(of: Literal["turn", "response"], values: dict[str, Any] | None) -> Classification:
            if values is not None:
                return Classification({k: frozenset(v) if isinstance(v, list) else v for k, v in values.items()})
            if classifier is None:
                raise ValueError("no classifier: set the values, or start `ruleswitch serve` with --classifier")
            if of == "turn":
                return await classifier.classify(convo, "turn", hits)
            return await classifier.classify([*convo, Message("assistant", response_text)], "response")

        async def both() -> tuple[Classification, Classification | None]:
            turn = read("turn", request.get("turn_values"))
            if request.get("response_values") is None and not response_text:
                return await turn, None
            return await asyncio.gather(turn, read("response", request.get("response_values")))

        turn, response = asyncio.run(both())
        with self.lock:
            note = nudge(policy, turn, hits)
        prescription = prescribe(policy, turn)
        return {
            "turn": _classification(turn),
            "hits": [{"text": h.text, "meaning": h.entry.meaning, "reminds": h.reminds} for h in hits],
            "prescription": prescription and asdict(prescription),
            "nudge": note,
            "response": response and _classification(response),
            "compliance": response and asdict(comply(policy, turn, response)),
        }


def _classification(c: Classification) -> dict[str, Any]:
    values = {k: sorted(v) if isinstance(v, frozenset) else v for k, v in c.values.items()}
    return {**asdict(c), "values": values}


def _outline(policy: Policy) -> dict[str, Any]:
    """What the page needs to draw the grids, the try panel's choices, and the previews of every id."""

    def axes(side: Mapping[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "id": a.id,
                "multi": a.multi,
                "definition": a.definition,
                "values": [
                    {"id": v.id, "label": v.label, "definition": v.definition, "default": v.default} for v in a.values
                ],
            }
            for a in side.values()
        ]

    return {
        "name": f"{policy.root.name} · {policy.name}",
        "turn_axes": axes(policy.turn_axes),
        "response_axes": axes(policy.response_axes),
        "tiers": [
            {
                "id": t.id,
                "label": t.label,
                "definition": t.definition,
                "instruction": t.instruction,
                "condition": t.condition,
                "cells": {c.id: c.allowed for c in t.cells.values()},
            }
            for t in policy.tiers.values()
        ],
        "prohibitions": [{"id": p.id, "text": p.text} for p in policy.prohibitions.values()],
    }


def _handler(workspace: _Workspace) -> type[BaseHTTPRequestHandler]:
    page = package_files("ruleswitch").joinpath("editor.html").read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: bytes, kind: str = "application/json") -> None:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path == "/":
                self._send(200, page, "text/html; charset=utf-8")
            elif self.path == "/api/files":
                body = {"files": workspace.files(), "classifier": workspace.classifier is not None}
                self._send(200, json.dumps(body).encode())
            else:
                self._send(404, b"{}")

        def do_POST(self) -> None:
            request = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            texts = request.pop("files", {})
            routes: dict[str, Callable[[], Any]] = {
                "/api/view": lambda: workspace.view(texts),
                "/api/save": lambda: workspace.save(texts),
                "/api/cell": lambda: {"text": workspace.set_cell(texts, **request)},
                "/api/try": lambda: workspace.attempt(texts, request),
            }
            if self.path not in routes:
                return self._send(404, b"{}")
            try:
                self._send(200, json.dumps(routes[self.path](), default=list).encode())
            except Exception as error:  # the page shows any failure, such as a classifier's, next to what caused it
                self._send(400, json.dumps({"error": f"{type(error).__name__}: {error}"}).encode())

        def log_message(self, format: str, *args: Any) -> None:
            pass

    return Handler


def serve(path: str | Path, port: int = 8765, classifier: Callable[[Policy], Classifier] | None = None) -> None:
    """Serve the editor for the profile at `path` on `http://127.0.0.1:{port}`, until interrupted.

    Args:
        path: a profile directory, such as `examples/mallow/profiles/fr`.
        port: the local port.
        classifier: makes the try panel's classifier from the policy being edited. Without it, the try panel reads
            the values set by hand.

    Raises:
        PolicyError: when the profile does not load.
    """
    server = ThreadingHTTPServer(("127.0.0.1", port), _handler(_Workspace(Path(path), classifier)))
    print(f"ruleswitch editor on http://127.0.0.1:{server.server_port}", flush=True)
    if classifier is None:
        print("no --classifier: the try panel takes values set by hand", flush=True)
    with contextlib.suppress(KeyboardInterrupt):
        server.serve_forever()
