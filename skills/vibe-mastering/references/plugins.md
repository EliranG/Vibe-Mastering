# Optional open-source stages: what they are and how they measured

Installed under `~/.local/share/master-song/plugins/` (not the system Plug-Ins folder, so nothing else changes).
Loaded headless through `pedalboard`. The `objc[...] Class ... is implemented in both` lines on load are
harmless duplicate-class warnings from the two JUCE builds.

## CHOWTapeModel 2.11.4 (GPL-3, jatinchowdhury18/AnalogTapeModel)
Signed and notarized pkg (Developer ID Jatin Chowdhury). Physical hysteresis model of analog tape.

Settings used (`config.tape`): tape on, mode **STN** (default), drive 0.3, saturation 0.3, bias 0.5, 4x
linear-phase oversampling for render; wow/flutter, degrade, chew, loss, tone, compression and input filters OFF;
dry/wet 100%.

**Phase: only the bass is rotated.** Band-limited correlation against the input (a pop test song): above 200 Hz lag -1 to -2
samples, normal polarity, correlation 0.98; 150-500 Hz lag -9, normal; below 150 Hz the output looks inverted and
~160 samples late (correlation 0.98). So there is no plugin latency to compensate - there is a low-frequency phase
rotation. `mslib.align_to` therefore correlates above 200 Hz only (after a full-band version wrongly shifted and
flipped the whole signal by 130-173 samples, which broke A/B sync; fixed and verified: tape version vs master at lag 1).

**The key limitation - it costs about 3 dB of peak headroom.** At equal loudness the tape output's peak-to-loudness
ratio rose by +2.5 dB (STN), +3.0 (RK2/RK4/NR4/NR8) and +4.5 dB (V1); per 100 ms block, loud-passage peaks rose by a
median +0.9 dB and up to +5.2 dB. The bass phase rotation changes how bass and upper frequencies line up, which
makes the combined waveform peakier - it sharpens transients rather than rounding them off.
In the chain that means:

| Tape version (drive/sat 0.3) | Leveler active | Clip residual | Health |
|---|---|---|---|
| -10 LUFS, NR4 | 62% | -31.3 dB | flagged "squashed" |
| -10 LUFS, NR4 + -1.5/-2 dB @ 90 Hz to undo the head bump | 64% | -31.6 dB | flagged - the low end was not the cause |
| -10 LUFS, drive/sat 0.15 | 63% | -31.3 dB | flagged - drive was not the cause |
| **-11 LUFS, STN** | 8.6% | -38.5 dB | clean |
| **-12 LUFS, STN** | 0.6% | -45.0 dB | clean |

So offer tape as its own version at -11 or -12 LUFS, never on the -10 or louder master. Match it to a non-tape
version's loudness (normally the Dynamic -12) so the A/B isolates the tape itself. On a percussive test song even
-12 tape ran the leveler at 47% - read `health` and the leveler figure before recommending it.

Measured at 48 kHz:
- Never use the plugin's dry/wet for parallel blending: the rotated bass would partly cancel against the dry bass.
- Level drop -7.5 LU (drive/sat 0.3) and -14.6 LU (0.15); `master.py` restores loudness afterwards.
- Harmonic distortion on a -12 dBFS sine: about -39 to -40 dB (about 1%) at 100 Hz and 1 kHz, nearly the same for
  drive/sat 0.1-0.5.
- Low-level response (noise at -40 dBFS) vs 1 kHz: +1.5 to +2 dB head bump at 60-120 Hz, -0.4 to -1.6 dB at
  10-16 kHz. At programme level the top-end loss is material-dependent: a pop test song's tape version was 0.7 dB darker at
  10-16 kHz than the plain master, an electronic one's 2.1 dB (5-10 kHz) and 3.3 dB (10-16 kHz). Check `qc.py` spectra and tell
  the user when the tape version is noticeably darker.
- The level drop before make-up varied between identical runs on the electronic test song (-9.27 to -9.66 LU); make-up is measured
  per run, so this does not reach the output.
- Takes about 7 s for a 3.6 min song.

Offer it as "warmth / analog glue". It is a taste choice. Render it as its own version so the user can A/B it.

## ZL Equalizer 2 1.4.0 (AGPL-3, ZL-Audio/ZLEqualizer)
The pkg is unsigned (normal for this project); its SHA256 matches the digest GitHub publishes for the release asset.

Parameter pattern for band i: `filter_status{i}_filter_status` (On), `filter_type{i}_filter_type` (Peak),
`lrmode{i}_lrmode` (Stereo/Mid/Side), `freq{i}_freq`, `q{i}_q`, `gain{i}_gain` (static gain),
`target_gain{i}_target_gain` (gain reached when the band is over threshold), `dynamic_on{i}_dynamic_on`,
`threshold_db_{i}_threshold_db`, `knee_width{i}_knee_width`, `attack{i}_attack`, `release{i}_release`,
`side_freq{i}_side_freq`, `side_q{i}_side_q` (detector band). 609 parameters in total.

