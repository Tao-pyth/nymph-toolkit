"""Memory queries and the shared canonical record rules (ADR 0027)."""

# SPDX-License-Identifier: Apache-2.0
from nymph_toolkit.contracts._memory_record import KINDS, SOURCES, canonical, identifier


def filters(kind, source_kind, after, limit):
    if kind is not None and (type(kind) is not str or kind not in KINDS):
        raise ValueError("Unknown kind")
    if source_kind is not None and (type(source_kind) is not str or source_kind not in SOURCES):
        raise ValueError("Unknown source_kind")
    if type(after) is not int or not 0 <= after <= 2**63 - 1:
        raise ValueError("after must be an integer between 0 and 2^63-1")
    if type(limit) is not int or not 1 <= limit <= 8:
        raise ValueError("limit must be an integer between 1 and 8")
