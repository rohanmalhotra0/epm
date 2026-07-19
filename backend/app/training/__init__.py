"""Synthetic training-data generation (spec-grounded, validator-guaranteed).

Every emitted pair is anchored in real tenant metadata and checked by the
same deterministic validator the app uses — the corpus can be large because
correctness is manufactured, not hand-labelled.
"""

from __future__ import annotations

from .synthetic import (
    Phrase,
    TrainingPair,
    build_corpus,
    generate_edit_pair,
    generate_spec,
    pair_digest,
    phrase_spec,
    spec_to_json,
)

__all__ = [
    "Phrase",
    "TrainingPair",
    "build_corpus",
    "generate_edit_pair",
    "generate_spec",
    "pair_digest",
    "phrase_spec",
    "spec_to_json",
]
