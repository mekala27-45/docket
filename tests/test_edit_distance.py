from hypothesis import given
from hypothesis import strategies as st

from packages.evaluation import edit_distance


def reference(left: list[str] | str, right: list[str] | str) -> int:
    previous = list(range(len(right) + 1))
    for i, a in enumerate(left, 1):
        current = [i]
        for j, b in enumerate(right, 1):
            current.append(min(previous[j] + 1, current[-1] + 1, previous[j - 1] + (a != b)))
        previous = current
    return previous[-1]


@given(st.text(max_size=90), st.text(max_size=90))
def test_bit_vectors_match_reference_character_dp(left: str, right: str) -> None:
    assert edit_distance(left, right) == reference(left, right)
    assert edit_distance(right, left) == reference(left, right)


@given(st.lists(st.sampled_from(['total', 'Rp.118.000', 'tax', 'item']), max_size=90),
       st.lists(st.sampled_from(['total', 'Rp.118.000', 'tax', 'item']), max_size=90))
def test_bit_vectors_match_reference_word_dp(left: list[str], right: list[str]) -> None:
    assert edit_distance(left, right) == reference(left, right)


def test_long_strings_cross_machine_word_boundaries() -> None:
    left, right = 'invoice total ' * 100, 'invoice total ' * 99 + 'receipt sum '
    assert edit_distance(left, right) == reference(left, right)
