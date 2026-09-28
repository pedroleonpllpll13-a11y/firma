#!/usr/bin/env python3
"""structural_scan.py - deterministic scan for structural AI-writing tells.

Catches the pattern-matchable slice of the discourse-level tells identified by
StoryScope (Russell et al. 2026, arXiv:2604.03136). The full structural audit
requires judgment (see SKILL.md); this script flags:

  embodied_emotion   emotion performed through the body ("her chest tightened")
  stated_lesson      takeaway/moral markers ("the lesson here is")
  tidy_closer        wrap-it-with-a-bow phrases in the final two paragraphs
  vague_allusion     unnamed authorities/works ("experts say", "a well-known book")
  metrics            paragraph-length uniformity, reader address, concrete numbers

Usage:
  python3 structural_scan.py FILE [FILE ...]
  python3 structural_scan.py --html lesson.html     # strip tags first
  cat draft.md | python3 structural_scan.py -
  python3 structural_scan.py --json draft.md        # machine-readable output
  python3 structural_scan.py --strict draft.md      # exit 1 if any category >= threshold
                                                    # (hook-friendly)

Thresholds used by --strict (hits per document):
  embodied_emotion >= 2, stated_lesson >= 2, tidy_closer >= 2, vague_allusion >= 2
"""

import argparse
import html as html_mod
import json
import re
import statistics
import sys

PRONOUN = r"(?:my|his|her|their|your|the)"

EMBODIED_EMOTION = [
    rf"\b{PRONOUN}\s+(?:chest|throat|jaw|stomach|gut|shoulders?)\s+"
    r"(?:tighten|clench|knot|drop|sink|sag|constrict|seize|flip|turn|twist|churn)\w*",
    rf"\b{PRONOUN}\s+breath\s+(?:caught|hitched|stalled)\b",
    r"\bcaught\s+(?:my|his|her|their)\s+breath\b",
    rf"\b{PRONOUN}\s+heart\s+(?:pound|hammer|race|sink|sank|lurch|clench|skip|stutter)\w*",
    r"\ba\s+knot\s+(?:of\s+\w+\s+)?(?:in|form)\w*",
    r"\bblood\s+ran\s+cold\b",
    rf"\b{PRONOUN}\s+pulse\s+(?:quicken|race|spike)\w*",
    rf"\bsomething\s+in\s+{PRONOUN}\s+\w+\s+(?:shift|loosen|settle|break|broke|unclench)\w*",
    r"\bpit\s+of\s+(?:my|his|her|their)\s+stomach\b",
    r"\b(?:cold|nervous)\s+sweat\b",
    rf"\b{PRONOUN}\s+(?:spine|skin|scalp|neck)\s+(?:tingl|prickl|crawl)\w*",
    r"\bswallow(?:ed|s|ing)?\s+hard\b",
    rf"\b{PRONOUN}\s+hands?\s+(?:trembl|shak|shook)\w*",
    r"\bexhal\w+\s+(?:a\s+breath\s+)?(?:I|he|she|they)\s+(?:didn.t|had\s+not|hadn.t)\s+(?:know|known|realized?)\b",
    r"\bbreath\s+(?:I|he|she|they)\s+(?:didn.t|hadn.t)\s+(?:know|known|realized?)\b",
]

STATED_LESSON = [
    r"\bthe\s+(?:lesson|takeaway|point|moral)\s+(?:here\s+)?is\b",
    r"\bwhat\s+this\s+means\s+for\s+you\b",
    r"\bif\s+you\s+take\s+(?:one\s+thing|only\s+one\s+thing|nothing\s+else)\b",
    r"\bhere'?s\s+(?:the\s+thing|what\s+matters|what\s+I\s+want\s+you\s+to\s+(?:take|remember))\b",
    r"\bthe\s+bottom\s+line\b",
    r"\bmoral\s+of\s+the\s+story\b",
    r"\band\s+that'?s\s+(?:the\s+point|the\s+whole\s+point|why\s+\w[\w\s]{0,40}\s+matters)\b",
    r"\bthe\s+(?:real|key|big)\s+(?:insight|lesson|takeaway|idea)\s+(?:here\s+)?is\b",
    r"\blet\s+that\s+sink\s+in\b",
    r"\bthe\s+lesson\s+(?:I|we)\s+(?:learned|took)\b",
    r"\bwhich\s+is\s+exactly\s+why\b",
]

