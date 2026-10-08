"""Incremental best-scan DP for Prosodic 3.10's default lexical grammar.

All pronunciation branches are consumed word by word, never as a Cartesian
product. Positive additive constraint weights make every global score minimum
harmonically unbounded. We therefore need no all-candidate Pareto comparison
to choose that minimum. Tied minima retain sufficient statistics for Prosodic's
nonlocal ranking keys rather than choosing an arbitrary prefix winner.
"""
from dataclasses import dataclass, replace
from fractions import Fraction
import numpy as np


@dataclass(frozen=True, slots=True)
class Syllable:
    text: str
    ipa: str
    stressed: bool
    heavy: bool
    strong: bool
    functionword: bool

    @classmethod
    def from_row(cls, row):
        return cls(row['syll_text'], row['syll_ipa'], bool(row['is_stressed']),
                   bool(row['is_heavy']), bool(row['is_strong']), bool(row['is_functionword']))


@dataclass(frozen=True, slots=True)
class State:
    tail: tuple = ()          # last three metrical values
    run: int = 0             # size of the open position
    pending_w: int = 0       # weak position before an open strong position
    feet: int = 0            # bitset of CLOSED pseudo-foot types
    match2: int = 0
    match3: int = 0
    length: int = 0
    functionword: bool = False


@dataclass(frozen=True, slots=True)
class Trace:
    previous: object
    syllable: Syllable
    strong: bool
    violations: tuple


@dataclass(frozen=True, slots=True)
class Label:
    score: int = 0
    ss: int = 0
    ww: int = 0
    content: int = 0
    forms: tuple = ()
    trace: object = None

    @property
    def merge_key(self):
        return self.score, self.ss, self.ww, self.content, self.forms


def violations(syllable, previous, same_word, strong, extending):
    """Exact local formulas used by Prosodic's vectorized default constraints."""
    values = {}
    if not strong:
        if syllable.strong:
            values['w_peak'] = 1
        if syllable.stressed:
            values['w_stress'] = 1
    elif not syllable.stressed:
        values['s_unstress'] = 1
    if extending:
        if same_word:
            if previous.heavy or not previous.stressed:
                values['unres_within'] = 1
        elif strong or not (previous.functionword and syllable.functionword):
            values['unres_across'] = 1
    # foot_size is always zero: position sizes are constrained to 1 or 2.
    return tuple(values.items())


def _foot_bit(weak_size, strong_size):
    return 1 << (weak_size * 2 + strong_size - 1)


def words_from_frame(frame):
    """Adapt full Prosodic pronunciation features without dropping variants."""
    words = []
    for _, rows in frame[frame.is_punc == 0].groupby('word_num', sort=False):
        words.append(tuple(tuple(Syllable.from_row(row) for row in form.to_dict('records'))
                           for _, form in rows.groupby('form_idx', sort=True)))
    return tuple(words)


def _merge(target, state, label):
    old = target.get(state)
    if old is None or label.merge_key < old.merge_key:
        target[state] = label


def _prune(frontier):
    # Score and #ss are the first two ranking criteria. Future costs depend
    # only on the open position and lexical boundary context. A worse pair
    # cannot recover, regardless of regularity/pseudo-foot tie breakers.
    minima = {}
    def base(state):
        return state.tail[-1:] , state.run, state.functionword, min(state.length, 2)
    for state, label in frontier.items():
        key = base(state)
        pair = label.score, label.ss
        if key not in minima or pair < minima[key]:
            minima[key] = pair
    return {state: label for state, label in frontier.items()
            if (label.score, label.ss) == minima[base(state)]}


