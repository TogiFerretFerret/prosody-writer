import pytest
from prosody_writer.engine import Scanner
from prosody_writer.graph import ScansionDAG
from prosody_writer.runtime import prosodic
from prosodic.parsing.utils import get_possible_scansions


@pytest.mark.parametrize("limits", [(1, 1), (1, 2), (2, 2), (3, 2)])
def test_graph_matches_full_enumeration_and_order(limits):
    s, w = limits
    dag = ScansionDAG(s, w)
    for length in range(1, 13):
        assert dag.paths(length) == get_possible_scansions(length, max_s=s, max_w=w)
    before = dag.layers_added
    dag.paths(4)
    assert dag.layers_added == before
    dag.paths(13)
    assert dag.layers_added == before + 1


@pytest.mark.parametrize("line", [
    "Shall I compare thee to a summer's day?",
    "Thou art more lovely and more temperate:",
    "To be, or not to be",
    "The fire is bright",
    "I see 3 birds -- and rain.",
    "A horse! A horse!",
])
def test_matches_full_prosodic(line):
    scanner = Scanner()
    actual = scanner.update(line)["lines"][0]
    full = prosodic.Text(line, lang="en")
    full.parse()
    expected = full.line1.best_parse
    assert actual["status"] == "ok"
    assert actual["scansion"] == expected.meter_str
    assert actual["score"] == float(expected.score)
    assert actual["violations"] == dict(expected.viold)
    assert [s["ipa"] for s in actual["syllables"]] == [slot.unit.ipa for p in expected.positions for slot in p.children]


def test_typing_deletion_and_midline_edits():
    scanner = Scanner()
    fixed = "Shall I compare thee to a summer's day?"
    for line in ["To be", "To be or", "To be or not", "To be", "To sing", "To sing, or not to be"]:
        result = scanner.update(fixed + "\n" + line)
        assert result["lines"][1]["status"] == "ok"
        full = prosodic.Text(line, lang="en")
        full.parse()
        assert result["lines"][1]["scansion"] == full.line1.best_parse.meter_str
        assert result["work"]["parsed_lines"] <= (2 if line == "To be" else 1)
    repeat = scanner.update(fixed + "\nTo sing, or not to be")
    assert repeat["work"] == {"new_words": 0, "parsed_lines": 0, "graph_layers_added": 0}


def test_word_data_matches_full_frame():
    from pandas.testing import assert_frame_equal
    line = "The fire burns -- does it?"
    scanner = Scanner()
    actual = scanner.frame(line)
    expected = prosodic.Text(line, lang="en")._syll_df
    assert_frame_equal(actual, expected, check_dtype=False)


def test_empty_partial_and_limits():
    s = Scanner()
    result = s.update("\n \n...\nrose\n" + "rose " * 25)
    assert [l["status"] for l in result["lines"]] == ["empty", "empty", "partial", "partial", "limit"]


def test_out_of_dictionary_word_uses_espeak():
    scanner = Scanner()
    df = scanner.frame("florple moon")
    assert df[df.word_txt.str.strip() == "florple"].num_forms.min() > 0
