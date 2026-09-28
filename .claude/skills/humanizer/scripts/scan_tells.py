#!/usr/bin/env python3
"""Flag mechanical AI-writing tells in a text file, with line numbers.

Usage:
    python3 scan_tells.py FILE [FILE ...] [--lang en|es|auto]
    cat FILE | python3 scan_tells.py - [--lang es]
    python3 scan_tells.py --html page.html     # strip tags first
    python3 scan_tells.py --json draft.md      # machine-readable
    python3 scan_tells.py --strict draft.md    # exit 1 on hard or strong

Findings are candidates for the humanizer pass, not verdicts. Section
numbers (§) match SKILL.md; "copy" marks rules from references/copy-tells.md.
Exit status is 1 when a "hard" tell is found (chatbot markup, placeholders,
chat residue), or with --strict when any hard or strong tell is found.
Put `humanizer-ignore` on a line to skip it.

Fenced code blocks and inline code are skipped, except that a fence
labelled wikitext/markdown is itself reported (§28).
"""

import argparse
import html as html_mod
import json
import re
import sys
from collections import Counter

HARD, STRONG, WEAK = "hard", "strong", "weak"
ORDER = {HARD: 0, STRONG: 1, WEAK: 2}

I = re.IGNORECASE

# (severity, section, label, pattern, flags, languages)
RULES = [
    # §28 chatbot markup and tracking codes: checked on raw lines, any language.
    (HARD, 28, "chatbot citation markup", r"contentReference\[oaicite|oai_citation|\battributableIndex\b", 0, "raw"),
    (HARD, 28, "chatbot search markup", r"\bturn\d+(search|news|image|file|view)\d+", 0, "raw"),
    (HARD, 28, "Gemini citation markup", r"\[cite:\s*\d+|\(?start_span\)?|\[span_\d+\]", 0, "raw"),
    (HARD, 28, "Grok/DeepSeek/Perplexity markup", r"grok_card|grok_render|【\d+†|ppl-ai-file-upload", 0, "raw"),
    (HARD, 28, "chat document wrapper", r":::writing\{", 0, "raw"),
    (HARD, 28, "chatbot tracking parameter", r"utm_source=(chatgpt\.com|openai|copilot\.com)|referrer=grok\.com", 0, "raw"),
    (STRONG, 28, "footnote return arrow", r"↩", 0, "raw"),
    # §27 placeholders
    (HARD, 27, "unfilled placeholder",
     r"\[(your|insert|add|company|name|specific|client|tu|su|nombre|insertar|añadir|empresa|cliente)\b[^\]\n]{0,40}\]", I, "raw"),
    (HARD, 27, "unfilled placeholder",
     r"\((add|insert|if available|añad[ea]|inserta|si est[aá] disponible)\b[^)\n]{0,60}\)", I, "raw"),
    (HARD, 27, "placeholder date or URL", r"\b20\d\d-(XX|xx)-(XX|xx)\b|\burl\s*=\s*URL\b|\blorem ipsum\b", I, "raw"),

    # §1 not X but Y
    (STRONG, 1, "not-X-but-Y contrast", r"\bnot (just|only|merely|simply)\b[^.?!\n]{0,90}\bbut\b", I, "en"),
    (STRONG, 1, "not-X-but-Y contrast",
     r"\b(it'?s|it is|this is|that'?s|that is) not\b[^.?!\n]{1,60}[,;:—–-]\s*(it'?s|it is|this is|that'?s|that is)\b", I, "en"),
    (STRONG, 1, "split contrast", r"\bthis (doesn'?t|does not) mean\b", I, "en"),
    (STRONG, 1, "no-es-X-es-Y contrast",
     r"\bno (es|son|era|fue|será) (solo|sólo|solamente|simplemente|únicamente|un[ao]?)\b[^.?!\n]{0,90}[,;:—–]\s*(es|son|era|sino)\b", I, "es"),
    (STRONG, 1, "no-solo-sino contrast", r"\bno (solo|sólo|solamente)\b[^.?!\n]{0,110}\bsino\b", I, "es"),
    (STRONG, 1, "no-se-trata-de contrast", r"\bno se trata (solo |sólo )?de\b[^.?!\n]{0,90}\bsino\b", I, "es"),
    (STRONG, 1, "más-que-X-es-Y contrast", r"\bmás que (un|una)\b[^.?!\n]{0,60}[,;:]\s*(es|son)\b", I, "es"),

    # §2 closers and section summaries
    (STRONG, 2, "summary opener", r"(^\s*|[.!?]\s+)(in (summary|conclusion)|overall|ultimately|to sum up),", I, "en"),
    (STRONG, 2, "dramatic closer",
     r"\b(let that sink in|read that again|that'?s the real win|that distinction matters|and that changes everything|every\. single\. \w+)\b", I, "en"),
    (STRONG, 2, "summary opener", r"(^\s*|[.!?]\s+)(en (resumen|conclusión|definitiva|síntesis)|en suma),", I, "es"),
    (STRONG, 2, "dramatic closer", r"(y eso lo cambia todo|así de simple\.|léelo otra vez|punto\.$)", I, "es"),

    # §3 sayings
    (WEAK, 3, "deep-sounding saying",
     r"\b(the real question is|at its core|what really matters|the heart of the matter|the deeper issue)\b", I, "en"),
    (WEAK, 3, "deep-sounding saying", r"\b(la verdadera pregunta es|en el fondo,|lo que realmente importa|en esencia,)", I, "es"),

    # §4 staged run-up
    (STRONG, 4, "staged opener",
     r"\b(let'?s (dive|delve|explore|break (this|it) down|unpack)|here'?s (what you need to know|the thing)|without further ado|real talk)\b", I, "en"),
    (STRONG, 4, "staged opener", r"^\s*(honestly\?|look,|the thing is,|let'?s be honest)", I, "en"),
    (STRONG, 4, "staged opener",
     r"\b(vamos a ello|sumérgete|adéntrate|esto es lo que necesitas saber|te lo cuento|seamos sinceros|te explico)\b", I, "es"),
    (STRONG, 4, "staged question", r"¿(el resultado|la clave|el secreto|la respuesta|lo mejor)\?", I, "es"),
    (STRONG, 4, "staged question", r"\b(the result|the catch|the secret|the answer|the best part)\?", I, "en"),

    # §5 arguing with no one
    (WEAK, 5, "arguing with no one",
     r"\b(don'?t get me wrong|to be clear,|i'?m not saying|this is not to say|one might be tempted)\b", I, "en"),
    (WEAK, 5, "arguing with no one", r"\b(no me malinterpretes|para que quede claro|esto no significa que)\b", I, "es"),

    # §9 stacked qualifiers
    (WEAK, 9, "stacked qualifier", r"\b(could potentially|might arguably|may possibly|could possibly)\b", I, "en"),
    (WEAK, 9, "stacked qualifier", r"\b(podría potencialmente|en cierta medida podría)\b", I, "es"),

    # §13 / §16 inflation and sales language
    (WEAK, 16, "sales language",
     r"\b(nestled|in the heart of|breathtaking|must-visit|rich cultural heritage|natural beauty|diverse array|world-class)\b", I, "en"),
    (WEAK, 13, "inflated significance",
     r"\b(stands as a testament|a testament to|pivotal (moment|role)|plays? a (key|crucial|vital|pivotal) role|evolving landscape|indelible mark|setting the stage for|the future looks bright)\b", I, "en"),
    (WEAK, 16, "lenguaje de venta",
     r"\b(en el corazón de|enclave privilegiado|ubicación inmejorable|vistas (impresionantes|espectaculares|de ensueño)|oasis de|donde el lujo|estilo de vida|experiencia única|oportunidad única|sin igual)\b", I, "es"),
    (WEAK, 13, "trascendencia inflada",
     r"\b(un antes y un después|marca(r)? un hito|juega(n)? un papel (fundamental|clave|crucial)|huella imborrable|legado duradero|sienta las bases)\b", I, "es"),

    # Hype copy (references/copy-tells.md)
    (STRONG, 16, "hype copy",
     r"\b(transform your|supercharge|unleash|effortlessly|reimagined|game-?changer|unlock (your |the )?(full )?potential|"
     r"elevate your|in today'?s (fast-paced|digital) world|cutting-edge|best-in-class|revolutionary)\b|"
     r"\btake (your |it |things )?[^.\n]{0,30}to the next level", I, "en"),
    (STRONG, 16, "copy hype",
     r"\b(transforma tu|potencia tu|lleva tu [^.\n]{0,30} al siguiente nivel|desbloquea|sin esfuerzo|"
     r"revolucionari[oa]|de última generación|en el mundo actual|en la era digital|cambia las reglas del juego|"
     r"eleva tu|redefin(e|iendo) (el concepto|la forma))\b", I, "es"),

    # §15 -ing riders / gerundio de posterioridad
    (WEAK, 15, "-ing rider",
     r", (highlighting|underscoring|emphasizing|showcasing|reflecting|symbolizing|ensuring|fostering|cultivating|contributing to)\b", I, "en"),
    (WEAK, 15, "gerundio de posterioridad",
     r", (convirtiéndose|consolidándose|posicionándose|destacando|reflejando|subrayando|marcando|garantizando|aportando|resaltando)\b", I, "es"),

    # §17 borrowed authority
    (WEAK, 17, "borrowed authority",
     r"\b(experts (say|argue|believe|agree)|observers have|industry reports|active social media presence|independent coverage)\b", I, "en"),
    (WEAK, 17, "autoridad prestada", r"\b(según (los )?expertos|los expertos (coinciden|afirman)|numerosos estudios)\b", I, "es"),

    # §18 avoiding is/has
    (WEAK, 18, "avoids is/has", r"\b(serves|stands|functions|operates) as (a|an|the)\b|\bboasts\b", I, "en"),
    (WEAK, 18, "evita ser/tener", r"\bse (erige|posiciona) como\b|\bpresume de\b", I, "es"),

    # §22 chat residue
    (HARD, 22, "chat residue",
     r"\b(i hope this helps|great question|you'?re absolutely right|as an ai( language model)?|would you like me to|here is (a|an|the) (revised|updated|polished|rewritten))\b|\b(certainly|of course)!", I, "en"),
    (STRONG, 22, "didactic aside", r"\bit'?s (important|worth|crucial|essential) (to (note|remember|consider|mention)|noting)\b", I, "en"),
    (WEAK, 22, "offer/closing (fine in letters)", r"\blet me know if\b|\bfeel free to\b", I, "en"),
    (HARD, 22, "restos del chat",
     r"(¡claro!|¡por supuesto!|¡excelente pregunta!|espero que (te|le|os) (sea|resulte) útil|¿quieres que|aquí tienes|como modelo de lenguaje)", I, "es"),
    (STRONG, 22, "aviso didáctico",
     r"\b(cabe (destacar|señalar|mencionar)|es importante (tener en cuenta|destacar|señalar|recordar)|vale la pena (mencionar|destacar))\b", I, "es"),
    (WEAK, 22, "oferta/cierre (normal en cartas)", r"\b(no dudes en|si necesitas algo más)\b", I, "es"),

    # §23 knowledge limits
    (STRONG, 23, "knowledge-limit disclaimer",
     r"\b(as of my last (training|knowledge) update|up to my last|based on (the )?available information|not (widely|publicly) (documented|available|disclosed)|maintains a low profile)\b", I, "en"),
    (STRONG, 23, "límite de conocimiento",
     r"\b(según la información disponible|hasta mi última actualización|no hay (datos|información) públic)", I, "es"),
]

