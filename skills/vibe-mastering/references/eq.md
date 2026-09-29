# Deciding the tonal EQ (read before writing draft.json)

Kept apart from chain.md so a run reads only this part. Each band in `draft.json` carries its own reason in `why` - a
string, or `{"he": "...", "en": "..."}` when the report is in more than one language - and the pages show it next to
the band (explain.py). Example: `{"type": "peak", "f": 280, "g": -1.5, "q": 0.8, "ch": "stereo", "why": "250 Hz-1 kHz flat at -11 dB re total: boxy"}`.

## How to decide

There is no default tonal EQ: every move is decided per song. Read `analyze.py`'s spectrum and decide each move with
a one-line reason you can repeat to the user. Keep moves within +/-2 dB and broad (Q <= 1) - mastering EQ corrects
balance; it does not re-mix.

## Worked examples

Test song A (pop), `analyze.py` octave table - equal 1-octave bands, mid energy in dB re total, and side minus mid:

| Octave (Hz) | 31.5 | 63 | 125 | 250 | 500 | 1k | 2k | 4k | 8k | 16k |
|---|---|---|---|---|---|---|---|---|---|---|
| Mid re total | -7.5 | -4.1 | -8.4 | -10.8 | -11.0 | -11.3 | -15.2 | -18.1 | -21.4 | -30.1 |
| Side minus mid | -23.5 | -21.0 | -9.2 | -5.4 | -6.5 | -5.9 | -4.2 | -6.4 | -9.4 | -10.1 |

Third-octave bumps (>=1.5 dB over neighbours): 630 Hz 1.6, 1 kHz 1.6, 1.26 kHz 1.7, **10 kHz 2.2**.

What was concluded from it (judgement, not a validated norm):
- 250 Hz-1 kHz flat at about -11 while everything above falls away: mid-heavy/boxy -> -1.5 dB @ 280 Hz (mid), -1 dB (side).
- 2 kHz 4 dB below 1 kHz: vocal presence missing -> +1 dB @ 3.2 kHz, Q 0.8.
- 8-16 kHz low -> +2 dB high shelf @ 10 kHz (mid), +1.5 dB @ 5 kHz (side) for air and width. The shelf sits on a
  2.2 dB third-octave bump at 10 kHz; with a bump there, prefer a smaller shelf plus a dynamic band on the bump.
- 63 Hz octave the loudest (bass notes at 41/46/52 Hz, not a resonance) -> only -0.8 dB @ 45 Hz; the low-band compressor handles the rest.
- Side energy in the lowest octaves -> side HPF 100 Hz (mono bass). Result: side below 60 Hz went from -24 to -36 dB re mid.

After those moves the master measured (relative, loudness-matched): 2.5-5 kHz +1.8, 5-10 kHz +2.0, 10-16 kHz +2.4, 20-60 Hz -0.9 dB.

Test song B (electronic; source -15.2 LUFS / -2.52 dBTP, LRA 4.6): 40-60 Hz loudest, a 200-315 Hz plateau, the
deepest dip at 1.6-5 kHz, a local 10 kHz peak and energy up to 20 kHz. The EQ cut 50 Hz -0.8, 250 Hz -1.5, lifted
2.5 kHz +1.5 (Q 0.7), cut 10 kHz -1, dropped the air shelf, kept side HPF, side +1 dB from 5 kHz. A and B needed
opposite treatment at 10 kHz - decide from the analysis, never from a default.

Test song C (pop; source -15.96 LUFS / -3.21 dBTP, PLR 12.8, LRA 4.6): top already bright (8k/16k octaves -16.9/-22.2
re total vs A's -21.4/-30.1), 10 kHz bump +2.2 and 12.7 kHz +1.7, side at the top as wide as the mids, boxiness at
630-800 Hz rather than 280 Hz, bass notes at 36-39 Hz. EQ: -0.8 @ 40 Hz (mid), -1 @ 315 Hz and -1.5 @ 700 Hz (both
stereo), +1 @ 3.2 kHz (mid), side HPF 100 Hz, no air shelf, no side shelf; one dynamic band at 11.3 kHz Q 2.5
between the two bumps.

Mid and side: the same cut applied to both mid and side is simply a stereo cut - it does not change width. To narrow
or widen a region, change only the side (or change them by different amounts). Check with qc.py `side_minus_mid_db`.

Cautions:
- AI-generated sources often carry metallic/phasey artifacts in 8-16 kHz and a cut-off near 16 kHz.
  An air shelf lifts those too. Say so to the user; offer the ZL dynamic band at 6-9 kHz instead of more shelf.
- Nothing above the source's cut-off can be created by EQ; boosting there only raises noise.
- With Matchering on, use `config/matchering.json` (flat tonal EQ, side HPF kept) - Matchering already did the tone.
