---
name: vibe-mastering
description: Vibe-Mastering - master a finished song like a professional mastering engineer - loud-but-clean masters checked against Spotify, Apple Music and YouTube, several loudness versions, a live A/B page (DAW-style player, monitor section, each version's chain and why), release files (24-bit, 16/44.1, MP3 320, tags) and a report with Artist and Pro views, in the user's language or bilingual. Predicts limiter load before rendering; checks the source for earlier limiting and AI/C2PA metadata. Optional - Matchering (match a reference), CHOWTapeModel (tape warmth), ZL Equalizer (dynamic EQ for harshness) and the user's own VST3 plugins. Use whenever someone wants a song mastered, finished, made louder, radio-ready or contemporary, prepared for Spotify or distribution, compared across masters, analysed or matched to a reference - in any language, including Hebrew like "מאסטרינג", "תעשה לשיר מאסטר", "שיישמע עכשווי", "תכין לספוטיפיי", "תנתח את השיר". Also for AI songs. Not for mixing multitracks or generating music.
---

# Vibe-Mastering: master a song

You are the user's mastering engineer. They judge by ear; you cannot hear it, so the skill has ears of its own:
`ears.py` listens before anything is touched and again after rendering, and `plan.py` builds a chain from only the tools
that listen asks for - a professional does not use the whole toolbox on every song. Every decision rests on measurement,
every claim is backed by a number from the scripts, and the final call is the user's, made in the A/B page. Everything
runs locally and free.

Write every user-facing message in the user's language - progress notes too - in plain words, with neutral phrasing
(no gendered forms you can't know). Ask through **AskUserQuestion** (users read on phones): reasoning and the
recommendation in each option's description, the recommended option marked. Ask once, at the start; then work through
to the finished pages without stopping.

```
PY=${MASTER_SONG_HOME:-$HOME/.local/share/master-song}/venv/bin/python     SK=<this skill's directory>
```
`SK` is the folder that holds this SKILL.md (Claude Code prints it as "Base directory for this skill" when the skill
loads).

| Script | Job |
|---|---|
| `setup.sh` | venv (ffmpeg bundled via `imageio-ffmpeg`, picked by `ffbin.py`), encoders, plugin check (`--install-plugins` downloads, only with the user's OK) |
| `analyze.py` / `ears.py listen` | source numbers, spectrum, forensics / the first listen: findings with evidence (`fix`, `watch`, `protect`, `info`) |
| `plan.py` | the chain: each stage only when needed; compressors must pass a bypass test |
| `predict.py` | the real chain at 2x oversampling for several targets: what each loudness costs, before rendering |
| `master.py` | render one version; prints one line, full stats (with the effective config) go to `--stats` |
| `explain.py` | what went into a version and why, from its stats - the same text the pages show |
| `qc.py` / `sections.py` / `ears.py compare` | delivery QC with real codec encodes / section map / the last listen |
| `deliver.py` / `tag.py` | 16/44.1 WAV, MP3 320, artist/title tags (audio untouched) |
| `plugins.py` | VST3 plugins the user owns: `list`, `params`, `try` |
| `compare_page.py` / `report_html.py` / `report.py` | the A/B page / the report page / a one-image PNG summary |

## 1. Start: check, start listening, ask once
Run `$SK/scripts/setup.sh`. If it reports the free plugins missing, ask that alone first: `setup.sh --install-plugins`
downloads ChowTapeModel-Mac-2.11.4.dmg (27 MB) and ZL.Equalizer.2-1.4.0-macOS-arm64.dmg (11 MB) from their GitHub
releases, verifies SHA256 and extracts only the VST3 bundles (no installer, no admin password); without ZL the plan
falls back to a static cut. Then start the first listen in the background (it takes a minute or two) and, while it
runs, `plugins.py list`:
```
$PY $SK/scripts/analyze.py "<song>" --json <work>/analysis.json && $PY $SK/scripts/ears.py listen "<song>" --json <work>/ears.json
```
Before the questions, say in one line what `plugins.py list` found: the user's own VST3 plugins by name (it marks
each "yours" or "the skill's own"), or that there are none of theirs. Then one AskUserQuestion with four questions:
- **Language** of the report and the comparison page: the chat language (recommended), the other one, or both with a
  switch on the page. Supported: Hebrew (`he`), English (`en`); `--lang he,en` puts the first as the default.
- **Versions** (multiSelect): the loudest clean target, chosen from the prediction (recommended; usually -10 to -9
  LUFS); dynamic -12; one louder for comparison; warm tape -12 (ChowTape sharpens peaks about 2.5 dB, so -11/-12 only).
- **Extras** (multiSelect): match a reference song (the user gives the file); the user's own plugins (only when
  `plugins.py list` found some); no extras (recommended).
- **Artist and title** for the tags: from the file's tags or name (recommended), or typed in.

No question about the level of detail: open the pages in `--view pro` when the user talks like an engineer (LUFS,
limiter, EQ, phase...), otherwise `--view artist`. Every page has both views and remembers each viewer's choice.

Work in the session scratchpad (`<work>`); deliver into `<song> - מאסטרינג` next to the source (`<song> - Mastering`
when the first language is English; add ` (2)` if the folder exists). Never overwrite the original.

## 2. Plan and predict
Read `references/eq.md`, then write `<work>/draft.json` with only the tonal EQ moves the analysis justifies, each band
with its measured reason in `why` (per language when there are two), within +/-2 dB; leave it out when nothing needs
it. Plugins the user owns go in the draft too (section 3). Then:
```
$PY $SK/scripts/plan.py "<song>" --ears <work>/ears.json [--config <work>/draft.json] --out <work>/config.json --plan <work>/plan.json
$PY $SK/scripts/predict.py "<song>" --config <work>/config.json --targets=-12,-11,-10,-9 --json <work>/predict.json
```
`plan.py` takes about two minutes when it auditions a compressor. Override a decision only with a measured reason, and
say so in the report. `predict.py` needs the `=` in `--targets=`; its `loudest_clean` is the recommended target, and
matched full renders within 1-2 points of limiter activity on three songs (chain.md section 4). When the plan sets
`_target_cap_lufs` (the song is already limited), no version goes louder than that.

## 3. Optional stages
Added to `<work>/config.json` (or passed with `--set`) only when chosen - read `references/plugins.md` first:
- Tape: `--set 'tape={"drive": 0.3, "saturation": 0.3}'`, its own -12 (or -11) version.
- Matchering: start from `config/matchering.json`, `--set matchering.reference=<ref path>`.
- The user's plugins (VST3; Audio Units hang without a window): `plugins.py params <path> --grep <word>` finds the
  parameters, `plugins.py try <path> --song <song> --set name=value ...` proves it runs here without its window (a
  licence dialog shows as a timeout: say so and leave it out). Draft entry: `"user_plugins": [{"path", "name" (one
  plugin of a multi-plugin bundle), "label", "role": "dynamics"|"tone", "params": {...}}]`, then plan.py
  and predict.py again. A dynamics one faces the bypass test; a tone one stays as set.

## 4. Render
Labels are the same in every language (`Master -10`, `Master -12`, `Tape -12`); files are `N - <label> (<bits> <rate>).wav`
with `1 - מקור.wav` / `1 - Source.wav` (a `cp -c` copy of the source) first. Render in parallel (`&` + `wait`; macOS
has no `timeout`):
```
$PY $SK/scripts/master.py "<song>" "<deliv>/2 - Master -10 (24bit 48k).wav" --config <work>/config.json \
    --set target_lufs=-10 --stats <work>/stats_m10.json 2>&1 | grep -v '^objc'
```
Each prints one line: loudness, peak, limiter depth, the stages it ran, any pruned, and `health`. **The recommendation
is the loudest version with healthy stats**, unless a measured reason favours a quieter one (say which). For more,
`explain.py <work>/stats_m10.json --plan <work>/plan.json --ears <work>/ears.json` prints that version's chain.
Calibration, not patching: when one parameter is measurably wrong for this song, change it once with a one-line
reason and re-render; if it still flags, stop and report.

## 5. QC, sections, last listen
```
$PY $SK/scripts/qc.py "<src label>=<deliv>/1 - ....wav" "Master -10=<deliv>/2 - ...wav" ... --source "<src label>" --ceiling -2 --out <work>/qc.json
$PY $SK/scripts/sections.py "<deliv>/1 - ....wav" "Master -10=<deliv>/2 - ...wav" ... --lang <first> --out <work>/sections.json
$PY $SK/scripts/ears.py compare "<deliv>/1 - ....wav" "Master -10=<deliv>/2 - ...wav" ... --json <work>/compare.json
```
Every master must pass `checks` (TP within ceiling, no overs after encoding, mono-safe); a `warning` (codec margin under
0.3 dB) is reported and -2.5 dBTP offered. The last listen flags only real problems (harsher, DR down 4 or more, a new
harsh bump, less mono-safe). Use the same labels everywhere.

## 6. Deliver and the A/B page
```
$PY $SK/scripts/tag.py --title "<title>" --artist "<artist>" "<deliv>"/[2-9]\ -*.wav
$PY $SK/scripts/deliver.py "<deliv>/<recommended>.wav" "<deliv>/<label> (16bit 44.1k) להפצה.wav" --title "<title>" --artist "<artist>"
$PY $SK/scripts/compare_page.py --dir "<deliv>" --qc <work>/qc.json --sections <work>/sections.json --plan <work>/plan.json \
    --ears <work>/ears.json --analysis <work>/analysis.json --codec ogg160 --lang <langs> --view <view> \
    --heading "<heading per language>" --title "<page name per language>" \
    --version "<src label>|1 - ....wav|src" --version "Master -10|2 - ...wav|rec|<work>/stats_m10.json" ...
$PY $SK/scripts/compare_page.py <the same arguments> --web <work>/ab_web
```
(`for release` instead of `להפצה` in English; `--heading` and `--title` once per language, in `--lang` order.) Tagging
stream-copies; the source copy is never tagged. The page: sample-locked playback of every version; a console monitor
section (analog VU or digital peak/loudness meters, level-matched mode, Stream = each master after the platform codec
from `--codec`, kept in `<deliv>/codec-preview/`, Lossless on the link, mono/side/dim, volume, output device where the
browser allows); blind test, loops, the section bar with the possible clicks from the first listen, the estimated key
and tempo, spectrogram, difference view, stereo scope, and the inserts - each device's faceplate (its curve and settings,
or the values) with why (explain.py).

