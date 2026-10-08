"""Reuse token pronunciation blocks and completed line results across edits."""
from functools import lru_cache
from difflib import SequenceMatcher
from time import perf_counter
import pandas as pd
from .runtime import prosodic
from .analysis import assign_rhymes, classify_meter, rhyme_key, sound_devices, summarize
from .dp import IncrementalDP, Syllable
from prosodic.words.tokenizers import tokenize_sentwords_iter
from prosodic.texts.syll_df import build_syll_df

MAX_LINE_CHARS = 300
MAX_LINE_SYLLABLES = 128


class Scanner:
    def __init__(self):
        self.word_builds = 0
        self.line_parses = 0
        self._previous_lines = []
        self._dps = []
        self._current_dp = IncrementalDP()
        self._dp_work = {}
        # Instance-owned bounded caches: no poetry retained after session eviction.
        self.word_rows = lru_cache(maxsize=2048)(self._word_rows)
        self.word_forms = lru_cache(maxsize=2048)(self._word_forms)
        self.scan_line = lru_cache(maxsize=256)(self._scan_line)

    def _word_forms(self, text):
        rows = self.word_rows(text)
        if not rows or rows[0]['is_punc']:
            return ()
        forms = {}
        for row in rows:
            if not row['num_forms']:
                return None
            forms.setdefault(row['form_idx'], []).append(Syllable.from_row(row))
        return tuple(tuple(form) for _, form in sorted(forms.items()))

    def _word_rows(self, text):
        self.word_builds += 1
        token = {"txt": text, "num": 1, **{key: 1 for key in (
            "line_num", "para_num", "sent_num", "sentpart_num", "linepart_num")}}
        return build_syll_df([token], lang="en").to_dict("records")

    def frame(self, line):
        rows = []
        for token in tokenize_sentwords_iter(line):
            for original in self.word_rows(token["txt"]):
                row = dict(original)
                for field in ("line_num", "para_num", "sent_num", "sentpart_num", "linepart_num"):
                    row[field] = token.get(field)
                row["word_num"] = token["num"]
                rows.append(row)
        return pd.DataFrame(rows)

    def _scan_line(self, line):
        self.line_parses += 1
        if not line.strip():
            return {"status": "empty", "scansion": "", "syllables": []}
        if len(line) > MAX_LINE_CHARS:
            return {"status": "limit", "message": "Split this line into shorter verse lines.", "syllables": []}
        words, texts, unknown = [], [], []
        for token in tokenize_sentwords_iter(line):
            forms = self.word_forms(token['txt'])
            if forms is None:
                unknown.append(token['txt'].strip())
            elif forms:
                words.append(forms)
                texts.append(token['txt'].strip())
        if unknown:
            return {"status": "unknown", "message": "No pronunciation for: " + ", ".join(unknown), "syllables": []}
        if sum(len(forms[0]) for forms in words) < 2:
            return {"status": "partial", "message": "Keep typing to form a metrical foot.", "syllables": []}
        if sum(max(map(len, forms)) for forms in words) > MAX_LINE_SYLLABLES:
            return {"status": "limit", "message": "This line exceeds the interactive budget of 128 syllables.", "syllables": []}
        dp = self._current_dp
        before = dp.transitions
        best = dp.update(words)
        self._dp_work['transitions'] += dp.transitions - before
        self._dp_work['reused_prefix_words'] += dp.reused_words
        self._dp_work['words_evaluated'] += dp.words_evaluated
        self._dp_work['peak_states'] = max(self._dp_work['peak_states'], dp.peak_states)
        if best is None:
            return {"status": "partial", "message": "No complete scansion yet.", "syllables": []}
        return self._annotate(best, words, texts)

    @staticmethod
    def _annotate(best, words, texts):
        """Add what a writer asks next: syllable count, meter name, rhyme sound, sound devices."""
        chosen = [forms[choice] for forms, choice in zip(words, best['forms'])]
        spans, at = [], 0
        for text, form, options in zip(texts, chosen, words):
            counts = sorted({len(f) for f in options})
            spans.append({'text': text, 'start': at, 'end': at + len(form),
                          'function': all(x.functionword for x in form),
                          'alt': counts if len(counts) > 1 else None})
            at += len(form)
        alliteration, assonance = sound_devices(list(zip(texts, chosen)))
        return {**best, 'words': spans, 'syllable_count': len(best['syllables']),
                'meter': classify_meter(best['scansion']),
                'rhyme_key': rhyme_key(texts[-1], chosen[-1]),
                'alliteration': alliteration, 'assonance': assonance}

    def update(self, text):
        started = perf_counter()
        before = self.word_builds, self.line_parses
        self._dp_work = {'transitions': 0, 'reused_prefix_words': 0,
                         'words_evaluated': 0, 'peak_states': 0, 'materialized_paths': 0}
        text_lines = text.split('\n')
        dps = [None] * len(text_lines)
        # Preserve a line's frontier when insertions/deletions move it.
        for tag, old_start, old_end, new_start, new_end in SequenceMatcher(
                a=self._previous_lines, b=text_lines, autojunk=False).get_opcodes():
            if tag in ('equal', 'replace'):
                for old, new in zip(range(old_start, old_end), range(new_start, new_end)):
                    dps[new] = self._dps[old]
        lines = []
        for i, line in enumerate(text_lines):
            if dps[i] is None:
                dps[i] = IncrementalDP()
            self._current_dp = dps[i]
            lines.append({'text': line, **self.scan_line(line)})
        self._previous_lines, self._dps = text_lines, dps
        rhymes = assign_rhymes([l.pop('rhyme_key', None) if l['status'] == 'ok' else None for l in lines])
        for l, rhyme in zip(lines, rhymes):
            l['rhyme'] = rhyme
        return {"lines": lines, "analysis": summarize(lines), "elapsed_ms": round((perf_counter() - started) * 1000, 2),
                "work": {"new_words": self.word_builds - before[0],
                         "parsed_lines": self.line_parses - before[1],
                         "graph_layers_added": 0}, 'dp': dict(self._dp_work)}
