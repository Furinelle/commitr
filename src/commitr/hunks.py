"""Hunk-level diff splitting.

Parse a unified diff into per-file hunks, ask the LLM to group hunks into
independent commits, then synthesize a patch per group that `git apply
--cached` can stage. This unlocks splitting *within* a single file — the
roadmap's #1 differentiator.

Patch format we emit (one per group):

    diff --git a/<path> b/<path>
    --- a/<path>
    +++ b/<path>
    @@ ...
    <hunk body>
    @@ ...
    <hunk body>

This is the canonical `git diff` shape and `git apply --cached --whitespace=nowarn`
accepts it. We only split inside *modify* hunks; pure renames, mode changes,
binary patches, and adds/deletes are kept atomic (whole-file).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import litellm


HUNK_HEADER_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@")
DIFF_HEADER_RE = re.compile(r"^diff --git a/(.+) b/(.+)$")


@dataclass
class Hunk:
    """One @@ … @@ block plus its body lines (including the header line)."""
    text: str
    header: str  # "@@ -1,3 +1,4 @@"
    old_start: int
    new_start: int


@dataclass
class FilePatch:
    """All hunks for one file, plus the file-header preamble."""
    path: str
    preamble: str  # everything before the first hunk: diff --git, ---, +++, mode, etc.
    hunks: list[Hunk] = field(default_factory=list)
    atomic: bool = False  # True for binary / rename / add-delete-only: don't split

    def render(self, hunks: list[Hunk] | None = None) -> str:
        """Render the preamble + selected hunks as a valid patch fragment."""
        chosen = self.hunks if hunks is None else hunks
        if not chosen and not self.atomic:
            return ""
        body = "".join(h.text for h in chosen) if chosen else ""
        return self.preamble + body


@dataclass
class HunkRef:
    """Stable reference to a single hunk: file path + index within that file."""
    path: str
    index: int  # 0-based hunk index within the file


@dataclass
class HunkGroup:
    """Logical commit: one message, a list of hunk references."""
    message: str
    refs: list[HunkRef] = field(default_factory=list)
    rationale: str = ""


def parse_diff(diff: str) -> list[FilePatch]:
    """Split a unified `git diff` into per-file FilePatch objects.

    Robust to common git diff variants: mode changes, renames (handled as
    atomic — no hunks to split), binary patches, new files, deleted files.
    """
    if not diff.strip():
        return []
    files: list[FilePatch] = []
    current: FilePatch | None = None
    current_preamble: list[str] = []
    current_hunks: list[Hunk] = []
    current_hunk_lines: list[str] = []
    in_hunk = False
    atomic_marker = False

    def flush_hunk() -> None:
        nonlocal current_hunk_lines, in_hunk
        if current_hunk_lines:
            text = "".join(current_hunk_lines)
            header_line = current_hunk_lines[0]
            old_start, new_start = _parse_hunk_header(header_line)
            current_hunks.append(Hunk(
                text=text, header=header_line.rstrip("\n"),
                old_start=old_start, new_start=new_start,
            ))
        current_hunk_lines = []
        in_hunk = False

    def flush_file() -> None:
        nonlocal current, current_preamble, current_hunks, atomic_marker
        if current is not None:
            flush_hunk()
            current.preamble = "".join(current_preamble)
            current.hunks = current_hunks
            current.atomic = atomic_marker or not current_hunks
            files.append(current)
        current = None
        current_preamble = []
        current_hunks = []
        atomic_marker = False

    for raw_line in diff.splitlines(keepends=True):
        if raw_line.startswith("diff --git "):
            flush_file()
            match = DIFF_HEADER_RE.match(raw_line.rstrip("\n"))
            path = match.group(2) if match else "unknown"
            current = FilePatch(path=path, preamble="")
            current_preamble = [raw_line]
            continue
        if current is None:
            # Stray content before any diff header. Skip.
            continue
        if raw_line.startswith("@@ "):
            flush_hunk()
            in_hunk = True
            current_hunk_lines = [raw_line]
            continue
        if in_hunk:
            current_hunk_lines.append(raw_line)
            continue
        # File-level preamble lines.
        current_preamble.append(raw_line)
        if raw_line.startswith("Binary files ") or raw_line.startswith("GIT binary patch"):
            atomic_marker = True
        if raw_line.startswith("rename from ") or raw_line.startswith("rename to "):
            atomic_marker = True
        if raw_line.startswith("similarity index "):
            atomic_marker = True

    flush_file()
    return files


def _parse_hunk_header(line: str) -> tuple[int, int]:
    """Pull old_start and new_start from a `@@ -a,b +c,d @@` line."""
    m = re.match(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
    if not m:
        return (0, 0)
    return (int(m.group(1)), int(m.group(2)))


def summarize_for_llm(file_patches: list[FilePatch], max_chars_per_hunk: int = 400) -> str:
    """Render a compact view of every hunk so the LLM can group them.

    We give each hunk a stable ID like `path#0`, `path#1`. The model returns
    the IDs in groups; we resolve them back to FilePatch objects to stage.
    """
    lines: list[str] = []
    for fp in file_patches:
        if fp.atomic or not fp.hunks:
            lines.append(f"\n## File: {fp.path}  (atomic — must commit whole)")
            continue
        lines.append(f"\n## File: {fp.path}")
        for i, h in enumerate(fp.hunks):
            preview = h.text
            if len(preview) > max_chars_per_hunk:
                preview = preview[:max_chars_per_hunk] + "\n... [truncated]\n"
            lines.append(f"\n### Hunk {fp.path}#{i}  ({h.header})")
            lines.append(preview.rstrip())
    return "\n".join(lines).strip()


def parse_groups_response(raw: str, file_patches: list[FilePatch]) -> list[HunkGroup]:
    """Parse the LLM's JSON response into HunkGroup objects.

    Expected JSON shape:
        {"groups": [{"message": "...", "hunks": ["path#0", "path#2"], "rationale": "..."}, ...]}
    """
    s = raw.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```\s*$", "", s)
    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", s, re.DOTALL)
        if not match:
            return []
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return []

    by_path = {fp.path: fp for fp in file_patches}
    seen: set[tuple[str, int]] = set()
    groups: list[HunkGroup] = []
    for g in data.get("groups", []) or []:
        if not isinstance(g, dict):
            continue
        refs: list[HunkRef] = []
        for raw_ref in g.get("hunks", []) or []:
            if not isinstance(raw_ref, str) or "#" not in raw_ref:
                continue
            path, _, idx_str = raw_ref.rpartition("#")
            try:
                idx = int(idx_str)
            except ValueError:
                continue
            fp = by_path.get(path)
            if not fp or idx < 0 or idx >= len(fp.hunks):
                continue
            key = (path, idx)
            if key in seen:
                continue
            seen.add(key)
            refs.append(HunkRef(path=path, index=idx))
        if not refs:
            continue
        groups.append(HunkGroup(
            message=(g.get("message") or "").strip(),
            refs=refs,
            rationale=(g.get("rationale") or "").strip(),
        ))

    # Coverage: any hunk not assigned goes into a catch-all group.
    missing: list[HunkRef] = []
    for fp in file_patches:
        if fp.atomic:
            # Atomic files are pinned to whichever group already claimed any
            # hunk of theirs; if none did, put them all in the catch-all.
            already = any(ref.path == fp.path for g in groups for ref in g.refs)
            if not already:
                missing.append(HunkRef(path=fp.path, index=0))
            continue
        for i in range(len(fp.hunks)):
            if (fp.path, i) not in seen:
                missing.append(HunkRef(path=fp.path, index=i))
    if missing:
        groups.append(HunkGroup(
            message="", refs=missing,
            rationale="(hunks not assigned by the model)",
        ))
    return groups


HUNK_SPLIT_SYSTEM_PROMPT = """You analyze a unified git diff broken into HUNK-level chunks
and group those hunks into independent logical commits.

