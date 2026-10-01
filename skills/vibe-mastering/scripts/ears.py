#!/usr/bin/env python3
"""The skill's ears: listen before touching anything, and listen again after rendering.
  ears.py listen  SONG [--json out.json]                                  first listen: measurements + findings
  ears.py compare SOURCE "label=version.wav" ... [--json out.json]        last listen: every version vs the source
A mastering engineer listens first and reaches for a tool only when the song needs it. These are the measurements
that stand in for that listening. Each finding names the evidence, how serious it is (fix / watch / protect / info)
and which tool, if any, addresses it; plan.py turns the findings into a chain. Everything is compared at equal
loudness, because a louder version always sounds "better" (the reason loudness-matched A/B exists at all).

Provenance of the thresholds (details and sources in references/chain.md section 8):
- DR (TT Dynamic Range, the Pleasurize Music Foundation meter): Ian Shepherd - DR12+ very dynamic, DR8 or lower risks
  sounding squashed, DR6 or less "loudness war". PSR (peak to short-term loudness, AES e-Brief by Shepherd et al.):
  under 8 suggests heavy limiting. PLR/limiting verdicts: calibrated on this skill's own sources and masters.
- Sharpness: DIN 45692 via MoSQITo (Apache-2.0), heard at -18 LUFS with 0 dBFS = 100 dB SPL. The +/-0.05 and 0.1 acum
  steps used here are this skill's judgement, not a published just-noticeable difference.
- Everything else (bumps, low end, stereo) uses the evidence rules in references/eq.md and chain.md section 7."""
import sys, os, json, argparse, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mslib as L, forensics
from scipy.signal import butter, sosfilt, welch, resample_poly

LISTEN_LUFS, FS_SPL = -18.0, 100.0          # sharpness is heard at this level: every file loudness-matched first
THIRDS = [1000*2**(k/3) for k in range(3, 13)]   # 2 - 16 kHz, where harshness lives
OCTAVES = [31.5, 63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]

def dr_tt(x, sr):
    """TT Dynamic Range: per channel, 3 s blocks; RMS (x sqrt 2) of the loudest 20% of blocks vs the 2nd-highest block
    peak; the channels are averaged. Same algorithm as the Pleasurize Music Foundation meter (open implementation:
    github.com/simon-r/dr14_t.meter), written independently here."""
    blk = 3*sr; n = len(x)//blk
    if n < 2: return None
    b = x[:n*blk].reshape(n, blk, x.shape[1])
    rms = np.sqrt(2*np.mean(b**2, axis=1)); pk = np.max(np.abs(b), axis=1)
    rms.sort(0); pk.sort(0); top = max(1, int(n*0.2))
    ch = 20*np.log10(pk[-2]/np.sqrt(np.mean(rms[-top:]**2, 0) + 1e-20))
    return round(float(np.mean(ch)), 1)

def psr(x, sr, I):
    """Peak to short-term loudness ratio over 3 s windows (1 s hop), true peak by 4x oversampling per window.
    Returned as the median over the louder half of the song, where limiting shows."""
    st = L.kweighted_blocks(x, sr, 3.0, 1.0); w = 3*sr; out = []
    for i, s in enumerate(st):
        seg = x[i*sr:i*sr + w]
        if len(seg) < w: break
        tp = 20*np.log10(np.abs(resample_poly(seg, 4, 1, axis=0)).max() + 1e-12); out.append((s, tp - s))
    if not out: return None
    a = np.array(out); loud = a[:, 0] >= np.median(a[:, 0])
    return round(float(np.median(a[loud, 1])), 1)

def sharpness(x, sr):
    """DIN 45692 sharpness (acum) of the whole song, loudness-matched; None when MoSQITo is not installed."""
    try: from mosqito.sq_metrics import sharpness_din_st
    except ImportError: return None
    p = (x*10**((LISTEN_LUFS - L.lufs(x, sr))/20)).mean(1)*(2e-5*10**(FS_SPL/20))
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore"); return round(float(np.squeeze(sharpness_din_st(p, sr))), 3)

