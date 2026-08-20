from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence


LONG_GAP_SECONDS = 60
READ_HEAVY_MIN_READS = 15
READ_HEAVY_RATIO = 5.0
EXPLORER_MISMATCH_TOOLS = frozenset(
    {
        "tool:Bash",
        "tool:Edit",
        "tool:EnterPlanMode",
        "tool:ExitPlanMode",
        "tool:NotebookEdit",
        "tool:Write",
    }
)


@dataclass(frozen=True)
class DiagnosticSignal:
    name: str
    count: int
    detail: str


def analyze_signals(
    invocations: Iterable[tuple[str, bool]],
    activities: Sequence[tuple[str, int, str]],
    terminals: Sequence[tuple[str, int, int]],
) -> tuple[DiagnosticSignal, ...]:
    events = Counter(event for _, _, event in activities)
    signals: list[DiagnosticSignal] = []

    tool_errors = events.get("tool_result:error", 0)
    if tool_errors:
        signals.append(
            DiagnosticSignal("tool_error_event", tool_errors, "provider tool errors")
        )

    invocation_rows = tuple(invocations)
    agents = tuple(agent for agent, _ in invocation_rows)
    mismatch_count = sum(events.get(tool, 0) for tool in EXPLORER_MISMATCH_TOOLS)
    if agents and all(agent == "explorer" for agent in agents) and mismatch_count:
        signals.append(
            DiagnosticSignal(
                "explorer_tool_mismatch",
                mismatch_count,
                "read-only explorer requested shell or mutating tools",
            )
        )

    elapsed_by_session: dict[str, list[int]] = defaultdict(list)
    for session, elapsed, _ in activities:
        elapsed_by_session[session].append(elapsed)
    gaps = [
        current - previous
        for elapsed_values in elapsed_by_session.values()
        for previous, current in zip(elapsed_values, elapsed_values[1:])
        if current - previous >= LONG_GAP_SECONDS
    ]
    if gaps:
        signals.append(
            DiagnosticSignal(
                "long_activity_gap",
                len(gaps),
                f"max_gap_seconds={max(gaps)}",
            )
        )

    dialogue_only = bool(invocation_rows) and all(
        dialogue for _, dialogue in invocation_rows
    )
    zero_evidence = sum(
        1
        for agent_status, evidence_count, _ in terminals
        if dialogue_only
        and agent_status in {"DONE", "DONE_WITH_CONCERNS"}
        and evidence_count == 0
    )
    if zero_evidence:
        signals.append(
            DiagnosticSignal(
                "zero_terminal_evidence",
                zero_evidence,
                "completed terminal reported no observed evidence paths",
            )
        )

    reads = events.get("tool:Read", 0)
    greps = events.get("tool:Grep", 0)
    ratio = reads / max(greps, 1)
    if reads >= READ_HEAVY_MIN_READS and ratio >= READ_HEAVY_RATIO:
        signals.append(
            DiagnosticSignal(
                "read_heavy_exploration",
                1,
                f"read={reads}, grep={greps}, ratio={ratio:.1f}",
            )
        )

    return tuple(signals)


def optimization_leads(signals: Iterable[DiagnosticSignal]) -> tuple[str, ...]:
    lead_by_signal: Mapping[str, str] = {
        "tool_error_event": "Inspect the failed tool class and whether the role should see it.",
        "explorer_tool_mismatch": "Inspect explorer tool-surface enforcement; do not grant a tool solely because it was requested.",
        "long_activity_gap": "Distinguish normal reasoning or StructuredOutput pauses from real stagnation before tuning timeouts.",
        "zero_terminal_evidence": "Inspect whether file-level evidence was required before changing grants or prompts.",
        "read_heavy_exploration": "Compare search-first prompting and evidence quality before changing explorer routing.",
        "external_session_prefix_canonicalized": "Inspect transport chunk boundaries when external session IDs arrive truncated.",
    }
    return tuple(
        lead_by_signal[signal.name]
        for signal in signals
        if signal.name in lead_by_signal
    )


def stable_fingerprint(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]
