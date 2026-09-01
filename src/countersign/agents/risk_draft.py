"""What the model is allowed to return.

Note what is absent: no weight, no score, no risk level, no recommended action.
Those are computed from the table in `risk_weights`, so the model cannot move
the decision by writing a number. It writes the wording and the citations.

`citations` is allowed to arrive empty on purpose. The schema could forbid it,
but then an uncited claim would surface as a parse error instead of as the
grounding failure it actually is, and the rejection rule would be enforced by
accident rather than on the record.
"""

from autocurricula.schemas.common import StrictBaseModel
from pydantic import Field

from countersign.schemas.verdict import SignalKind


class DraftCitation(StrictBaseModel):
    """A pointer into the evidence index, plus the words being relied on."""

    evidence_id: str = Field(min_length=1)
    quote: str = ""


class DraftClaim(StrictBaseModel):
    statement: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    citations: list[DraftCitation] = Field(default_factory=list)


class DraftSignal(StrictBaseModel):
    kind: SignalKind
    claim: DraftClaim


class DraftVerdict(StrictBaseModel):
    headline: str = Field(min_length=1)
    reasoning: str = ""
    signals: list[DraftSignal] = Field(default_factory=list)

    @property
    def kinds(self) -> list[SignalKind]:
        return [signal.kind for signal in self.signals]


RESPONSE_SHAPE = """{
  "headline": "one sentence a finance analyst can act on",
  "reasoning": "why these signals, in prose",
  "signals": [
    {
      "kind": "<one of the listed signal kinds>",
      "claim": {
        "statement": "the assertion, in one sentence",
        "confidence": 0.0,
        "citations": [{"evidence_id": "E1", "quote": "verbatim words from E1"}]
      }
    }
  ]
}"""
