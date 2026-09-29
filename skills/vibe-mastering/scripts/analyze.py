#!/usr/bin/env python3
"""Source analysis before mastering.   analyze.py IN.wav [--json out.json]
Prints loudness/peaks/dynamics, a loudness timeline, spectral balance (mid, and side relative to mid),
low-frequency peaks, stereo/mono facts and head/tail click risk. Numbers only - interpretation is in
references/chain.md."""
import sys, os, json, argparse, numpy as np, soundfile as sf
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mslib as L, forensics, musical
from scipy.signal import welch

OCTAVES = [31.5, 63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]      # equal-width (1 octave) so neighbours compare
THIRDS = [1000*2**(k/3) for k in range(-3, 13)]                          # 500 Hz .. 16 kHz, for bump detection
HARSH_BANDS = [(2000, 3500), (3500, 6000), (6000, 9000), (9000, 14000)]

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("src"); ap.add_argument("--json"); a = ap.parse_args()
    info = sf.info(a.src); x, sr = L.read_stereo(a.src)
    I = L.lufs(x, sr); tp = L.true_peak_db(x, sr); sp = 20*np.log10(np.abs(x).max()+1e-12)
    r = dict(file=os.path.basename(a.src), format=f"{info.subtype} {sr} Hz {info.channels} ch", seconds=round(len(x)/sr, 2),
             lufs_i=round(I, 2), true_peak_dbtp=round(tp, 2), sample_peak_db=round(sp, 2), plr_db=round(tp-I, 1),
             lra_lu=round(L.lra(x, sr), 1), max_short_term=round(float(L.kweighted_blocks(x, sr, 3, 0.1).max()), 1),
             clipped_samples=int((np.abs(x) >= 0.9999).sum()), dc=[round(float(x[:,0].mean()), 5), round(float(x[:,1].mean()), 5)],
             lr_correlation=round(float(np.corrcoef(x[:,0], x[:,1])[0,1]), 3))
    mono = (x[:,0]+x[:,1])/2; r["mono_fold_change_db"] = round(L.lufs(np.stack([mono, mono], 1), sr) - I, 2)
    st = L.kweighted_blocks(x, sr, 3.0, 6.0)
    r["timeline_st_lufs"] = {f"{int(i*6)//60}:{int(i*6)%60:02d}": round(float(v), 1) for i, v in enumerate(st)}
    M, S = mono, (x[:,0]-x[:,1])/2
    f, Pm = welch(M, sr, nperseg=16384); _, Ps = welch(S, sr, nperseg=16384); tot = Pm.sum()
    band = lambda P, lo, hi: P[(f >= lo) & (f < hi)].sum()
    r["spectrum_octaves"] = {f"{c:g}": dict(mid_rel_total_db=round(float(10*np.log10(band(Pm, c/2**0.5, c*2**0.5)/tot + 1e-20)), 1),
                                            side_minus_mid_db=round(float(10*np.log10(band(Ps, c/2**0.5, c*2**0.5)/(band(Pm, c/2**0.5, c*2**0.5)+1e-20) + 1e-20)), 1))
                             for c in OCTAVES if c*2**0.5 <= sr/2}
    # harshness evidence: 1/3-octave bumps vs neighbours, and how much each upper band swings over time
    th = np.array([10*np.log10(band(Pm, c/2**(1/6), c*2**(1/6)) + 1e-20) for c in THIRDS if c*2**(1/6) < sr/2])
    r["third_octave_bumps_db"] = {f"{THIRDS[i]:.0f}": round(float(th[i] - (th[i-1]+th[i+1])/2), 1)
                                  for i in range(1, len(th)-1) if th[i] - (th[i-1]+th[i+1])/2 >= 1.5}
    from scipy.signal import butter, sosfilt
    from scipy.ndimage import uniform_filter1d
    sw = {}
    for lo, hi in HARSH_BANDS:
        if hi >= sr/2: continue
        b = sosfilt(butter(2, [lo, hi], "bandpass", fs=sr, output="sos"), M)
        lv = 10*np.log10(uniform_filter1d(b**2, int(0.05*sr)) + 1e-12)[::int(0.01*sr)]
        sw[f"{lo}-{hi}"] = round(float(np.percentile(lv, 95) - np.percentile(lv, 50)), 1)
    r["band_swing_p95_minus_p50_db"] = sw
    f2, P2 = welch(M, sr, nperseg=65536); idx = (f2 > 20) & (f2 < 200); top = np.argsort(P2[idx])[::-1][:8]
    r["low_peaks_hz"] = sorted(round(float(f2[idx][i]), 1) for i in top)
    ms10 = int(0.01*sr)
    r["head_peak_10ms_db"] = round(float(20*np.log10(np.abs(x[:ms10]).max()+1e-12)), 1)
    r["tail_peak_50ms_db"] = round(float(20*np.log10(np.abs(x[-5*ms10:]).max()+1e-12)), 1)
    r["abrupt_end"] = r["tail_peak_50ms_db"] > -50
    r["forensics"] = forensics.run(a.src, x, sr)
    k, t = musical.key(x, sr), musical.tempo(x, sr)             # estimates for the pages, never used by the chain
    r["key"] = k["name"] if k else None; r["key_detail"] = k; r["tempo_bpm"] = t["bpm"] if t else None; r["tempo_detail"] = t
    if a.json: json.dump(r, open(a.json, "w"), ensure_ascii=False, indent=1)
    tl = r.pop("timeline_st_lufs"); sp_ = r.pop("spectrum_octaves"); fo = r.pop("forensics"); r.pop("key_detail"); r.pop("tempo_detail")
    for k, v in r.items(): print(f"{k:28} {v}")
    print("\noctave (Hz)   mid dB re total   side minus mid dB")
    for k, v in sp_.items(): print(f"  {k:>8}       {v['mid_rel_total_db']:8.1f}          {v['side_minus_mid_db']:6.1f}")
    print("\nsource forensics:")
    for k, v in fo.items(): print(f"  {k:18} {json.dumps(v, ensure_ascii=False)}")
    print("\nshort-term loudness every 6 s:")
    print("  " + "  ".join(f"{k} {v}" for k, v in tl.items()))

if __name__ == "__main__":
    main()
