# Plan: Refactor to All-Bidirectional Connecting Roads

## Current State

Each junction pair (A↔B) currently generates:
- **Straight-through pairs**: 1 bidirectional CR (right + left lane) ✓
- **Turn pairs**: 2 separate unidirectional CRs — one with right lane only, one with left lane only

This leads to reversed-path CRs for left-lane turns (path goes to→from, pred=to_road, succ=from_road), which caused the heading-sign alignment bug (now fixed).

### Numbers (BorasEkas project)

| Metric | Current | After refactor |
|--------|---------|----------------|
| CRs per 3-road junction | 5 | 3 |
| Total CRs | 20 | 12 |
| Unidirectional CRs | 16 | 0 (or few for one-way roads) |
| Path reversals | 8 | 0 |

## Why Bidirectional Works for Turns

Complementary turn pairs (A→B right turn + B→A left turn) follow the **same geometric curve** in opposite directions. A single bidirectional CR with both left and right lanes correctly handles both traffic directions — exactly as straight-through CRs already do.

OpenDRIVE allows this; the spec doesn't restrict connecting roads to unidirectional use.

## Proposed Changes

### 1. `junction_analyzer.py` — `create_connecting_roads_from_patterns`

**Current**: Finds straight pairs for bidirectional CRs, creates unidirectional CRs for everything else.

**Change**: Find **all complementary pairs** (same road pair, opposite directions) regardless of turn type. Use `_create_bidirectional_cr` for all paired patterns. Only fall back to `_create_unidirectional_cr` for unpaired patterns (one-way streets, turn restrictions).

```python
# Instead of only pairing straights:
all_pairs = {}
for pattern in patterns:
    key = tuple(sorted([pattern.from_road_id, pattern.to_road_id]))
    if key not in all_pairs:
        all_pairs[key] = []
    all_pairs[key].append(pattern)

# Create bidirectional CRs for all pairs with 2 complementary patterns
for pair_patterns in all_pairs.values():
    if len(pair_patterns) == 2:
        _create_bidirectional_cr(junction, pair_patterns, endpoint_lookup, ...)
    else:
        for p in pair_patterns:
            _create_unidirectional_cr(junction, p, endpoint_lookup, ...)
```

### 2. `junction_analyzer.py` — `_create_bidirectional_cr`

**Current**: Picks the pattern where `from_endpoint.at_junction == "end"` for the canonical path direction. Computes `conn_left` and `conn_right` from endpoint lane counts.

**Change**: The function already handles the general case. Verify it works for turn pairs:
- Path direction: always from the endpoint at "end" (if one exists) toward the other
- If both endpoints are at "start", pick one canonical direction (e.g., alphabetical road ID)
- Lane counts: `conn_left = max(1, min(...))`, `conn_right = max(1, min(...))` — already correct

Likely no code change needed, but verify with turn geometry.

### 3. `connecting_road_alignment.py`

**Current**: Has heading-sign fix for reversed-path CRs.

**Change**: With no reversed paths, the heading-sign fix becomes a safety net (harmless but rarely triggered). The alignment logic simplifies because `cr.predecessor_id` always matches `conn.from_road_id` for the right-lane direction.

The reversed-path branch (`else: pred_target_lane_id = conn.to_lane_id`) would only trigger for legacy projects or edge cases. Keep it for backward compatibility.

### 4. `opendrive_writer.py` — Export

All the reversed-path fixes we just made become dead code for new imports, but should be kept for backward compatibility with existing `.orbit` files that have unidirectional CRs.

The `contactPoint` fix (derived from topology) is correct regardless of architecture.

### 5. Lane connection generation

**Current**: `_add_lane_connections` generates lane links for each pattern direction separately, using `generate_lane_links_for_connection`.

**Change**: No change needed — the bidirectional CR already handles this by calling `_add_lane_connections` for both patterns in the pair (see existing code in `_create_bidirectional_cr` lines 686–692).

### 6. Turn restrictions

**Current**: Turn restrictions (from OSM relations) filter patterns before CR creation.

**Change**: When a turn restriction forbids A→B but allows B→A, the pair won't have 2 complementary patterns. It falls through to `_create_unidirectional_cr`. Verify this edge case.

### 7. Tests

- Update `test_junction_analyzer.py` to verify bidirectional CRs are created for turn pairs
- Add test: 3-road junction produces exactly 3 CRs (all bidirectional)
- Add test: one-way road produces unidirectional CR (no complement)
- Regression test: existing straight-through bidirectional behavior unchanged

## Risks & Edge Cases

1. **One-way roads**: Only one direction → unpaired pattern → stays unidirectional ✓
2. **Turn restrictions**: May create unpaired patterns → stays unidirectional ✓
3. **Different lane widths per direction**: `_create_bidirectional_cr` already averages widths. Could use `lane_width_start`/`lane_width_end` for transitions.
4. **Existing `.orbit` files**: Already have unidirectional CRs. Old files load fine with the heading-sign fix. New imports would generate bidirectional CRs.
5. **OpenDRIVE viewer compatibility**: Some viewers might render bidirectional turn CRs differently. Test with esmini and ODDLOT.

## Summary

The change is architecturally clean — it generalizes the existing straight-through bidirectional logic to all complementary pairs. The main risk is viewer compatibility with bidirectional turn CRs. The primary code change is ~10 lines in `create_connecting_roads_from_patterns` (replacing the `straight_pairs` filter with an `all_pairs` grouping).