TIDY_CLOSER = [
    r"^(?:so|ultimately|in\s+the\s+end|at\s+the\s+end\s+of\s+the\s+day|looking\s+back)\b[,:]?",
    r"\bin\s+the\s+end\b",
    r"\bat\s+the\s+end\s+of\s+the\s+day\b",
    r"\bultimately\b",
    r"\bthe\s+future\s+(?:looks|is)\b",
    r"\band\s+(?:I|we)\s+(?:finally\s+)?(?:realized|understood|learned)\s+that\b",
    r"\bfull\s+circle\b",
]

VAGUE_ALLUSION = [
    r"\b(?:experts?|researchers?|scientists|economists|psychologists|professionals)\s+"
    r"(?:say|agree|believe|argue|warn|suggest|estimate)\b",
    r"\bstudies\s+(?:show|suggest|have\s+shown|indicate)\b",
    r"\bresearch\s+(?:shows|suggests|indicates|has\s+shown)\b",
    r"\ba\s+(?:famous|popular|well-known|renowned|leading|prominent)\s+"
    r"(?:book|author|study|expert|entrepreneur|investor|writer|thinker|framework)\b",
    r"\bas\s+the\s+(?:old\s+)?saying\s+goes\b",
    r"\bthere'?s\s+an?\s+(?:old\s+)?(?:saying|adage|quote)\b",
    r"\bsome\s+(?:people|critics|observers|folks)\s+(?:say|argue|believe|claim)\b",
    r"\bit'?s\s+(?:often|widely|commonly)\s+(?:said|believed|claimed)\b",
    r"\byou'?ve\s+probably\s+heard\s+(?:the\s+saying|it\s+said)\b",
]

# Spanish equivalents (added for the firma repo).
PRON_ES = r"(?:me|te|le|nos|os|les|se)"

EMBODIED_EMOTION_ES = [
    rf"\b{PRON_ES}\s+(?:encogi[óo]|encoge|apret[óo]|oprimi[óo]|dio un vuelco|dio un brinco)\s+(?:el|la)\s+"
    r"(?:coraz[óo]n|pecho|est[óo]mago|garganta)",
    r"\bun\s+nudo\s+en\s+(?:la\s+garganta|el\s+est[óo]mago|el\s+pecho)",
    r"\bcontuv(?:o|e|ieron|imos)\s+(?:la\s+)?(?:respiraci[óo]n|el\s+aliento)",
    r"\bsin\s+saber\s+que\s+(?:la\s+)?(?:estaba|estaban)\s+conteniendo",
    r"\bun\s+escalofr[íi]o\s+(?:le|me|te|nos)?\s*recorri[óo]",
    r"\bse\s+(?:le|me|te|nos)\s+hel[óo]\s+la\s+sangre",
    r"\bel\s+coraz[óo]n\s+(?:le|me|te|nos)?\s*(?:lat[íi]a|golpeaba|martilleaba|se\s+aceler[óo]|dio\s+un\s+vuelco)",
    r"\bsudor\s+fr[íi]o\b",
    r"\b(?:le|me|te|nos)\s+temblaban\s+las\s+manos\b",
    r"\btrag[óo]\s+saliva\b",
    r"\bla\s+boca\s+del\s+est[óo]mago\b",
    r"\balgo\s+(?:dentro\s+de\s+(?:[ée]l|ella|m[íi])|en\s+su\s+interior)\s+(?:cambi[óo]|se\s+rompi[óo]|se\s+afloj[óo]|se\s+asent[óo])",
]

STATED_LESSON_ES = [
    r"\bla\s+(?:lecci[óo]n|moraleja|ense[ñn]anza|clave)\s+(?:aqu[íi]\s+)?(?:es|est[áa])\b",
    r"\bmoraleja\b",
    r"\blo\s+que\s+(?:aprend[íi]|aprendimos|me\s+llevo)\b",
    r"\bqu[ée]date\s+con\s+esto\b",
    r"\bsi\s+te\s+quedas\s+con\s+una\s+sola\s+cosa\b",
    r"\blo\s+que\s+(?:de\s+verdad|realmente)\s+importa\b",
    r"\by\s+esa\s+es\s+(?:la\s+)?(?:clave|lecci[óo]n|diferencia)\b",
    r"\bla\s+conclusi[óo]n\s+es\s+clara\b",
    r"\bqu[ée]\s+significa\s+esto\s+para\s+ti\b",
]