AI_WORDS = {
    "en": r"additionally|align(s|ed)? with|bolster(ed|s)?|crucial|deep dive|delv(e|es|ed|ing)|enduring|enhanc(e|es|ed|ing)|"
          r"foster(s|ed|ing)?|garner(s|ed)?|highlight(s|ed|ing)?|interplay|intricate|intricacies|landscape|"
          r"meticulous(ly)?|pivotal|robust|showcas(e|es|ed|ing)|tapestry|testament|underscor(e|es|ed|ing)|"
          r"valuable|vibrant|seamless(ly)?|elevate[sd]?|unlock(s|ed)?|empower(s|ed|ing)?",
    "es": r"crucial(es)?|fundamental(es)?|esencial(es)?|potenci(ar|a|an|ando)|foment(ar|a|an|ando)|impuls(ar|a|an|ando)|"
          r"optimiz(ar|a|an|ando)|abord(ar|a|an|ando)|garantiz(ar|a|an|ando)|resalt(ar|a|an|ando)|subray(ar|a|an|ando)|"
          r"panorama|ecosistema|entramado|sinergia(s)?|robust[oa]s?|integral(es)?|hol[ií]stic[oa]s?|"
          r"desbloque(ar|a)|elev(ar|a) (tu|su|la|el)|transformador(a|es)?|vanguardista(s)?|vibrante(s)?|"
          r"sin precedentes|innovador(a|es)?",
}