def bump_time(mid, sr, centers):
    """Per 100 ms: each third-octave band minus the mean of its two neighbours - does a bump come and go, or stay?"""
    blk = int(0.1*sr); n = len(mid)//blk; w = np.hanning(blk); fr = np.fft.rfftfreq(blk, 1/sr)
    bands = sorted({round(c*2**(k/3), 1) for c in centers for k in (-1, 0, 1)})
    lv = {b: np.zeros(n) for b in bands}; tot = np.zeros(n)
    for i in range(n):
        s = np.abs(np.fft.rfft(mid[i*blk:(i+1)*blk]*w))**2; tot[i] = s.sum()
        for b in bands: lv[b][i] = 10*np.log10(s[(fr >= b/2**(1/6)) & (fr < b*2**(1/6))].sum() + 1e-20)
    keep = tot > np.percentile(tot, 20)
    out = {}
    for c in centers:
        lo, mi, hi = (lv[round(c*2**(k/3), 1)][keep] for k in (-1, 0, 1)); d = mi - 0.5*(lo + hi)
        out[f"{c:.0f}"] = dict(median=round(float(np.median(d)), 1), p10=round(float(np.percentile(d, 10)), 1),
                               p90=round(float(np.percentile(d, 90)), 1), over2_pct=round(float(100*(d > 2).mean())))
    return out

def clicks(x, sr, ratio=12.0, win_ms=10, floor_db=-60, top=12):
    """Possible clicks: a jump in the waveform's curvature (second difference) that stands 12x above its own 10 ms
    neighbourhood - a pure one-sample click scores about 22 there, a drum hit spreads its energy over milliseconds and
    stays near 5-8. A warning to check by ear, never a verdict (on a pop test song: 4 candidates, one of them also
    flagged by another tool; none confirmed by ear)."""
    from scipy.ndimage import uniform_filter1d, maximum_filter1d
    hits = []
    for c in range(x.shape[1]):
        s = x[:, c]; d2 = np.zeros_like(s); d2[1:-1] = s[2:] - 2*s[1:-1] + s[:-2]
        r = np.abs(d2)/np.sqrt(uniform_filter1d(d2**2, int(win_ms*1e-3*sr)) + 1e-18)
        lvl = maximum_filter1d(np.abs(s), int(0.005*sr))
        for i in np.flatnonzero((r > ratio) & (lvl > 10**(floor_db/20)) & (np.abs(d2) > 1e-3)):
            hits.append((int(i), float(r[i]), float(20*np.log10(lvl[i] + 1e-12))))
    hits.sort(); merged = []
    for h in hits:                                                  # one event per 20 ms, the strongest
        if merged and h[0] - merged[-1][0] < 0.02*sr:
            if h[1] > merged[-1][1]: merged[-1] = h
        else: merged.append(h)
    best = sorted(merged, key=lambda h: -h[1])[:top]
    return [dict(t=round(i/sr, 3), ratio=round(r, 1), level_db=round(db, 1)) for i, r, db in sorted(best)]