Rules:
- Each hunk has an ID like `path/to/file.py#0`. Use those IDs verbatim.
- A hunk belongs to EXACTLY one group. Don't repeat hunk IDs across groups.
- Group hunks that work together (same feature, same bug). Split clearly
  independent concerns (e.g. unrelated bugfix + docs typo + new feature).
- Files marked "atomic" must keep ALL their hunks in one group.
- Commit messages must match the project's existing style (see samples).

Output STRICT JSON only. No prose, no code fences. Schema:

{
  "groups": [
    {
      "message": "<full commit message — subject + optional body>",
      "hunks": ["path/a.py#0", "path/a.py#2", "path/b.py#0"],
      "rationale": "<one-sentence why these belong together>"
    }
  ]
}

If everything is one coherent change, return a single group with every hunk."""


HUNK_SPLIT_USER_TEMPLATE = """Recent commit subjects (style scan):
{subjects}

Full sample commits from this repo:
{samples}

Hunks to group:
{hunks_view}

Return the JSON now."""


def analyze_hunk_splits(
    file_patches: list[FilePatch],
    subjects: list[str],
    samples: list[str],
    model: str,
) -> list[HunkGroup]:
    """Ask the LLM to assign hunks to groups. Returns at least one group.

    On parse failure / empty response, returns one catch-all group with an
    empty message — caller falls back to the normal flow.
    """
    if not file_patches:
        return []
    hunks_view = summarize_for_llm(file_patches)
    user = HUNK_SPLIT_USER_TEMPLATE.format(
        subjects="\n".join(f"- {s}" for s in subjects) or "(none)",
        samples="\n\n---\n\n".join(samples) or "(none)",
        hunks_view=hunks_view,
    )
    messages = [
        {"role": "system", "content": HUNK_SPLIT_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]
    try:
        response = litellm.completion(
            model=model, messages=messages,
            temperature=0.1, max_tokens=2500,
            response_format={"type": "json_object"},
        )
    except Exception:
        response = litellm.completion(
            model=model, messages=messages,
            temperature=0.1, max_tokens=2500,
        )
    raw = response.choices[0].message.content or ""
    groups = parse_groups_response(raw, file_patches)
    if not groups:
        # Final fallback: one group with every hunk and empty message.
        all_refs: list[HunkRef] = []
        for fp in file_patches:
            if fp.atomic:
                all_refs.append(HunkRef(path=fp.path, index=0))
            else:
                all_refs.extend(HunkRef(path=fp.path, index=i) for i in range(len(fp.hunks)))
        return [HunkGroup(message="", refs=all_refs, rationale="(parse failure)")]
    return groups


def render_patch_for_group(group: HunkGroup, file_patches: list[FilePatch]) -> str:
    """Build a valid `git apply`-able patch covering only this group's hunks.

    Hunks from the same file are concatenated under one diff header. Hunks
    within a file are emitted in their original order (matters for offsets).
    """
    by_path: dict[str, list[int]] = {}
    for ref in group.refs:
        by_path.setdefault(ref.path, []).append(ref.index)

    patches: list[str] = []
    for fp in file_patches:
        indices = by_path.get(fp.path)
        if indices is None:
            continue
        if fp.atomic:
            patches.append(fp.preamble + "".join(h.text for h in fp.hunks))
            continue
        chosen = [fp.hunks[i] for i in sorted(set(indices)) if 0 <= i < len(fp.hunks)]
        if not chosen:
            continue
        patches.append(fp.preamble + "".join(h.text for h in chosen))
    return "".join(patches)
