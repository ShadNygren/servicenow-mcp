"""
Natural-language query and command parsing for ServiceNow.

Rule-based regex parser that translates phrases like:

  - "find all incidents about SAP"
  - "close incident INC0010003 with resolution: fixed the issue"
  - "update INC0010001 saying I'm working on it"

into structured ServiceNow Table API operations. No LLM needed at the
server layer — the calling LLM does the language understanding, this
module does the deterministic translation step.

Ported from ``michaelbuckner/servicenow-mcp`` (commit ``39e0910``,
``mcp_server_servicenow/nlp.py``, MIT-licensed). Original copyright
preserved in the project NOTICE file. Behavior is unchanged from the
upstream module — table-name mapping is hardcoded for now; a follow-up
will use the ``servicenow://schema/{table}`` resource for
schema-driven resolution.
"""

import re
from typing import Any, Dict, Tuple


class NLPProcessor:
    """Natural-language processing for ServiceNow queries and commands."""

    @staticmethod
    def parse_search_query(query: str) -> Dict[str, Any]:
        """Parse a natural-language search query.

        Examples:
            "find all incidents about SAP"
            "search for incidents related to email"
            "show me all incidents with high priority"

        Returns:
            Dict with ``table``, ``query`` (encoded sysparm_query string),
            and ``limit``.
        """
        # Default to incident table.
        table = "incident"

        table_match = re.search(
            r"(incidents?|problems?|changes?|tasks?|users?|groups?)",
            query,
            re.IGNORECASE,
        )
        if table_match:
            table_type = table_match.group(1).lower()
            if table_type.startswith("incident"):
                table = "incident"
            elif table_type.startswith("problem"):
                table = "problem"
            elif table_type.startswith("change"):
                table = "change_request"
            elif table_type.startswith("task"):
                table = "task"
            elif table_type.startswith("user"):
                table = "sys_user"
            elif table_type.startswith("group"):
                table = "sys_user_group"

        # Search terms — try the "about/related to/..." form first, then
        # fall back to anything after a search verb.
        about_match = re.search(
            r"(?:about|related to|regarding|concerning|with|containing)\s+([^\.]+)",
            query,
            re.IGNORECASE,
        )
        search_term = ""
        if about_match:
            search_term = about_match.group(1).strip()
        else:
            term_match = re.search(
                r"(?:find|search for|show|get|list|display)\s+(?:all|any|)(?:\s+\w+)?\s+(?:\w+\s+)?(.+)",
                query,
                re.IGNORECASE,
            )
            if term_match:
                search_term = term_match.group(1).strip()

        # Priority.
        priority = None
        if re.search(r"\b(high|critical)\s+priority\b", query, re.IGNORECASE):
            priority = "1"
        elif re.search(r"\b(medium)\s+priority\b", query, re.IGNORECASE):
            priority = "2"
        elif re.search(r"\b(low)\s+priority\b", query, re.IGNORECASE):
            priority = "3"

        # State.
        state = None
        if re.search(r"\b(new|open)\b", query, re.IGNORECASE):
            state = "1"
        elif re.search(r"\b(in progress|working)\b", query, re.IGNORECASE):
            state = "2"
        elif re.search(r"\b(closed|resolved)\b", query, re.IGNORECASE):
            state = "7"

        # Build the query string. ``123TEXTQUERY321=`` is ServiceNow's
        # encoded-query syntax for a full-text search across the table.
        query_parts = []
        if search_term:
            query_parts.append(f"123TEXTQUERY321={search_term}")
        if priority:
            query_parts.append(f"priority={priority}")
        if state:
            query_parts.append(f"state={state}")

        query_string = "^".join(query_parts) if query_parts else ""

        return {
            "table": table,
            "query": query_string,
            "limit": 10,
        }

    @staticmethod
    def parse_update_command(command: str) -> Tuple[str, Dict[str, Any]]:
        """Parse a natural-language update command.

        Examples:
            "Update incident INC0010001 saying I'm working on it"
            "Set incident INC0010002 to in progress"
            "Close incident INC0010003 with resolution: fixed the issue"

        Returns:
            (record_number, updates_dict)

        Raises:
            ValueError: If no record number was found.
        """
        number_match = re.search(
            r"(INC\d+|PRB\d+|CHG\d+|TASK\d+)",
            command,
            re.IGNORECASE,
        )
        if not number_match:
            raise ValueError("No record number found in command")
        record_number = number_match.group(1).upper()

        updates: Dict[str, Any] = {}

        # State changes.
        if re.search(r"\b(working on|in progress|assign)\b", command, re.IGNORECASE):
            updates["state"] = 2  # In Progress
        elif re.search(r"\b(resolve|resolved|fix|fixed)\b", command, re.IGNORECASE):
            updates["state"] = 6  # Resolved
        elif re.search(r"\b(close|closed)\b", command, re.IGNORECASE):
            updates["state"] = 7  # Closed

        # Comments / work notes.
        comment_match = re.search(
            r"(?:saying|comment|note|with comment|with note)(?:s|)\s*:?\s*(.+?)(?:$|\.(?:\s|$))",
            command,
            re.IGNORECASE,
        )
        if comment_match:
            comment_text = comment_match.group(1).strip()
            if re.search(r"\b(work note|internal|private)\b", command, re.IGNORECASE):
                updates["work_notes"] = comment_text
            else:
                updates["comments"] = comment_text

        # Close notes when transitioning to Resolved/Closed.
        if "state" in updates and updates["state"] in [6, 7]:
            close_match = re.search(
                r"(?:with resolution|resolution|close note|resolve with)(?:s|)\s*:?\s*(.+?)(?:$|\.(?:\s|$))",
                command,
                re.IGNORECASE,
            )
            if close_match:
                updates["close_notes"] = close_match.group(1).strip()
                updates["close_code"] = "Solved (Permanently)"

        return record_number, updates
