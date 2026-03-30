# Phase 8: Name Resolution - Research

**Researched:** 2026-03-30
**Domain:** Fuzzy string matching, name parsing, pitcher ID lookup from Statcast parquet
**Confidence:** HIGH

## Summary

Phase 8 builds a standalone `resolver.py` module that translates human-typed pitcher names into numeric MLB pitcher IDs. The dataset contains 1,651 unique pitchers in "Last, First" format within a 19.6MB Statcast parquet file. Key challenges are: (1) 168 duplicate last-name families (Rodriguez has 12 entries), (2) 71 names with accented/unicode characters, (3) 10 names with suffixes (Jr., II, III, IV), and (4) user input arriving in multiple formats (first-last, last-first, last-only, typos).

The locked decisions prescribe a tiered pipeline: normalize, exact match, case-insensitive exact, then rapidfuzz fallback with WRatio scorer at a 70 score cutoff. Both `rapidfuzz` (3.14.3) and `nameparser` (1.1.3) have been verified to work with Python 3.14 and to correctly handle the dataset's name formats. Performance is excellent -- fuzzy matching against all 1,651 pitchers completes in 1-3ms per query.

**Primary recommendation:** Build the lookup table with TWO indexes -- a full-name index ("first last" normalized form) for exact/fuzzy matching AND a separate last-name-only index for single-word queries and typo correction. This dual-index approach is critical because WRatio scoring on full "first last" strings misses obvious typos like "Cese" -> "Cease" (scores 67.5, below the 70 cutoff), while matching against last names alone catches them (scores 89).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Tiered pipeline: normalize -> exact match -> case-insensitive exact -> rapidfuzz fallback
- Fuzzy score cutoff: 70 (filters garbage while catching typos like "Cese" -> "Cease")
- Scorer: `fuzz.WRatio` (handles partial matches, reordering, substrings)
- Max disambiguation candidates: 5
- Support all common formats: "Cease", "Dylan Cease", "cease, dylan", "cease"
- Unicode normalization via `unicodedata.normalize('NFKD')` + strip combining marks ("Acuna" matches "Acuna")
- Use `nameparser` library for suffix handling ("Acuna Jr" -> "Acuna" for matching)
- Data source: Statcast parquet `player_name` + `pitcher` columns (1,651 unique pitchers, "Last, First" format)
- Return type: Dataclass `ResolveResult(pitcher_id, pitcher_name, candidates, match_type)` -- typed and testable
- Lookup table: Built lazily on first call, cached in module-level variable (~50ms from parquet)
- Dependencies: Add `rapidfuzz` and `nameparser` as hard dependencies in pyproject.toml
- New file: `src/pitcher_narratives/resolver.py`
- Does NOT modify `data.py` or any existing module

### Claude's Discretion
- Internal matching function signatures and helper decomposition
- Test fixture strategy (real parquet vs synthetic data)
- Error message wording for "not found" results

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RESOLVE-01 | User can identify a pitcher by partial name, full name, or last name (fuzzy matching via rapidfuzz) | Verified: tiered pipeline with dual-index (full-name + last-name) handles all input formats. rapidfuzz WRatio at cutoff 70 catches typos and partial matches. nameparser normalizes "Last, First" and suffix formats. |
| RESOLVE-02 | User sees a disambiguation list when multiple pitchers match (e.g., "Johnson" -> candidates) | Verified: `process.extract(limit=5)` returns ranked candidates with scores. 168 last-name families have duplicates (Rodriguez: 12, Johnson: 8). Return type `ResolveResult.candidates` carries the list. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| rapidfuzz | 3.14.3 | Fuzzy string matching with WRatio scorer | C++ backed, 10-100x faster than thefuzz/fuzzywuzzy. Supports score_cutoff for early exit. Python 3.14 wheels available. |
| nameparser | 1.1.3 | Parse human names into first/last/suffix components | Handles "Last, First" format, extracts Jr/Sr/II/III/IV suffixes. Pure Python, stable since 2023. |
| polars | >=1.39.3 (already installed) | Read parquet for pitcher name lookup table | Already used by data.py. Provides fast parquet I/O for the 19.6MB statcast file. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| unicodedata (stdlib) | N/A | NFKD normalization to strip diacritics | Always -- 71 names have accented characters. Used in normalization layer. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| rapidfuzz WRatio | rapidfuzz token_set_ratio | token_set_ratio gives 100 for any subset match (too loose for names). WRatio balances multiple strategies. |
| nameparser | Manual regex | nameparser handles Jr/Sr/II/III/IV and "Last, First" parsing robustly. Regex would need to cover many edge cases. |
| Module-level cache | functools.lru_cache | Module-level is simpler; there is exactly one lookup table, never invalidated. LRU cache adds needless complexity. |

