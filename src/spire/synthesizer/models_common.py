"""Sub-models and field definitions shared across every response schema.

The bottom of the synthesizer's dependency graph. This module imports
nothing from the package and everything else in it may import from here,
which is what keeps the module split acyclic.

Two kinds of thing live here:

- Sub-models that appear nested inside more than one top-level response
  (BuyerInfo under suppliers and purchase orders, AddressInfo under
  suppliers). A sub-model used by exactly one module belongs in that
  module instead.
- The two Field definitions every top-level response reuses. They are
  shared objects rather than copied text on purpose: the truncation and
  summary instructions are the ones most often got wrong by a model, and
  a divergent copy in one schema is a defect nobody would notice until it
  produced a wrong total in front of a user.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────
# Shared sub-models
# ─────────────────────────────────────────────────────────────────────


class BuyerInfo(BaseModel):
    """One buyer mentioned in the synthesized response.

    person_id is validated against the executor's buyers output after
    synthesis — it MUST appear there."""

    person_id: int = Field(description="The buyer's PersonId (HCM key).")
    display_name: str = Field(description="The buyer's display name.")


class AddressInfo(BaseModel):
    """One address nested under a supplier in a supplier-rooted response.

    address_id is validated against the executor's output after synthesis
    — it MUST appear there. Used for the "suppliers with their addresses"
    shape, where addresses hang off each supplier record."""

    address_id: int = Field(
        description="The address's SupplierAddressId (numeric key). "
        "Must appear in the data."
    )
    country: str = Field(default="", description="Full country name, if present.")
    city: str = Field(default="", description="City, if present.")
    state: str = Field(default="", description="State/province, if present.")
    formatted_address: str = Field(
        default="", description="One-line formatted address, if present."
    )


# ─────────────────────────────────────────────────────────────────────
# Shared field definitions
#
# Reused by every top-level response schema. Kept as shared objects so
# the wording cannot drift between entities: both of these instructions
# exist to stop the model reporting a page size as a total, and a
# weakened copy in one schema would reintroduce that defect on one route
# only — the hardest kind to notice.
# ─────────────────────────────────────────────────────────────────────


_TRUNCATION_FIELD = Field(
    default_factory=list,
    description="One short note per truncated step. Each note states the "
    "step's output_name, the total_available count if known, and how many "
    "records were examined. Empty when no step was truncated. Populate ONLY "
    "from the truncation block in the executor output; never invent counts.",
)

_SUMMARY_FIELD = Field(
    description="One-paragraph natural-language summary (3-5 sentences). "
    "Do not invent specifics not in the data. If truncation_notes is "
    "non-empty this summary MUST say the result is partial and give the "
    "total from the truncation block — the count of rows shown is NOT the "
    "number that exist."
)
