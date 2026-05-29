"""Shared types for MCP tools.

ToolResult wraps a tool's returned items with metadata about completeness,
so callers can tell the difference between "this is everything" and "this
is a capped subset of a larger result set."
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class ToolResult:
    """Standard return shape for MCP tools that fetch lists of records.

    Fields:
        items: The records returned (already filtered, projected, and
            capped at limit_applied).
        total_available: Total matching records in the source, if known.
            None when the source can't or doesn't report a count.
        limit_applied: The limit the tool used when fetching. Equals the
            caller's `limit` argument unless the tool over-fetched
            internally for client-side filtering.
        truncated: True iff total_available is known and exceeds
            len(items). When total_available is None, truncated is False
            (we can't claim truncation we can't prove).
    """

    items: list[dict] = field(default_factory=list)
    total_available: int | None = None
    limit_applied: int = 0
    truncated: bool = False

    @classmethod
    def build(
        cls,
        items: list[dict],
        limit_applied: int,
        total_available: int | None,
    ) -> "ToolResult":
        """Construct a ToolResult, deriving `truncated` from the counts."""
        truncated = (
            total_available is not None and total_available > len(items)
        )
        return cls(
            items=items,
            total_available=total_available,
            limit_applied=limit_applied,
            truncated=truncated,
        )

    def to_dict(self) -> dict:
        """Serialize to a plain dict for JSON transport over MCP."""
        return asdict(self)
