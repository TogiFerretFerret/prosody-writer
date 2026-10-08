"""Poem analysis on top of the scansion: meter naming, rhyme, sound devices and form.

Everything here is pure: it takes the pronunciation the scanner already chose and
returns plain data, so it is cheap to cache per line and easy to test on its own.
"""
from collections import Counter

STRESS_MARKS = "'ˈˌ,"
VOWELS = set("aeiouyɑæɛəɪʊʌɔɜɒɐɚɝøœɨɯʏɘɵɤɞɶ")
NORMALIZE = {"ɹ": "r", "ɡ": "g", "ɚ": "ər", "ɝ": "ɜr", "ː": "", "͡": "", "‿": ""}
AFFRICATES = ("tʃ", "dʒ", "ʧ", "ʤ", "ts", "dz")


def clean_ipa(ipa):
    out = "".join(c for c in ipa if c not in STRESS_MARKS)
    for old, new in NORMALIZE.items():
        out = out.replace(old, new)
    return out


def split_onset(ipa):
    """('str', 'eɪt') for 'streɪt'; a syllable with no vowel is all nucleus."""
    for i, c in enumerate(ipa):
        if c in VOWELS:
            return ipa[:i], ipa[i:]
    return "", ipa


def nucleus_of(rest):
    n = 0
    while n < len(rest) and rest[n] in VOWELS:
        n += 1
    return rest[:n] or rest, rest[n:]


# --------------------------------------------------------------------------- meter

FEET = (("iambic", "-+"), ("trochaic", "+-"), ("anapestic", "--+"), ("dactylic", "+--"))
LENGTHS = ("", "monometer", "dimeter", "trimeter", "tetrameter", "pentameter",
           "hexameter", "heptameter", "octameter")
FOOT_NAMES = {"-+": "iamb", "+-": "trochee", "++": "spondee", "--": "pyrrhic",
              "--+": "anapest", "+--": "dactyl", "-+-": "amphibrach", "+-+": "cretic",
              "-": "weak beat", "+": "strong beat"}


def _chunks(pattern, size):
    return [pattern[i:i + size] for i in range(0, len(pattern), size)]


