# Platform targets and delivery facts

Verified 2026-09-23. Re-check the Spotify page if a decision depends on it and this date is old.

## Loudness normalization

| Platform | Plays at | Turns quiet tracks up? | Source |
|---|---|---|---|
| Spotify (Normal) | -14 LUFS | Yes, keeping 1 dB headroom for lossy encoding | Spotify for Artists, official |
| Spotify Loud / Quiet | -11 / -19 LUFS | Loud mode applies a limiter at -1 dB (5 ms attack, 100 ms decay) | official |
| YouTube | -14 LUFS | No, only turns loud content down | secondary sources |
| Apple Music (Sound Check) | -16 LUFS | No, only down | secondary sources |

Consequence: a louder master is not louder on streaming; it is turned down. Loudness above about -14 buys density,
not level. Radio has no universal LUFS target; stations run their own processing, so deliver the same master.

## True peak

Spotify, official: keep true peak below -1 dBTP; if the master is louder than -14 LUFS, keep it below **-2 dBTP**.
Measured on the test songs (decode to float after encoding with the real codecs):

| Master TP | AAC 256 (Apple) | Ogg 160 (Spotify) | Ogg 320 | Opus 128 (YouTube) | MP3 320 | MP3 128 |
|---|---|---|---|---|---|---|
| -1.08 dBTP (-9.5 LUFS) | -0.38 | +0.01 | -0.76 | **+0.12** (3 clipped samples) | -0.85 | **+0.32** |
| -2.05 dBTP (-10 LUFS) | -1.11 | -1.02 | -1.58 | -0.79 | -1.70 | - |
| -2.04 dBTP (-8.9 LUFS) | -0.81 | -0.49 | -1.72 | -0.47 | -1.55 | - |

Lossy codecs added up to about 1.3 dB of peak on a pop test song and 1.7-1.8 dB (Opus) on an electronic one, where the
-2 dBTP masters still passed but with only 0.3-0.4 dB to spare. -2 dBTP kept every codec clean on both; -1 did not on
the pop song.
`qc.py` warns when the worst decoded peak is within 0.3 dB of 0 dBFS; in that case consider -2.5 dBTP. Default ceiling: -2 dBTP
for any master louder than -14 LUFS; -1 dBTP is acceptable only at -14 LUFS or quieter.

## Deliverables

- **Master:** 24-bit WAV at the source sample rate (no SRC in the main file), TPDF dither.
- **Distribution/radio/CD:** 16-bit 44.1 kHz WAV via `deliver.py` (soxr VHQ + TPDF, TP re-trimmed after SRC).
- **ISRC:** assigned by the distributor; do not invent one.
- Files over 30 MB cannot be sent to the phone with SendUserFile; a 3.5 min 24/48 WAV is about 60 MB. Say where it is on disk.

## Sources
- https://support.spotify.com/us/artists/article/loudness-normalization/
