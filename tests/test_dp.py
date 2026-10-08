import pytest
from prosody_writer.dp import IncrementalDP, words_from_frame
from prosody_writer.runtime import prosodic

LINES = [
    "Shall I compare thee to a summer's day?",
    "Thou art more lovely and more temperate:",
    "To be, or not to be", "The fire is bright", "A horse! A horse!",
    "Pity the world", "The the the the", "To sing, or not to be",
    "Bright star, would I were steadfast as thou art",
    "Tiger tiger burning bright", "When in the chronicle of wasted time",
    "I see 3 birds -- and rain.", "Our hour of fire", "The moon is a balloon",
]


def compare(line, dp=None):
    text = prosodic.Text(line, lang='en')
    words = words_from_frame(text._syll_df)
    actual = (dp or IncrementalDP()).update(words)
    text.parse()
    best = text.line1.best_parse
    assert actual['score'] == best.score, line
    assert actual['scansion'] == best.meter_str, line
    assert actual['violations'] == dict(best.viold), line
    expected = [(slot.unit.txt, slot.unit.ipa, bool(slot.unit.is_stressed), p.meter_val, dict(slot.viold))
                for p in best.positions for slot in p.children]
    assert [(s['text'], s['ipa'], s['stress'], s['meter'], s['violations'])
            for s in actual['syllables']] == expected, line


@pytest.mark.parametrize('line', LINES)
def test_exact_best_scan(line):
    compare(line)


def test_incremental_append_rollback_and_substitution():
    dp = IncrementalDP()
    for line in ['To be', 'To be or', 'To be or not', 'To be or not to be',
                 'To be or not', 'To be or sing', 'To be or sing to me']:
        compare(line, dp)
    assert dp.reused_words >= 3


def test_append_retains_checkpoint_identity():
    dp = IncrementalDP()
    first = words_from_frame(prosodic.Text('To be or', lang='en')._syll_df)
    dp.update(first)
    checkpoint = dp.checkpoints[-1]
    dp.update(words_from_frame(prosodic.Text('To be or not', lang='en')._syll_df))
    assert dp.checkpoints[len(first)] is checkpoint
    assert dp.words_evaluated == 1
    assert dp.reused_words == len(first)


def test_seeded_synthetic_pronunciation_lattices():
    """Exercise tie statistics and variant lengths against exhaustive pooling."""
    import random
    import pandas as pd
    from prosodic.parsing.vectorized import parse_batch_from_df
    rng = random.Random(72841)
    base = prosodic.Text('moon', lang='en')._syll_df.iloc[0].to_dict()
    for case in range(150):
        rows = []
        for word in range(1, rng.randint(2, 5) + 1):
            nforms = rng.randint(1, 3)
            for form in range(nforms):
                for syll in range(rng.randint(1, 2)):
                    stressed = rng.choice([True, False])
                    row = {**base, 'word_num': word, 'form_idx': form,
                           'num_forms': nforms, 'syll_idx': syll,
                           'syll_text': f'{word}.{form}.{syll}',
                           'syll_ipa': "'mʊn" if stressed else 'mʊn',
                           'is_stressed': stressed, 'is_heavy': rng.choice([True, False]),
                           'is_strong': rng.choice([True, False]),
                           'is_functionword': rng.choice([True, False])}
                    rows.append(row)
        frame = pd.DataFrame(rows)
        actual = IncrementalDP().update(words_from_frame(frame))
        best = parse_batch_from_df(frame, prosodic.Meter())[1].best_parse
        assert actual['score'] == best.score, case
        assert actual['scansion'] == best.meter_str, case
        assert actual['violations'] == dict(best.viold), case
        expected = [slot.unit.txt for position in best.positions for slot in position.children]
        assert [s['text'] for s in actual['syllables']] == expected, case