def classify_meter(pattern):
    """Name the meter of a '+'/'-' scansion, tolerating the usual variations.

    Returns None for lines too short or too irregular to name. Variations that are
    reported rather than counted against the line: a feminine ending (iambic and
    anapestic lines ending on extra weak syllables) and a catalectic last foot
    (trochaic and dactylic lines missing their final weak syllables).
    """
    n = len(pattern)
    if n < 3:
        return None
    best = None
    for order, (foot, template) in enumerate(FEET):
        size = len(template)
        body, feminine = pattern, 0
        if template[-1] == "+":
            stripped = pattern.rstrip("-")
            if 0 < len(pattern) - len(stripped) < size and stripped:
                body, feminine = stripped, len(pattern) - len(stripped)
        ideal = (template * (len(body) // size + 2))[:len(body)]
        distance = sum(a != b for a, b in zip(body, ideal))
        if distance > max(1, len(body) // 5):
            continue
        feet = -(-len(body) // size)
        if feet >= len(LENGTHS) or (best and (distance, order) >= best[0]):
            continue
        found = _chunks(body, size)
        expected = _chunks(ideal, size)
        deviations = [{"foot": i + 1, "pattern": f, "name": FOOT_NAMES.get(f, f)}
                      for i, (f, e) in enumerate(zip(found, expected)) if f != e and len(f) == len(e)]
        variants = []
        if feminine:
            variants.append("feminine ending")
        if template[0] == "+" and len(body) % size:
            variants.append("catalectic")
        best = ((distance, order), {
            "foot": foot, "feet": feet, "length": LENGTHS[feet],
            "label": f"{foot} {LENGTHS[feet]}", "variants": variants,
            "deviations": deviations, "distance": distance})
    return best[1] if best else None


# --------------------------------------------------------------------------- rhyme

def rhyme_key(word, syllables):
    """The sound a word offers to a rhyme: everything from its last stressed vowel on.

    `syllables` are the chosen pronunciation, objects with .ipa and .stressed.
    """
    if not syllables:
        return None
    idx = max((i for i, s in enumerate(syllables) if s.stressed), default=len(syllables) - 1)
    onset, rest = split_onset(clean_ipa(syllables[idx].ipa))
    tail = rest + "".join(clean_ipa(s.ipa) for s in syllables[idx + 1:])
    _, last = split_onset(clean_ipa(syllables[-1].ipa))
    return {"word": word, "onset": onset, "tail": tail, "from": idx, "last": last}


def rhyme_kind(a, b):
    """perfect / identical / assonant / consonant / None between two rhyme keys."""
    if not a or not b:
        return None
    if a["tail"] and a["tail"] == b["tail"]:
        return "perfect" if a["onset"] != b["onset"] else "identical"
    nuc_a, coda_a = nucleus_of(a["tail"])
    nuc_b, coda_b = nucleus_of(b["tail"])
    if nuc_a and nuc_a == nuc_b:
        return "assonant"
    if coda_a and coda_a == coda_b:
        return "consonant"
    # Verse often gives a word's closing syllable the beat even when the dictionary does not
    # (temperate / date), so a shared final consonant still counts as an echo.
    _, end_a = nucleus_of(a.get("last", ""))
    _, end_b = nucleus_of(b.get("last", ""))
    if end_a and end_a == end_b:
        return "consonant"
    return None


def _letter(i):
    out = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        out = chr(65 + r) + out
    return out


NEAR_RANK = {"consonant": 0, "assonant": 1}


def assign_rhymes(keys):
    """keys: one rhyme key (or None) per line, in order. Returns per-line rhyme info.

    Two passes. First, lines that rhyme perfectly (or identically) share a letter.
    Then any line still alone is attached to the nearest earlier or later line it
    half-rhymes with, flagged `near`, so a weak echo never steals a line from the
    perfect rhyme it would otherwise find further down the poem.
    """
    n = len(keys)
    group = [None] * n
    kinds = [None] * n
    withs = [None] * n
    count = 0
    for i, key in enumerate(keys):
        if key is None:
            continue
        for j in range(i):
            if group[j] is None:
                continue
            kind = rhyme_kind(keys[j], key)
            if kind in ("perfect", "identical"):
                group[i], kinds[i], withs[i] = group[j], kind, j
                break
        else:
            group[i] = count
            count += 1
    sizes = Counter(g for g in group if g is not None)
    near = [False] * n
    for i, key in enumerate(keys):
        if key is None or sizes[group[i]] > 1:
            continue
        best = None
        for j, other in enumerate(keys):
            if j == i or other is None:
                continue
            kind = rhyme_kind(other, key)
            if kind in NEAR_RANK:
                rank = (NEAR_RANK[kind], abs(i - j))
                if best is None or rank < best[0]:
                    best = (rank, j, kind)
        if best:
            _, j, kind = best
            group[i], kinds[i], withs[i], near[i] = group[j], kind, j, True
    letters = {}
    out = []
    for i, key in enumerate(keys):
        if key is None:
            out.append(None)
            continue
        letter = letters.setdefault(group[i], _letter(len(letters)))
        out.append({"letter": letter, "kind": kinds[i], "with": withs[i], "near": near[i],
                    "from": key["from"], "word": key["word"], "sound": key["tail"]})
    members = Counter(r["letter"] for r in out if r)
    for r in out:
        if r:
            r["unrhymed"] = members[r["letter"]] == 1
    return out


# --------------------------------------------------------------------------- sound devices

def _first_sound(onset):
    for digraph in AFFRICATES:
        if onset.startswith(digraph):
            return digraph
    return onset[:1]


def sound_devices(words):
    """Alliteration and assonance within one line.

    `words` is a list of (text, syllables) in the chosen pronunciation. Alliteration
    counts shared opening consonant sounds on stressed content words; assonance counts
    a shared vowel across stressed syllables.
    """
    starts, vowels = {}, {}
    for text, syllables in words:
        if not syllables:
            continue
        first = syllables[0]
        if first.stressed and not first.functionword:
            onset, _ = split_onset(clean_ipa(first.ipa))
            sound = _first_sound(onset)
            if sound:
                starts.setdefault(sound, []).append(text)
        for syl in syllables:
            if syl.stressed:
                _, rest = split_onset(clean_ipa(syl.ipa))
                nucleus, _ = nucleus_of(rest)
                if nucleus:
                    vowels.setdefault(nucleus, []).append(text)
    def pick(groups):
        # the same word twice is repetition, not alliteration
        return [{"sound": s, "words": w} for s, w in groups.items()
                if len({x.lower() for x in w}) >= 2]
    return pick(starts), pick(vowels)


# --------------------------------------------------------------------------- poem level

def _scheme_string(letters, stanza_sizes):
    out, at = [], 0
    for size in stanza_sizes:
        out.append("".join(letters[at:at + size]))
        at += size
    return " ".join(out)


def detect_form(letters, counts, meters, stanza_sizes):
    """Name the poem's form when the evidence fits a known one."""
    n = len(letters)
    flat = "".join(letters)
    if n == 3 and counts == [5, 7, 5]:
        return "Haiku"
    if n == 5 and counts == [5, 7, 5, 7, 7]:
        return "Tanka"
    if n == 5 and flat == "AABBA":
        return "Limerick"
    pentameter = sum(1 for m in meters if m and m["length"] == "pentameter")
    if n == 14:
        if flat == "ABABCDCDEFEFGG":
            return "Shakespearean sonnet" if pentameter >= 10 else "Sonnet (Shakespearean rhyme scheme)"
        if flat[:8] == "ABBAABBA":
            return "Petrarchan sonnet" if pentameter >= 10 else "Sonnet (Petrarchan rhyme scheme)"
        return "Fourteen lines (sonnet length)"
    if n == 19 and flat == "ABAABAABAABAABAABAA":
        return "Villanelle"
    if n >= 6 and all(s == 3 for s in stanza_sizes[:-1]) and stanza_sizes[-1] in (1, 2, 3):
        want = []
        for i in range(0, n - n % 3, 3):
            want += [i // 3, i // 3 + 1, i // 3]
        # terza rima chains ABA BCB CDC ...; compare the shape, not the letters themselves
        if _renumber(letters[:len(want)]) == _renumber(want):
            return "Terza rima"
    if n >= 4 and n % 2 == 0:
        pairs = all(letters[i] == letters[i + 1] and letters[i] not in letters[:i] for i in range(0, n, 2))
        if pairs:
            return "Rhyming couplets"
    if stanza_sizes and all(s == 4 for s in stanza_sizes) and n >= 4:
        shapes = {"ABAB": "alternate rhyme", "ABBA": "enclosed rhyme", "AABB": "paired couplets",
                  "ABCB": "ballad stanzas"}
        found = {"".join(map(chr, [65 + i for i in _renumber(flat[at:at + 4])])) for at in range(0, n, 4)}
        if len(found) == 1 and (shape := found.pop()) in shapes:
            return f"Quatrains, {shapes[shape]}"
    return None


def _renumber(seq):
    seen = {}
    return [seen.setdefault(x, len(seen)) for x in seq]


def summarize(lines):
    """lines: scanned line dicts (with status, syllable_count, meter, rhyme). Returns the poem summary."""
    stanza_sizes, run = [], 0
    scanned = []
    for line in lines:
        if line["status"] == "empty":
            if run:
                stanza_sizes.append(run)
            run = 0
            continue
        run += 1
        scanned.append(line)
    if run:
        stanza_sizes.append(run)
    ok = [l for l in scanned if l["status"] == "ok"]
    meters = [l.get("meter") for l in ok]
    names = Counter(m["label"] for m in meters if m)
    dominant = None
    if names:
        label, count = names.most_common(1)[0]
        dominant = {"label": label, "lines": count, "of": len(ok)}
    letters = [l["rhyme"]["letter"] if l.get("rhyme") else "?" for l in scanned]
    counts = [l.get("syllable_count") for l in scanned]
    complete = len(ok) == len(scanned) and all(l.get("rhyme") for l in scanned)
    form = detect_form(letters, counts, [l.get("meter") for l in scanned], stanza_sizes) if complete else None
    syllables = sum(c for c in counts if c)
    groups = {}
    for l in ok:
        r = l.get("rhyme")
        if r:
            g = groups.setdefault(r["letter"], {"letter": r["letter"], "sound": r["sound"], "words": []})
            g["words"].append(r["word"])
    repeats = Counter()
    for l in ok:
        for w in l.get("words", []):
            if not w.get("function"):
                repeats[w["text"].lower()] += 1
    return {
        "lines": len(scanned), "stanzas": len(stanza_sizes), "syllables": syllables,
        "average_syllables": round(syllables / len(ok), 1) if ok else 0,
        "scheme": _scheme_string(letters, stanza_sizes) if complete and scanned else "",
        "meter": dominant, "form": form,
        "rhymed_lines": sum(1 for l in ok if l.get("rhyme") and not l["rhyme"]["unrhymed"]),
        "rhyme_groups": [g for g in groups.values() if len(g["words"]) > 1],
        "shortest": min((c for c in counts if c), default=0),
        "longest": max((c for c in counts if c), default=0),
        "repeats": [{"word": w, "count": c} for w, c in repeats.most_common(8) if c >= 2],
    }
