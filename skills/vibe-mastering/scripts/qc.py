#!/usr/bin/env python3
"""Delivery QC.   qc.py "label=path" ["label=path" ...] [--source label] [--reference ref.wav] [--ceiling -2] --out qc.json
Per file: EBU R128 (I, LRA, max M/S), true peak, PLR, mono fold-down, L/R correlation, per-platform playback gain,
decoded true peak after AAC(Apple)/Ogg(Spotify)/Opus(YouTube)/MP3 encoding, and spectral balance.
The file tagged with --source skips the codec test (it is the unmastered input)."""
import sys, os, json, argparse, subprocess, tempfile, numpy as np, soundfile as sf
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mslib as L
from ffbin import FFMPEG
from scipy.signal import welch

CODECS = [("AAC 256 (Apple)", ["-c:a", "aac_at", "-b:a", "256k"], "m4a"),
          ("Ogg 160 (Spotify)", ["-c:a", "libvorbis", "-b:a", "160k"], "ogg"),
          ("Ogg 320 (Spotify)", ["-c:a", "libvorbis", "-q:a", "9"], "ogg"),
          ("Opus 128 (YouTube)", ["-c:a", "libopus", "-b:a", "128k"], "opus"),
          ("MP3 320", ["-c:a", "libmp3lame", "-b:a", "320k"], "mp3")]
BANDS = [(20,60),(60,120),(120,300),(300,800),(800,2500),(2500,5000),(5000,10000),(10000,16000)]

def codec_peaks(path, sr):
    out = {}
    with tempfile.TemporaryDirectory() as d:
        for name, args, ext in CODECS:
            e, w = f"{d}/e.{ext}", f"{d}/d.wav"
            enc = subprocess.run([FFMPEG, "-v", "error", "-y", "-i", path, *args, e], capture_output=True)
            if enc.returncode:  # e.g. aac_at missing on non-mac ffmpeg builds
                out[name] = None; continue
            subprocess.run([FFMPEG, "-v", "error", "-y", "-i", e, "-c:a", "pcm_f32le", "-ar", str(sr), w], check=True)
            y, _ = sf.read(w, always_2d=True); out[name] = round(float(L.true_peak_db(y, sr)), 2)
    return out

def side_vs_mid(x, sr):
    """Stereo width per region (dB, side energy re mid): below 60 Hz should be far down (mono bass)."""
    f, Pm = welch((x[:,0]+x[:,1])/2, sr, nperseg=16384); _, Ps = welch((x[:,0]-x[:,1])/2, sr, nperseg=16384)
    return {k: round(float(10*np.log10(Ps[(f>=lo)&(f<hi)].sum()/(Pm[(f>=lo)&(f<hi)].sum()+1e-20)+1e-20)), 1)
            for k, (lo, hi) in {"<60": (20, 60), "60-120": (60, 120), "120-500": (120, 500), "500-5k": (500, 5000), "5k-16k": (5000, 16000)}.items()}

def spectrum(x, sr):
    f, P = welch(x.mean(1), sr, nperseg=8192); tot = P.sum()
    return {f"{lo}-{hi}": round(float(10*np.log10(P[(f>=lo)&(f<hi)].sum()/tot)), 1) for lo, hi in BANDS}

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("files", nargs="+"); ap.add_argument("--source")
    ap.add_argument("--reference"); ap.add_argument("--ceiling", type=float, default=-2.0); ap.add_argument("--out", default="qc.json")
    a = ap.parse_args(); res = {}
    if a.reference:
        rx, rsr = L.read_stereo(a.reference)
        res["_reference"] = dict(file=os.path.basename(a.reference), lufs_i=round(L.lufs(rx, rsr), 2),
                                 true_peak_dbtp=round(L.true_peak_db(rx, rsr), 2), lra_lu=round(L.lra(rx, rsr), 1), spectrum=spectrum(rx, rsr))
    for item in a.files:
        label, path = item.split("=", 1); x, sr = L.read_stereo(path)
        I = L.lufs(x, sr); tp = L.true_peak_db(x, sr); mono = (x[:,0]+x[:,1])/2
        r = dict(file=os.path.basename(path), lufs_i=round(I, 2), true_peak_dbtp=round(tp, 2), plr_db=round(tp-I, 1),
                 lra_lu=round(L.lra(x, sr), 1), max_short_term=round(float(L.kweighted_blocks(x, sr, 3, 0.1).max()), 1),
                 max_momentary=round(float(L.kweighted_blocks(x, sr, 0.4, 0.1).max()), 1),
                 lr_correlation=round(float(np.corrcoef(x[:,0], x[:,1])[0,1]), 3),
                 mono_fold_change_db=round(L.lufs(np.stack([mono, mono], 1), sr) - I, 2),
                 side_minus_mid_db=side_vs_mid(x, sr),
                 playback_gain_db={"Spotify (-14)": round(-14-I, 1), "YouTube (-14, down only)": round(min(0, -14-I), 1),
                                   "Apple Music (-16, down only)": round(min(0, -16-I), 1)},
                 spectrum=spectrum(x, sr))
        if label != a.source:
            r["codec_decoded_true_peak"] = codec_peaks(path, sr)
            worst = max(v for v in r["codec_decoded_true_peak"].values() if v is not None)
            r["checks"] = {"true_peak_within_ceiling": tp <= a.ceiling + 0.05, "no_overs_after_encoding": worst < 0.0,
                           "mono_safe(>-3 dB)": r["mono_fold_change_db"] > -3.0}
            if -0.3 < worst < 0.0: r["warning"] = f"codec margin thin: worst decoded peak {worst} dBTP (under 0.3 dB to clipping)"
        if a.reference:
            r["spectrum_minus_reference_db"] = {k: round(v - res["_reference"]["spectrum"][k], 1) for k, v in r["spectrum"].items()}
        res[label] = r
        cp = r.get("codec_decoded_true_peak") or {}
        worst = max((v for v in cp.values() if v is not None), default=None)
        fails = [k for k, ok in r.get("checks", {}).items() if not ok]
        print(f"{label}: {r['lufs_i']} LUFS | TP {r['true_peak_dbtp']} dBTP | PLR {r['plr_db']} | LRA {r['lra_lu']} | "
              f"mono {r['mono_fold_change_db']:+} dB | worst decoded codec peak {worst} | "
              + ("" if "checks" not in r else ("checks OK" if not fails else f"FAILED: {', '.join(fails)}"))
              + (f" | WARNING {r['warning']}" if r.get("warning") else "") + f"\n    side minus mid: {r['side_minus_mid_db']}"
              + (f"\n    spectrum minus reference: {r['spectrum_minus_reference_db']}" if a.reference else ""), flush=True)
    json.dump(res, open(a.out, "w"), ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))

if __name__ == "__main__":
    main()
