"""Shared constants for the synthesizer package.

Split out of synthesizer.py so that modules which must not import each
other can still share a value. LIFECYCLE_SHAPE is the case that forces
it: it is read by the shape detector that stays in synthesizer.py and by
the id harvest that moves to builders.py. Putting the string in either
module would make the other depend on it for no reason.

Model and temperature come from spire.config, which remains the single
source of truth; they are re-exported here only so that the modules that
build LLM calls do not each need their own config import.
"""

from __future__ import annotations

from spire.config import GEMINI_MODEL, GEMINI_TEMPERATURE

# Model and determinism come from spire.config (single source of truth).
_MODEL_NAME = GEMINI_MODEL
_TEMPERATURE = GEMINI_TEMPERATURE

# The 'shape' tag the PO lifecycle tool stamps on its record.
#
# THIS IS A CONTRACT, NOT A LABEL. The value must equal _SHAPE in
# src/spire/mcp_server/tools/po_lifecycle.py. When they disagree, a
# lifecycle record falls through to the PO-LIST schema and the model
# quotes ids that schema never harvested — which the hallucination guard
# then reports as invented data, pointing at the model rather than at the
# mismatch. Change one, change both.
LIFECYCLE_SHAPE = "po_lifecycle_status"
