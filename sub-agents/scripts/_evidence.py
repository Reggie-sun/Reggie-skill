from __future__ import annotations

from pathlib import Path


def normalize_required_evidence_paths(
    cwd: str,
    paths: list[str] | tuple[str, ...],
) -> tuple[str, ...]:
    """Validate evidence files and return stable paths relative to ``cwd``."""
    root = Path(cwd).resolve()
    normalized: list[str] = []
    seen: set[str] = set()

    for raw_path in paths:
        if (
            not isinstance(raw_path, str)
            or not raw_path.strip()
            or raw_path.startswith("~")
            or any(ord(character) < 32 for character in raw_path)
        ):
            raise ValueError(
                f"Invalid required evidence path {raw_path!r}: use a non-empty "
                "regular file path inside --cwd."
            )
        supplied = Path(raw_path)
        candidate = supplied if supplied.is_absolute() else root / supplied
        if candidate.is_symlink():
            raise ValueError(
                f"Required evidence path {raw_path!r} must not be a symlink."
            )
        resolved = candidate.resolve()
        if not resolved.is_relative_to(root):
            raise ValueError(
                f"Required evidence path {raw_path!r} resolves outside --cwd."
            )
        if not resolved.is_file():
            raise ValueError(
                f"Required evidence path {raw_path!r} must be an existing regular file."
            )
        relative = resolved.relative_to(root).as_posix()
        if relative not in seen:
            seen.add(relative)
            normalized.append(relative)

    return tuple(normalized)