TIDY_CLOSER_ES = [
    r"^(?:as[íi]\s+que|al\s+final|en\s+definitiva|a\s+fin\s+de\s+cuentas|mirando\s+atr[áa]s)\b[,:]?",
    r"\bal\s+final\s+del\s+d[íi]a\b",
    r"\ben\s+definitiva\b",
    r"\bel\s+futuro\s+(?:se\s+presenta|es|parece)\b",
    r"\by\s+(?:entend[íi]|entendi[óo]|comprend[íi]|comprendi[óo]|aprend[íi])\s+que\b",
    r"\bcerrar\s+el\s+c[íi]rculo\b",
]

VAGUE_ALLUSION_ES = [
    r"\b(?:los\s+)?expertos\s+(?:dicen|coinciden|afirman|advierten|creen|aseguran)\b",
    r"\b(?:los\s+|numerosos\s+|varios\s+)?estudios\s+(?:demuestran|indican|sugieren|han\s+demostrado)\b",
    r"\bun[ao]?\s+(?:famos[oa]|conocid[oa]|reconocid[oa]|prestigios[oa])\s+"
    r"(?:libro|autor|autora|estudio|experto|experta|empresario|inversor|escritor|marco)\b",
    r"\bcomo\s+dice\s+el\s+refr[áa]n\b",
    r"\bhay\s+un\s+(?:viejo\s+)?(?:dicho|refr[áa]n)\b",
    r"\balgunos\s+(?:dicen|opinan|creen|afirman)\b",
    r"\bse\s+(?:suele\s+decir|dice\s+a\s+menudo)\b",
]

PATTERNS = {
    "en": (EMBODIED_EMOTION, STATED_LESSON, TIDY_CLOSER, VAGUE_ALLUSION),
    "es": (EMBODIED_EMOTION_ES, STATED_LESSON_ES, TIDY_CLOSER_ES, VAGUE_ALLUSION_ES),
}
WORD_RE = r"[A-Za-zÀ-ÿ']+"
YOU_RE = {
    "en": r"\byou(?:r|'re|'ll|'ve)?\b",
    "es": r"\b(?:t[úu]|te|ti|tu|tus|contigo|usted|ustedes|vosotros|vosotras|os)\b",
}


def detect_lang(text):
    es = len(re.findall(r"\b(?:el|la|los|las|que|de|del|y|en|con|para|por|una|es|pero|como|m[áa]s)\b", text, re.I))
    en = len(re.findall(r"\b(?:the|and|of|to|is|in|that|with|for|are|this|it)\b", text, re.I))
    return "es" if es > en else "en"


STRICT_THRESHOLDS = {
    "embodied_emotion": 2,
    "stated_lesson": 2,
    "tidy_closer": 2,
    "vague_allusion": 2,
}


def strip_html(text):
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return html_mod.unescape(text)


def find_hits(lines, patterns):
    hits = []
    for lineno, line in enumerate(lines, 1):
        claimed = []  # spans already matched on this line, to dedup overlapping patterns
        for pat in patterns:
            for m in re.finditer(pat, line, re.IGNORECASE):
                if any(m.start() < e and m.end() > s for s, e in claimed):
                    continue
                claimed.append((m.start(), m.end()))
                excerpt = line.strip()
                if len(excerpt) > 100:
                    start = max(0, m.start() - 40)
                    excerpt = "..." + line[start:start + 100].strip() + "..."
                hits.append({"line": lineno, "match": m.group(0), "excerpt": excerpt})
    return hits


