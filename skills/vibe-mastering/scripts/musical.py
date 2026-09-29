#!/usr/bin/env python3
"""Key and tempo estimates for a song - shown on the pages as an estimate, never used by the chain.
  musical.py SONG.wav          prints the key, the tempo and how sure each one is

key(x, sr)   chroma from the tonal peaks of the spectrum (drums and noise have no peaks to count), correlated with the
             Albrecht & Shanahan (2013) major/minor profiles, built from popular music, in all 12 keys; `confidence` =
             best minus second-best correlation. The classic Krumhansl-Kessler profiles named a pop test song F# major
             although its bass plays E, which F# major does not have; these profiles name G# minor, which fits its notes.
tempo(x, sr) spectral-flux onset strength, its autocorrelation weighted by a log-normal prior around 120 BPM (the usual
             guard against half/double-tempo answers); the other octave is reported too, as `alt`.
Both are standard, approximate methods: a close relative key (C major vs A minor) or half/double tempo can come out."""
import sys, os, json, numpy as np

NAMES = {"major": ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"],   # the spelling musicians use for each key
         "minor": ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "G#", "A", "Bb", "B"]}
MAJOR = np.array([0.238, 0.006, 0.111, 0.006, 0.137, 0.094, 0.016, 0.214, 0.009, 0.080, 0.008, 0.081])
MINOR = np.array([0.220, 0.006, 0.104, 0.123, 0.019, 0.103, 0.012, 0.214, 0.062, 0.022, 0.061, 0.052])

def key(x, sr, n=8192):
    m = x.mean(1) if x.ndim == 2 else x
    win = np.hanning(n); f = np.fft.rfftfreq(n, 1/sr); ok = (f >= 60) & (f <= 2500)
    pc = (np.round(69 + 12*np.log2(f[ok]/440.0)).astype(int)) % 12
    chroma = np.zeros(12)
    for s0 in range(0, len(m) - n, n):
        mag = np.abs(np.fft.rfft(m[s0:s0+n]*win))[ok]
        if mag.max() < 1e-6: continue
        # tonal peaks only: a bin above both neighbours and 4x the local median of the frame
        loc = np.convolve(mag, np.ones(31)/31, mode="same")
        peak = (mag[1:-1] > mag[:-2]) & (mag[1:-1] > mag[2:]) & (mag[1:-1] > 4*loc[1:-1])
        idx = np.flatnonzero(peak) + 1
        np.add.at(chroma, pc[idx], mag[idx])
    if chroma.sum() == 0: return None
    scores = []
    for tonic in range(12):
        for mode, prof in (("major", MAJOR), ("minor", MINOR)):
            scores.append((float(np.corrcoef(chroma, np.roll(prof, tonic))[0, 1]), tonic, mode))
    scores.sort(reverse=True)
    (r, tonic, mode), second = scores[0], scores[1]
    rel, rmode = (tonic + (3 if mode == "minor" else 9)) % 12, ("major" if mode == "minor" else "minor")   # the relative key
    nm = NAMES[mode][tonic]
    return dict(name=f"{nm} {mode}", short=nm + ("m" if mode == "minor" else ""), tonic=nm, mode=mode,
                relative=f"{NAMES[rmode][rel]} {rmode}", correlation=round(r, 3),
                confidence=round(r - second[0], 3), runner_up=f"{NAMES[second[2]][second[1]]} {second[2]}")

def tempo(x, sr, n=2048, hop=512, lo=60.0, hi=200.0):
    m = x.mean(1) if x.ndim == 2 else x
    win = np.hanning(n); f = np.fft.rfftfreq(n, 1/sr); band = (f >= 30) & (f <= 8000)
    frames = (len(m) - n)//hop
    if frames < 100: return None
    prev = None; onset = np.zeros(frames)
    for i in range(frames):
        s = np.log1p(1000*np.abs(np.fft.rfft(m[i*hop:i*hop+n]*win))[band])
        if prev is not None: onset[i] = np.maximum(s - prev, 0).sum()
        prev = s
    k = int(0.5*sr/hop); onset = np.maximum(onset - np.convolve(onset, np.ones(k)/k, mode="same"), 0)
    fps = sr/hop; lags = np.arange(int(fps*60/hi), int(fps*60/lo) + 2)
    o = onset - onset.mean()
    acf = np.array([np.dot(o[:-L], o[L:])/(len(o) - L) for L in lags])
    bpm = 60*fps/lags
    prior = np.exp(-0.5*(np.log2(bpm/120.0)/1.0)**2)
    score = acf*prior; i = int(np.argmax(score))
    if 0 < i < len(score) - 1:                                     # parabolic refinement of the lag
        a, b, c = score[i-1], score[i], score[i+1]; d = 0.5*(a - c)/(a - 2*b + c) if (a - 2*b + c) != 0 else 0
        L = lags[i] + d
    else: L = lags[i]
    est = 60*fps/L
    alt = est*2 if est < 100 else est/2
    top = np.sort(score)[::-1]
    return dict(bpm=round(est*2)/2, alt=round(alt*2)/2, clarity=round(float((top[0] - np.median(score))/(abs(top[0]) + 1e-12)), 2))

def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import mslib as L
    x, sr = L.read_stereo(sys.argv[1])
    print(json.dumps(dict(key=key(x, sr), tempo=tempo(x, sr)), ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main()
