"""Reciprocal Rank Fusion merges ranked id lists (k=60)."""

from __future__ import annotations

from wikiforge.search.rrf import reciprocal_rank_fusion


def test_single_list_preserves_order() -> None:
    fused = reciprocal_rank_fusion([[3, 1, 2]], k=60)
    assert [i for i, _ in fused] == [3, 1, 2]


def test_item_in_both_lists_outranks_singletons() -> None:
    # id 5 is rank0 in list A and rank1 in list B; ids 9 and 7 appear once each.
    fused = reciprocal_rank_fusion([[5, 9], [7, 5]], k=60)
    assert fused[0][0] == 5  # highest fused score (appears in both)
    scores = dict(fused)
    assert scores[5] > scores[9]
    assert scores[5] > scores[7]


def test_scores_use_k_and_rank() -> None:
    fused = reciprocal_rank_fusion([[1, 2]], k=60)
    scores = dict(fused)
    assert scores[1] == 1 / 60  # rank 0 -> 1/(60+0)
    assert scores[2] == 1 / 61  # rank 1 -> 1/(60+1)


def test_empty_and_ties_are_stable() -> None:
    assert reciprocal_rank_fusion([], k=60) == []
    fused = reciprocal_rank_fusion([[1], [2]], k=60)  # equal scores
    assert {i for i, _ in fused} == {1, 2}
