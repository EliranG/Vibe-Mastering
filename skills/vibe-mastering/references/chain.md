# The mastering chain: design, parameters, and how to read the numbers

Read this before editing a song's config or interpreting `master.py` stats.

The measurements below come from three AI-generated test songs: **A** (pop), **B** (electronic, percussive) and
**C** (pop, with a brighter top and a higher peak-to-loudness ratio than A).

## Contents
1. Signal flow and why each stage exists
2. Gain staging (why thresholds carry over between songs)
3. Deciding the EQ from `analyze.py`
4. Loudness target trade-off (measured)
5. Stats reference and health limits
6. Pitfalls
7. Prediction, forensics and sections (how far to trust them)
8. Stage selection: ears.py and plan.py

## 1. Signal flow

| # | Stage | Rate | Why |
|---|---|---|---|
| 0 | Normalize input to `input_norm_lufs` (-15) | base | Makes absolute thresholds mean the same thing for every song |
| 1 | Matchering (optional) | 44.1k via soxr VHQ | Tone + width matched to a reference track |
| 2 | ZL Equalizer 2 dynamic bands (optional) | base | Cuts harshness / sibilance only when it happens |
| 3 | CHOWTapeModel (optional) | base (plugin oversamples 4x internally) | Tape color: head bump, soft harmonics |
| 4 | HQ 4x oversampling (709-tap Kaiser FIR at 48k, >=140 dB rejection) | 4x | EQ curves keep their analog shape near 20 kHz; clipper/limiter do not alias |
| 5 | HPF 25 Hz (12 dB/oct) | 4x | Removes sub-sonic energy and DC that waste limiter headroom |
| 6 | M/S EQ (RBJ biquads designed at 4x) | 4x | Tonal balance; side HPF puts bass in mono (club/phone/vinyl-safe) |
| 7 | Low-band compressor < 120 Hz (LR4 split, perfect reconstruction) | 4x | Evens out bass notes so the sub does not drive the limiter |
| 8 | Glue compressor 2:1, sidechain HPF 90 Hz | 4x | Cohesion; the HPF stops the kick from pumping the whole mix |
| 9 | Leveling limiter (3 ms look-ahead, 200 ms release) | 4x | Caps how deep the clipper ever has to cut (`clip_max_depth_db`) |
| 10 | Soft clipper (tanh knee 3 dB) | 4x | Shaves fast transients cleaner than a limiter can at the same loudness |
| 11 | True-peak limiter (1.5 ms look-ahead, 80 ms release) | 4x | Final ceiling, provably held at 4x; margin `os_margin_db` covers downsampling |
| 12 | Downsample, TP re-check/trim, fades, TPDF dither, 24-bit | base | Delivery |

The limiter design (sliding-min over the look-ahead window -> exponential release -> boxcar of the same length)
guarantees output <= ceiling at the processing rate, so peak control is a property of the math, not of tuning.

## 2. Gain staging

Everything downstream of stage 0 sees the song at -15 LUFS integrated. `glue.thr=-17.3` and `lowcomp.thr=-18.3`
were calibrated on test song A (source -14.73 LUFS, thresholds -17/-18 there), i.e. about 2.3 and 3.3 dB below
integrated loudness. Keep that relationship: if you move `input_norm_lufs`, move the thresholds with it.
Optional stages re-normalize to -15 after they run, so enabling tape or Matchering does not shift compression.

## 3. Deciding the EQ

See `references/eq.md` (the part every run reads, kept separate so a run does not load this whole file).

## 4. Loudness target trade-off (measured, all at -2 dBTP)

| Test song A target | Reached | Leveler active | Clip residual | Limiter GR p90 | PLR | LRA (EBU, ffmpeg-verified) | Spotify turns it down |
|---|---|---|---|---|---|---|---|
| -12 LUFS | -12.01 | 0% | -53 dB | 0.2 dB | 9.9 | 10.5 (source 11.4) | 2.0 dB |
| -10 LUFS | -10.03 | 18% | -35 dB | 1.1 dB | 8.0 | 9.6 | 4.0 dB |
| -8.5 LUFS | -8.87 (not reached) | 73% | -28 dB | 1.3 dB | 6.8 | 7.4 | 5.1 dB |

Test song B: -10 failed three health checks (leveler 76%, clip residual -27.7 dB, reached -10.22); -11 failed two
(63%, -28.6 dB); -12 was clean (21.7%, -31.9 dB) and became the recommendation. Its peaks came from percussion (about
80% of peak amplitude above 120 Hz), not from bass or EQ. So -10 is a starting point, not a promise: the recommended
version is the loudest one that renders without health flags.

Every normalized platform plays all three at the same level, so the extra loudness buys density at the cost of
punch and distortion. On A, -10 was the recommended master: holding -9.5 at -2 dBTP pushed the leveler to 46% active
and clip residual to -31.8 dB, which is why -10 and not -9.5 became the default.

