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
        capped: bool = False,
    ) -> "ToolResult":
        """Construct a ToolResult, deriving `truncated` from the counts.

        `capped` exists for the one case the counts cannot express: the
        source said "there are more" but did not say how many. Without it,
        leaving `total_available` at None would also leave `truncated`
        False — so an unknown total would read as a complete answer, which
        is the SP-005 defect wearing different clothes.
        """
        truncated = capped or (
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


def child_page_count(
    response: dict, items: list[dict]
) -> tuple[int | None, bool]:
    """Split a child-collection response into ``(total_available, capped)``.

    Shared because SP-005 was one bug copied into five tools. The child
    resources report `count` as the size of the page they returned, not the
    size of the collection, so a tool that reads `count` or `len(items)`
    states a cap as a total. Measured on dev49, invoice 1601397:

        limit=50   count=50  hasMore=True   totalResults=184   items=50
        limit=100  count=58  hasMore=False  totalResults=58    items=58

    So `count` is ``min(total, limit)`` and tells you nothing you cannot
    already see. The honest signals are:

    - `totalResults`, when present: the true total. Ask for it with
      ``totalResults=true``; the child resources honour it (invoice lines
      and AR invoice lines both verified on dev49, 2026-11-28).
    - `hasMore`, when `totalResults` is absent: at least one more record
      exists, but the total is unknown.

    Returns:
        ``(total_available, capped)``. When the total is known, `capped` is
        False and `ToolResult.build` derives truncation from the counts.
        When only `hasMore` is available, the total is None and `capped` is
        True, so the answer says "a sample" without inventing a
        denominator. When the page is complete, the total is the row count,
        which is not a guess: nothing was left behind.
    """
    total = response.get("totalResults")
    if isinstance(total, int):
        return total, False
    if response.get("hasMore"):
        return None, True
    return len(items), False
