# CLAUDE.md

## Human-facing text runs the humanizer passes

Before you deliver or commit any text a person will read (docs, READMEs, PR descriptions,
commit messages, emails, WhatsApp messages, Instagram captions, video scripts, property
descriptions, dossiers, newsletters), run it through the skills in `.claude/skills/`:

1. **`humanizer`** (pass 1: words and phrasing). Use embedded mode: return only the
   final text. For Spanish, it reads `references/espanol.md`.
2. **`structural-humanizer`** (pass 2: shape). Run it on outward-facing pieces that tell
   a story or make an argument: captions, scripts, newsletters, blog posts, client
   stories. Skip it for short factual text such as commit messages, listings, and
   one-line replies.
3. **Voice layer** last, when one applies (for example the `pedro-leon-brand` or
   `tailex-brand` skill). Brand rules win on word choice and tone.

When the text is in a file, run the scanners before handing it over and fix every hard
or strong finding:

```bash
python3 .claude/skills/humanizer/scripts/scan_tells.py FILE
python3 .claude/skills/structural-humanizer/scripts/structural_scan.py FILE
```

Never invent a fact, name, number, quote, or feeling to make text sound more human. If
a sentence needs a specific you do not have, ask for it.

Does not apply to code, config, data, quotations, or text the user asks to keep
verbatim.
