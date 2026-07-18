"""Pluggable NLU strategies evaluated against the same corpus.

The harness scores whatever turns an utterance into a ``FormSpecification``. Today
that is the deterministic regex parser (:class:`DeterministicStrategy`). When the
hybrid *LLM-proposes / deterministic-validates* path lands, wrap it in a second
``Strategy`` and run the identical corpus through both — the coverage delta is the
evidence that the change helped, with no correctness risk moved onto the model
(the produced spec is still validated by ``validate_form`` in the scorer).
"""

from __future__ import annotations

from typing import Protocol

from ..agent.form_nlu import apply_edit, build_initial_spec
from ..agent.intent import detect_intent
from ..artifacts.metadata import TenantMetadata
from ..schemas.form_spec import FormSpecification


class Strategy(Protocol):
    name: str

    def route(self, utterance: str) -> str:
        """Return the routed skill name for an utterance."""
        ...

    def build(self, utterance: str, md: TenantMetadata, application: str) -> FormSpecification:
        """Turn a build utterance into a proposed FormSpecification."""
        ...

    def edit(self, spec: FormSpecification, utterance: str, md: TenantMetadata) -> bool:
        """Apply a conversational edit in place; return whether anything changed."""
        ...


class DeterministicStrategy:
    """The shipping regex/keyword NLU — the baseline every alternative must beat."""

    name = "deterministic"

    def route(self, utterance: str) -> str:
        return detect_intent(utterance).skill

    def build(self, utterance: str, md: TenantMetadata, application: str) -> FormSpecification:
        spec, _inferences, _questions = build_initial_spec(utterance, md, application)
        return spec

    def edit(self, spec: FormSpecification, utterance: str, md: TenantMetadata) -> bool:
        changed, _changes, _questions = apply_edit(spec, utterance, md)
        return changed