SPANISH_HINTS = re.compile(
    r"\b(el|la|los|las|que|de|del|y|en|con|para|por|una|es|está|son|muy|pero|como|más)\b", I)
ENGLISH_HINTS = re.compile(r"\b(the|and|of|to|is|in|that|with|for|are|this|it)\b", I)
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⭐✅❌→]")


def detect_lang(text):
    es, en = len(SPANISH_HINTS.findall(text)), len(ENGLISH_HINTS.findall(text))
    return "es" if es > en else "en"


def mask_code(lines):
    """Return prose lines with code blanked, plus fence findings for §28."""
    out, fences, in_fence = [], [], False
    for n, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            label = stripped.strip("`~ ").lower()
            if not in_fence and label in ("wikitext", "markdown", "md"):
                fences.append((HARD, 28, "text wrapped in a %s fence" % label, n, stripped))
            in_fence = not in_fence
            out.append("")
            continue
        out.append("" if in_fence else re.sub(r"`[^`\n]*`", lambda m: " " * len(m.group()), line))
    return out, fences


def snippet(line, start, end, width=70):
    a = max(0, start - 20)
    s = line[a:max(end, a + width)].strip()
    return ("…" if a else "") + s[:width + 20]


def scan(text, lang):
    raw_lines = ["" if "humanizer-ignore" in l else l for l in text.splitlines()]
    prose, findings = mask_code(raw_lines)
    no_urls = [re.sub(r"https?://\S+", "", l) for l in prose]

    for sev, sec, label, pat, flags, langs in RULES:
        rx = re.compile(pat, flags | re.MULTILINE)
        use_raw = langs == "raw"
        if not use_raw and langs != lang:
            continue
        for n, line in enumerate(raw_lines if use_raw else no_urls, 1):
            for m in rx.finditer(line):
                findings.append((sev, sec, label, n, snippet(line, m.start(), m.end())))

    # §8 dashes. Spanish keeps paired rayas and dialogue rayas.
    for n, line in enumerate(no_urls, 1):
        check = line
        if lang == "es":
            check = re.sub(r"^\s*—.*$", "", check)            # dialogue line
            check = re.sub(r"—[^—\n]{1,200}—", "", check)      # paired inciso
            check = re.sub(r"—[^—\n]*[.?!…]?\s*$", "", check) if line.count("—") == 1 and re.search(r"[.?!]\s*—", line) else check
        for m in re.finditer(r"\s—\s|—|\s–\s|\s--\s", check):
            findings.append((WEAK, 8, "dash as connector", n, snippet(check, m.start(), m.end())))

    # §12 stock AI words: density across the text.
    words_rx = re.compile(r"\b(%s)\b" % AI_WORDS[lang], I)
    hits = Counter()
    for n, line in enumerate(no_urls, 1):
        for m in words_rx.finditer(line):
            hits[m.group().lower()] += 1
    total_words = max(1, len(" ".join(no_urls).split()))
    if hits:
        per_k = 1000.0 * sum(hits.values()) / total_words
        sev = STRONG if len(hits) >= 3 or per_k >= 10 else WEAK
        top = ", ".join("%s×%d" % (w, c) for w, c in hits.most_common(12))
        findings.append((sev, 12, "stock AI words (%.1f per 1,000 words)" % per_k, 0, top))

    # §19 bold labels, §20 headings and rules, §21 curly quotes.
    hr = 0
    for n, line in enumerate(prose, 1):
        if re.match(r"^\s*([-*+]|\d+\.)\s+\*\*[^*\n]{1,60}(:\*\*|\*\*:)", line):
            findings.append((WEAK, 19, "bold inline label", n, line.strip()[:80]))
        h = re.match(r"^\s*#{1,6}\s+(.*)$", line)
        if h:
            title = h.group(1)
            if EMOJI.search(title):
                findings.append((WEAK, 20, "emoji in heading", n, title[:80]))
            words = [w for w in re.findall(r"[^\W\d_]+", title) if len(w) > 3]
            caps = [w for w in words[1:] if w[0].isupper()]
            if len(words) >= 3 and len(caps) >= (2 if lang == "es" else len(words) - 1):
                findings.append((WEAK if lang == "en" else STRONG, 20, "title case heading", n, title[:80]))
        elif EMOJI.match(line.strip()[:2] if line.strip() else ""):
            findings.append((WEAK, 20, "emoji as bullet", n, line.strip()[:80]))
        if re.match(r"^\s*(-{3,}|\*{3,}|_{3,})\s*$", line):
            hr += 1
        if lang == "en" and re.search(r"[“”‘]", line):
            findings.append((WEAK, 21, "curly quotes", n, line.strip()[:80]))
    if hr >= 2:
        findings.append((WEAK, 20, "%d horizontal rules between sections" % hr, 0, ""))

    findings.sort(key=lambda f: (ORDER[f[0]], f[3], f[1]))
    return findings