**Installation:**
```bash
uv add rapidfuzz nameparser
```

**Version verification:** Confirmed via PyPI on 2026-03-30:
- rapidfuzz 3.14.3 (released 2025-11-01, Python 3.14 classifier present)
- nameparser 1.1.3 (released 2023-09-21, pure Python, works on 3.14)

## Architecture Patterns

### Recommended Project Structure
```
src/pitcher_narratives/
    resolver.py          # NEW -- name resolution module
    data.py              # UNCHANGED -- parquet/CSV loading
    cli.py               # UNCHANGED (Phase 10 will add ask_cli.py)
    context.py           # UNCHANGED
    ...
```

### Pattern 1: Dual-Index Lookup Table
**What:** Build two dict-based indexes on first call: (1) normalized "first last" -> (pitcher_id, original_name), (2) normalized last-name-only -> list[(pitcher_id, original_name)]. Cache both at module level.
**When to use:** Always. Single-word queries ("Cease", "Rodriguez") need the last-name index for exact matching. Multi-word queries ("Dylan Cease") use the full-name index.
**Why critical:** Verified empirically -- WRatio("cese", "dylan cease") = 67.5 (below 70 cutoff), but WRatio("cese", "cease") = 88.9. Without the last-name index, common typos fail to resolve.

**Example:**
```python
# Source: Empirically verified against statcast_2026.parquet
_name_table: _NameTable | None = None

@dataclass
class _NameTable:
    full_index: dict[str, tuple[int, str]]    # "dylan cease" -> (656302, "Cease, Dylan")
    last_index: dict[str, list[tuple[int, str]]]  # "cease" -> [(656302, "Cease, Dylan")]

def _build_name_table() -> _NameTable:
    global _name_table
    if _name_table is not None:
        return _name_table
    df = pl.read_parquet(PARQUET_PATH, columns=["pitcher", "player_name"])
    unique = df.unique(subset=["pitcher"])
    # ... build both indexes
    _name_table = _NameTable(full_index=full, last_index=last)
    return _name_table
```

### Pattern 2: Tiered Resolution Pipeline
**What:** Process queries through increasingly fuzzy tiers, stopping at the first match.
**When to use:** Every resolution call.

**Example:**
```python
# Source: Locked decision from CONTEXT.md + empirical tuning
def resolve(query: str) -> ResolveResult:
    table = _build_name_table()
    normalized = _normalize(query)

    # Tier 1: Exact full-name match
    if normalized in table.full_index:
        pid, name = table.full_index[normalized]
        return ResolveResult(pitcher_id=pid, pitcher_name=name, candidates=[], match_type="exact")

    # Tier 2: Exact last-name match
    if normalized in table.last_index:
        entries = table.last_index[normalized]
        if len(entries) == 1:
            pid, name = entries[0]
            return ResolveResult(pitcher_id=pid, pitcher_name=name, candidates=[], match_type="exact_last")
        return ResolveResult(pitcher_id=None, pitcher_name=None,
                           candidates=entries[:5], match_type="ambiguous")

    # Tier 3: Fuzzy match on full names
    fuzzy_full = process.extract(normalized, table.full_index.keys(),
                                 scorer=fuzz.WRatio, limit=5, score_cutoff=70)
    if fuzzy_full:
        # ... return best or candidates

    # Tier 4: Fuzzy match on last names only (catches typos)
    fuzzy_last = process.extract(normalized, list(set(table.last_index.keys())),
                                 scorer=fuzz.WRatio, limit=5, score_cutoff=70)
    if fuzzy_last:
        # ... expand to full entries, deduplicate, return

    return ResolveResult(pitcher_id=None, pitcher_name=None,
                        candidates=[], match_type="not_found")
```