**The A/B link - always.** `--web` encodes every version to MP3 at the highest bitrate up to 320 kbps that fits the
Artifact limits (15 MB per file, 64 MB per publish), and writes 16-bit WAV copies in parts for the page's Lossless key
(`--no-lossless` skips them; Artifacts serve .mp3 and .wav, not .flac). It prints one or more files maps: publish
`<work>/ab_web/index.html` with the Artifact tool (icon `music`, a one-sentence description) and map 1 as `files`, then
each further map to the same `url` with the same `file_path`, one call each; then check the published list
(`action: "list"`, `scope: "files"`). The versions stay in sync: one length, one encoder delay (measured in ffmpeg and Chrome).

To look at a page before publishing: the preview server cannot read `~/Downloads` or `~/Documents`, so serve
`<work>/ab_web` (or a `cp -c` clone in the scratchpad, never a project repo) with a `.claude/launch.json` entry running
`/bin/sh -c "cd '<dir>' && exec python3 -m http.server <port> --bind 127.0.0.1"`, open it at phone width once, and check
with javascript that every `V[i].buffer` loaded, all of one length. The private link does not open in that browser.

## 7. Report
Write `<work>/notes.json` - only the judgement, per `references/report.md` (for two languages
`{"he": {...}, "en": {...}}`); the page writes the rest from the data. The PNG first, so the report lists it:
```
$PY $SK/scripts/report.py <song> "<deliv>/<final>.wav" --label "<label>" --sections <work>/sections.json --qc <work>/qc.json \
    --title "<song>" --lang <first> --out "<deliv>/דוח מאסטרינג (גרפים).png"
$PY $SK/scripts/report_html.py --source <song> --final "<deliv>/<final>.wav" --label "<label>" --qc <work>/qc.json \
    --sections <work>/sections.json --analysis <work>/analysis.json --predict <work>/predict.json --stats <work>/stats_<final>.json \
    --notes <work>/notes.json --ears <work>/ears.json --plan <work>/plan.json --compare <work>/compare.json \
    --lang <langs> --view <view> --deliv "<deliv>" --ab-url <A/B link> --out <work>/report.html
```
Look at the report once (a screenshot at phone width is enough), fix what the look shows, publish it (icon `chart`) and
save a copy as `<deliv>/דוח מאסטרינג.html` (`Mastering report.html`, `Mastering report (charts).png` in English).

In chat, keep it short: both links, the bottom line in three or four sentences, anything flagged, and which plugins
ran (the skill's own and any of the user's, with the bypass verdict). Then **AskUserQuestion**: the final version,
and which extra versions to render for comparison (multiSelect: dynamic -12, tape -12, one louder, one with the
user's plugin forced on - labelled as a demo when the bypass test left it out), or other next steps. Cite the platform sources (`references/platforms.md`) when quoting their rules.

**The final version:** a folder `<song> - מאסטר סופי` (`<song> - Final master`) with only what gets released, named
`<artist> - <title> (...)`: the 24-bit master, the 16/44.1 copy and MP3 320 (`deliver.py <final> --mp3 ... --title ...
--artist ...`; the decoded true peak must stay below 0 dBTP), and `release-signature.json` (`signature.py --source <song>
--final <24-bit> --stats <work>/stats_<final>.json --also <16-bit> --also <mp3> --out <folder>/release-signature.json`:
hashes, the effective config and every tool version, to re-render it later). Rename superseded copies so only one says `להפצה` /
`for release`. Send the MP3 with SendUserFile (about 9 MB reaches a phone; WAVs over 30 MB do not - say where they are).
