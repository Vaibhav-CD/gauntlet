"""
Workspace State Manager: Single Source of Truth
Maintains centralized workspace state snapshot, open file buffers,
disk synchronization, block replacements, unified diffs, and rollback history.
"""

import os
import difflib
import hashlib
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path

from .types import (
    WorkspaceSnapshot,
    Turn,
    CodeMutation,
    BlockReplacement,
)


class WorkspaceStateManager:
    """
    Centralized controller for the workspace snapshot.
    Ensures zero context drift by keeping all file buffers, active file,
    and recent interactions in a single, strictly maintained snapshot.
    """

    def __init__(self, project_root: str, max_history_turns: int = 15):
        self.project_root = Path(project_root).resolve()
        self.max_history_turns = max_history_turns
        self.snapshot = WorkspaceSnapshot()
        self.undo_stack: List[WorkspaceSnapshot] = []
        self._ensure_project_root()

    def _ensure_project_root(self):
        if not self.project_root.exists():
            self.project_root.mkdir(parents=True, exist_ok=True)

    def _normalize_path(self, file_path: str) -> str:
        """Converts paths to clean relative paths matching project root."""
        p = Path(file_path)
        if p.is_absolute():
            try:
                rel = p.resolve().relative_to(self.project_root)
                return str(rel).replace("\\", "/")
            except ValueError:
                return str(p).replace("\\", "/")
        return str(p).replace("\\", "/")

    def _get_absolute_path(self, rel_or_abs_path: str) -> Path:
        p = Path(rel_or_abs_path)
        if p.is_absolute():
            return p.resolve()
        return (self.project_root / p).resolve()

    def _compute_checksum(self, content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]

    def _save_undo_state(self):
        """Preserves a deep copy of the current snapshot for rollback."""
        self.undo_stack.append(self.snapshot.model_copy(deep=True))
        if len(self.undo_stack) > 30:
            self.undo_stack.pop(0)

    def rollback(self) -> Optional[WorkspaceSnapshot]:
        """Rollback to the previous snapshot state and restore files on disk."""
        if not self.undo_stack:
            return None
        previous_snapshot = self.undo_stack.pop()
        self.snapshot = previous_snapshot

        # Sync buffers back to disk
        for rel_path, code in self.snapshot.open_files.items():
            abs_path = self._get_absolute_path(rel_path)
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_text(code, encoding="utf-8")

        return self.snapshot

    def get_snapshot(self) -> WorkspaceSnapshot:
        """Return the current single source of truth snapshot."""
        return self.snapshot.model_copy(deep=True)

    def set_snapshot(self, snapshot: WorkspaceSnapshot):
        """Set or overwrite the current snapshot."""
        self._save_undo_state()
        self.snapshot = snapshot.model_copy(deep=True)

    def open_file(self, file_path: str, set_as_active: bool = True) -> str:
        """Reads a file from disk into the open files buffer and optionally sets active."""
        rel_path = self._normalize_path(file_path)
        abs_path = self._get_absolute_path(rel_path)

        if not abs_path.exists():
            raise FileNotFoundError(f"File not found on disk: {abs_path}")

        content = abs_path.read_text(encoding="utf-8", errors="replace")
        self.snapshot.open_files[rel_path] = content
        if set_as_active or not self.snapshot.active_file:
            self.snapshot.active_file = rel_path

        self.snapshot.metadata[f"checksum_{rel_path}"] = self._compute_checksum(content)
        return content

    def close_file(self, file_path: str):
        """Closes a file from the open buffer."""
        rel_path = self._normalize_path(file_path)
        if rel_path in self.snapshot.open_files:
            del self.snapshot.open_files[rel_path]
        if self.snapshot.active_file == rel_path:
            remaining = list(self.snapshot.open_files.keys())
            self.snapshot.active_file = remaining[0] if remaining else None

    def set_active_file(self, file_path: str):
        """Sets the active file buffer."""
        rel_path = self._normalize_path(file_path)
        if rel_path not in self.snapshot.open_files:
            # Try to open it if it exists on disk
            self.open_file(rel_path, set_as_active=True)
        else:
            self.snapshot.active_file = rel_path

    def _smart_block_replace(self, old_code: str, search_target: str, replacement_text: str, file_path: str = "") -> str:
        """
        Performs robust surgical block replacement:
        1. Exact character match.
        2. Indentation/whitespace-aware line matching with automatic indentation preservation.
        """
        normalized_old = old_code.replace("\r\n", "\n")
        normalized_search = search_target.replace("\r\n", "\n")
        normalized_replace = replacement_text.replace("\r\n", "\n")

        # 1. Exact match
        if normalized_search in normalized_old:
            return normalized_old.replace(normalized_search, normalized_replace, 1)

        # 2. Indentation/whitespace-aware line matching
        old_lines = normalized_old.split("\n")
        search_lines = [line for line in normalized_search.split("\n") if line.strip()]

        if not search_lines:
            raise ValueError(f"Block search target in {file_path} contains no non-empty lines.")

        stripped_search = [line.strip() for line in search_lines]
        window_size = len(stripped_search)

        match_start = -1
        for i in range(len(old_lines) - window_size + 1):
            window = [old_lines[i + j].strip() for j in range(window_size)]
            if window == stripped_search:
                match_start = i
                break

        if match_start == -1:
            raise ValueError(f"Block search target not found in {file_path}:\n'''\n{search_target}\n'''")

        # Determine original indentation of matched block
        orig_first_line = old_lines[match_start]
        orig_indent = orig_first_line[:len(orig_first_line) - len(orig_first_line.lstrip())]

        # Determine search indentation
        search_indent = search_lines[0][:len(search_lines[0]) - len(search_lines[0].lstrip())]

        # Indent replacement lines to match original context
        replace_lines = normalized_replace.split("\n")
        reindented_replace = []
        for line in replace_lines:
            if not line.strip():
                reindented_replace.append("")
            elif line.startswith(search_indent):
                reindented_replace.append(orig_indent + line[len(search_indent):])
            else:
                reindented_replace.append(orig_indent + line.lstrip())

        new_lines = old_lines[:match_start] + reindented_replace + old_lines[match_start + window_size:]
        return "\n".join(new_lines)

    def compute_diff(self, old_content: str, new_content: str, file_path: str) -> str:
        """Generates unified diff between two string contents."""
        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        diff_lines = list(difflib.unified_diff(
            old_lines, new_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
            lineterm=""
        ))
        return "\n".join(diff_lines)

    def apply_mutation(self, mutation: CodeMutation, write_to_disk: bool = True) -> CodeMutation:
        """
        Applies an atomic code mutation (create, update, replace_block, delete)
        to the snapshot buffer and optionally to disk.
        """
        self._save_undo_state()
        rel_path = self._normalize_path(mutation.file_path)
        abs_path = self._get_absolute_path(rel_path)

        try:
            if mutation.action == "create":
                old_code = ""
                new_code = mutation.content or ""
                self.snapshot.open_files[rel_path] = new_code
                self.snapshot.active_file = rel_path
                diff = self.compute_diff(old_code, new_code, rel_path)
                mutation.diff = diff

                if write_to_disk:
                    abs_path.parent.mkdir(parents=True, exist_ok=True)
                    abs_path.write_text(new_code, encoding="utf-8")

                self.snapshot.metadata[f"checksum_{rel_path}"] = self._compute_checksum(new_code)
                mutation.success = True

            elif mutation.action == "update":
                old_code = self.snapshot.open_files.get(rel_path)
                if old_code is None and abs_path.exists():
                    old_code = abs_path.read_text(encoding="utf-8", errors="replace")
                elif old_code is None:
                    old_code = ""

                new_code = mutation.content if mutation.content is not None else old_code
                self.snapshot.open_files[rel_path] = new_code
                self.snapshot.active_file = rel_path
                diff = self.compute_diff(old_code, new_code, rel_path)
                mutation.diff = diff

                if write_to_disk:
                    abs_path.parent.mkdir(parents=True, exist_ok=True)
                    abs_path.write_text(new_code, encoding="utf-8")

                self.snapshot.metadata[f"checksum_{rel_path}"] = self._compute_checksum(new_code)
                mutation.success = True

            elif mutation.action == "replace_block":
                if not mutation.block_replacement:
                    raise ValueError("block_replacement required for replace_block action")

                search_target = mutation.block_replacement.search
                replacement_text = mutation.block_replacement.replace

                old_code = self.snapshot.open_files.get(rel_path)
                if old_code is None and abs_path.exists():
                    old_code = abs_path.read_text(encoding="utf-8", errors="replace")
                elif old_code is None:
                    raise FileNotFoundError(f"Cannot replace block: file {rel_path} does not exist.")

                new_code = self._smart_block_replace(old_code, search_target, replacement_text, file_path=rel_path)
                self.snapshot.open_files[rel_path] = new_code
                self.snapshot.active_file = rel_path
                diff = self.compute_diff(old_code, new_code, rel_path)
                mutation.diff = diff

                if write_to_disk:
                    abs_path.parent.mkdir(parents=True, exist_ok=True)
                    abs_path.write_text(new_code, encoding="utf-8")

                self.snapshot.metadata[f"checksum_{rel_path}"] = self._compute_checksum(new_code)
                mutation.success = True

            elif mutation.action == "delete":
                if rel_path in self.snapshot.open_files:
                    del self.snapshot.open_files[rel_path]
                if self.snapshot.active_file == rel_path:
                    remaining = list(self.snapshot.open_files.keys())
                    self.snapshot.active_file = remaining[0] if remaining else None
                if write_to_disk and abs_path.exists():
                    abs_path.unlink()
                mutation.success = True

        except Exception as e:
            mutation.success = False
            mutation.error = str(e)

        return mutation

    def append_interaction(
        self,
        role: str,
        content: str,
        model_name: Optional[str] = None,
        diffs: Optional[List[Dict[str, Any]]] = None,
        handoff_notes: Optional[List[str]] = None
    ) -> Turn:
        """Appends a new interaction turn to recent_history and trims to max size."""
        turn = Turn(
            role=role,  # type: ignore
            content=content,
            model_name=model_name,
            diffs=diffs or [],
            handoff_notes=handoff_notes or []
        )
        self.snapshot.recent_history.append(turn)
        if len(self.snapshot.recent_history) > self.max_history_turns:
            self.snapshot.recent_history = self.snapshot.recent_history[-self.max_history_turns:]
        return turn

    def sync_from_disk(self):
        """Reloads all open file buffers from disk to catch external changes."""
        for rel_path in list(self.snapshot.open_files.keys()):
            abs_path = self._get_absolute_path(rel_path)
            if abs_path.exists():
                content = abs_path.read_text(encoding="utf-8", errors="replace")
                self.snapshot.open_files[rel_path] = content
                self.snapshot.metadata[f"checksum_{rel_path}"] = self._compute_checksum(content)

    def list_project_files(self, max_depth: int = 4) -> List[str]:
        """Discovers files in project directory, excluding common ignored folders."""
        ignored = {".git", ".idea", "__pycache__", "node_modules", ".venv", "venv", ".pytest_cache", ".gemini"}
        discovered: List[str] = []

        for root, dirs, files in os.walk(self.project_root):
            dirs[:] = [d for d in dirs if d not in ignored and not d.startswith(".")]
            for f in files:
                if f.startswith("."):
                    continue
                p = Path(root) / f
                try:
                    rel = p.relative_to(self.project_root)
                    discovered.append(str(rel).replace("\\", "/"))
                except ValueError:
                    pass

        return sorted(discovered)
