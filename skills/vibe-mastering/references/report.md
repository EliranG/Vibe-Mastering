# Writing the report (notes.json for report_html.py)

`report_html.py` draws every number, chart and table, explains each metric, and writes by itself everything that only
restates the data: what you get (from `--deliv`), the chain and what was left out, with the reasons (explain.py - the
same text as the A/B page), the section to listen to, the platforms and codecs, the prediction, the sound pictures.
`notes.json` carries only what needs judgement for this song. Keep it short: every word is written once per language.

## Views and languages
The page has an Artist view (plain words, the essentials) and a Pro view (every number, table and chart); `--view`
picks the one it opens in and each reader can switch. The audio and the conclusions are the same in both, so write one
set of notes that reads well in both: conclusions first, numbers as evidence. With `--lang he,en` give one object per
language, `{"he": {...}, "en": {...}}` - the same content, not a translation that adds or drops points.

## Tone
- The reader's language, plain words; the glossary explains LUFS, True Peak, PLR, LRA, limiter/clipper, EQ.
- Conclusions first: "הבית הראשון נדחס יותר מכל שאר הקטעים: ה'פאנץ׳' שלו ירד ב-4.1 dB".
- Say what is uncertain or a judgement call, and say plainly when a version carries a health flag. Never present a
  flagged version as fine; never claim you heard anything; never repeat the AI's verdicts as facts.
- Numbers with units are isolated automatically for right-to-left text.

## Fields
| Field | Content |
|---|---|
| `page_title` | the Artifact name: `מאסטר „<song>״` / `Master: <song>` - a name, no explainer after a dash |
| `title`, `artist`, `date` | header |
| `bottom_line` | a JSON list of 3-5 sentences, one string each (a single string is split at sentence ends): ready or not (LUFS/TP, checks), what the listener gains, what streaming does to the level, the trade-off the chain made, any refinement |
| `chips` | `[[text, "ok"/"warn"/"bad"/""], ...]` - status at a glance |
| `recommendations` | a JSON list, one next step per string - concrete steps: which section to audition and how (loop, normalized mode, mono), device checks, which file to upload, the distributor's AI disclosure when the source is AI-generated |

Optional, only when the automatic text would miss something: `files` (`[{name, use, url?}]`), `steps`
(`[{what, why, effect?}]`, shown in the Pro view as engineer's notes), `sections_notes`, `sound_notes`,
`platform_notes`, `prediction_notes`, `source_notes` - each replaces the automatic paragraph.

Worked examples of the older, longer format, names anonymized: `references/examples/notes_example_en.json` (English)
and `references/examples/notes_example_he.json` (Hebrew).