### Pattern 3: Input Normalization with nameparser
**What:** Normalize user input before matching: use nameparser to handle "Last, First" and suffix variants, then apply unicode NFKD + case folding.
**When to use:** Before every comparison.

**Example:**
```python
# Source: Verified against dataset name formats
def _normalize(raw: str) -> str:
    parsed = HumanName(raw)
    if parsed.last:
        # Reconstruct as "first last" (no suffix) for matching
        name = f"{parsed.first} {parsed.last}".strip()
    else:
        # Single word -- could be first or last name
        name = parsed.first
    # Unicode normalization
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_only = "".join(c for c in nfkd if not unicodedata.combining(c))
    return ascii_only.lower().strip()
```

### Anti-Patterns to Avoid
- **Matching against raw "Last, First" format:** Users type "Dylan Cease" not "Cease, Dylan". Always convert stored names to "First Last" before building the index.
- **Single-index fuzzy only:** WRatio on "first last" strings misses single-word typos. Must have a separate last-name fuzzy tier.
- **Using fuzz.ratio directly:** Too strict for name matching where word order varies. WRatio adapts its strategy based on string lengths.
- **Sorting candidates by score alone:** When multiple candidates tie (e.g., 8 Johnsons all score 90.0), results are non-deterministic. Sort by (score desc, name asc) for stable output.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Fuzzy string matching | Custom edit-distance | `rapidfuzz.fuzz.WRatio` + `process.extract` | Handles partial matches, reordering, substrings automatically. C++ performance. |
| Name parsing (suffix/format) | Regex for Jr/Sr/III | `nameparser.HumanName` | Handles 10+ suffix variants, "Last, First" format, multi-word last names ("De Leon"). |
| Unicode normalization | Manual character mapping | `unicodedata.normalize('NFKD')` + combining char strip | stdlib, handles all Unicode edge cases. Verified: "Munoz" matches "Munoz" correctly. |
| Parquet column extraction | CSV export / manual parsing | `polars.read_parquet(columns=["pitcher", "player_name"])` | Already used project-wide. Column projection minimizes I/O. |

**Key insight:** The combination of nameparser + unicodedata + rapidfuzz covers ALL the normalization and matching complexity. There are no cases in this dataset that require additional custom logic.

## Common Pitfalls

### Pitfall 1: Single-Word Input Ambiguity
**What goes wrong:** `nameparser.HumanName("Cease")` puts "Cease" in `.first`, not `.last`. The resolver would look for a first name "Cease" and miss.
**Why it happens:** nameparser treats single-word input as a first name by default.
**How to avoid:** For single-word inputs (where `parsed.last` is empty), match against BOTH the full-name index AND the last-name index. Treat the single word as a potential last name.
**Warning signs:** Any query with one word returns "not found" when it should match.

### Pitfall 2: WRatio Cutoff Too Low for Full-Name Typos
**What goes wrong:** Typo "Cese" matches "dylan cease" at only 67.5 (below 70 cutoff) because WRatio penalizes length mismatch.
**Why it happens:** WRatio divides score by string length ratio. "cese" (4 chars) vs "dylan cease" (11 chars) has a large ratio.
**How to avoid:** Add a dedicated fuzzy-on-last-names tier AFTER fuzzy-on-full-names. Last-name-only matching: WRatio("cese", "cease") = 88.9.
**Warning signs:** Short typos of last names return "not found" or wrong matches.

### Pitfall 3: Suffix Mismatch Blocking Exact Matches
**What goes wrong:** User types "Mark Leiter" but dataset has "Leiter Jr., Mark". Exact match fails.
**Why it happens:** The dataset stores names WITH suffixes. Matching must strip suffixes from both sides.
**How to avoid:** Use nameparser on BOTH the stored names (when building the index) and user input. Build the index without suffixes. Stored "Leiter Jr., Mark" -> indexed as "mark leiter".
**Warning signs:** Pitchers with Jr/Sr/II/III/IV are never found by exact match.

### Pitfall 4: "Casey" Matches When User Searches "Cease"
**What goes wrong:** WRatio("cease", "casey mize") = 80.0, which beats WRatio("cease", "dylan cease") = 90.0 in some configurations but the Casey matches appear first in lexicographic sorting.
**Why it happens:** "cease" is a substring of "casey" when letters are rearranged. WRatio is aggressive about partial matching.
**How to avoid:** When exact last-name match exists (Tier 2), return it immediately. Only fall through to fuzzy when no exact last-name match is found. The tiered pipeline already handles this.
**Warning signs:** Exact last-name searches return unexpected fuzzy matches.