def strip_html(text):
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", text)
    return html_mod.unescape(re.sub(r"<[^>]+>", " ", text))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", help="text, Markdown, or HTML files, or - for stdin")
    ap.add_argument("--lang", choices=["en", "es", "auto"], default="auto")
    ap.add_argument("--html", action="store_true", help="strip HTML tags before scanning")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--strict", action="store_true", help="exit 1 on any hard or strong finding")
    args = ap.parse_args()

    status, out = 0, {}
    for path in args.files:
        if path == "-":
            name, text = "<stdin>", sys.stdin.read()
        else:
            name = path
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        if args.html or name.endswith((".html", ".htm")):
            text = strip_html(text)
        lang = detect_lang(text) if args.lang == "auto" else args.lang
        findings = scan(text, lang)
        counts = Counter(f[0] for f in findings)
        if counts[HARD] or (args.strict and counts[STRONG]):
            status = 1

        if args.json:
            out[name] = {"language": lang, "counts": dict(counts), "findings": [
                {"severity": s, "section": sec, "label": lb, "line": ln, "text": tx}
                for s, sec, lb, ln, tx in findings]}
            continue
        if len(args.files) > 1:
            print("\n=== %s ===" % name)
        print("language: %s | hard: %d | strong: %d | weak: %d" % (lang, counts[HARD], counts[STRONG], counts[WEAK]))
        for sev, sec, label, line, text_ in findings:
            where = "L%d" % line if line else "all"
            print("%-6s %-5s §%-2d %s: %s" % (sev, where, sec, label, text_))
        if not findings:
            print("No mechanical tells found. Still read it for §3, §6, §7, §26 and the cadence tells, "
                  "then run the structural pass.")

    if args.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
    return status


if __name__ == "__main__":
    sys.exit(main())
