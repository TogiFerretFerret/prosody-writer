import pytest
from prosody_writer.analysis import (assign_rhymes, classify_meter, clean_ipa, detect_form,
                                     nucleus_of, rhyme_kind, rhyme_key, split_onset, sound_devices)
from prosody_writer.dp import Syllable
from prosody_writer.engine import Scanner


def syl(ipa, stressed=False, function=False):
    return Syllable(ipa, ipa, stressed, True, stressed, function)


@pytest.mark.parametrize("pattern,label,variants", [
    ("-+-+-+-+-+", "iambic pentameter", []),
    ("-+-+-+-+-+-", "iambic pentameter", ["feminine ending"]),
    ("-+-+-+-+", "iambic tetrameter", []),
    ("+-+-+-+-", "trochaic tetrameter", []),
    ("+-+-+-+", "trochaic tetrameter", ["catalectic"]),
    ("--+--+--+", "anapestic trimeter", []),
    ("+--+--+--+--", "dactylic tetrameter", []),
])
def test_meter_names(pattern, label, variants):
    meter = classify_meter(pattern)
    assert meter["label"] == label
    assert meter["variants"] == variants


def test_first_foot_inversion_is_reported_not_rejected():
    meter = classify_meter("+--+-+-+-+")
    assert meter["label"] == "iambic pentameter"
    assert meter["deviations"] == [{"foot": 1, "pattern": "+-", "name": "trochee"},
                                   {"foot": 2, "pattern": "-+", "name": "iamb"}] or \
        meter["deviations"][0]["name"] == "trochee"


def test_irregular_and_tiny_lines_are_unnamed():
    assert classify_meter("++++++++") is None
    assert classify_meter("-+") is None


def test_ipa_helpers():
    assert clean_ipa("'deɪ") == "deɪ"
    assert split_onset("streɪt") == ("str", "eɪt")
    assert nucleus_of("eɪt") == ("eɪ", "t")
    assert clean_ipa("ˈfaɪɚ") == "faɪər"


def key(word, *syllables):
    return rhyme_key(word, list(syllables))


def test_perfect_rhyme_needs_a_different_onset():
    day, may, dey = key("day", syl("deɪ", True)), key("may", syl("meɪ", True)), key("dey", syl("deɪ", True))
    assert rhyme_kind(day, may) == "perfect"
    assert rhyme_kind(day, dey) == "identical"


def test_feminine_rhyme_uses_the_stressed_syllable_onward():
    a = key("tender", syl("tɛn", True), syl("dər"))
    b = key("slender", syl("slɛn", True), syl("dər"))
    c = key("render", syl("rɛn", True), syl("də"))
    assert rhyme_kind(a, b) == "perfect"
    assert a["from"] == 0 and a["tail"] == "ɛndər"
    assert rhyme_kind(a, c) in ("assonant", "consonant")


def test_near_rhymes():
    assert rhyme_kind(key("day", syl("deɪ", True)), key("date", syl("deɪt", True))) == "assonant"
    assert rhyme_kind(key("kid", syl("kɪd", True)), key("mud", syl("mʌd", True))) == "consonant"
    assert rhyme_kind(key("cat", syl("kæt", True)), key("dog", syl("dɔg", True))) is None


def test_a_weak_echo_does_not_steal_a_line_from_its_perfect_rhyme():
    keys = [key("day", syl("deɪ", True)), key("date", syl("deɪt", True)),
            key("fade", syl("feɪd", True)), key("shade", syl("ʃeɪd", True))]
    rhymes = assign_rhymes(keys)
    assert [r["letter"] for r in rhymes[2:]] == [rhymes[2]["letter"]] * 2
    assert rhymes[2]["letter"] != rhymes[0]["letter"]


def test_unrhymed_lines_are_flagged_and_gaps_are_skipped():
    rhymes = assign_rhymes([key("day", syl("deɪ", True)), None, key("cat", syl("kæt", True))])
    assert rhymes[1] is None
    assert all(r["unrhymed"] for r in (rhymes[0], rhymes[2]))


def test_sound_devices_ignore_repeated_words():
    words = [("fair", [syl("fɛr", True)]), ("fair", [syl("fɛr", True)]),
             ("hot", [syl("hɑt", True)]), ("heaven", [syl("hɛ", True), syl("vən")])]
    alliteration, assonance = sound_devices(words)
    assert alliteration == [{"sound": "h", "words": ["hot", "heaven"]}]
    assert any(group["sound"] == "ɛ" for group in assonance)


@pytest.mark.parametrize("letters,counts,expected", [
    ("ABABCDCDEFEFGG", [10] * 14, "Sonnet (Shakespearean rhyme scheme)"),
    ("ABBAABBACDECDE", [10] * 14, "Sonnet (Petrarchan rhyme scheme)"),
    ("AABBA", [9, 9, 6, 6, 9], "Limerick"),
    ("ABC", [5, 7, 5], "Haiku"),
    ("AABBCC", [8] * 6, "Rhyming couplets"),
])
def test_form_detection(letters, counts, expected):
    assert detect_form(list(letters), counts, [None] * len(letters), [len(letters)]) == expected


def test_quatrain_and_terza_rima_shapes():
    assert detect_form(list("ABABCDCD"), [8] * 8, [None] * 8, [4, 4]) == "Quatrains, alternate rhyme"
    assert detect_form(list("ABABCBCDCDED"), [10] * 12, [None] * 12, [3, 3, 3, 3]) == "Terza rima"


SONNET_18 = """Shall I compare thee to a summer's day?
Thou art more lovely and more temperate:
Rough winds do shake the darling buds of May,
And summer's lease hath all too short a date;
Sometime too hot the eye of heaven shines,
And often is his gold complexion dimm'd;
And every fair from fair sometime declines,
By chance or nature's changing course untrimm'd;
But thy eternal summer shall not fade,
Nor lose possession of that fair thou ow'st;
Nor shall death brag thou wander'st in his shade,
When in eternal lines to time thou grow'st:
So long as men can breathe or eyes can see,
So long lives this, and this gives life to thee."""


def test_sonnet_18_end_to_end():
    result = Scanner().update(SONNET_18)
    analysis = result["analysis"]
    assert analysis["scheme"] == "ABABCDCDEFEFGG"
    assert analysis["form"] == "Shakespearean sonnet"
    assert analysis["meter"]["label"] == "iambic pentameter"
    assert analysis["lines"] == 14 and analysis["stanzas"] == 1
    assert all(line["syllable_count"] == len(line["syllables"]) for line in result["lines"])
    last = result["lines"][-1]
    assert [w["text"] for w in last["words"]][-1] == "thee"
    assert last["words"][-1]["end"] == last["syllable_count"]
    assert last["rhyme"]["letter"] == "G" and last["rhyme"]["kind"] == "perfect"


def test_stanza_breaks_and_haiku():
    scanner = Scanner()
    result = scanner.update("An old silent pond\nA frog jumps into the pond\nSplash silence again")
    assert result["analysis"]["form"] == "Haiku"
    broken = scanner.update("The day was long\nThe night was long\n\nThe day was long\nThe night was long")
    assert broken["analysis"]["stanzas"] == 2


def test_incomplete_poems_get_no_scheme_or_form():
    result = Scanner().update("The cat sat on the mat\nHi")
    assert result["analysis"]["scheme"] == "" and result["analysis"]["form"] is None
