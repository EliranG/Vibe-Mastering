#!/usr/bin/env python3
"""One-page visual report (PNG) - readable on a phone, where the A/B page cannot run.
  report.py SOURCE.wav FINAL.wav --label "Master -10" --sections sections.json [--qc qc.json] --title "Song" --out report.png [--lang en|he]
Panels: short-term loudness over time with the section map, spectrogram of the final version, difference spectrogram
(final minus source at equal integrated loudness), octave balance, PLR per section, and the numbers per version."""
import sys, os, json, argparse, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mslib as L
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Rectangle
from scipy.signal import stft, welch

for fp in ("/System/Library/Fonts/Supplemental/Arial Unicode.ttf", "/Library/Fonts/Arial Unicode.ttf"):
    if os.path.exists(fp): font_manager.fontManager.addfont(fp); plt.rcParams["font.family"] = font_manager.FontProperties(fname=fp).get_name(); break
H = lambda s: s   # matplotlib >= 3.11 lays out Hebrew right-to-left itself; python-bidi on top reverses it (tested)
from report_html import cmaps
from compare_page import BRAND, TAG, CREDIT, REPO
BG, GLASS, INK, MUTED, LINE, SRC_C, FIN_C = "#0a0c10", "#0b0e12", "#e8edf3", "#8f9aa8", "#2b3139", "#9b8cff", "#3fd8ff"
plt.rcParams.update({"figure.facecolor": BG, "axes.facecolor": GLASS, "axes.edgecolor": LINE, "axes.labelcolor": MUTED, "text.color": INK,
                     "axes.titlecolor": INK, "xtick.color": "#7d8896", "ytick.color": "#7d8896", "legend.facecolor": "#14181d",
                     "legend.edgecolor": LINE, "legend.labelcolor": "#c9d3de"})   # the titanium look of the A/B app and the report
COLORS = ["#ff8a5c", "#5b9dff", "#5cf07a", "#b28cff", "#ffd84d", "#3fd8ff", "#ff6fb1", "#9bd65a", "#8f7dff", "#ff5a4d"]
col = lambda letter: COLORS[(ord(letter) - 65) % len(COLORS)]
T = {
 "en": dict(title="{title}: mastering report - {label} vs the source",
            loud="Loudness over the song (short-term) and the section map - same letter = repeated section",
            spec="Spectrogram - {label}", diff="Difference from the source at equal integrated loudness: orange = added, blue = reduced, dark = unchanged (±6 dB)",
            octave="Octave balance (equal loudness)", plr="PLR per section: peaks above loudness (drop = compression)",
            hdr=["Version", "LUFS", "True Peak", "PLR", "LRA", "Spotify dB", "Encoded peak", "Checks"],
            worst="Numbers for every version · most compressed section: #{i} ({letter}, {at}), PLR down {d:.1f} dB"),
 "he": dict(title="{title}: דוח מאסטרינג - {label} מול המקור",
            loud="עוצמה לאורך השיר (short-term) ומפת הקטעים - אות זהה = קטע חוזר",
            spec="ספקטרוגרמה - {label}", diff="הפרש מהמקור בעוצמה כוללת שווה: כתום = נוסף, כחול = הורד, כהה = ללא שינוי (±6 dB)",
            octave="איזון תדרים באוקטבות (עוצמה שווה)", plr="PLR לפי קטע: כמה השיאים מעל העוצמה (ירידה = דחיסה)",
            hdr=["גרסה", "LUFS", "True Peak", "PLR", "LRA", "Spotify dB", "שיא אחרי קידוד", "בדיקות"],
            worst="המספרים לכל הגרסאות · הקטע שנדחס הכי הרבה: #{i} ({letter}, {at}), PLR ירד ב-{d:.1f} dB")}

