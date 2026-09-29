"""Source forensics: signs of earlier limiting/clipping, the high-frequency ceiling, and what metadata the file carries.
Used by analyze.py. Facts only; the file cannot prove that no compression or EQ was ever applied."""
import os, json, struct, subprocess, numpy as np
from scipy.signal import welch
import mslib as L
from ffbin import FFMPEG

def dynamics_history(x, sr):
    a = np.abs(x); pk = float(a.max())
    near = {f"{d} dB": int((a >= pk*10**(-d/20)).sum()) for d in (0.1, 0.5, 1.0)}
    # flat tops: runs of >=3 identical samples at the channel's absolute maximum = hard clipping
    flat = 0
    for ch in range(x.shape[1]):
        m = np.abs(x[:, ch]) >= a[:, ch].max() - 1e-9
        if m.any():
            d = np.diff(np.concatenate([[0], m.astype(np.int8), [0]])); runs = np.flatnonzero(d == -1) - np.flatnonzero(d == 1)
            flat += int((runs >= 3).sum())
    w = int(0.1*sr); k = len(x)//w; bp = 20*np.log10(a[:k*w].reshape(k, -1).max(1) + 1e-12); loud = bp > 20*np.log10(pk) - 20
    spread = float(bp[loud].max() - np.percentile(bp[loud], 99)) if loud.sum() > 100 else None
    st = L.kweighted_blocks(x, sr, 3.0, 3.0); n = int(3*sr)
    plr = [20*np.log10(a[i*n:(i+1)*n].max() + 1e-12) - st[i] for i in range(len(st)) if st[i] > st.max() - 10]
    # thresholds calibrated on four files: an unlimited source (spread 1.24 dB, 11 samples within 0.5 dB) = none;
    # a lightly peak-controlled source (0.30 dB, 275) = light; two masters at -10 and -8.9 LUFS (0.10 dB, 53k-102k) = limited
    n05 = near["0.5 dB"]
    if flat >= 10: verdict = "hard-clipped (flat tops at the maximum)"
    elif (spread is not None and spread < 0.2) or n05 >= 10000: verdict = "limited to a ceiling (peaks pile up at one level)"
    elif (spread is not None and spread < 0.5) or n05 >= 200: verdict = "light peak control likely (peaks cluster near the maximum)"
    else: verdict = "no sign of a final limiter or clipper"
    return dict(verdict=verdict, samples_near_peak=near, flat_top_runs=flat,
                top1pct_block_peak_spread_db=round(spread, 2) if spread is not None else None,
                short_term_plr_loud_median_db=round(float(np.median(plr)), 1) if plr else None)

def hf_ceiling(x, sr):
    """Frequency above which the spectrum falls >20 dB within 1 kHz and stays down (codec low-pass or generator band limit)."""
    f, P = welch(x.mean(1), sr, nperseg=32768); d = 10*np.log10(P + 1e-30); step = f[1]
    lvl = lambda lo, hi: float(np.mean(d[(f >= lo) & (f < hi)]))
    for fc in np.arange(10000, sr/2 - 1000, 250):
        below, above, rest = lvl(fc - 1000, fc), lvl(fc, fc + 1000), lvl(fc, sr/2)
        if below - above > 20 and below - rest > 20:
            return dict(cutoff_khz=round(float(fc)/1000, 2), drop_db=round(below - above, 1))
    return dict(cutoff_khz=None, note="no steep wall below Nyquist")

def input_tags(path):
    """The container's global tags exactly as ffprobe lists them (format_tags), read from `ffmpeg -i`, so no ffprobe is
    needed. Values that span lines come back joined with newlines."""
    err = subprocess.run([FFMPEG, "-hide_banner", "-i", path], capture_output=True, text=True, errors="replace").stderr
    tags, key, state = {}, None, None
    for line in err.splitlines():
        if state is None and line.startswith("Input #0"): state = "input"
        elif state == "input" and line.startswith("  Metadata:"): state = "tags"
        elif state == "tags":
            if not line.startswith("    "): break                # "  Duration: ..." ends the container's block
            k, _, v = line[4:].partition(": ")
            if k.strip(): key = k.strip(); tags[key] = v
            elif key: tags[key] += "\n" + v                     # a continuation line has an empty key
    return tags

def metadata(path):
    out = {}
    try:
        tags = input_tags(path)
        out["tags"] = {k: (v if len(v) < 160 else v[:160] + "...") for k, v in tags.items()}
    except Exception as e: out["tags_error"] = str(e)
    if path.lower().endswith(".wav"):
        chunks, c2pa = [], None
        with open(path, "rb") as fh:
            fh.read(12)
            while True:
                h = fh.read(8)
                if len(h) < 8: break
                cid, size = h[:4].decode("latin1"), struct.unpack("<I", h[4:])[0]; chunks.append(cid)
                if cid.upper() == "C2PA" or cid == "jumb":
                    body = fh.read(size); c2pa = dict(bytes=size)
                    i = body.find(b"digitalsourcetype/")
                    if i >= 0: c2pa["digitalSourceType"] = body[i+18:i+60].split(b"\x00")[0].decode("latin1", "ignore").strip()
                    fh.seek(size & 1, 1)
                else: fh.seek(size + (size & 1), 1)
        out["riff_chunks"] = chunks
        if c2pa: out["c2pa_content_credentials"] = c2pa
    return out

def run(path, x, sr):
    return dict(dynamics_history=dynamics_history(x, sr), hf_ceiling=hf_ceiling(x, sr), metadata=metadata(path))
