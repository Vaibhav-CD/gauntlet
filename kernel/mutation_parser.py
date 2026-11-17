"""
Mutation Parser for Automatic State Mutation.
Extracts file updates, surgical search/replace blocks, and deletions from model responses,
allowing the Workspace State Manager to update open buffers and disk without manual copy-pasting.
"""

import re
from typing import List, Tuple
from .types import CodeMutation, BlockReplacement


class MutationParser:
    """
    Parses structured code mutations and diffs from raw AI output.
    """

    FILE_UPDATE_PATTERN = re.compile(
        r"<<<FILE_UPDATE:\s*([^\r\n>]+)>>>\r?\n([\s\S]*?)<<<END_FILE_UPDATE>>>",
        re.MULTILINE
    )

    SEARCH_REPLACE_PATTERN = re.compile(
        r"<<<SEARCH_REPLACE:\s*([^\r\n>]+)>>>\r?\n<<<<<<< SEARCH\r?\n([\s\S]*?)=======\r?\n([\s\S]*?)>>>>>>>\r?\n<<<END_SEARCH_REPLACE>>>",
        re.MULTILINE
    )

    FILE_DELETE_PATTERN = re.compile(
        r"<<<FILE_DELETE:\s*([^\r\n>]+)>>>",
        re.MULTILINE
    )

    @classmethod
    def parse(cls, raw_text: str) -> Tuple[str, List[CodeMutation]]:
        """
        Parses mutations and strips them to produce a clean conversational explanation.
        Returns:
            clean_text: Explanation suitable for chat display.
            mutations: List of CodeMutation objects to apply.
        """
        mutations: List[CodeMutation] = []
        cleaned_text = raw_text

        # 1. Parse Search & Replace Blocks
        for match in cls.SEARCH_REPLACE_PATTERN.finditer(raw_text):
            file_path = match.group(1).strip()
            search_block = match.group(2)
            replace_block = match.group(3)

            mutations.append(CodeMutation(
                action="replace_block",
                file_path=file_path,
                block_replacement=BlockReplacement(
                    search=search_block,
                    replace=replace_block
                )
            ))

        cleaned_text = cls.SEARCH_REPLACE_PATTERN.sub(
            lambda m: f"\n*[Applied block replacement to `{m.group(1).strip()}`]*\n",
            cleaned_text
        )

        # 2. Parse Full File Updates
        for match in cls.FILE_UPDATE_PATTERN.finditer(raw_text):
            file_path = match.group(1).strip()
            content = match.group(2)

            mutations.append(CodeMutation(
                action="update",
                file_path=file_path,
                content=content
            ))

        cleaned_text = cls.FILE_UPDATE_PATTERN.sub(
            lambda m: f"\n*[Updated file `{m.group(1).strip()}`]*\n",
            cleaned_text
        )

        # 3. Parse File Deletions
        for match in cls.FILE_DELETE_PATTERN.finditer(raw_text):
            file_path = match.group(1).strip()
            mutations.append(CodeMutation(
                action="delete",
                file_path=file_path
            ))

        cleaned_text = cls.FILE_DELETE_PATTERN.sub(
            lambda m: f"\n*[Deleted file `{m.group(1).strip()}`]*\n",
            cleaned_text
        )

        return cleaned_text.strip(), mutations
