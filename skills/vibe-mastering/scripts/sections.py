#!/usr/bin/env python3
"""Section map + per-section stats.
  sections.py SOURCE.wav ["label=version.wav" ...] --out sections.json [--lang en|he] [--source-label LABEL]
Finds section boundaries on the source (Foote checkerboard novelty on a self-similarity matrix of chroma + spectral
shape + loudness, 0.5 s frames), groups repeated sections by letter (A, B, ...) and tags each with an energy level.
Then measures every version per section: integrated loudness, true peak, PLR and top-end (8-16 kHz) share.
Automatic and approximate: it finds where the song changes character, it does not know what a "chorus" is.
Letters are conservative (cosine distance 0.35): only clear repeats share a letter. On the reference song both
choruses (1:04, 2:12) got the same letter; the two verses did not. Energy is relative to the loudest section."""
import sys, os, json, argparse, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mslib as L
from scipy.signal import stft, find_peaks
from scipy.ndimage import uniform_filter1d
from scipy.cluster.hierarchy import linkage, fcluster

HOP = 0.5   # seconds per feature frame
SOURCE = {"en": "Source", "he": "מקור"}                          # default label of the source version
ENERGY = {"en": ("loud", "medium", "quiet"), "he": ("שיא", "בינוני", "שקט")}

def features(x, sr):
    m = x.mean(1); n = 8192; hop = int(HOP*sr)
    f, t, Z = stft(m, sr, nperseg=n, noverlap=n-hop, boundary=None, padded=False); P = np.abs(Z)**2
    ok = (f > 55) & (f < 5000); midi = 69 + 12*np.log2(f[ok]/440.0); pc = np.round(midi).astype(int) % 12
    chroma = np.stack([P[ok][pc == k].sum(0) for k in range(12)]); chroma /= chroma.sum(0, keepdims=True) + 1e-12
    edges = np.geomspace(60, min(16000, sr/2 - 500), 25)
    bands = np.stack([P[(f >= lo) & (f < hi)].sum(0) for lo, hi in zip(edges[:-1], edges[1:])])
    bands_db = 10*np.log10(bands + 1e-12); shape = bands_db - bands_db.mean(0, keepdims=True)
    loud = 10*np.log10(P.sum(0) + 1e-12)
    z = lambda a: (a - a.mean(1, keepdims=True)) / (a.std(1, keepdims=True) + 1e-9)
    F = np.vstack([z(chroma), 0.7*z(shape), 2.0*z(loud[None])])
    return uniform_filter1d(F, 4, axis=1), loud, t

def novelty(F, half=16):
    Fn = F / (np.linalg.norm(F, axis=0, keepdims=True) + 1e-9); S = Fn.T @ Fn; N = S.shape[0]
    g = np.exp(-0.5*(np.linspace(-2, 2, 2*half)**2)); K = np.outer(g, g)*np.outer(np.r_[-np.ones(half), np.ones(half)], np.r_[-np.ones(half), np.ones(half)])
    Sp = np.pad(S, half, mode="edge"); nov = np.array([np.sum(Sp[i:i+2*half, i:i+2*half]*K) for i in range(N)])
    return np.maximum(nov, 0)

def segment(x, sr, min_len=8.0):
    F, loud, t = features(x, sr); nov = novelty(F); N = len(nov); dur = len(x)/sr
    pk, _ = find_peaks(nov, distance=int(min_len/HOP), height=nov.mean() + 0.3*nov.std())
    # a silence gap is always a boundary (breaks, stops)
    quiet = loud < np.percentile(loud, 95) - 25
    edges = np.flatnonzero(np.diff(quiet.astype(int)) != 0) + 1
    b = sorted(set([0] + [int(p) for p in pk] + [int(e) for e in edges] + [N]))
    merged = [b[0]]
    for v in b[1:]:
        if (v - merged[-1])*HOP >= min_len or v == N: merged.append(v)
    if len(merged) > 2 and (merged[-1] - merged[-2])*HOP < min_len: merged.pop(-2)
    segs = [(merged[i], merged[i+1]) for i in range(len(merged)-1)]
    means = np.stack([F[:, a:b].mean(1) for a, b in segs])
    letters = ["A"]*len(segs)
    if len(segs) > 1:
        Z = linkage(means, "average", metric="cosine"); cl = fcluster(Z, t=0.35, criterion="distance"); order = {}
        letters = [order.setdefault(c, "ABCDEFGHIJ"[len(order) % 10]) for c in cl]
    return [(a*HOP, min(b*HOP, dur), letters[i]) for i, (a, b) in enumerate(segs)]

def seg_stats(x, sr, a, b):
    s = x[int(a*sr):int(b*sr)]
    I = L.lufs(s, sr) if len(s) > 0.5*sr else float("nan"); tp = L.true_peak_db(s, sr)
    from scipy.signal import welch
    f, P = welch(s.mean(1), sr, nperseg=4096); top = 10*np.log10(P[(f >= 8000) & (f < 16000)].sum()/(P.sum() + 1e-20) + 1e-20)
    r = lambda v: None if not np.isfinite(v) else round(float(v), 1)
    return dict(lufs=r(I), true_peak=r(tp), plr=r(tp - I), top_8_16k_db=r(top))

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("source"); ap.add_argument("versions", nargs="*"); ap.add_argument("--out", required=True)
    ap.add_argument("--lang", choices=sorted(SOURCE), default="en")
    ap.add_argument("--source-label", help="the source's label, the same one given to qc.py (default: Source / מקור)")
    a = ap.parse_args(); x, sr = L.read_stereo(a.source); src = a.source_label or SOURCE[a.lang]
    loud, medium, quiet = ENERGY[a.lang]
    segs = segment(x, sr)
    out = dict(source=src, sections=[], versions=[src] + [v.split("=", 1)[0] for v in a.versions])
    vers = [(src, x, sr)] + [(lab, *L.read_stereo(p)) for lab, p in (v.split("=", 1) for v in a.versions)]
    rows = [(s0, s1, letter, {lab: seg_stats(y, ysr, s0, s1) for lab, y, ysr in vers}) for s0, s1, letter in segs]
    top = max(r[3][src]["lufs"] for r in rows if r[3][src]["lufs"] is not None)
    for i, (s0, s1, letter, st) in enumerate(rows):
        rel = (st[src]["lufs"] - top) if st[src]["lufs"] is not None else -99   # vs the loudest section
        key = "loud" if rel >= -2 else ("quiet" if rel <= -8 else "medium")        # energy_key lets a page show it in any language
        energy = dict(zip(("loud", "medium", "quiet"), (loud, medium, quiet)))[key]
        out["sections"].append(dict(index=i+1, start=round(s0, 1), end=round(s1, 1), letter=letter, energy=energy, energy_key=key, stats=st))
        print(f"{i+1:2d} {int(s0)//60}:{int(s0)%60:02d}-{int(s1)//60}:{int(s1)%60:02d} {letter} {energy:6} | "
              + " | ".join(f"{lab}: {v['lufs']} LUFS PLR {v['plr']}" for lab, v in st.items()), flush=True)
    json.dump(out, open(a.out, "w"), ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
