"""
Uniform Prompt Engine for Dynamic Model Agnosticism.
Constructs consistent, structured prompts injecting the Single Source of Truth
workspace snapshot (active file, open buffers, recent history, handoff notes)
and precise code mutation instructions.
"""

from typing import List
from .types import ExecutionPayload, WorkspaceSnapshot, Turn


class PromptEngine:
    """
    Constructs model-agnostic prompts ensuring zero context drift across any AI model.
    """

    SYSTEM_INSTRUCTIONS = """You are the System Kernel of a custom, multi-model developer environment.
Your purpose is to manage project state, execute coding tasks, and output precise code changes.

CRITICAL INSTRUCTIONS:
1. When modifying or creating code, DO NOT ask the user to copy-paste.
2. The workspace state manager will automatically parse and apply your code mutations directly into open buffers and disk.
3. To replace a specific block of code in an existing file, use this EXACT syntax:
<<<SEARCH_REPLACE:relative/path/to/file.ext>>>
<<<<<<< SEARCH
exact lines to be replaced from the current buffer
=======
new replacement lines of code
>>>>>>>
<<<END_SEARCH_REPLACE>>>

4. To create a new file or rewrite an entire file, use this EXACT syntax:
<<<FILE_UPDATE:relative/path/to/file.ext>>>
full file content here
<<<END_FILE_UPDATE>>>

5. To delete a file, use:
<<<FILE_DELETE:relative/path/to/file.ext>>>

6. Always verify the active file and open file buffers provided in the workspace snapshot before generating code.
7. Always provide a clear, concise explanation of the changes made.
"""

    @classmethod
    def build_system_prompt(cls) -> str:
        return cls.SYSTEM_INSTRUCTIONS.strip()

    @classmethod
    def build_user_prompt(cls, payload: ExecutionPayload, handoff_notes: List[str] = None) -> str:
        """
        Formats the execution payload and snapshot into a rich, structured context.
        """
        snapshot = payload.workspace_snapshot
        handoff_notes = handoff_notes or []

        sections = []

        # 1. Handoff context (if failover occurred)
        if handoff_notes:
            notes_str = "\n".join([f"- {note}" for note in handoff_notes])
            sections.append(f"### [RUNTIME FAILOVER CONTEXT & HANDOFF NOTES]\n{notes_str}\n")

        # 2. Workspace State Snapshot (Single Source of Truth)
        sections.append("### [CENTRALIZED WORKSPACE SNAPSHOT]")
        active_file = snapshot.active_file or "None (No active file selected)"
        sections.append(f"ACTIVE FILE: {active_file}\n")

        sections.append("OPEN FILE BUFFERS:")
        if not snapshot.open_files:
            sections.append("(No open files in current buffer)")
        else:
            for file_path, content in snapshot.open_files.items():
                is_active = " [ACTIVE]" if file_path == snapshot.active_file else ""
                sections.append(f"--- File: {file_path}{is_active} ---")
                sections.append("```")
                sections.append(content)
                sections.append("```\n")

        # 3. Recent Interaction History (Temporal Continuity)
        if snapshot.recent_history:
            sections.append("### [RECENT INTERACTION HISTORY]")
            for turn in snapshot.recent_history[-6:]:  # Keep recent turns concise
                role_label = turn.role.upper()
                model_tag = f" ({turn.model_name})" if turn.model_name else ""
                sections.append(f"[{role_label}{model_tag} at {turn.timestamp}]:\n{turn.content.strip()}\n")

        # 4. Current Task Prompt
        sections.append("### [CURRENT TASK PROMPT]")
        sections.append(payload.task_prompt.strip())

        return "\n".join(sections)
