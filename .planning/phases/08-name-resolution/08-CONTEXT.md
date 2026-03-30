# Phase 8: Name Resolution - Context

**Gathered:** 2026-03-30
**Status:** Ready for planning

<domain>
## Phase Boundary

Build `resolver.py` — a fuzzy pitcher name resolution module. Users provide a name string (partial, full, or last-name-only) and get back a pitcher ID, or a ranked disambiguation list when multiple pitchers match. This is a pure-Python module with zero LLM dependencies, independently testable, and consumed by the Phase 10 CLI.

</domain>

<decisions>
## Implementation Decisions

### Matching Strategy
- Tiered pipeline: normalize → exact match → case-insensitive exact → rapidfuzz fallback
- Fuzzy score cutoff: 70 (filters garbage while catching typos like "Cese" → "Cease")
- Scorer: `fuzz.WRatio` (handles partial matches, reordering, substrings)
- Max disambiguation candidates: 5

### Input Formats & Normalization
- Support all common formats: "Cease", "Dylan Cease", "cease, dylan", "cease"
- Unicode normalization via `unicodedata.normalize('NFKD')` + strip combining marks ("Acuña" matches "Acuna")
- Use `nameparser` library for suffix handling ("Acuña Jr" → "Acuña" for matching)

### Module Design
- Data source: Statcast parquet `player_name` + `pitcher` columns (1,651 unique pitchers, "Last, First" format)
- Return type: Dataclass `ResolveResult(pitcher_id, pitcher_name, candidates, match_type)` — typed and testable
- Lookup table: Built lazily on first call, cached in module-level variable (~50ms from parquet)
- Dependencies: Add `rapidfuzz` and `nameparser` as hard dependencies in pyproject.toml

### Claude's Discretion
- Internal matching function signatures and helper decomposition
- Test fixture strategy (real parquet vs synthetic data)
- Error message wording for "not found" results

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `data.py` already loads statcast parquet filtered by pitcher ID — the same parquet is the name lookup source
- `player_name` column format is "Last, First" (e.g., "Cease, Dylan") — 1,651 unique pitchers
- 168 duplicate last-name families (Rodriguez: 12, Garcia: 11, Anderson: 9, Smith: 9)
- 71 pitchers have accented characters in names

### Established Patterns
- All modules use dataclasses or Pydantic models for structured returns
- `data.py` loads parquet with `pl.scan_parquet().filter().collect()` pattern
- Error handling uses specific exception types (not bare except)

### Integration Points
- Consumed by Phase 10 CLI (`ask_cli.py`) which passes resolved pitcher_id to `data.load_pitcher_data()`
- Does NOT modify `data.py` or any existing module
- New file: `src/pitcher_narratives/resolver.py`

</code_context>

<specifics>
## Specific Ideas

- User explicitly requested `nameparser` for name normalization (not just regex)
- Unicode normalization is mandatory — 71 accented names in dataset
- The resolver should work with the "Last, First" format stored in parquet AND the "First Last" format users will type

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>