def logspec(x, sr, lufs_val, cols=1200, rows=160, fmin=40, fmax=20000):
    n = 4096; hop = max(1, (len(x) - n)//cols)
    f, t, Z = stft(x.mean(1), sr, nperseg=n, noverlap=n-hop, boundary=None, padded=False); P = np.abs(Z)**2
    edges = np.geomspace(fmin, min(fmax, sr/2), rows + 1); out = np.empty((rows, P.shape[1]))
    for r in range(rows):
        m = (f >= edges[r]) & (f < edges[r+1])
        out[r] = P[m].mean(0) if m.any() else P[np.argmin(np.abs(f - edges[r]))]
    return 10*np.log10(out + 1e-20) - lufs_val, t, edges

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("source"); ap.add_argument("final"); ap.add_argument("--label", required=True)
    ap.add_argument("--sections", required=True); ap.add_argument("--qc"); ap.add_argument("--title", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--lang", choices=sorted(T), default="en")
    a = ap.parse_args(); t_ = T[a.lang]
    x, sr = L.read_stereo(a.source); y, sry = L.read_stereo(a.final); Ix, Iy = L.lufs(x, sr), L.lufs(y, sry)
    S = json.load(open(a.sections)); sec = S["sections"]; src = S.get("source") or S["versions"][0]
    qc = json.load(open(a.qc)) if a.qc else {}
    dur = len(x)/sr
    fig = plt.figure(figsize=(12, 15.5), dpi=110); fig.patch.set_facecolor(BG)
    gs = fig.add_gridspec(5, 2, height_ratios=[1.1, 1.3, 1.3, 1.15, 0.95], hspace=0.5, wspace=0.25, top=0.95, bottom=0.03)
    fig.suptitle(H(t_["title"].format(title=a.title, label=a.label)), fontsize=18, y=0.985)

    # 1. loudness over time + section map
    ax = fig.add_subplot(gs[0, :])
    for s in sec:
        ax.add_patch(Rectangle((s["start"], -60), s["end"] - s["start"], 100, color=col(s["letter"]), alpha=0.13, lw=0))
        ax.text((s["start"] + s["end"])/2, -4.5, s["letter"], ha="center", va="center", fontsize=11, color=col(s["letter"]))
    for sig, rate, lab, c, ls in ((x, sr, src, SRC_C, "--"), (y, sry, a.label, FIN_C, "-")):
        st = L.kweighted_blocks(sig, rate, 3.0, 0.5); tt = np.arange(len(st))*0.5 + 1.5
        if c == FIN_C: ax.plot(tt, st, color=c, lw=5, alpha=0.18)                       # glow under the final version
        ax.plot(tt, st, color=c, lw=1.5, ls=ls, label=H(lab))
    ax.set_xlim(0, dur); ax.set_ylim(-40, -2); ax.set_ylabel("LUFS (3s)"); ax.legend(loc="lower right", fontsize=9)
    ax.set_title(H(t_["loud"]), fontsize=12)
    ax.set_xticks(np.arange(0, dur, 30)); ax.set_xticklabels([f"{int(t)//60}:{int(t)%60:02d}" for t in np.arange(0, dur, 30)])

    # 2-3. spectrogram and difference
    Sx, t, edges = logspec(x, sr, Ix); Sy, _, _ = logspec(y, sry, Iy); m = min(Sx.shape[1], Sy.shape[1]); Sx, Sy = Sx[:, :m], Sy[:, :m]
    ext = [0, dur, 0, len(edges) - 1]; yt = [np.searchsorted(edges, f) for f in (100, 1000, 10000)]
    cm_spec, cm_diff = cmaps()
    for row, data, cmap, vmin, vmax, ttl in ((1, Sy, cm_spec, np.percentile(Sy, 99.5) - 70, np.percentile(Sy, 99.5), t_["spec"].format(label=a.label)),
                                             (2, np.clip(Sy - Sx, -6, 6), cm_diff, -6, 6, t_["diff"])):
        ax = fig.add_subplot(gs[row, :]); im = ax.imshow(data, origin="lower", aspect="auto", extent=ext, cmap=cmap, vmin=vmin, vmax=vmax, interpolation="bilinear")
        for s in sec: ax.axvline(s["start"], color="white", lw=0.6, alpha=0.2)
        ax.set_yticks(yt); ax.set_yticklabels(["100", "1k", "10k"]); ax.set_ylabel("Hz"); ax.set_title(H(ttl), fontsize=12)
        ax.set_xticks(np.arange(0, dur, 30)); ax.set_xticklabels([f"{int(t)//60}:{int(t)%60:02d}" for t in np.arange(0, dur, 30)])
        fig.colorbar(im, ax=ax, pad=0.01, fraction=0.025).set_label("dB")

    # 4. octave balance (equal integrated loudness)
    ax = fig.add_subplot(gs[3, 0]); oct_c = [31.5, 63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]
    for sig, rate, I, lab, c, off in ((x, sr, Ix, src, "#5a4fb8", -0.2), (y, sry, Iy, a.label, FIN_C, 0.2)):
        f, P = welch(sig.mean(1)*10**((-14 - I)/20), rate, nperseg=16384)
        v = [10*np.log10(P[(f >= c/2**0.5) & (f < c*2**0.5)].sum() + 1e-20) for c in oct_c]
        ax.bar(np.arange(len(oct_c)) + off, np.array(v) - max(v) + 40, width=0.38, color=c, label=H(lab), bottom=0)
    ax.set_xticks(range(len(oct_c))); ax.set_xticklabels(["31", "63", "125", "250", "500", "1k", "2k", "4k", "8k", "16k"], fontsize=8)
    ax.set_title(H(t_["octave"]), fontsize=12); ax.set_ylabel("dB (rel.)"); ax.legend(fontsize=8)

    # 5. PLR per section
    ax = fig.add_subplot(gs[3, 1]); idx = np.arange(len(sec))
    px = [s["stats"][src]["plr"] for s in sec]; py = [s["stats"].get(a.label, {}).get("plr") for s in sec]
    ax.bar(idx - 0.2, px, 0.38, color="#5a4fb8", label=H(src)); ax.bar(idx + 0.2, [v or 0 for v in py], 0.38, color=FIN_C, label=H(a.label))
    ax.set_xticks(idx); ax.set_xticklabels([f"{s['index']}{s['letter']}" for s in sec], fontsize=8)
    ax.set_title(H(t_["plr"]), fontsize=12); ax.set_ylabel("dB"); ax.legend(fontsize=8)

    # 6. numbers table
    ax = fig.add_subplot(gs[4, :]); ax.axis("off")
    rows = []
    for lab, q in qc.items():
        if lab.startswith("_"): continue
        cp = q.get("codec_decoded_true_peak") or {}; worst = max((v for v in cp.values() if v is not None), default=None)
        rows.append([H(lab), f"{q['lufs_i']:.1f}", f"{q['true_peak_dbtp']:.2f}", f"{q['plr_db']:.1f}", f"{q['lra_lu']:.1f}",
                     f"{q['playback_gain_db']['Spotify (-14)']:+.1f}", "-" if worst is None else f"{worst:.2f}",
                     "-" if "checks" not in q else ("OK" if all(q["checks"].values()) else "FAIL")])
    if rows:
        hdr = [H(h) for h in t_["hdr"]]
        tb = ax.table(cellText=rows, colLabels=hdr, loc="upper center", cellLoc="center"); tb.auto_set_font_size(False); tb.set_fontsize(10); tb.scale(1, 1.6)
        for (r, c), cell in tb.get_celld().items():
            cell.set_edgecolor(LINE); cell.get_text().set_color(INK if r else MUTED)
            cell.set_facecolor("#1b2027" if r == 0 else ("#0f2a33" if rows[r-1][0] == H(a.label) else "#11151a"))
    worst_sec = min(sec, key=lambda s: (s["stats"].get(a.label, {}).get("plr") or 99) - (s["stats"][src]["plr"] or 0))
    d = worst_sec["stats"][a.label]["plr"] - worst_sec["stats"][src]["plr"]
    ax.set_title(H(t_["worst"].format(i=worst_sec["index"], letter=worst_sec["letter"], d=abs(d),
                                      at=f"{int(worst_sec['start'])//60}:{int(worst_sec['start'])%60:02d}")), fontsize=12, pad=4)
    fig.text(0.5, 0.004, f"{BRAND} · {TAG} · {CREDIT} · {REPO.split('//')[1]}", ha="center", va="bottom", color=MUTED, fontsize=9)
    fig.savefig(a.out, bbox_inches="tight", facecolor=BG); print(a.out)

if __name__ == "__main__":
    main()