def paragraphs_of(text):
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def scan(text, lang="en"):
    lines = text.splitlines()
    paras = paragraphs_of(text)
    words = re.findall(WORD_RE, text)
    n_words = len(words) or 1
    embodied, lesson, closer, vague = PATTERNS[lang]

    result = {
        "language": lang,
        "embodied_emotion": find_hits(lines, embodied),
        "stated_lesson": find_hits(lines, lesson),
        "vague_allusion": find_hits(lines, vague),
    }

    # tidy closers only matter near the end: scan the final two paragraphs
    tail = "\n".join(paras[-2:]) if paras else ""
    tail_offset = len(lines) - len(tail.splitlines())
    tail_hits = find_hits(tail.splitlines(), closer)
    for h in tail_hits:
        h["line"] += max(tail_offset, 0)
    result["tidy_closer"] = tail_hits

    # ---- metrics (informational; not counted by --strict) ----
    metrics = {}
    para_lens = [len(re.findall(WORD_RE, p)) for p in paras]
    if len(para_lens) >= 5 and statistics.mean(para_lens) > 0:
        cv = statistics.pstdev(para_lens) / statistics.mean(para_lens)
        metrics["paragraph_length_cv"] = round(cv, 2)
        metrics["uniform_paragraphs"] = cv < 0.35
    you_count = len(re.findall(YOU_RE[lang], text, re.IGNORECASE))
    metrics["reader_address_per_100w"] = round(100 * you_count / n_words, 1)
    num_count = len(re.findall(r"(?<![A-Za-z])[$€£]?\d[\d,.]*%?", text))
    metrics["numbers_per_100w"] = round(100 * num_count / n_words, 1)
    if n_words > 300 and num_count == 0:
        metrics["no_concrete_numbers"] = True
    metrics["word_count"] = n_words
    result["metrics"] = metrics
    return result


def report(name, result):
    print(f"\n=== {name} ===")
    total = 0
    for cat in ("embodied_emotion", "stated_lesson", "tidy_closer", "vague_allusion"):
        hits = result[cat]
        total += len(hits)
        flag = " <-- over threshold" if len(hits) >= STRICT_THRESHOLDS[cat] else ""
        print(f"\n[{cat}] {len(hits)} hit(s){flag}")
        for h in hits:
            print(f"  L{h['line']}: \"{h['match']}\"  |  {h['excerpt']}")
    m = result["metrics"]
    print(f"\n[metrics] language={result['language']}  words={m['word_count']}"
          f"  reader-address/100w={m['reader_address_per_100w']}"
          f"  numbers/100w={m['numbers_per_100w']}"
          + (f"  paragraph-CV={m['paragraph_length_cv']}" if "paragraph_length_cv" in m else ""))
    if m.get("uniform_paragraphs"):
        print("  NOTE: paragraph lengths are suspiciously uniform (CV < 0.35). Vary them.")
    if m.get("no_concrete_numbers"):
        print("  NOTE: 300+ words and zero concrete numbers. Add named specifics.")
    if total == 0:
        print("\nClean on the grep-able tells. The judgment-level audits (theme "
              "explicitness, structure, shape convergence) still apply; see SKILL.md.")
    return total


def over_threshold(result):
    return any(len(result[c]) >= t for c, t in STRICT_THRESHOLDS.items())


def main():
    ap = argparse.ArgumentParser(description="Scan text for structural AI-writing tells.")
    ap.add_argument("files", nargs="+", help="files to scan, or '-' for stdin")
    ap.add_argument("--html", action="store_true", help="strip HTML tags before scanning")
    ap.add_argument("--lang", choices=["en", "es", "auto"], default="auto",
                    help="pattern language (default: auto-detect)")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of a report")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 if any category meets its threshold (for hooks)")
    args = ap.parse_args()

    any_over = False
    json_out = {}
    for path in args.files:
        if path == "-":
            text, name = sys.stdin.read(), "<stdin>"
        else:
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
            name = path
        if args.html or path.endswith((".html", ".htm")):
            text = strip_html(text)
        lang = detect_lang(text) if args.lang == "auto" else args.lang
        result = scan(text, lang)
        if args.json:
            json_out[name] = result
        else:
            report(name, result)
        if over_threshold(result):
            any_over = True

    if args.json:
        print(json.dumps(json_out, indent=2))
    sys.exit(1 if (args.strict and any_over) else 0)


if __name__ == "__main__":
    main()