def measure(path):
    """Everything the first listen needs, on the file as delivered."""
    x, sr = L.read_stereo(path); I = L.lufs(x, sr); tp = L.true_peak_db(x, sr); n = len(x)
    fo = forensics.dynamics_history(x, sr); hf = forensics.hf_ceiling(x, sr)
    mid, side = x.mean(1), (x[:, 0] - x[:, 1])/2
    f, Pm = welch(mid, sr, nperseg=16384); _, Ps = welch(side, sr, nperseg=16384); tot = Pm.sum() + Ps.sum()
    band = lambda P, lo, hi: P[(f >= lo) & (f < hi)].sum()
    db = lambda v: round(float(10*np.log10(v + 1e-20)), 1)
    m = dict(file=os.path.basename(path), sr=sr, seconds=round(n/sr, 1), lufs=round(I, 2), true_peak_dbtp=round(tp, 2),
             plr_db=round(tp - I, 1), psr_db=psr(x, sr, I), dr=dr_tt(x, sr), lra_lu=round(L.lra(x, sr), 1),
             prior_limiting=fo["verdict"], hf_cutoff_khz=hf.get("cutoff_khz"), sharpness_acum=sharpness(x, sr),
             clipped_samples=int((np.abs(x) >= 0.9999).sum()), dc=round(float(np.abs(x.mean(0)).max()), 5),
             lr_correlation=round(float(np.corrcoef(x[:, 0], x[:, 1])[0, 1]), 3),
             tail_peak_db=round(float(20*np.log10(np.abs(x[-int(0.05*sr):]).max() + 1e-12)), 1))
    m["octaves"] = {f"{c:g}": dict(mid_re_total_db=db(band(Pm, c/2**0.5, c*2**0.5)/tot),
                                   side_minus_mid_db=db(band(Ps, c/2**0.5, c*2**0.5)/(band(Pm, c/2**0.5, c*2**0.5) + 1e-20)))
                    for c in OCTAVES if c*2**0.5 <= sr/2}
    th = {c: 10*np.log10(band(Pm, c/2**(1/6), c*2**(1/6)) + 1e-20) for c in [THIRDS[0]/2**(1/3)] + THIRDS + [THIRDS[-1]*2**(1/3)]}
    cs = sorted(th); cut = (m["hf_cutoff_khz"] or sr/2000)*1000
    m["hf_bumps_db"] = {f"{c:.0f}": round(float(th[c] - (th[cs[i]] + th[cs[i+2]])/2), 1)
                        for i, c in enumerate(cs[1:-1]) if c*2**0.5 < cut}   # a band touching the cut-off is an edge, not a bump
    cand = [c for c in THIRDS if m["hf_bumps_db"].get(f"{c:.0f}", 0) >= 1.5]
    m["hf_bump_time"] = bump_time(mid, sr, cand) if cand else {}
    # low end: how much there is below 25 Hz, how much bass sits in the sides, and whether the bass drives the peaks
    m["sub25_db"] = db((band(Pm, 0, 25) + band(Ps, 0, 25))/tot)
    m["sub25_re_bass_db"] = db((band(Pm, 0, 25) + band(Ps, 0, 25))/(band(Pm, 25, 120) + band(Ps, 25, 120) + 1e-20))
    m["low_share_db"] = db((band(Pm, 20, 120) + band(Ps, 20, 120))/tot)
    m["side_minus_mid_below80_db"] = db(band(Ps, 20, 80)/(band(Pm, 20, 80) + 1e-20))
    lp = butter(2, 120, "lp", fs=sr, output="sos"); hp = butter(2, 120, "hp", fs=sr, output="sos")
    lo = sosfilt(lp, sosfilt(lp, x, axis=0), axis=0); hi = sosfilt(hp, sosfilt(hp, x, axis=0), axis=0); full = lo + hi
    a = np.abs(full).max(1); idx = np.flatnonzero(a >= np.percentile(a, 99.9)); chn = np.abs(full[idx]).argmax(1)
    sgn = np.sign(full[idx, chn])
    m["bass_share_of_peaks_pct"] = round(float(100*np.mean(lo[idx, chn]*sgn/np.abs(full[idx, chn]))))
    mono = mid[:, None].repeat(2, 1); m["mono_fold_change_db"] = round(L.lufs(mono, sr) - I, 2)
    m["clicks"] = clicks(x, sr)
    return m

