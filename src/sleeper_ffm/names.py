"""Canonical player-name normalization — the shared match key across data sources.

Every join between two data sources that only share a player by NAME (not a stable
ID) needs the same fold: nflverse weekly stats <-> Sleeper player dump, CFBD college
stats <-> Sleeper rookie names, combine measurables <-> draft prospects, ESPN college
box scores <-> CFBD recruiting names, and AI-generated recommendation text <-> the
nflverse box score it gets graded against.

Before this module existed, six call sites each hand-rolled a slightly different fold
(some stripped punctuation, some didn't; the suffix set ranged from Jr/Sr/II/III/IV to
also including V; only one handled accented characters or a trailing "(POS TEAM)"
annotation). This is the single canonical behavior — the union of what those six did,
so joins that previously silently missed a match (e.g. an un-stripped "Jr." suffix)
now succeed.
"""

from __future__ import annotations

import re
import unicodedata

_ANNOTATION_RE = re.compile(r"\s*\([^)]*\)\s*$")
_SUFFIX_RE = re.compile(r"\s+(jr\.?|sr\.?|ii|iii|iv|v)$", re.IGNORECASE)
_PUNCT_RE = re.compile(r"[^a-z0-9\s]")


def normalize_name(name: str | None) -> str:
    """Fold a player name to a stable cross-source match key.

    Pipeline: drop a trailing ``"(POS TEAM)"``-style annotation (some AI-generated
    recs append one) -> ascii-fold accented characters -> lowercase -> strip a
    trailing generational suffix (Jr/Sr/II/III/IV/V) -> drop remaining punctuation
    -> collapse whitespace.

    Args:
        name: Raw player name from any source. ``None`` or empty returns ``""``.

    Returns:
        The normalized match key.
    """
    if not name:
        return ""
    base = _ANNOTATION_RE.sub("", name)
    base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode()
    base = base.lower().strip()
    base = _SUFFIX_RE.sub("", base)
    base = _PUNCT_RE.sub("", base)
    return " ".join(base.split())
