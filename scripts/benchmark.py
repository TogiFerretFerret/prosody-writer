"""Run from the checkout: .venv/bin/python scripts/benchmark.py."""
import json
import statistics
from time import perf_counter
from prosody_writer.engine import Scanner
from prosody_writer.runtime import prosodic

fixed = "Shall I compare thee to a summer's day?"
prefixes = ["To be", "To be or", "To be or not", "To be or not to", "To be or not to be"]
rows = []
for line in prefixes:
    incremental, full = [], []
    for _ in range(5):
        scanner = Scanner()
        scanner.update(fixed + '\nTo be')
        result = scanner.update(fixed + '\n' + line)
        incremental.append(result['elapsed_ms'])
        start = perf_counter()
        text = prosodic.Text(fixed + '\n' + line, lang='en')
        text.parse()
        # Match the editor's requirement to materialize the chosen syllables.
        for parsed_line in text.lines:
            _ = parsed_line.best_parse
        full.append((perf_counter() - start) * 1000)
    rows.append({'text': line, 'incremental_ms': round(statistics.median(incremental), 2),
                 'full_document_ms': round(statistics.median(full), 2), 'work': result['work']})
print(json.dumps(rows, indent=2))