def findings(m):
    """Turn the measurements into what an engineer would note on a first listen."""
    F = []
    add = lambda id_, area, sev, ev, tool=None: F.append(dict(id=id_, area=area, severity=sev, evidence=ev, tool=tool))
    limited = m["prior_limiting"].startswith(("limited", "hard-clipped"))
    # DR thresholds judge a finished master; on a source, earlier limiting shows in the peaks (forensics) and in PSR/PLR
    if limited or (m["psr_db"] is not None and m["psr_db"] < 8) or m["plr_db"] < 9:
        add("already_dense", "dynamics", "protect",
            f"DR {m['dr']}, PLR {m['plr_db']} dB, PSR {m['psr_db']} dB, source check: {m['prior_limiting']}", None)
    elif m["dr"] is not None and m["dr"] >= 12:
        add("very_dynamic", "dynamics", "info", f"DR {m['dr']}, PLR {m['plr_db']} dB: plenty of punch to protect", None)
    if (m["low_share_db"] > -30 and m["sub25_re_bass_db"] > -20) or m["dc"] > 1e-3:
        add("subsonic", "low end", "fix", f"energy below 25 Hz {m['sub25_re_bass_db']} dB re the 25-120 Hz band, DC {m['dc']}", "hpf")
    if m["low_share_db"] > -20 and m["side_minus_mid_below80_db"] > -20:
        add("stereo_bass", "low end", "fix", f"side vs mid below 80 Hz {m['side_minus_mid_below80_db']} dB", "side_hp")
    if m["low_share_db"] > -20 and m["bass_share_of_peaks_pct"] >= 50:
        add("bass_drives_peaks", "low end", "watch", f"{m['bass_share_of_peaks_pct']}% of the loudest peaks come from below 120 Hz", "lowcomp")
    for c, s in m["hf_bump_time"].items():
        if m["hf_bumps_db"].get(c, 0) < 2: continue
        steady = s["p10"] >= 1.0; comes_goes = s["p10"] < 1.0 and s["p90"] >= 4.0
        if steady: add(f"bump_{c}", "tone", "fix", f"{c} Hz stands {m['hf_bumps_db'][c]} dB above its neighbours almost all the time (p10 {s['p10']})", "static_eq")
        elif comes_goes: add(f"bump_{c}", "tone", "fix", f"{c} Hz bump comes and goes: median {s['median']}, p90 {s['p90']} dB, over 2 dB {s['over2_pct']}% of the time", "dyneq")
    o = m["octaves"]
    if "1000" in o and "2000" in o and o["2000"]["mid_re_total_db"] - o["1000"]["mid_re_total_db"] <= -3:
        add("presence_dip", "tone", "watch", f"2 kHz octave {o['2000']['mid_re_total_db'] - o['1000']['mid_re_total_db']:+.1f} dB vs 1 kHz", "eq")
    if m["tail_peak_db"] > -50: add("abrupt_end", "edges", "fix", f"last 50 ms peak {m['tail_peak_db']} dBFS", "fade")
    if m["clipped_samples"] > 0: add("clipped_source", "edges", "watch", f"{m['clipped_samples']} samples at full scale", None)
    if m["mono_fold_change_db"] < -3: add("mono_loss", "stereo", "watch", f"folding to mono loses {m['mono_fold_change_db']} dB", None)
    if m["hf_cutoff_khz"] and m["hf_cutoff_khz"] < 19: add("hf_wall", "tone", "info", f"nothing above {m['hf_cutoff_khz']} kHz: an air boost would only lift noise", None)
    if m.get("clicks"):
        at = ", ".join(f"{int(c['t'])//60}:{c['t'] % 60:04.1f}" for c in m["clicks"][:6])
        add("possible_clicks", "edges", "watch", f"{len(m['clicks'])} possible click(s) at {at}" + (" ..." if len(m["clicks"]) > 6 else "") + " - check by ear", None)
    return F

