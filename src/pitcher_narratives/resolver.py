"""Fuzzy pitcher name resolution from manifest-covered PitchingPlus data."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from nameparser import HumanName
from rapidfuzz import fuzz, process

from pitcher_narratives.data import load_emitted_grain

__all__ = ["ResolveResult", "extract_pitcher_from_question", "resolve"]

_SCORE_CUTOFF = 70
_MAX_CANDIDATES = 5


@dataclass
class ResolveResult:
    """Result of a pitcher name resolution attempt.

    Attributes:
        pitcher_id: Resolved MLB pitcher ID, or None if ambiguous/not found.
        pitcher_name: Original "Last, First" name from dataset, or None.
        candidates: List of (pitcher_id, name) tuples for disambiguation.
        match_type: One of "exact", "exact_last", "fuzzy", "ambiguous",
            or "not_found".
    """

    pitcher_id: int | None
    pitcher_name: str | None
    candidates: list[tuple[int, str]] = field(default_factory=list)
    match_type: str = "not_found"


@dataclass
class _NameTable:
    """Cached dual-index lookup table for pitcher names.

    Attributes:
        full_index: Normalized "first last" -> (pitcher_id, original_name).
        last_index: Normalized last name -> list of (pitcher_id, original_name).
    """

    full_index: dict[str, tuple[int, str]] = field(default_factory=dict)
    last_index: dict[str, list[tuple[int, str]]] = field(default_factory=dict)


_name_table: _NameTable | None = None


def _strip_diacritics(s: str) -> str:
    """Remove diacritical marks from a string via NFKD normalization.

    Args:
        s: Input string, possibly containing accented characters.

    Returns:
        ASCII-compatible string with combining characters removed.
    """
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _normalize(raw: str) -> str:
    """Normalize a name string for matching.

    Parses with nameparser to handle "Last, First" and suffix variants,
    reconstructs as "first last" (no suffix), then applies diacritic
    stripping and lowercasing.

    Args:
        raw: Raw name string in any common format.

    Returns:
        Lowercase, accent-stripped, suffix-stripped "first last" form.
    """
    parsed = HumanName(raw)
    name = f"{parsed.first} {parsed.last}".strip() if parsed.last else parsed.first
    return _strip_diacritics(name).lower().strip()


def _build_name_table() -> _NameTable:
    """Build or return the cached dual-index lookup table.

    Reads unique pitcher/player_name pairs from the emitted all-pitches grain
    - full_index: normalized "first last" -> (pitcher_id, original_name)
    - last_index: normalized last name -> [(pitcher_id, original_name), ...]

    Returns:
        Cached _NameTable instance.
    """
    global _name_table
    if _name_table is not None:
        return _name_table

    df = load_emitted_grain("all_pitches").select("pitcher", "player_name")
    unique = df.unique(subset=["pitcher"])

    full_index: dict[str, tuple[int, str]] = {}
    last_index: dict[str, list[tuple[int, str]]] = {}

    for row in unique.iter_rows(named=True):
        original = row["player_name"]
        pid = row["pitcher"]
        parsed = HumanName(original)

        # Build full-name key: "first last" without suffix
        full_norm = _strip_diacritics(f"{parsed.first} {parsed.last}".strip()).lower().strip()

        # Build last-name key: last name only, without suffix
        last_norm = _strip_diacritics(parsed.last).lower().strip()

        if full_norm:
            full_index[full_norm] = (pid, original)
        if last_norm:
            last_index.setdefault(last_norm, []).append((pid, original))

    # Sort each last_index entry by name for deterministic ordering
    for key in last_index:
        last_index[key].sort(key=lambda entry: entry[1])

    _name_table = _NameTable(full_index=full_index, last_index=last_index)
    return _name_table


def _fuzzy_ranked(
    scored_items: list[tuple[float, int, str]],
) -> ResolveResult | None:
    """Deduplicate, rank, and return a ResolveResult from fuzzy matches.

    Args:
        scored_items: List of (score, pitcher_id, original_name) tuples.

    Returns:
        ResolveResult if matches found, None if scored_items is empty.
    """
    if not scored_items:
        return None

    # Deduplicate by pitcher_id, keeping highest score
    seen: dict[int, tuple[float, str]] = {}
    for score, pid, original in scored_items:
        if pid not in seen or score > seen[pid][0]:
            seen[pid] = (score, original)

    # Sort by score descending, then name ascending for determinism
    ranked = sorted(seen.items(), key=lambda item: (-item[1][0], item[1][1]))

    if len(ranked) == 1:
        pid, (_, name) = ranked[0]
        return ResolveResult(pitcher_id=pid, pitcher_name=name, candidates=[], match_type="fuzzy")

    # Check if top result is significantly ahead (>=5 points gap)
    top_score = ranked[0][1][0]
    second_score = ranked[1][1][0]
    if top_score - second_score >= 5:
        pid, (_, name) = ranked[0]
        return ResolveResult(pitcher_id=pid, pitcher_name=name, candidates=[], match_type="fuzzy")

    # Multiple close results -> ambiguous
    candidates = [(pid, info[1]) for pid, info in ranked[:_MAX_CANDIDATES]]
    return ResolveResult(
        pitcher_id=None,
        pitcher_name=None,
        candidates=candidates,
        match_type="ambiguous",
    )


def _fuzzy_last_name_match(
    query_last: str, unique_last_names: list[str], table: _NameTable
) -> ResolveResult | None:
    """Try fuzzy matching against the last-name index.

    Args:
        query_last: Normalized last-name query string.
        unique_last_names: List of unique normalized last names.
        table: The name table with last_index.

    Returns:
        ResolveResult if a match is found, None otherwise.
    """
    # Plain ratio, not WRatio: WRatio's partial-match component scores a
    # short last name embedded anywhere inside a longer garbage query
    # (e.g. 'tapia' inside 'zzzznotapitcher' -> 72), turning nonsense
    # into a confident fuzzy hit. Plain ratio keeps genuine typos
    # (skubol->skubal 83) while garbage falls below the cutoff.
    fuzzy_last = process.extract(
        query_last,
        unique_last_names,
        scorer=fuzz.ratio,
        limit=_MAX_CANDIDATES,
        score_cutoff=_SCORE_CUTOFF,
    )
    if not fuzzy_last:
        return None

    # Expand matched last names to full entries
    scored: list[tuple[float, int, str]] = []
    for match_last, score, _idx in fuzzy_last:
        for pid, original in table.last_index[match_last]:
            scored.append((score, pid, original))

    return _fuzzy_ranked(scored)


def resolve(query: str) -> ResolveResult:
    """Resolve a pitcher name to an MLB pitcher ID.

    Runs a tiered pipeline. For single-word queries, fuzzy last-name
    matching runs before fuzzy full-name matching because short words
    score poorly against long "first last" strings (Pitfall 2).

    Tier order:
    1. Exact full-name match
    2. Exact last-name match (unique or ambiguous)
    3. Fuzzy last-name match (single-word queries only)
    4. Fuzzy full-name match
    5. Fuzzy last-name match (multi-word queries only)
    6. Not found

    Args:
        query: Pitcher name in any common format (e.g., "Dylan Cease",
            "cease, dylan", "Cease", "Cese").

    Returns:
        ResolveResult with pitcher_id (if resolved), candidates (if
        ambiguous), and match_type indicating which tier matched.
    """
    table = _build_name_table()
    normalized = _normalize(query)
    is_single_word = " " not in normalized

    # --- Tier 1: Exact full-name match ---
    if normalized in table.full_index:
        pid, name = table.full_index[normalized]
        return ResolveResult(pitcher_id=pid, pitcher_name=name, candidates=[], match_type="exact")

    # --- Tier 2: Exact last-name match ---
    # For single-word queries, use the normalized form as a last-name key.
    # For multi-word queries, extract the last name via nameparser.
    if is_single_word:
        last_key = normalized
    else:
        parsed = HumanName(query)
        last_key = _strip_diacritics(parsed.last).lower().strip()

    if last_key in table.last_index:
        entries = table.last_index[last_key]
        if len(entries) == 1:
            pid, name = entries[0]
            return ResolveResult(
                pitcher_id=pid,
                pitcher_name=name,
                candidates=[],
                match_type="exact_last",
            )
        return ResolveResult(
            pitcher_id=None,
            pitcher_name=None,
            candidates=entries[:_MAX_CANDIDATES],
            match_type="ambiguous",
        )

    # Precompute for fuzzy tiers
    unique_last_names = list(set(table.last_index.keys()))
    query_for_last = normalized if is_single_word else last_key

    # --- Tier 3 (single-word only): Fuzzy last-name match ---
    # Single words are almost certainly last names. WRatio on full "first last"
    # strings penalizes short queries due to length mismatch (Pitfall 2).
    if is_single_word:
        result = _fuzzy_last_name_match(query_for_last, unique_last_names, table)
        if result is not None:
            return result

    # --- Tier 4: Fuzzy full-name match ---
    fuzzy_full = process.extract(
        normalized,
        table.full_index.keys(),
        scorer=fuzz.WRatio,
        limit=_MAX_CANDIDATES,
        score_cutoff=_SCORE_CUTOFF,
    )
    if fuzzy_full:
        scored: list[tuple[float, int, str]] = []
        for match_name, score, _idx in fuzzy_full:
            pid, original = table.full_index[match_name]
            scored.append((score, pid, original))

        result = _fuzzy_ranked(scored)
        if result is not None:
            return result

    # --- Tier 5 (multi-word only): Fuzzy last-name match ---
    if not is_single_word:
        result = _fuzzy_last_name_match(query_for_last, unique_last_names, table)
        if result is not None:
            return result

    # --- Tier 6: Not found ---
    return ResolveResult(pitcher_id=None, pitcher_name=None, candidates=[], match_type="not_found")


def extract_pitcher_from_question(
    question: str,
) -> tuple[str | None, ResolveResult | None]:
    """Extract a pitcher name from a natural-language question.

    Tokenizes the question, strips possessives, and tries contiguous 3-word,
    2-word, then 1-word subsequences through the resolver. Returns the first
    definite match (exact, exact_last, fuzzy). If only ambiguous results are
    found, returns those for disambiguation. If nothing matches, returns
    (None, None).

    Args:
        question: Natural-language question containing a pitcher name.

    Returns:
        Tuple of (matched_query, ResolveResult) on success, or (None, result)
        for ambiguous, or (None, None) for not found.
    """
    # Tokenize and strip possessives, tracking capitalization
    words = question.split()
    cleaned: list[str] = []
    is_capitalized: list[bool] = []
    for idx, word in enumerate(words):
        # Remove trailing punctuation for matching, but keep the word itself
        w = re.sub(r"[?.!,;:]+$", "", word)
        # Strip possessives: "Cease's" -> "Cease", "Cease'" -> "Cease"
        w = re.sub(r"'s$", "", w)
        w = re.sub(r"'$", "", w)
        if w:
            cleaned.append(w)
            # Track if word was capitalized (proper noun indicator);
            # skip first word since sentence-initial caps are unreliable
            is_capitalized.append(idx > 0 and w[0].isupper())

    best_ambiguous: tuple[str | None, ResolveResult | None] = (None, None)

    # Try progressively shorter phrases: 3-word, 2-word, 1-word
    # Exact/exact_last matches are always accepted (high confidence).
    # Fuzzy and ambiguous results require at least one capitalized word
    # in the candidate phrase (proper noun heuristic) to avoid false
    # positives like "about" -> "Abbott" or "Tell me" -> ambiguous.
    for width in (3, 2, 1):
        for i in range(len(cleaned) - width + 1):
            candidate = " ".join(cleaned[i : i + width])
            result = resolve(candidate)
            if result.match_type in ("exact", "exact_last"):
                return (candidate, result)
            # For fuzzy/ambiguous, check capitalization:
            # - Single words: must be capitalized (proper noun heuristic)
            # - Multi-word: ALL words must be capitalized (e.g., "Dylan Cease"
            #   yes, "Johnson pitching" no -- "pitching" isn't a name)
            if width == 1:
                has_capital = is_capitalized[i]
            else:
                has_capital = all(is_capitalized[i + j] for j in range(width) if i + j < len(is_capitalized))
            if result.match_type == "fuzzy" and has_capital:
                return (candidate, result)
            if result.match_type == "ambiguous" and best_ambiguous[1] is None and has_capital:
                best_ambiguous = (None, result)

    # Return best ambiguous result or (None, None)
    return best_ambiguous
