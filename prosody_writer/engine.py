"""Reuse token pronunciation blocks and completed line results across edits."""
from functools import lru_cache
from time import perf_counter
import pandas as pd
from .runtime import prosodic
from .graph import IncrementalMeter
from prosodic.words.tokenizers import tokenize_sentwords_iter
from prosodic.texts.syll_df import build_syll_df
from prosodic.parsing.vectorized import parse_batch_from_df
from prosodic.imports import MAX_SYLL_IN_PARSE_UNIT

MAX_LINE_CHARS = 300


class Scanner:
    def __init__(self):
        self.meter = IncrementalMeter()
        self.word_builds = 0
        self.line_parses = 0
        # Instance-owned bounded caches: no poetry retained after session eviction.
        self.word_rows = lru_cache(maxsize=2048)(self._word_rows)
        self.scan_line = lru_cache(maxsize=256)(self._scan_line)

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
        df = self.frame(line)
        if df.empty:
            return {"status": "empty", "scansion": "", "syllables": []}
        words = df[df.is_punc == 0]
        unknown = words[words.num_forms == 0].word_txt.unique().tolist()
        if unknown:
            return {"status": "unknown", "message": "No pronunciation for: " + ", ".join(unknown), "syllables": []}
        canonical = words[words.form_idx == 0]
        if len(canonical) < 2:
            return {"status": "partial", "message": "Keep typing to form a metrical foot.", "syllables": []}
        # Avoid materializing pathological pronunciation spaces interactively.
        # Never silently drop variants or return an approximate parse.
        combinations = 1
        largest = 0
        for _, word in words.groupby("word_num", sort=False):
            lengths = word.groupby("form_idx").size()
            combinations *= len(lengths)
            largest += int(lengths.max())
        if largest > MAX_SYLL_IN_PARSE_UNIT or combinations > 256:
            return {"status": "limit", "message": "This line exceeds the interactive parsing budget (18 syllables / 256 pronunciation combinations).", "syllables": []}
        results = parse_batch_from_df(df, self.meter)
        parses = results.get(1)
        best = parses.best_parse if parses is not None and len(parses) else None
        if best is None:
            return {"status": "partial", "message": "No complete scansion yet.", "syllables": []}
        syllables = []
        for position in best.positions:
            for slot in position.children:
                syllables.append({"text": slot.unit.txt, "ipa": slot.unit.ipa,
                                  "stress": bool(slot.unit.is_stressed),
                                  "meter": position.meter_val,
                                  "violations": dict(slot.viold)})
        return {"status": "ok", "scansion": best.meter_str,
                "score": float(best.score), "violations": dict(best.viold),
                "syllables": syllables}

    def update(self, text):
        started = perf_counter()
        before = self.word_builds, self.line_parses, self.meter.dag.layers_added
        lines = [{"text": line, **self.scan_line(line)} for line in text.split("\n")]
        return {"lines": lines, "elapsed_ms": round((perf_counter() - started) * 1000, 2),
                "work": {"new_words": self.word_builds - before[0],
                         "parsed_lines": self.line_parses - before[1],
                         "graph_layers_added": self.meter.dag.layers_added - before[2]}}