### Pitfall 5: Non-Deterministic Disambiguation Order
**What goes wrong:** "Rodriguez" returns 12 candidates. With `limit=5`, which 5 appear depends on dict iteration order.
**Why it happens:** rapidfuzz may return ties in arbitrary order. Python dicts maintain insertion order but parquet row order is not guaranteed.
**How to avoid:** After getting candidates, sort by (score descending, name ascending) for deterministic output. Document this sort order.
**Warning signs:** Same query returns different candidate lists across runs.

## Code Examples

Verified patterns from empirical testing against the dataset:

### Building the Lookup Table from Parquet
```python
# Source: Verified against statcast_2026.parquet (1,651 unique pitchers)
import polars as pl
from nameparser import HumanName

df = pl.read_parquet(PARQUET_PATH, columns=["pitcher", "player_name"])
unique = df.unique(subset=["pitcher"])

full_index: dict[str, tuple[int, str]] = {}
last_index: dict[str, list[tuple[int, str]]] = {}

for row in unique.iter_rows(named=True):
    original = row["player_name"]      # "Cease, Dylan"
    pid = row["pitcher"]               # 656302
    parsed = HumanName(original)       # first='Dylan', last='Cease', suffix=''
    full_norm = _normalize(f"{parsed.first} {parsed.last}")  # "dylan cease"
    last_norm = _normalize(parsed.last)                       # "cease"
    full_index[full_norm] = (pid, original)
    last_index.setdefault(last_norm, []).append((pid, original))
```

### Unicode Normalization Function
```python
# Source: Verified against 71 accented names in dataset
import unicodedata

def _strip_diacritics(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))

# "Munoz, Andres" -> matches "Munoz, Andres"
assert _strip_diacritics("Munoz") == "Munoz"
# "Berrios, Jose" -> matches "Berrios, Jose"
assert _strip_diacritics("Berrios") == "Berrios"
```

### Fuzzy Matching with process.extract
```python
# Source: Verified with rapidfuzz 3.14.3 against dataset
from rapidfuzz import fuzz, process

results = process.extract(
    query="Johnson",
    choices=list(last_index.keys()),  # all normalized last names
    scorer=fuzz.WRatio,
    limit=5,
    score_cutoff=70,
)
# Returns: [("johnson", 100.0, idx), ...]
# Each match expands to multiple pitchers via last_index["johnson"]
```