class IncrementalDP:
    """Word-boundary checkpoints support append and rollback to first edit."""
    def __init__(self):
        self.words = ()
        self.checkpoints = [{State(): Label()}]
        self.transitions = 0
        self.peak_states = 1
        self.reused_words = 0
        self.words_evaluated = 0

    def _consume(self, frontier, syllable, previous_in_word):
        out = {}
        for state, label in frontier.items():
            for strong in (False, True):
                extending = bool(state.tail and strong == state.tail[-1])
                if extending and state.run == 2:
                    continue
                feet, pending = state.feet, state.pending_w
                if state.tail and not extending:
                    if state.tail[-1]:
                        feet |= _foot_bit(pending, state.run)
                        pending = 0
                    else:
                        pending = state.run
                previous = previous_in_word
                if previous is None:
                    # Only functionword is consulted at a cross-word boundary.
                    previous = Syllable('', '', False, False, False, state.functionword)
                v = violations(syllable, previous, previous_in_word is not None, strong, extending)
                next_state = State(
                    (state.tail + (strong,))[-3:], state.run + 1 if extending else 1,
                    pending, feet,
                    state.match2 + int(len(state.tail) >= 2 and strong == state.tail[-2]),
                    state.match3 + int(len(state.tail) >= 3 and strong == state.tail[-3]),
                    state.length + 1, syllable.functionword)
                next_label = Label(label.score + len(v),
                                   label.ss + int(extending and strong),
                                   label.ww + int(extending and not strong),
                                   label.content * 2 + int(strong), label.forms,
                                   Trace(label.trace, syllable, strong, v))
                _merge(out, next_state, next_label)
                self.transitions += 1
        out = _prune(out)
        self.peak_states = max(self.peak_states, len(out))
        return out

    def update(self, words):
        """words = tuple[word[pronunciation[syllable]]]; all alternatives kept."""
        words = tuple(words)
        prefix = 0
        for old, new in zip(self.words, words):
            if old != new:
                break
            prefix += 1
        self.reused_words = prefix
        self.words_evaluated = len(words) - prefix
        self.checkpoints = self.checkpoints[:prefix + 1]
        frontier = self.checkpoints[-1]
        for forms in words[prefix:]:
            merged = {}
            for choice, form in enumerate(forms):
                branch = {s: replace(label, forms=label.forms + (choice,))
                          for s, label in frontier.items()}
                for i, syllable in enumerate(form):
                    branch = self._consume(branch, syllable, form[i - 1] if i else None)
                for state, label in branch.items():
                    _merge(merged, state, label)
            frontier = _prune(merged)
            self.peak_states = max(self.peak_states, len(frontier))
            self.checkpoints.append(frontier)
        self.words = words
        # Prosodic's ragged comparator treats short mixed-length readings
        # differently from the rectangular comparator; preserve that detail.
        ragged = any(len({len(form) for form in word}) > 1 for word in words)
        def final_key(item):
            state, label = item
            n = state.length
            regularity = 1.0 - max(state.match2 / (n - 2) if n > 2 else 0,
                                   state.match3 / (n - 3) if n > 3 else 0)
            if not ragged and n < 3:
                regularity = 0
            feet = state.feet
            if state.tail[-1]:
                feet |= _foot_bit(state.pending_w, state.run)
            else:
                feet |= 1 << (6 + state.run - 1)
            return (label.score, label.ss, float(np.float32(regularity)),
                    feet.bit_count(), label.ww, Fraction(label.content, 2 ** n), label.forms)
        candidates = [(s, l) for s, l in frontier.items() if s.length >= 2]
        if not candidates:
            return None
        state, best = min(candidates, key=final_key)
        syllables, counts, trace = [], {}, best.trace
        while trace:
            v = dict(trace.violations)
            for key, count in v.items():
                counts[key] = counts.get(key, 0) + count
            syllables.append({'text': trace.syllable.text, 'ipa': trace.syllable.ipa,
                              'stress': trace.syllable.stressed,
                              'meter': 's' if trace.strong else 'w', 'violations': v})
            trace = trace.previous
        syllables.reverse()
        return {'status': 'ok', 'scansion': ''.join('+' if s['meter'] == 's' else '-' for s in syllables),
                'score': float(best.score), 'violations': counts, 'syllables': syllables}