Test song C: -12 / -11 / -10.5 / -10 / -9.5 predicted leveler 0.2% / 5.4% / 15.9% / 38.0% / 80.2% (full 4x renders:
-10.5 16.2% -36.6 dB, -10 38.5% -33.9 dB). Calibration at -10 with lowcomp.thr -19.3, lowcomp.att_ms 15, a -1.5 dB
cut at 40 Hz, or glue.thr -18.3 left the leveler at 37.4-39.8%: the extra load came from the source's higher PLR
(12.8 vs A's 11.4, so 1.5 dB more peak to shave; 62% of top-0.1% peak amplitude above 120 Hz), and no compressor
setting fixes that. -10 was flag-free but -10.5 was recommended: the same cleanliness as A at -10 (leveler 16% vs
17%), and -10 left only 0.39 dB of Opus margin vs 0.81 at -10.5. When compressor tweaks do not move the leveler, the
loudness target is the parameter to change.

## 5. Stats reference (`master.py` output)

| Stat | Meaning | Healthy (test songs) | Flag at |
|---|---|---|---|
| `lowcomp_gr_db.p95` | bass compression on loud moments | ~2 | > 3 (bass pumping) |
| `glue_gr_db.p95` | glue compression on loud moments | ~1.5 | > 3 |
| `leveler_active_pct` | share of time the pre-clip limiter works | 0-20% | > 50% (squashed) |
| `clip_residual_db` | energy the clipper removed, re signal | <= -35 | > -30 (audible risk) |
| `limiter_gr_max_db` | final limiter depth | ~1.4 | - |
| `target_reached` | within 0.2 LU of target | true | false = chain pushing back |
| `true_peak_dbtp` | after downsampling + trim | <= ceiling | - |

`health` lists any flag that fired. Report flags to the user as they are; never present a flagged version as fine.

## 6. Pitfalls

- Early settings compressed too hard (low band p95 4.8 dB, glue 3 dB). Measure GR before trusting a threshold.
- LRA/short-term were once computed with the K-filter running across channels instead of time (scipy lfilter's default
  axis); values read 1-2 LU high. Fixed in mslib and verified against ffmpeg ebur128 (11.4 / 10.5 / 9.6 / 7.4 LU).
- The loudness search takes secant steps and stops when +1 dB of gain buys under 0.25 LU (saturation); the
  `loudness_search` stat lists every (gain, LUFS) step.
- True peak rises after sample-rate conversion (48k -> 44.1k raised it from -2.05 to -1.92); `deliver.py` re-trims.
- A source that ends mid-reverb (-32 dB at the last sample) clicks audibly after +7 dB of gain. `fade_out_ms: "auto"`
  applies a 1 s fade when the last 50 ms peaks above -50 dBFS.
- Changing a parameter and re-rendering is calibration, not patching - tell the user what changed and why, and keep
  one chain: no patch-on-patch fixes.

## 7. Prediction, forensics and sections (how far to trust them)

**predict.py** runs `prepare` + `peak_stage` from master.py at 2x oversampling (1x overestimates limiter load: 33% vs
19% at -10 on A). Measured against full 4x renders:

| Song | Target | Full render: leveler / clip residual | Prediction (2x) |
|---|---|---|---|
| A | -12 / -10 / -8.5 | 0% -53.4 / 18.8% -34.9 / 75.1% -27.9 | 0% -53.4 / 19.6% -34.8 / 75.0% -27.9 |
| A (second config) | -10 | 17.4% -34.7 | 17.1% -34.7 |
| B | -12 / -11 | 21.7% -31.9 / 63.4% -28.6 | 22.6% -31.7 / 65.2% -28.5 |
| B | -10 | 76.3% -27.7 (old loudness loop) | 82.8% -27.2 |

Both songs got the same loudest-clean target from prediction and from full renders. About a minute for 4-5 targets
(targets run in forked processes that share the prepared signal).

**forensics.py** (inside analyze.py) - limiter verdict thresholds calibrated on four files: the A source (spread of the
top 1% block peaks 1.24 dB, 11 samples within 0.5 dB of the peak) = none; the B source (0.30 dB, 275) = light peak
control; two masters at -10 and -8.9 LUFS (0.10 dB, 53k-102k samples) = limited. HF wall: both AI-generated sources
are cut at 20 kHz; the -8.9 master showed content to 22.75 kHz - clipper harmonics above the source's own ceiling.

**sections.py** - Foote novelty on chroma + spectral shape + loudness; letters at cosine distance 0.35 group only clear
repeats (on A: both choruses; the two verses were not grouped). Energy labels are relative to the loudest section.
On A the table showed the first verse lost the most PLR (-4.1 dB vs -2.8 in the choruses) - a verse is quieter and
gets lifted more, so the compressors work on it relatively harder. Point the user at such a section.

## 8. Stage selection: ears.py and plan.py

A mastering engineer listens first and reaches for a tool only when the song needs it ("do no harm" - Bob Katz;
every comparison loudness-matched - Ian Shepherd, productionadvice.co.uk). `ears.py listen` stands in for that first
listen, `plan.py` builds the chain from it, and `ears.py compare` is the last listen.

**First-listen rules** (a finding names its evidence and the tool that answers it):

| Finding | Condition | Tool |
|---|---|---|
| already dense | source check says limited/clipped, or PSR < 8, or PLR < 9 | protect: no compressors, loudness capped at the source's |
| subsonic | energy below 25 Hz > -20 dB re the 25-120 Hz band (and low end present), or DC > 0.001 | 25 Hz high-pass |
| stereo bass | side vs mid below 80 Hz > -20 dB | side high-pass 100 Hz |
| bass drives peaks | >= 50% of the top-0.1% peak amplitude from below 120 Hz | low-band compressor candidate |
| harsh bump | third-octave bump >= 2 dB (2-16 kHz, bands touching the HF cut-off excluded); comes and goes (p10 < 1, p90 >= 4) | dynamic EQ band (adjacent bumps share one band) |
| steady bump | same, but p10 >= 1 dB | static cut, min(2, median) dB |
| presence dip | 2 kHz octave >= 3 dB under 1 kHz | +1 dB @ 3.2 kHz, Q 0.8, mid |
| abrupt end | last 50 ms peak > -50 dBFS | 1 s fade |

DR thresholds (Shepherd, read on productionadvice.co.uk: DR12+ very dynamic, DR8 or lower risks squashed, DR6 or less
"loudness war") judge a finished master, not a source: the A source is DR 6.2 with no limiter at all, so the
"already dense" rule uses the source check and PSR/PLR instead. PSR < 8 as "heavy limiting" is reported from Shepherd's
AES e-Brief (the brief's existence verified; the threshold not read in full text). Sharpness is DIN 45692 via MoSQITo
(Apache-2.0), heard at -18 LUFS with 0 dBFS = 100 dB SPL, 2.2 s per song; the 0.1 acum "harsher" flag is judgement -
no published just-noticeable difference was found. No verified genre target curve exists (the numeric slope attributed
to Pestana et al. 2013 could not be read in the paper), so tonal EQ stays a per-song judgement.

**Compressor bypass test.** A candidate compressor is rendered with and without at the probe loudness (default -10,
2x oversampling, same code as predict.py) and stays only if it saves >= 5 points of leveler activity, >= 3 dB of
clipper residual, or >= 1 DR point (judgement thresholds). Test song C at -10.5 with a hand-made EQ:

| Chain | Leveler active | Clipper residual |
|---|---|---|
| both compressors | 15.9% | -36.6 dB |
| no glue | 14.9% | -34.5 dB |
| no low-band | 15.9% | -36.6 dB |
| none | 14.6% | -34.9 dB |

With the planned (minimal) EQ at -10: glue on vs off = leveler 18.5% vs 13.2%, DR 5.2 vs 4.9 (C) and 1.5% vs 0.6%,
DR 3.6 vs 3.5 (A): out on both. The low-band compressor never became a candidate (38% and 42% of the peaks come
from the bass).

**Five inputs, first listen -> plan:** the A and C sources: presence EQ + a dynamic band at 10 kHz (+ a fade on A,
which ends mid-reverb); two finished masters: "already dense" (source check: limited; DR 5.9 and 4.3), nothing added,
loudness capped; an isolated lead vocal (DR 14.9): dynamic band at 10 kHz (sibilance) + fade, no low-end stages.

**Full chain vs planned chain, C at -10.5:** leveler 16.2% vs 3.4% of the time; DR 5.9 vs 5.3; sharpness change
+0.011 vs -0.037 acum; largest octave change 1.9 vs 1.0 dB. The planned chain stays closer to the source's tone and
limits far less often, but its loud sections are denser (DR -0.6; the glue accounts for about 0.3 of it). The ears
report such trade-offs; the user's ears decide.

**Full chain vs planned chain, A at -10** (same loudness, same source): leveler 17% vs 1.1%; LRA 9.5 vs 10.9 (source
11.4); most compressed section (verse 1) PLR -4.1 vs -3.7, median section -2.5 vs -2.1; DR 4.3 vs 3.6; sharpness
+0.002 vs +0.000; codecs worst -0.68 vs -0.80 dBTP. The dynamic band at 10 kHz acted dynamically here (-2.0 dB loud /
-0.6 dB quiet), unlike on C. The planned chain keeps the verse/chorus contrast and limits far less, but the choruses
sit denser (lower DR) because nothing evens them out - the ears report the trade-off, the user decides by ear.

**Idle peak stages.** `master.py` renders again without the leveler and/or the clipper when they had nothing to do
(leveler < 1% active and < 1 dB; clipper residual < -45 dB) and keeps that render only if it still reaches the target
with no health flag AND the final limiter's deepest reduction grows by at most 1 dB. The second condition came from a
measurement: dropping an "idle" clipper (residual -54.9 / -46.7 dB) handed its few shaved peaks to the limiter, whose
maximum went from 1.39 to 3.59 dB (C at -12) and 4.05 dB (A, tape -12) - the clipper exists to shave short transients
more cleanly than a limiter, so that was not idle. With the rule, A's tape -12 dropped only the leveler (limiter
+0.02 dB) and kept the clipper.

**predict.py deadlock (fixed).** With both compressors off, the first numba load happened inside the forked workers and
they hung at 0% CPU; the parent now loads the numba functions before forking (the same run then took 71 s).