### ResolveResult Dataclass
```python
# Source: Locked decision from CONTEXT.md
from dataclasses import dataclass

@dataclass
class ResolveResult:
    pitcher_id: int | None          # Resolved ID (None if ambiguous/not found)
    pitcher_name: str | None        # Original "Last, First" name (None if ambiguous/not found)
    candidates: list[tuple[int, str]]  # [(pitcher_id, name), ...] for disambiguation
    match_type: str                 # "exact" | "exact_last" | "fuzzy" | "ambiguous" | "not_found"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| fuzzywuzzy (Python-only) | rapidfuzz (C++ backed) | 2020+ | 10-100x faster, MIT licensed, actively maintained |
| thefuzz (fuzzywuzzy fork) | rapidfuzz | 2021+ | rapidfuzz is the ecosystem standard for new projects |
| Manual Levenshtein | rapidfuzz.distance.Levenshtein | N/A | rapidfuzz bundles multiple distance metrics in one package |

**Deprecated/outdated:**
- `fuzzywuzzy`: Unmaintained, GPL license issues, Python-only (slow)
- `thefuzz`: Fork of fuzzywuzzy, still Python-only, less actively maintained than rapidfuzz
- `difflib.get_close_matches`: stdlib but much slower and less configurable than rapidfuzz

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_resolver.py -x` |
| Full suite command | `uv run pytest tests/ -x` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RESOLVE-01a | Exact full name "Dylan Cease" returns correct pitcher ID | unit | `uv run pytest tests/test_resolver.py::test_exact_full_name -x` | Wave 0 |
| RESOLVE-01b | Case-insensitive "dylan cease" matches | unit | `uv run pytest tests/test_resolver.py::test_case_insensitive -x` | Wave 0 |
| RESOLVE-01c | Last-name-only "Cease" returns correct pitcher | unit | `uv run pytest tests/test_resolver.py::test_last_name_only -x` | Wave 0 |
| RESOLVE-01d | Comma-separated "cease, dylan" matches | unit | `uv run pytest tests/test_resolver.py::test_comma_format -x` | Wave 0 |
| RESOLVE-01e | Unicode "Munoz" matches "Munoz, Andres" | unit | `uv run pytest tests/test_resolver.py::test_unicode_normalization -x` | Wave 0 |
| RESOLVE-01f | Typo "Cese" fuzzy matches "Cease, Dylan" | unit | `uv run pytest tests/test_resolver.py::test_fuzzy_typo -x` | Wave 0 |
| RESOLVE-01g | Suffix "Mark Leiter" matches "Leiter Jr., Mark" | unit | `uv run pytest tests/test_resolver.py::test_suffix_handling -x` | Wave 0 |
| RESOLVE-02a | Ambiguous "Johnson" returns ranked candidates | unit | `uv run pytest tests/test_resolver.py::test_disambiguation_list -x` | Wave 0 |
| RESOLVE-02b | Candidates list has at most 5 entries | unit | `uv run pytest tests/test_resolver.py::test_max_candidates -x` | Wave 0 |
| RESOLVE-02c | Unknown name returns not_found with empty candidates | unit | `uv run pytest tests/test_resolver.py::test_not_found -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_resolver.py -x`
- **Per wave merge:** `uv run pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_resolver.py` -- covers RESOLVE-01 and RESOLVE-02 (all sub-tests above)
- [ ] Dependencies: `uv add rapidfuzz nameparser` -- neither is currently in pyproject.toml

## Sources

### Primary (HIGH confidence)
- [PyPI: RapidFuzz 3.14.3](https://pypi.org/project/RapidFuzz/) - Version, Python 3.14 classifier, release date
- [RapidFuzz Documentation](https://rapidfuzz.github.io/RapidFuzz/) - fuzz.WRatio behavior, process.extract API, score_cutoff parameter
- [PyPI: nameparser 1.1.3](https://pypi.org/project/nameparser/) - Version, API for HumanName, suffix handling
- [GitHub: python-nameparser](https://github.com/derek73/python-nameparser) - "Last, First" format support, suffix behavior
- Empirical verification against `statcast_2026.parquet` - All data statistics (1,651 pitchers, 71 accented, 168 duplicate families, 10 suffixed) and scoring benchmarks

### Secondary (MEDIUM confidence)
- [RapidFuzz GitHub](https://github.com/rapidfuzz/RapidFuzz) - Python 3.14 support added in v3.14.0
- [Medium: All about RapidFuzz](https://medium.com/@shahparthvi22/all-about-rapidfuzz-string-similarity-and-matching-cd26fdc963d8) - WRatio vs token_set_ratio comparison

### Tertiary (LOW confidence)
- None -- all findings verified against official sources or empirical testing.

## Project Constraints (from CLAUDE.md)

- **Tech stack**: Python, polars, pydantic-ai, Claude -- already in pyproject.toml
- **Data format**: Static parquet + CSV files, no live API calls
- **Python version**: 3.14+
- **Naming**: snake_case for modules/functions, PascalCase for classes, dataclasses for structured returns
- **Imports**: Absolute imports, grouped with blank lines, sorted alphabetically
- **Module design**: Use `__all__` for public APIs, prefix internal helpers with `_`
- **Error handling**: Specific exception types, no bare `except:`
- **Docstrings**: Google-style, type hints on all function signatures
- **Testing**: pytest, testpaths = ["tests"]
- **Tooling**: ruff for formatting/linting, config in pyproject.toml

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Both libraries verified on PyPI, empirically tested against real dataset, Python 3.14 compatible
- Architecture: HIGH - Dual-index + tiered pipeline verified empirically. Scoring thresholds tested with real data.
- Pitfalls: HIGH - All pitfalls discovered through empirical testing against the actual parquet file. Quantified with specific score values.

**Research date:** 2026-03-30
**Valid until:** 2026-04-30 (stable domain -- string matching libraries change slowly)