def compare(src, versions):
    """Last listen: each version against the source, loudness-matched where it matters."""
    ms = measure(src); rows = {}
    for lab, p in versions:
        mv = measure(p); o, os_ = mv["octaves"], ms["octaves"]
        tilt = {k: round((o[k]["mid_re_total_db"] - os_[k]["mid_re_total_db"]), 1) for k in o if k in os_}
        flags = []
        if ms["sharpness_acum"] is not None and mv["sharpness_acum"] is not None and mv["sharpness_acum"] - ms["sharpness_acum"] >= 0.1:
            flags.append(f"harsher: sharpness {ms['sharpness_acum']} -> {mv['sharpness_acum']} acum at equal loudness")
        if mv["dr"] is not None and ms["dr"] is not None and ms["dr"] - mv["dr"] >= 4:
            flags.append(f"squashed: DR {ms['dr']} -> {mv['dr']} (a drop of 4 or more)")
        if mv["mono_fold_change_db"] < ms["mono_fold_change_db"] - 1:
            flags.append(f"less mono-safe: fold-down {ms['mono_fold_change_db']} -> {mv['mono_fold_change_db']} dB")
        new_bumps = [c for c, v in mv["hf_bumps_db"].items() if v >= 2 and ms["hf_bumps_db"].get(c, 0) < 1.5]
        if new_bumps: flags.append("new harsh bump(s) at " + ", ".join(f"{c} Hz" for c in new_bumps))
        band_ = "very dynamic" if (mv["dr"] or 0) >= 12 else "moderate" if (mv["dr"] or 0) > 8 else "dense (squashed risk)" if (mv["dr"] or 0) > 6 else "loudness-war territory"
        notes = [f"DR {mv['dr']}: {band_} on Ian Shepherd's scale", f"PSR {mv['psr_db']} dB" + (" - under 8, the level that suggests heavy limiting" if (mv["psr_db"] or 99) < 8 else "")]
        rows[lab] = dict(dr=mv["dr"], psr_db=mv["psr_db"], plr_db=mv["plr_db"], sharpness_acum=mv["sharpness_acum"], notes=notes,
                         sharpness_change=None if None in (mv["sharpness_acum"], ms["sharpness_acum"]) else round(mv["sharpness_acum"] - ms["sharpness_acum"], 3),
                         octave_change_db=tilt, mono_fold_change_db=mv["mono_fold_change_db"], flags=flags, clicks=mv["clicks"])
    return dict(source=dict(dr=ms["dr"], psr_db=ms["psr_db"], plr_db=ms["plr_db"], sharpness_acum=ms["sharpness_acum"],
                            mono_fold_change_db=ms["mono_fold_change_db"], clicks=ms["clicks"]), versions=rows)

def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    a1 = sub.add_parser("listen"); a1.add_argument("song"); a1.add_argument("--json")
    a2 = sub.add_parser("compare"); a2.add_argument("source"); a2.add_argument("versions", nargs="+"); a2.add_argument("--json")
    a = ap.parse_args()
    if a.cmd == "listen":
        m = measure(a.song); out = dict(measurements=m, findings=findings(m))
        print(f"{m['file']}: {m['lufs']} LUFS, TP {m['true_peak_dbtp']} dBTP, PLR {m['plr_db']}, PSR {m['psr_db']}, DR {m['dr']}, "
              f"LRA {m['lra_lu']}, sharpness {m['sharpness_acum']} acum")
        for x in out["findings"]: print(f"  [{x['severity']:7s}] {x['area']:9s} {x['id']:18s} {x['evidence']}" + (f"  -> {x['tool']}" if x["tool"] else ""))
    else:
        out = compare(a.source, [v.split("=", 1) for v in a.versions]); s = out["source"]
        print(f"source: DR {s['dr']}, PSR {s['psr_db']}, PLR {s['plr_db']}, sharpness {s['sharpness_acum']}")
        for lab, r in out["versions"].items():
            print(f"  {lab}: DR {r['dr']}, PSR {r['psr_db']}, PLR {r['plr_db']}, sharpness {r['sharpness_acum']} ({'n/a' if r['sharpness_change'] is None else '%+.3f' % r['sharpness_change']}) "
                  + ("| " + "; ".join(r["flags"]) if r["flags"] else "| no flags"))
    if a.json: json.dump(out, open(a.json, "w"), ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