Measured: zero latency; with no bands the output nulls against the input at -156 dB (transparent).
A Mid band at 3.5 kHz, Q 1, target -4 dB, threshold = 85th percentile of that band's 50 ms level (auto), attack
5 ms, release 120 ms: the band dropped **3.1 dB when loud** and **0.3 dB when quiet** - it acts only on the peaks.

The auto threshold is a percentile of our own 50 ms RMS band level, while ZL's detector reads the band its own way, so on a band that is present almost all the time the dynamic band acts nearly statically. On a bright pop test song (11.3 kHz, Q 2.5, range -3): -2.11 dB when loud, -1.94 when quiet at pct 60; -1.62 quiet even at pct 95 (threshold 10 dB higher). Two bands (10k + 12.7k, Q 3) cut about -3 dB constantly. Report such a band as a near-constant cut, and read `change_when_quiet_db` before calling it dynamic.

`config.dyneq.bands[]`: `{f, q, ch: mid|side|stereo, range_db (negative = cut), threshold: "auto"|dBFS, pct, att_ms, rel_ms, knee}`.
Typical uses: harsh vocal 2.5-5 kHz (mid), sibilance 6-9 kHz (mid, Q 2, range -3 to -5), boomy bass notes 80-200 Hz.
`stats.dyneq.bands[].change_when_loud_db / change_when_quiet_db` report what it actually did.

## Matchering 2.0.6 (GPL-3, sergree/matchering, PyPI)
Matches the target's frequency response, RMS and stereo width to a reference track. Needs a **reference file from
the user**: a released song whose sound they want (lossless WAV/FLAC ideal; a good MP3 works).

How `master.py` uses it: target and reference go to 44.1 kHz with soxr VHQ (Matchering works internally at 44.1k
and would otherwise resample with resampy), Matchering runs with `use_limiter=False, normalize=False` into a float
file, the result comes back to the source rate with soxr, and is aligned. Our chain then sets loudness and true
peak, so the platform rules still hold. Use `config/matchering.json` (tonal EQ flat, mono-bass side HPF kept).
QC can print the master's spectrum minus the reference's (`qc.py --reference`).

Limits: it matches an average spectrum, so a reference in a different style or key/arrangement density can pull the
tone somewhere odd. If `spectrum_minus_reference_db` shows the master still far off (>3 dB in a band) or the
result sounds wrong, say so rather than forcing it.

## Plugins the user owns (VST3, `user_plugins`)
Any VST3 the user has bought can join the chain through pedalboard, which also selects one plugin out of a bundle
of several (`plugin_name`, for bundles that hold many plugins in one file). `scripts/plugins.py`:
- `list` scans the standard VST3 folders (and the skill's own plugins folder); `params <path> [--grep]` prints each
  parameter's name for the config, units, range and value now; `try <path> --song ... --set name=value` runs the
  loudest 20 s without the plugin's window and reports the delay, polarity, level and peak change it adds.
- Every load runs in a child process with a time limit: a plugin that waits for a licence dialog never returns, and
  that must fail during `try`, not in the middle of a render.
- Audio Units are not supported: `get_plugin_names_for_file` on Apple's own
  `/System/Library/Components/AudioDSP.component` hung for over 2 minutes without a window.

In the chain (`master.py stage_user_plugin`): after Matchering, dynamic EQ and tape, in the order listed, at the
song's own rate, each followed by `align_to` (delay and polarity measured above 200 Hz and undone) and the usual
renormalisation. The skill's EQ, compressors and three-stage peak control come after them, so the ceiling holds
whatever the plugin does. `plan.py`: `role: "tone"` is the user's taste and stays as set; `role: "dynamics"` gets the
same bypass test as the built-in compressors, against the finished chain, and is dropped with its numbers when it
does not help.

Validated with the two open-source VST3s standing in for a user's plugins (60 s excerpt of a test song):
CHOWTapeModel with only its compressor on (`role: "dynamics"`, amount 6 dB): lag 0,
normal polarity, +4.8 LU before make-up; bypass test at -10 LUFS with it vs without: clipper residual -112.9 vs
-38.7 dB, DR 3.6 vs 4.5, so it stayed on the clipper rule (while costing 0.9 DR - the same rule as the built-in
compressors). ZL Equalizer 2 left flat (`role: "tone"`): lag 0, 0.0 LU. The render reached -10.01 LUFS / -3.02 dBTP
with no warnings and listed both in `chain_used`. No commercial plugin has been tested yet:
whether its licence works without a window is exactly what `plugins.py try` answers.
