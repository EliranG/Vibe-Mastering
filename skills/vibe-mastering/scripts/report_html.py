#!/usr/bin/env python3
"""Detailed mastering report as one self-contained HTML page (English or Hebrew, light + dark), for an Artifact or a file.
  report_html.py --source SRC.wav --final FINAL.wav --label "Master -10" --qc qc.json --sections sections.json
                 --analysis analysis.json [--predict predict.json] [--stats stats_final.json] --notes notes.json --out report.html
                 [--lang en|he]   (page language and direction; every fixed string lives in TXT below)
                 [--ab-url URL]   (the A/B page published from compare_page.py --web: a link under the bottom line,
                                   and on the files entry that names the A/B page, or any entry with its own "url")
Numbers, charts and the plain-language meaning of each measurement are generated here; the conclusions are written by the
agent per song in notes.json (see references/report.md for its fields and tone). Charts are inline SVG coloured by theme
tokens; spectrograms are embedded PNG pixels with the axes drawn in HTML."""
import sys, os, io, json, base64, argparse, html, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mslib as L, explain
from scipy.signal import stft, welch
from compare_page import BRAND, TAG, CREDIT, REPO
LOGO = ('<svg class="logo" viewBox="0 0 32 32" aria-hidden="true"><rect x="1" y="1" width="30" height="30" rx="8" fill="#10161d" stroke="#3fd8ff" stroke-opacity=".55"/>'
        '<rect x="7" y="14" width="3" height="10" rx="1.5" fill="#3fd8ff"/><rect x="12" y="8" width="3" height="16" rx="1.5" fill="#3fd8ff"/>'
        '<rect x="17" y="11" width="3" height="13" rx="1.5" fill="#3fd8ff"/><rect x="22" y="17" width="3" height="7" rx="1.5" fill="#9b8cff"/></svg>')

import re
_NUM = re.compile(r"(?<![A-Za-z0-9#])((?:[A-Za-z][\w'’]*\s){0,2}(?:[‎‏]?(?<![֐-׿])[-+−])?\d[\d.,:]*(?:[-–]\d[\d.,:]*)*(?:\s?(?:dBTP|dB|LUFS|LU|kHz|Hz|ms|%|bit))?(?:/\d[\d.,:]*(?:\s?(?:dBTP|dB|LUFS|LU|kHz|Hz|ms|%|bit))?)*)")  # one isolate for a number with its unit, a date (2026-09-29), and up to two English words before it ("Master -10"); "ב-20": hyphen after Hebrew = joiner
# the leading look-behind keeps digits inside Latin words ("MP3", "C2PA") and inside the escaped apostrophe "&#x27;" unwrapped
def E(s):
    """Escape, then isolate every number(+unit) so Hebrew bidi cannot flip "4.7 dB" into "dB 4.7"."""
    return _NUM.sub(lambda m: f'<bdi dir="ltr">{m.group(1)}</bdi>', html.escape(str(s)))
A = lambda s: html.escape(str(s))   # for attributes (no markup)
LETTER = ["#ff8a5c", "#5b9dff", "#5cf07a", "#b28cff", "#ffd84d", "#3fd8ff", "#ff6fb1", "#9bd65a", "#8f7dff", "#ff5a4d"]
col = lambda l: LETTER[(ord(l) - 65) % len(LETTER)]
mmss = lambda t: f"{int(t)//60}:{int(t)%60:02d}"

# ---------------- data ----------------
def logspec(x, sr, I, cols=1100, rows=150, fmin=40, fmax=20000):
    n = 4096; hop = max(1, (len(x) - n)//cols)
    f, _, Z = stft(x.mean(1), sr, nperseg=n, noverlap=n-hop, boundary=None, padded=False); P = np.abs(Z)**2
    edges = np.geomspace(fmin, min(fmax, sr/2), rows + 1); out = np.empty((rows, P.shape[1]))
    for r in range(rows):
        m = (f >= edges[r]) & (f < edges[r+1]); out[r] = P[m].mean(0) if m.any() else P[np.argmin(np.abs(f - edges[r]))]
    return 10*np.log10(out + 1e-20) - I

def cmaps():
    """The titanium look: a spectrogram from dark glass to cyan, and a difference map where dark means unchanged."""
    from matplotlib.colors import LinearSegmentedColormap as C
    spec = C.from_list("glass_cyan", [(0, "#05070b"), (0.35, "#0d1f4d"), (0.6, "#1a73bf"), (0.82, "#40d9ff"), (1, "#e6ffff")])
    diff = C.from_list("blue_dark_orange", [(0, "#5b9dff"), (0.5, "#0b0e12"), (1, "#ff9f5a")])
    return spec, diff

def png(arr, cmap, vmin, vmax):
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    buf = io.BytesIO(); plt.imsave(buf, np.clip(arr, vmin, vmax)[::-1], cmap=cmap, vmin=vmin, vmax=vmax, format="png")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

def octaves(x, sr, I):
    f, P = welch(x.mean(1)*10**((-14 - I)/20), sr, nperseg=16384)
    return [10*np.log10(P[(f >= c/2**0.5) & (f < c*2**0.5)].sum() + 1e-20) for c in OCT]
OCT = [31.5, 63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]
OCT_L = ["31", "63", "125", "250", "500", "1k", "2k", "4k", "8k", "16k"]

# ---------------- svg charts (colours from CSS tokens) ----------------
def svg_timeline(src_st, fin_st, hop, dur, sec, label, tx):
    W, H, l, r, t, b = 760, 250, 44, 12, 26, 30; pw, ph = W - l - r, H - t - b; lo, hi = -40, -4
    X = lambda s: l + s/dur*pw; Y = lambda v: t + (hi - max(lo, min(hi, v)))/(hi - lo)*ph
    o = [f'<svg viewBox="0 0 {W} {H}" class="chart" role="img" aria-label="{A(tx["aria_timeline"].format(label=label))}">']
    for s in sec:
        o.append(f'<rect x="{X(s["start"]):.1f}" y="{t}" width="{X(s["end"]) - X(s["start"]):.1f}" height="{ph}" fill="{col(s["letter"])}" fill-opacity=".11"/>')
        o.append(f'<text x="{(X(s["start"]) + X(s["end"]))/2:.1f}" y="{t - 8}" text-anchor="middle" class="lt" fill="{col(s["letter"])}">{s["letter"]}</text>')
    for v in range(-40, -3, 6):
        o.append(f'<line x1="{l}" x2="{W - r}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" class="grid"/><text x="{l - 6}" y="{Y(v) + 4:.1f}" text-anchor="end" class="tk">{v}</text>')
    for s in range(0, int(dur) + 1, 30):
        o.append(f'<text x="{X(s):.1f}" y="{H - 10}" text-anchor="middle" class="tk">{mmss(s)}</text>')
    for arr, cls in ((src_st, "ln-src"), (fin_st, "ln-fin")):
        pts = " ".join(f"{X(i*hop + 1.5):.1f},{Y(v):.1f}" for i, v in enumerate(arr) if i*hop + 1.5 <= dur)
        o.append(f'<polyline points="{pts}" class="{cls}" fill="none"/>')
    o.append('</svg>')
    return "".join(o)

def svg_bars(labels, a, b, la, lb, unit="dB", zero=False):
    W, H, l, r, t, bt = 760, 230, 40, 10, 16, 44; pw, ph = W - l - r, H - t - bt
    vals = [v for v in a + b if v is not None]; hi = max(vals + [0]); lo = min(vals + [0]) if zero else 0
    hi = np.ceil(hi/2)*2 + (1 if zero else 0); lo = np.floor(lo/2)*2 - (1 if zero and lo < 0 else 0)
    Y = lambda v: t + (hi - v)/(hi - lo)*ph; n = len(labels); gw = pw/n; bw = gw*0.34
    o = [f'<svg viewBox="0 0 {W} {H}" class="chart" role="img">']
    step = max(1, int((hi - lo)/5))
    for v in np.arange(lo, hi + 0.01, step):
        o.append(f'<line x1="{l}" x2="{W - r}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" class="{"axis" if abs(v) < 1e-9 else "grid"}"/><text x="{l - 6}" y="{Y(v) + 4:.1f}" text-anchor="end" class="tk">{v:g}</text>')
    for i, lab in enumerate(labels):
        cx = l + gw*i + gw/2
        for j, (vals_, cls) in enumerate(((a, "b-src"), (b, "b-fin"))):
            v = vals_[i]
            if v is None: continue
            x = cx + (-bw - 1 if j == 0 else 1); y0, y1 = sorted((Y(0), Y(v)))
            o.append(f'<rect x="{x:.1f}" y="{y0:.1f}" width="{bw:.1f}" height="{max(1, y1 - y0):.1f}" class="{cls}" rx="2"/>')
        o.append(f'<text x="{cx:.1f}" y="{H - bt + 18}" text-anchor="middle" class="tk">{E(lab)}</text>')
    o.append(f'<text x="{l}" y="{H - 6}" class="tk">{unit}</text></svg>')
    return "".join(o)

def svg_delta(labels, d):
    W, H, l, r, t, bt = 760, 200, 40, 10, 14, 30; pw, ph = W - l - r, H - t - bt; m = max(3, np.ceil(max(abs(v) for v in d)))
    Y = lambda v: t + (m - v)/(2*m)*ph; gw = pw/len(labels)
    o = [f'<svg viewBox="0 0 {W} {H}" class="chart" role="img">']
    for v in (-m, -m/2, 0, m/2, m):
        o.append(f'<line x1="{l}" x2="{W - r}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" class="{"axis" if v == 0 else "grid"}"/><text x="{l - 6}" y="{Y(v) + 4:.1f}" text-anchor="end" class="tk">{v:+g}</text>')
    for i, (lab, v) in enumerate(zip(labels, d)):
        cx = l + gw*i + gw/2; y0, y1 = sorted((Y(0), Y(v)))
        o.append(f'<rect x="{cx - gw*0.3:.1f}" y="{y0:.1f}" width="{gw*0.6:.1f}" height="{max(1, y1 - y0):.1f}" class="{"b-up" if v >= 0 else "b-dn"}" rx="2"/>')
        o.append(f'<text x="{cx:.1f}" y="{(y0 - 4) if v >= 0 else (y1 + 12):.1f}" text-anchor="middle" class="tk">{v:+.1f}</text>')
        o.append(f'<text x="{cx:.1f}" y="{H - 10}" text-anchor="middle" class="tk">{lab}</text>')
    return "".join(o) + "</svg>"

# ---------------- page ----------------
CSS = """
:root{color-scheme:dark;--bg:#0a0c10;--glass:#0b0e12;--ink:#e8edf3;--muted:#8f9aa8;--line:#262c34;--src:#9b8cff;--fin:#3fd8ff;
--fin-soft:rgba(63,216,255,.09);--good:#5cf07a;--warn:#ffd84d;--bad:#ff6b5d;--up:#ff9f5a;--dn:#5b9dff;--grid:#1a212a;--chip:#1b2027;
--ui:"Chakra Petch","Heebo",system-ui,sans-serif;--mono:"JetBrains Mono",ui-monospace,Menlo,monospace}
html{background:var(--bg)}
body{background:radial-gradient(1000px 480px at 50% -120px,#1d2631 0%,rgba(10,12,16,0) 70%),var(--bg);color:var(--ink);font:16px/1.65 __FONT__}
.wrap{max-width:800px;margin:0 auto;padding-inline:16px;padding-block:22px 64px}
a{color:var(--fin)}
.brandrow{display:flex;align-items:center;gap:10px;flex-wrap:wrap;direction:ltr;padding:10px 14px;margin-bottom:22px;
  background:linear-gradient(180deg,#2a2f37 0%,#1b1f25 30%,#15181d 100%);border:1px solid #303741;border-radius:12px;
  box-shadow:0 14px 40px rgba(0,0,0,.45),inset 0 1px 0 rgba(255,255,255,.08)}
.logo{width:26px;height:26px;flex:none;filter:drop-shadow(0 0 6px rgba(63,216,255,.35))}
.brand{font:700 12.5px/1 var(--ui);letter-spacing:.16em;text-transform:uppercase}
.tag{font:700 10.5px/1 var(--ui);letter-spacing:.14em;text-transform:uppercase;color:var(--fin);border:1px solid rgba(63,216,255,.5);border-radius:999px;padding:5px 9px}
.credit{font:500 12px/1 var(--ui);color:var(--muted)}
.repo{margin-left:auto;font:600 12px/1 var(--ui);letter-spacing:.06em;border:1px solid #39404a;border-radius:999px;padding:6px 11px;color:var(--ink);text-decoration:none}
.repo:hover{border-color:var(--fin)}.repo:focus-visible,a:focus-visible{outline:2px solid #fff;outline-offset:2px}
h1,h2,h3{font-family:var(--ui);text-wrap:balance;line-height:1.2;letter-spacing:.01em}
h1{font-size:clamp(28px,6vw,40px);margin:4px 0 6px;font-weight:700}
h2{font-size:22px;margin:44px 0 10px;padding-top:18px;border-top:1px solid var(--line);font-weight:700}
h3{font-size:15px;margin:18px 0 6px;font-weight:600;color:#c9d3de}
.eyebrow{font:600 11.5px/1.2 var(--ui);letter-spacing:.14em;text-transform:uppercase;color:var(--muted)}
[dir="rtl"] .eyebrow,[dir="rtl"] th{letter-spacing:0}
.lede{color:var(--muted);margin:0 0 18px}
.num,.mono,td.n{font-family:var(--mono);font-variant-numeric:tabular-nums;direction:ltr;unicode-bidi:isolate}
.lede .num{white-space:nowrap}
.verdict{background:linear-gradient(180deg,#1b2026,#14181d);border:1px solid #2b323b;border-top:2px solid var(--fin);border-radius:12px;padding:18px 20px;margin-top:18px;box-shadow:0 0 30px rgba(63,216,255,.06)}
.verdict h2{border:0;margin:0 0 6px;padding:0;font-size:20px}
.verdict ul{margin:8px 0 0;padding-inline-start:20px;display:grid;gap:8px}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0 0}
.chip{background:var(--chip);border:1px solid var(--line);border-radius:999px;padding:3px 12px;font-size:13px}
.chip.ok{color:var(--good);border-color:rgba(92,240,122,.35)}.chip.warn{color:var(--warn);border-color:rgba(255,216,77,.35)}.chip.bad{color:var(--bad);border-color:rgba(255,107,93,.4)}
.meters{display:grid;gap:14px;margin-top:10px}
.meter{display:grid;grid-template-columns:minmax(120px,170px) 1fr;gap:4px 16px;align-items:start;padding:12px 0;border-bottom:1px solid var(--line)}
.meter .k{font-weight:600}.meter .k small{display:block;font-weight:400;color:var(--muted);font-size:13px}
.meter .v{font-size:15px}.meter .v b{font-family:var(--mono);font-weight:600}
.meter .ex{grid-column:2;color:var(--muted);font-size:14.5px}
.arrow{color:var(--muted);padding:0 6px}.src{color:var(--src)}.fin{color:var(--fin);text-shadow:0 0 8px rgba(63,216,255,.35)}
figure{margin:14px 0 6px;background:var(--glass);border:1px solid var(--line);border-radius:10px;padding:12px 12px 10px;box-shadow:inset 0 2px 12px rgba(0,0,0,.6)}
figcaption{color:var(--muted);font-size:13.5px;margin-top:8px}
.chart{width:100%;height:auto;display:block;direction:ltr}
.chart .grid{stroke:var(--grid);stroke-width:1}.chart .axis{stroke:#3a4450;stroke-width:1}
.chart .tk{fill:#7d8896;font:11px "JetBrains Mono",monospace}.chart .lt{font:600 12px "JetBrains Mono",monospace}
.chart .ln-src{stroke:var(--src);stroke-width:1.6;stroke-dasharray:5 3}.chart .ln-fin{stroke:var(--fin);stroke-width:2.2;filter:drop-shadow(0 0 3px rgba(63,216,255,.8))}
.chart .b-src{fill:#4b4394}.chart .b-fin{fill:var(--fin);filter:drop-shadow(0 0 3px rgba(63,216,255,.6))}
.chart .b-up{fill:var(--up);filter:drop-shadow(0 0 3px rgba(255,159,90,.5))}.chart .b-dn{fill:var(--dn)}
.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:13px;color:var(--muted);margin-top:6px}
.legend i{display:inline-block;width:12px;height:12px;border-radius:3px;vertical-align:-1px;margin-inline-end:6px}
.spec{position:relative;direction:ltr;border-radius:8px;overflow:hidden;border:1px solid var(--line);box-shadow:inset 0 2px 12px rgba(0,0,0,.6)}
.spec img{display:block;width:100%;height:170px;object-fit:fill}
.spec .ft{position:absolute;left:6px;font:11px "JetBrains Mono",monospace;color:#cfe3f0;text-shadow:0 0 3px #000}
.spec .sl{position:absolute;top:0;bottom:0;width:1px;background:rgba(255,255,255,.18)}
.taxis{display:flex;justify-content:space-between;direction:ltr;font:11px "JetBrains Mono",monospace;color:var(--muted);margin-top:4px}
.scroll{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:14.5px}
th,td{padding:7px 8px;border-bottom:1px solid var(--line);text-align:start;vertical-align:top}
th{color:var(--muted);font:600 11px/1.3 var(--ui);letter-spacing:.1em;text-transform:uppercase}
tr.hl td{background:var(--fin-soft)}
.steps{display:grid;gap:0}
.step{display:grid;grid-template-columns:30px 1fr;gap:12px;padding:12px 0;border-bottom:1px solid var(--line)}
.step .i{font-family:var(--mono);color:var(--fin);padding-top:2px}
.step b{display:block}.step p{margin:2px 0 0;color:var(--muted);font-size:14.5px}
.step .fx{color:var(--ink);font-size:14px}
ul.plain{padding-inline-start:20px;display:grid;gap:6px}
dl.gl{display:grid;grid-template-columns:minmax(90px,140px) 1fr;gap:8px 16px}dl.gl dt{font-weight:600}dl.gl dd{margin:0;color:var(--muted)}
.ev{color:var(--muted);font-size:13.5px}
[dir="ltr"].ev,td[dir="ltr"]{text-align:left}
a.ab{display:flex;align-items:center;gap:14px;margin:18px 0 0;padding:14px 18px;border:1.5px solid var(--fin);border-radius:12px;background:rgba(63,216,255,.07);color:var(--ink);text-decoration:none;box-shadow:0 0 24px rgba(63,216,255,.12)}
a.ab:hover{background:rgba(63,216,255,.12)}
a.ab .pl{flex:none;width:38px;height:38px;border-radius:50%;background:linear-gradient(180deg,#63e3ff,#1fb8e0);color:#03131a;display:grid;place-items:center;font-size:15px;box-shadow:0 0 14px rgba(63,216,255,.5)}
a.ab b{display:block;font-size:17px;font-family:var(--ui)}a.ab small{display:block;color:var(--muted);font-size:14px}
.files a{color:var(--fin)}
.files li{margin-bottom:6px}.files code{font-family:var(--mono);font-size:13px;background:var(--chip);border:1px solid var(--line);padding:1px 6px;border-radius:4px;word-break:break-all}
.sig{margin-top:10px;font-size:13px;direction:ltr;unicode-bidi:isolate}
@media (max-width:560px){.meter{grid-template-columns:1fr}.meter .ex{grid-column:1}.spec img{height:130px}.repo{margin-left:0}}
"""

TXT = {
 "en": dict(
    dir="ltr", font='"IBM Plex Sans",system-ui,sans-serif', font_css="IBM+Plex+Sans:wght@400;600", arrow="→", source="Source",
    aria_timeline="Loudness over the song, the source vs {label}",
    m_loud=("Loudness", "The song is {dL:.1f} dB louder. By the rule of thumb (10 dB ≈ twice as loud) that is about {ratio:.1f}x the perceived loudness."),
    m_tp=("True peak", "The peak is kept below -2 so it does not distort after Spotify, Apple and YouTube encode it (Spotify's guideline for loud masters)."),
    m_plr=("Punch", "The gap between the peaks and the loudness dropped by {d:.1f} dB: the song is denser and louder, with slightly fewer sharp hits. Below about 6 it starts to sound squashed."),
    m_lra=("Dynamic range", "The difference between the quiet and loud parts of the song narrowed a little: verses and choruses are closer in level, but the shape is still there."),
    passed="Passed", failed="Failed", clean="Clean", border="Borderline", distorts="Distorts", squashed="Squashed",
    h_pred="How the loudness was chosen", th_pred=["Target (LUFS)", "Reached", "Limiter active", "Clipper residue (dB)", "Status"],
    pred_lede="A fast run of the same chain for each target, before rendering. The highlighted row is the loudest target that comes out clean.",
    f_hist="Signs of earlier processing: {verdict} (samples within 0.5 dB of the peak: {n}).",
    f_cut="Frequency ceiling: a sharp cut at {khz} kHz.", f_nocut="Frequency ceiling: no sharp cut.",
    f_meta="Metadata in the source: ", f_c2pa="; C2PA credential ({t})",
    eyebrow="Mastering report", final="Final version", h_bottom="Bottom line", h_files="What you get",
    ab_link="Listen and compare every version", ab_note="All versions in sync on one timeline, with Spotify-normalized playback and a blind test. Opens on a phone too.",
    h_before="Before and after", before_lede="The four measurements that describe how the song sounds, and what each one means in plain words.",
    lg_sections="Coloured background = the song's sections (same letter = a repeated section)",
    cap_timeline="Loudness over the song. The cyan line (the master) is higher all the way through, and the gap is smaller in the loud sections: that is the compression.",
    h_steps="What was done to the song, and why", h_sections="Section map",
    lg_plr_src="PLR in the source", lg_plr_fin="PLR in {label}",
    cap_plr="Punch (PLR) in each section. A cyan bar much lower than the violet one = that section was compressed more.",
    th_sec=["#", "Time", "Section", "Energy", "LUFS source", "LUFS final", "PLR source", "PLR final", "Change"],
    h_sound="The sound, pictured", h_spec="Spectrogram of {label}", alt_spec="Spectrogram of the final version",
    h_diff="What changed compared with the source", alt_diff="Difference between the final version and the source",
    lg_added="Added", lg_reduced="Reduced", lg_white="Dark = unchanged (scale ±6 dB, at equal integrated loudness)",
    cap_oct="Change in the octave balance (at equal loudness): how much each region, from bass (left) to highs (right), went up or down.",
    h_platforms="Ready for the platforms", th_plat=["Platform", "Playback level change"],
    p_spotify="Spotify (-14 LUFS)", p_youtube="YouTube (-14, turns down only)", p_apple="Apple Music (-16, turns down only)",
    h_codec="After encoding (peak after decoding, dBTP: below 0 = no distortion)", th_codec=["Codec", "Peak", "Status"],
    h_all="All versions", th_all=["Version", "LUFS", "True Peak", "PLR", "LRA", "Spotify", "Peak after encoding", "Checks"],
    h_source="Source check", h_recs="Recommendations", h_gloss="Glossary",
    m_key="Key", m_tempo="Tempo", m_est="(estimates)", h_clicks="Possible clicks", th_clicks=["Time", "Section", "Where", "Strength"],
    clicks_lede="Moments where the waveform jumps sharply within a few milliseconds. Often it is a sharp drum hit, sometimes a real click. Listen to each one (the comparison page marks them on its timeline); none was confirmed by ear.",
    clicks_lede_src="Moments in the source where the waveform jumps sharply within a few milliseconds. Often it is a sharp drum hit, sometimes a real click; listen to each one. None was confirmed by ear.",
    clicks_none="No possible clicks were found in the source or the master.", ck_src="Source only", ck_both="Source and master", ck_new="New in the master",
    footer="Every number in this report was measured on the files themselves. The report does not replace listening: the final call is made by ear.",
    h_ears="First listen: what the ears heard",
    ears_lede="Measurements that stand in for an engineer's first listen. Each finding names its evidence and the tool that answers it.",
    sev=dict(fix="fix", watch="watch", protect="protect", info="info"),
    area=dict(dynamics="dynamics", tone="tone", edges="edges", stereo="stereo", **{"low end": "low end"}),
    find=dict(already_dense="Already dense or limited", very_dynamic="Very dynamic", subsonic="Energy below 25 Hz", stereo_bass="Stereo bass",
              bass_drives_peaks="The bass drives the peaks", bump="Harsh bump at {f} Hz", presence_dip="Vocal presence dip",
              abrupt_end="Abrupt ending", clipped_source="Clipped samples in the source", mono_loss="Loses level in mono", hf_wall="High-frequency ceiling"),
    no_findings="Nothing that needs a tool.",
    h_chain="The chain: what was used and what was left out",
    chain_lede="Every stage is switched on only when the first listen asks for it, and a compressor must also pass a bypass test. What stayed out is listed with the reason.",
    stage=dict(hpf="Sub-sonic high-pass", mono_bass="Mono bass", presence_eq="Presence EQ", dynamic_eq="Dynamic EQ", static_cut="Static cut",
               fade_out="Fade-out", lowcomp="Low-band compressor", glue="Glue compressor", loudness_cap="Loudness cap", tape="Tape",
               matchering="Reference matching", user_plugin="Your plugin"),
    on="on", off="off", th_chain=["Stage", "", "Why"],
    ran="Stages in the final render: ", pruned="Left out at this loudness because they had nothing to do: ",
    h_last="Last listen: each version against the source",
    last_lede="At equal loudness. DR and PSR show how much dynamics were traded for density; sharpness shows whether it got harsher. A flag appears only for a real problem.",
    th_last=["Version", "DR", "PSR (dB)", "PLR (dB)", "Sharpness change (acum)", "Flags"], none="none",
    gloss_more=[("DR", "Dynamic range as the TT DR meter measures it: peaks vs the loudness of the loudest parts. On Ian Shepherd's scale 12+ is very dynamic, 8 or less risks sounding squashed."),
                ("PSR", "Peak to short-term loudness: how far the peaks stand above the music moment by moment. Under 8 suggests heavy limiting."),
                ("Sharpness (acum)", "A psychoacoustic measure (DIN 45692) of how sharp or harsh a sound is, compared here at equal loudness.")],
    glossary=[
      ("LUFS", "Loudness as the ear hears it. Closer to zero = louder. Spotify and YouTube bring every song to -14."),
      ("True Peak", "The highest point of the waveform, including between samples. Too close to 0 and encoding to MP3/AAC/Opus can distort."),
      ("PLR", "The distance between the peaks and the average loudness. Large = sharper hits and more space; small = dense and loud. Too steep a drop = sounds squashed."),
      ("LRA", "The loudness range between the quiet and the loud parts of the song (verse vs chorus)."),
      ("Limiter / clipper", "Tools that stop the peaks from going over a ceiling. Working a little = clean; working most of the time = squashed."),
      ("EQ", "Frequency balance: remove mud, bring the vocal forward, add air. A dynamic EQ acts only in the moments a problem appears."),
      ("Spectrogram", "A picture of the sound: time on the horizontal axis, frequency on the vertical (bass at the bottom, highs at the top), brightness = level."),
      ("C2PA", "A signed digital provenance certificate embedded in the file that records how it was made (for example, by AI).")]),
 "he": dict(
    dir="rtl", font='"IBM Plex Sans Hebrew","Arial Hebrew",system-ui,sans-serif', font_css="IBM+Plex+Sans+Hebrew:wght@400;600", arrow="←", source="מקור",
    aria_timeline="עוצמה לאורך השיר, המקור מול {label}",
    m_loud=("עוצמה", "השיר חזק ב-{dL:.1f} dB – לפי כלל האצבע (10 dB ≈ פי 2 בתחושה) זה בערך פי {ratio:.1f} בעוצמה הנתפסת."),
    m_tp=("שיא אמיתי", "השיא נשמר מתחת ל-‎-2‏ כדי שלא יתעוות אחרי הקידוד של ספוטיפיי, אפל ויוטיוב (ההנחיה של ספוטיפיי לשירים חזקים)."),
    m_plr=("פאנץ׳", "המרחק בין השיאים לעוצמה ירד ב-{d:.1f} dB: השיר צפוף וחזק יותר, עם מעט פחות 'מכות' חדות. מתחת לבערך 6 זה מתחיל להישמע מעוך."),
    m_lra=("טווח דינמי", "ההבדל בין החלקים השקטים לחזקים לאורך השיר הצטמצם מעט – הבתים והפזמונים קרובים יותר בעוצמה, אבל עדיין נשמר מבנה."),
    passed="עבר", failed="נכשל", clean="נקי", border="גבולי", distorts="עיוות", squashed="נמעך",
    h_pred="איך נבחרה העוצמה", th_pred=["יעד (LUFS)", "הושג", "לימיטר פעיל", "עיוות קליפר (dB)", "מצב"],
    pred_lede="הרצה מהירה של אותה שרשרת לכל יעד לפני הרינדור. השורה המודגשת היא העוצמה הגבוהה ביותר שיוצאת נקייה.",
    f_hist="סימני עיבוד קודם: {verdict} (דגימות בטווח חצי dB מהשיא: {n}).",
    f_cut="תקרת תדרים: חיתוך חד ב-{khz} kHz.", f_nocut="תקרת תדרים: אין חיתוך חד.",
    f_meta="מטא-דאטה במקור: ", f_c2pa="; תעודת C2PA ({t})",
    eyebrow="דוח מאסטרינג", final="הגרסה הסופית", h_bottom="בשורה התחתונה", h_files="מה קיבלת",
    ab_link="להאזנה והשוואה בין כל הגרסאות", ab_note="כל הגרסאות מסונכרנות על ציר זמן אחד, עם השמעה מנורמלת כמו בספוטיפיי ובדיקה עיוורת. נפתח גם בטלפון.",
    h_before="לפני ואחרי", before_lede="ארבעת המדדים שמתארים איך השיר נשמע, והמשמעות של כל אחד במילים פשוטות.",
    lg_sections="הרקע הצבעוני = קטעי השיר (אות זהה = קטע שחוזר)",
    cap_timeline="העוצמה לאורך השיר. הקו התכלת (המאסטר) גבוה יותר לאורך כל הדרך, והפער קטן יותר בקטעים החזקים – זו הדחיסה.",
    h_steps="מה נעשה לשיר ולמה", h_sections="מפת הקטעים",
    lg_plr_src="PLR במקור", lg_plr_fin="PLR ב-{label}",
    cap_plr="הפאנץ׳ (PLR) בכל קטע. עמודה תכלת נמוכה בהרבה מהסגולה = הקטע נדחס יותר.",
    th_sec=["#", "זמן", "קטע", "אופי", "LUFS מקור", "LUFS סופי", "PLR מקור", "PLR סופי", "שינוי"],
    h_sound="תמונת הצליל", h_spec="ספקטרוגרמה של {label}", alt_spec="ספקטרוגרמה של הגרסה הסופית",
    h_diff="מה השתנה לעומת המקור", alt_diff="הפרש בין הגרסה הסופית למקור",
    lg_added="נוסף", lg_reduced="הורד", lg_white="כהה = ללא שינוי (עד ±6 dB, בעוצמה כוללת שווה)",
    cap_oct="שינוי באיזון התדרים באוקטבות (בעוצמה שווה): כמה כל אזור, מבס (משמאל) ועד גבוהים (מימין), עלה או ירד.",
    h_platforms="מוכן לפלטפורמות", th_plat=["פלטפורמה", "שינוי עוצמה בהשמעה"],
    p_spotify="Spotify (‎-14 LUFS)", p_youtube="YouTube (‎-14, רק מנמיך)", p_apple="Apple Music (‎-16, רק מנמיך)",
    h_codec="אחרי קידוד (השיא אחרי פענוח, dBTP – מתחת ל-0 = בלי עיוות)", th_codec=["קודק", "שיא", "מצב"],
    h_all="כל הגרסאות", th_all=["גרסה", "LUFS", "True Peak", "PLR", "LRA", "Spotify", "שיא אחרי קידוד", "בדיקות"],
    h_source="בדיקת המקור", h_recs="המלצות", h_gloss="מילון מונחים",
    m_key="סולם", m_tempo="טמפו", m_est="(הערכות)", h_clicks="קליקים אפשריים", th_clicks=["זמן", "קטע", "איפה", "עוצמה"],
    clicks_lede="רגעים שבהם צורת הגל קופצת בחדות בתוך אלפיות שנייה. לרוב זו מכה חדה של תוף, לפעמים קליק אמיתי. כדאי להקשיב לכל אחד (בעמוד ההשוואה הם מסומנים על ציר הזמן); אף אחד מהם לא אומת באוזן.",
    clicks_lede_src="רגעים במקור שבהם צורת הגל קופצת בחדות בתוך אלפיות שנייה. לרוב זו מכה חדה של תוף, לפעמים קליק אמיתי; כדאי להקשיב לכל אחד. אף אחד מהם לא אומת באוזן.",
    clicks_none="לא נמצאו קליקים אפשריים במקור או במאסטר.", ck_src="רק במקור", ck_both="במקור ובמאסטר", ck_new="חדש במאסטר",
    footer="כל המספרים בדוח נמדדו על הקבצים עצמם. הדוח לא מחליף האזנה – ההכרעה הסופית היא באוזניים.",
    h_ears="האזנה ראשונה: מה האוזניים שמעו",
    ears_lede="מדידות שמחליפות את ההאזנה הראשונה של טכנאי. כל ממצא מציין את הראיה ואת הכלי שמטפל בו.",
    sev=dict(fix="לתקן", watch="לשים לב", protect="לשמור", info="מידע"),
    area=dict(dynamics="דינמיקה", tone="גוון", edges="קצוות", stereo="סטריאו", **{"low end": "תחתונים"}),
    find=dict(already_dense="כבר צפוף או מוגבל", very_dynamic="דינמי מאוד", subsonic="אנרגיה מתחת ל-25 Hz", stereo_bass="בס בסטריאו",
              bass_drives_peaks="הבס מוביל את השיאים", bump="בליטה צורמת ב-{f} Hz", presence_dip="חוסר נוכחות לשירה",
              abrupt_end="סוף קטוע", clipped_source="דגימות קטומות במקור", mono_loss="מאבד עוצמה במונו", hf_wall="תקרת תדרים גבוהים"),
    no_findings="לא נמצא משהו שדורש כלי.",
    h_chain="השרשרת: מה הופעל ומה נשאר בחוץ",
    chain_lede="כל שלב מופעל רק כשההאזנה הראשונה מצדיקה אותו, ומדחס צריך גם לעבור מבחן 'באייפס'. מה שנשאר בחוץ מופיע עם הסיבה.",
    stage=dict(hpf="סינון תת-קולי", mono_bass="בס במונו", presence_eq="הבלטת נוכחות", dynamic_eq="EQ דינמי", static_cut="הורדה קבועה",
               fade_out="פייד בסוף", lowcomp="קומפרסור בס", glue="קומפרסור דבק", loudness_cap="תקרת עוצמה", tape="טייפ",
               matchering="התאמה לרפרנס", user_plugin="הפלאגין שלך"),
    on="מופעל", off="בחוץ", th_chain=["שלב", "", "למה"],
    ran="השלבים שרצו ברינדור הסופי: ", pruned="נשארו בחוץ בעוצמה הזו כי לא היה להם מה לעשות: ",
    h_last="האזנה אחרונה: כל גרסה מול המקור",
    last_lede="בעוצמה שווה. DR ו-PSR מראים כמה דינמיקה הוחלפה בצפיפות, והחדות מראה אם נעשה צורם יותר. דגל מופיע רק על בעיה אמיתית.",
    th_last=["גרסה", "DR", "PSR (dB)", "PLR (dB)", "שינוי חדות (acum)", "דגלים"], none="אין",
    gloss_more=[("DR", "טווח דינמי כפי שמודד אותו מד TT DR: השיאים מול העוצמה של החלקים החזקים. בסולם של איאן שפרד, 12 ומעלה דינמי מאוד, 8 ומטה עלול להישמע מעוך."),
                ("PSR", "שיא מול עוצמה רגעית: כמה השיאים מתנשאים מעל המוזיקה מרגע לרגע. מתחת ל-8 מעיד על הגבלה כבדה."),
                ("חדות (acum)", "מדד פסיכואקוסטי (‎DIN 45692‎) לכמה צליל חד או צורם, כאן בהשוואה בעוצמה שווה.")],
    glossary=[
      ("LUFS", "מידת העוצמה כפי שהאוזן שומעת אותה. מספר קרוב יותר לאפס = חזק יותר. ספוטיפיי ויוטיוב מיישרים כל שיר ל-‎-14‏."),
      ("True Peak", "השיא הגבוה ביותר של הגל, כולל בין הדגימות. אם הוא קרוב מדי ל-0, קידוד ל-MP3/AAC/Opus עלול לעוות."),
      ("PLR", "המרחק בין השיאים לעוצמה הממוצעת. גדול = יותר 'מכות' חדות ומרווח; קטן = צפוף וחזק. ירידה חדה מדי = נשמע מעוך."),
      ("LRA", "טווח העוצמה בין החלקים השקטים לחזקים לאורך השיר (בית מול פזמון)."),
      ("לימיטר / קליפר", "כלים שמונעים מהשיאים לעבור תקרה. עובדים מעט = נקי; עובדים רוב הזמן = נמעך."),
      ("EQ", "איזון תדרים: להוריד 'בוץ', להבליט שירה, להוסיף 'אוויר'. EQ דינמי פועל רק ברגעים שבהם בעיה מופיעה."),
      ("ספקטרוגרמה", "תמונה של הצליל: ציר אופקי זמן, ציר אנכי תדר (בס למטה, גבוהים למעלה), ובהירות = עוצמה."),
      ("C2PA", "תעודת מקור דיגיטלית חתומה שמוטמעת בקובץ ומתעדת איך נוצר (למשל ע״י AI).")]),
}

def meters(qsrc, qfin, label, t):
    dL = qfin["lufs_i"] - qsrc["lufs_i"]; ratio = 2**(dL/10)
    rows = [(t["m_loud"][0], "LUFS", qsrc["lufs_i"], qfin["lufs_i"], t["m_loud"][1].format(dL=dL, ratio=ratio)),
            (t["m_tp"][0], "True Peak, dBTP", qsrc["true_peak_dbtp"], qfin["true_peak_dbtp"], t["m_tp"][1]),
            (t["m_plr"][0], "PLR, dB", qsrc["plr_db"], qfin["plr_db"], t["m_plr"][1].format(d=qsrc["plr_db"] - qfin["plr_db"])),
            (t["m_lra"][0], "LRA, LU", qsrc["lra_lu"], qfin["lra_lu"], t["m_lra"][1])]
    o = ['<div class="meters">']
    for k, unit, a, b, ex in rows:
        o.append(f'<div class="meter"><div class="k">{k}<small>{E(unit)}</small></div>'
                 f'<div class="v"><span class="src">{E(t["source"])}</span> <b class="num src">{a:g}</b><span class="arrow">{t["arrow"]}</span><span class="fin">{E(label)}</span> <b class="num fin">{b:g}</b></div>'
                 f'<div class="ex">{E(ex)}</div></div>')
    return "".join(o) + "</div>"

def ths(cells): return "".join(f"<th>{E(c)}</th>" for c in cells)

def ears_html(t, ears):
    if not ears: return ""
    rows = []
    for f in ears.get("findings", []):
        title = t["find"]["bump"].format(f=f["id"].split("_")[1]) if f["id"].startswith("bump_") else t["find"].get(f["id"], f["id"])
        cls = {"fix": "warn", "watch": "", "protect": "ok", "info": ""}.get(f["severity"], "")
        rows.append(f'<tr><td><span class="chip {cls}">{A(t["sev"].get(f["severity"], f["severity"]))}</span></td>'
                    f'<td>{A(t["area"].get(f["area"], f["area"]))}</td><td><b>{E(title)}</b><div class="ev" dir="ltr">{E(f["evidence"])}</div></td></tr>')
    body = f'<div class="scroll"><table>{"".join(rows)}</table></div>' if rows else f'<p>{A(t["no_findings"])}</p>'
    return f'<h2>{A(t["h_ears"])}</h2><p class="lede">{A(t["ears_lede"])}</p>{body}'

def last_html(t, cmp, label):
    if not cmp: return ""
    sharp = lambda v: "–" if v["sharpness_change"] is None else "%+.3f" % v["sharpness_change"]
    s = cmp["source"]; src_row = f'<tr><td>{A(t["source"])}</td><td class="n">{s["dr"]}</td><td class="n">{s["psr_db"]}</td><td class="n">{s["plr_db"]}</td><td class="n">–</td><td>–</td></tr>'
    rows = "".join(f'<tr class="{"hl" if lab == label else ""}"><td>{E(lab)}</td><td class="n">{v["dr"]}</td><td class="n">{v["psr_db"]}</td><td class="n">{v["plr_db"]}</td>'
                   f'<td class="n">{sharp(v)}</td>'
                   f'<td dir="ltr">{E("; ".join(v["flags"])) if v["flags"] else A(t["none"])}</td></tr>' for lab, v in cmp["versions"].items())
    return f'<h2>{A(t["h_last"])}</h2><p class="lede">{A(t["last_lede"])}</p><div class="scroll"><table><tr>{ths(t["th_last"])}</tr>{src_row}{rows}</table></div>'

def paras(items): return "".join(f"<p>{E(p)}</p>" for p in items or [])
def _items(x):
    """Notes give a list of sentences; a single string is split into its sentences - never iterated letter by letter."""
    if not x: return []
    if isinstance(x, str): return [p for p in re.split(r"(?<=[.!?])\s+(?=\S)", x.strip()) if p]
    return [p for p in x if p]
mmss1 = lambda t: f"{int(t)//60}:{t % 60:04.1f}"

def music_line(an, t):
    """Key and tempo as the A/B page shows them: estimates, with the runner-up key when the two are this close."""
    kd = an.get("key_detail") or {}; bpm = an.get("tempo_bpm")
    short = lambda n: (n.split()[0] + ("m" if n.endswith("minor") else "")) if n else None
    nice = lambda k: re.sub(r"b(?=m?$)", "\u266d", k.replace("#", "\u266f")) if k else None
    key = nice(kd.get("short") or short(an.get("key")))
    alt = nice(short(kd.get("runner_up"))) if kd.get("confidence") is not None and kd["confidence"] < 0.03 else None
    parts = []
    if key: parts.append(f'{A(t["m_key"])} <span class="num" dir="ltr">{html.escape(key + (" / " + alt if alt else ""))}</span>')
    if bpm: parts.append(f'{A(t["m_tempo"])} <span class="num" dir="ltr">\u2248{round(bpm)} BPM</span>')
    return f'<p class="lede">{" · ".join(parts)} {A(t["m_est"])}</p>' if parts else ""

def clicks_html(t, ears, cmp, sec, label):
    """Possible clicks: when, in which section, and whether the master added them - a list to check by ear, never a verdict."""
    src = ((ears or {}).get("measurements") or {}).get("clicks")
    fin = (((cmp or {}).get("versions") or {}).get(label) or {}).get("clicks")
    if src is None and fin is None: return ""                     # a run from before clicks were measured
    near = lambda c, cs: any(abs(c["t"] - d["t"]) < 0.05 for d in cs or [])
    if fin is None: rows = [(c, "src") for c in src or []]
    else: rows = [(c, "both" if near(c, fin) else "src") for c in src or []] + [(c, "new") for c in fin if not near(c, src)]
    rows.sort(key=lambda r: r[0]["t"])
    head = f'<h2>{A(t["h_clicks"])}</h2>'
    if not rows: return head + f'<p class="lede">{A(t["clicks_none"])}</p>'
    letter = lambda s: next((x["letter"] for x in sec or [] if x["start"] <= s < x["end"]), "–")
    where = lambda w: f'<span class="chip warn">{A(t["ck_new"])}</span>' if w == "new" else A(t["ck_" + w])
    pro = ' class="pro-only"'
    th = "".join(f'<th{pro if i == 3 else ""}>{E(h)}</th>' for i, h in enumerate(t["th_clicks"]))
    tr = "".join(f'<tr><td class="n" dir="ltr">{mmss1(c["t"])}</td><td>{html.escape(letter(c["t"]))}</td><td>{where(w)}</td>'
                 f'<td class="n pro-only">{c.get("ratio", 0):.0f}\u00d7</td></tr>' for c, w in rows)
    lede = t["clicks_lede"] if fin is not None else t["clicks_lede_src"]
    return head + f'<p class="lede">{A(lede)}</p><div class="scroll"><table><tr>{th}</tr>{tr}</table></div>'

def bullets(items):
    items = _items(items)
    return '<ul class="plain">' + "".join(f"<li>{E(p)}</li>" for p in items) + "</ul>" if items else ""


# ---------------- the chain, in the words of each view (explain.py: the same source as the A/B page's inserts) ----------------
CAT = {"tone": "#3fd8ff", "color": "#ffb347", "dyn": "#9b8cff", "peak": "#ff7a6b", "util": "#8b94a1"}
def amt_word(a, t): return "" if a is None else t["amt"][0 if a < 0.25 else 1 if a < 0.6 else 2]
def pro_line(x):
    spec, _, why = x.partition("\n")                     # a setting, then its measured reason
    return f'<li dir="auto">{E(spec)}' + (f'<span class="r" dir="auto">{E(why)}</span>' if why else "") + "</li>"
def devices_html(ch, t, k):
    o = ['<div class="devs">']
    for i, d in enumerate(ch["devices"]):
        right = E(d["val"]) if k == "pro" else A(amt_word(d["amt"], t))
        bar = f'<div class="amt"><i style="width:{max(3, d["amt"]*100):.0f}%"></i></div>' if d["amt"] is not None else '<div class="amt"></div>'
        why = d["why"][k] or d["why"]["pro"] or d["why"]["art"]
        lines = ""
        if k == "pro" and d["pro"]: lines = '<ul class="pl">' + "".join(pro_line(x) for x in d["pro"]) + "</ul>"
        if k == "art" and d["art"]: lines = '<ul class="al">' + "".join(f'<li dir="auto">{E(x)}</li>' for x in d["art"]) + "</ul>"
        o.append(f'<div class="dev" style="--cc:{CAT.get(d["cat"], "#8b94a1")}"><div class="dh"><span class="sn">{i+1:02d}</span><i class="led"></i>'
                 f'<b>{E(d["name"][k])}</b><span class="val">{right}</span></div>{bar}<p dir="auto">{E(why)}</p>{lines}</div>')
    o.append("</div>")
    if ch["skipped"]:
        o.append(f'<h3>{A(t["left_out"])}</h3><ul class="left">' + "".join(
            f'<li><b>{E(s["name"][k])}</b><span dir="auto">{E(s["why"][k] or s["why"]["pro"])}</span></li>' for s in ch["skipped"]) + "</ul>")
    return "".join(o)

# ---------------- what only restates the data is written here, per language, so notes.json carries only judgement ----------------
def worst_section(sec, src, label):
    return min(sec, key=lambda s: (s["stats"][label]["plr"] or 99) - (s["stats"][src]["plr"] or 0))
def auto_sections(w, src, label, t):
    a, b = w["stats"][src]["plr"], w["stats"][label]["plr"]
    return t["sec_auto"].format(letter=w["letter"], t0=mmss(w["start"]), t1=mmss(w["end"]), a=f"{a:.1f}", b=f"{b:.1f}", d=f"{a - b:.1f}")
def codec_worst(q):
    cp = {k: v for k, v in (q.get("codec_decoded_true_peak") or {}).items() if v is not None}
    return max(cp.items(), key=lambda kv: kv[1]) if cp else (None, None)
def auto_platforms(q, t):
    g = q["playback_gain_db"]; name, w = codec_worst(q)
    out = [t["plat_auto"].format(s=f"{-g['Spotify (-14)']:.1f}", ap=f"{-g['Apple Music (-16, down only)']:.1f}")]
    if w is not None: out.append(t["codec_auto"].format(w=f"{w:.2f}", worst=name))
    return out
def auto_prediction(pr, t):
    rows = pr.get("rows") or []; best = pr.get("loudest_clean")
    if best is None or not rows: return []
    louder = [r for r in rows if r["target"] > best]
    more = t["pred_more"].format(t=f"{louder[0]['target']:g}", pct=f"{louder[0]['leveler_active_pct']:.0f}") if louder else ""
    return [t["pred_auto"].format(targets=", ".join(f"{r['target']:g}" for r in rows), best=f"{best:g}", more=more)]
def auto_sound(stt, t):
    out = [t["sound_gen"]]
    for b in (stt.get("dyneq") or {}).get("bands", []): out.append(t["sound_dyneq"].format(f=explain.hz(b["f"])))
    return out
def ready_html(q, t):
    g = q["playback_gain_db"]; _, w = codec_worst(q); ok = w is not None and w < -0.3
    items = [("ok", t["ready_spotify"].format(x=f"{-g['Spotify (-14)']:.1f}")), ("ok", t["ready_apple"].format(x=f"{-g['Apple Music (-16, down only)']:.1f}"))]
    if w is not None: items.append(("ok" if ok else "warn", (t["ready_codec"] if ok else t["ready_codec_warn"]).format(w=f"{w:.2f}")))
    if q.get("mono_fold_change_db") is not None:
        items.append(("ok" if q["mono_fold_change_db"] > -3 else "warn", t["ready_mono"].format(m=f"{q['mono_fold_change_db']:.1f}")))
    return '<ul class="ready">' + "".join(f'<li class="{c}">{E(x)}</li>' for c, x in items) + "</ul>"
FILE_RULES = [(r"^1 - ", "files_src"), (r"\(16bit 44\.1k\)", "files_dist"), (r"\((\d+)bit (\d+(?:\.\d+)?)k\)\.wav$", "files_master"),
              (r"\.mp3$", "files_mp3"), (r"A-B.*\.html$", "files_ab"), (r"\.html$", "files_report"), (r"\.png$", "files_png")]
def files_auto(deliv, t, final_label, lang):
    out = []
    for name in sorted(os.listdir(deliv), key=lambda n: (not n[:1].isdigit(), n)):
        for rx, key in FILE_RULES:
            m = re.search(rx, name)
            if not m: continue
            if key == "files_master":
                label = re.sub(r"^\d+ - ", "", name[:m.start()]).strip()
                use = t[key].format(label=label, bits=m.group(1), rate=m.group(2)) + (t["files_rec"] if label == final_label else "")
            else: use = t[key]
            out.append(dict(name=name, use=use)); break
    if not any(re.search(r"\.html$", f["name"]) and "A-B" not in f["name"] for f in out):   # the report itself, saved there next
        out.append(dict(name=REPORT_FILE[lang], use=t["files_report"]))
    return out
REPORT_FILE = {"he": "דוח מאסטרינג.html", "en": "Mastering report.html"}

TXT2 = {
 "en": dict(view_art="Artist", view_pro="Pro", lang_name="EN", view_t="Level of detail: the same master, explained plainly or with every number",
    h_done="What was done to your song", done_lede="Each step only where the song needed it; the bar shows how hard it works.",
    left_out="Checked and left out", amt=("light", "moderate", "strong"), energy=dict(loud="loud", medium="medium", quiet="quiet"),
    h_listen="Where to listen", listen_tip="In the comparison page choose “Normalized like Spotify”, loop section {letter} ({t0}–{t1}) and switch between the source and {label}: that section changed the most.",
    h_ready="Ready for streaming",
    ready_spotify="Spotify and YouTube turn it down by {x} dB to −14 LUFS, as they do with every loud master.",
    ready_apple="Apple Music turns it down by {x} dB to −16 LUFS.",
    ready_codec="No distortion after encoding to MP3, AAC or Opus: the highest peak after decoding is {w} dBTP.",
    ready_codec_warn="After encoding, the highest peak is {w} dBTP, close to 0: a version at −2.5 dBTP would be safer.",
    ready_mono="Holds up in mono (phones, smart speakers): it changes by {m} dB.",
    sec_auto="The section that changed the most is {letter} at {t0}–{t1}: its punch (PLR) went from {a} to {b} dB, a drop of {d} dB. That is the one to audition first.",
    plat_auto="Spotify and YouTube will play it {s} dB quieter (to −14 LUFS) and Apple Music {ap} dB quieter (to −16). On those services what you gain is density, not level.",
    codec_auto="After real encodes the highest peak is {w} dBTP ({worst}), below 0, so nothing distorts.",
    pred_auto="Of the targets tried ({targets} LUFS), the loudest one that stays clean is {best} LUFS. {more}",
    pred_more="At {t} LUFS the leveler would work {pct}% of the time.",
    sound_dyneq="In the difference view, the narrow blue line near {f} that shows only part of the time is the dynamic EQ at work.",
    sound_gen="Quiet sections look orange and loud ones bluish: that is the compression; the master is denser.",
    h_notes="Engineer's notes",
    files_src="Your original, untouched, for comparison.", files_master="{label}: the full-quality master ({bits}-bit, {rate} kHz).", files_rec=" The recommended one.",
    files_dist="The copy to upload to your distributor (16-bit, 44.1 kHz).", files_mp3="MP3 320 for listening and sending.",
    files_ab="The comparison page. The link opens it on any device (MP3); the file in the folder plays the full WAVs on a computer.",
    files_report="This report, as a file.", files_png="A one-image summary to share."),
 "he": dict(view_art="אמן", view_pro="מקצועי", lang_name="עב", view_t="רמת הפירוט: אותו מאסטר, בהסבר פשוט או עם כל המספרים",
    h_done="מה נעשה לשיר שלך", done_lede="כל שלב רק איפה שהשיר היה צריך; הפס מראה כמה הוא עובד.",
    left_out="נבדק ונשאר בחוץ", amt=("קל", "בינוני", "חזק"), energy=dict(loud="שיא", medium="בינוני", quiet="שקט"),
    h_listen="איפה להקשיב", listen_tip="בעמוד ההשוואה כדאי לבחור „מנורמל כמו ספוטיפיי”, לשים לופ על קטע {letter} ({t0}–{t1}) ולעבור בין המקור ל-{label}: זה הקטע שהשתנה הכי הרבה.",
    h_ready="מוכן לסטרימינג",
    ready_spotify="ספוטיפיי ויוטיוב מנמיכים אותו ב-{x} dB ל-‎−14 LUFS, כמו כל מאסטר חזק.",
    ready_apple="אפל מיוזיק מנמיך אותו ב-{x} dB ל-‎−16 LUFS.",
    ready_codec="בלי עיוות אחרי קידוד ל-MP3, ‏AAC או Opus: השיא הגבוה אחרי פענוח הוא {w} dBTP.",
    ready_codec_warn="אחרי קידוד השיא הגבוה הוא {w} dBTP, קרוב ל-0: גרסה ב-‎−2.5 dBTP תהיה בטוחה יותר.",
    ready_mono="מחזיק במונו (טלפונים, רמקולים חכמים): משתנה ב-{m} dB.",
    sec_auto="הקטע שהשתנה הכי הרבה הוא {letter} ב-{t0}–{t1}: הפאנץ׳ שלו (PLR) ירד מ-{a} ל-{b} dB, ירידה של {d} dB. אותו כדאי לשמוע ראשון.",
    plat_auto="ספוטיפיי ויוטיוב ינגנו אותו שקט יותר ב-{s} dB (ל-‎−14 LUFS), ואפל מיוזיק ב-{ap} dB (ל-‎−16). מה שמרוויחים שם הוא צפיפות, לא עוצמה.",
    codec_auto="אחרי קידוד אמיתי השיא הגבוה הוא {w} dBTP ({worst}), מתחת ל-0, ולכן שום דבר לא מתעוות.",
    pred_auto="מבין היעדים שנבדקו ({targets} LUFS), הגבוה ביותר שנשאר נקי הוא {best} LUFS. {more}",
    pred_more="ב-{t} LUFS הלימיטר המיישר היה עובד {pct}% מהזמן.",
    sound_dyneq="בתצוגת ההפרש, הקו הכחול הצר סביב {f}, שמופיע רק בחלק מהזמן, הוא ה-EQ הדינמי בפעולה.",
    sound_gen="קטעים שקטים נראים כתומים וחזקים כחלחלים: זו הדחיסה; המאסטר צפוף יותר.",
    h_notes="הערות הטכנאי",
    files_src="המקור שלך, בלי שינוי, להשוואה.", files_master="{label}: המאסטר באיכות מלאה ({bits} ביט, {rate} kHz).", files_rec=" המומלץ.",
    files_dist="העותק להעלאה למפיץ (16 ביט, 44.1 kHz).", files_mp3="MP3 320 להאזנה ולשליחה.",
    files_ab="עמוד ההשוואה. הקישור פותח אותו בכל מכשיר (MP3); הקובץ שבתיקייה מנגן את קובצי ה-WAV המלאים במחשב.",
    files_report="הדוח הזה, כקובץ.", files_png="סיכום בתמונה אחת לשיתוף."),
}
for _l in TXT: TXT[_l].update(TXT2[_l])

CSS += """
body{font:16px/1.65 "IBM Plex Sans","IBM Plex Sans Hebrew","Heebo",system-ui,sans-serif}
body.v-artist .pro-only{display:none!important}body.v-pro .art-only{display:none!important}
main[hidden]{display:none!important}
.sw{display:flex;gap:8px;margin-left:auto;flex-wrap:wrap}.sw+.repo{margin-left:0}
.seg{display:inline-flex;border:1px solid #0f1113;border-radius:999px;overflow:hidden;background:#1d2127}
.seg button{border:0;background:none;color:#c9d0d9;font:600 11.5px/1 var(--ui);letter-spacing:.06em;text-transform:uppercase;padding:8px 12px;cursor:pointer;display:inline-flex;align-items:center;gap:6px}
.seg button .led{width:6px;height:6px;border-radius:50%;background:#3b4047}
.seg button.on{color:#e9fbff;background:linear-gradient(#244b58,#1b3a45)}.seg button.on .led{background:var(--fin);box-shadow:0 0 6px var(--fin)}
.seg button:focus-visible{outline:2px solid #fff;outline-offset:-2px}
[dir="rtl"] .seg button{letter-spacing:0}
.devs{display:grid;gap:8px;margin-top:12px}
.dev{background:linear-gradient(180deg,#1b2026,#15191e);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.dh{display:flex;align-items:center;gap:10px}
.dh .sn{font:600 11px var(--mono);color:#5f6874}
.dh .led{width:8px;height:8px;border-radius:50%;background:var(--cc);box-shadow:0 0 8px var(--cc);flex:none}
.dh b{font:600 15px/1.3 var(--ui)}
.dh .val{margin-inline-start:auto;font:500 12.5px var(--mono);color:#cfe9f3;white-space:nowrap}
.dev .amt{height:3px;background:#1a1f25;border-radius:2px;margin:9px 0 6px;overflow:hidden;direction:ltr}
.dev .amt i{display:block;height:100%;background:var(--cc);box-shadow:0 0 6px var(--cc)}
.dev p{margin:4px 0 0;color:#b9c3cf;font-size:14.5px}
.dev ul{margin:6px 0 0;padding-inline-start:18px;color:#aeb8c4;font-size:14px;display:grid;gap:3px}
.dev ul.pl{font:500 12.5px/1.5 var(--mono);color:#9fb0bf;list-style:"· "}
.dev ul.pl .r{display:block;font:400 13px/1.45 "IBM Plex Sans","IBM Plex Sans Hebrew",sans-serif;color:#8d99a7;margin-bottom:3px}
ul.left{list-style:none;padding:0;display:grid;gap:8px;font-size:14.5px}ul.left b{display:block;font-weight:600}ul.left span{color:var(--muted)}
ul.ready{list-style:none;padding:0;display:grid;gap:8px}
ul.ready li{padding:10px 14px 10px 40px;position:relative;background:#161a1f;border:1px solid var(--line);border-radius:10px}
[dir="rtl"] ul.ready li{padding:10px 40px 10px 14px}
ul.ready li::before{content:"✓";position:absolute;inset-inline-start:14px;top:9px;color:var(--good);font-weight:700}
ul.ready li.warn::before{content:"!";color:var(--warn)}
bdi{white-space:nowrap}
@media (max-width:560px){.sw{margin-left:0;width:100%}}
"""

def spec_block(D, img, cls, alt):
    sec, dur = D["sec"], D["dur"]
    ticks = "".join(f'<span class="ft" style="bottom:{np.log(f/40)/np.log(20000/40)*100:.1f}%">{x}</span>' for f, x in ((100, "100 Hz"), (1000, "1k"), (10000, "10k")))
    lines = "".join(f'<span class="sl" style="left:{s["start"]/dur*100:.2f}%"></span>' for s in sec[1:])
    axis = "".join(f"<span>{mmss(x)}</span>" for x in np.linspace(0, dur, 6))
    return f'<div class="spec {cls}"><img src="{img}" alt="{A(alt)}">{ticks}{lines}</div><div class="taxis">{axis}</div>'

def render(lang, a, D, N):
    """One language's page body; D holds what every language shares (charts, measurements), N this language's notes."""
    t = TXT[lang]; qc, qsrc, qfin, sec, src, label, stt = D["qc"], D["qsrc"], D["qfin"], D["sec"], D["src"], a.label, D["stt"]
    ch = D["chain"][lang]; w = D["worst"]; plat = qfin["playback_gain_db"]
    labels = [f"{s['index']}{s['letter']}" for s in sec]
    ver_rows = []
    for lab, q in qc.items():
        if lab.startswith("_"): continue
        cp = q.get("codec_decoded_true_peak") or {}; wv = max((v for v in cp.values() if v is not None), default=None)
        ok = "–" if "checks" not in q else (f'<span class="chip ok">{t["passed"]}</span>' if all(q["checks"].values()) else f'<span class="chip bad">{t["failed"]}</span>')
        ver_rows.append(f'<tr class="{"hl" if lab == label else ""}"><td>{E(lab)}</td><td class="n">{q["lufs_i"]:.1f}</td><td class="n">{q["true_peak_dbtp"]:.2f}</td>'
                        f'<td class="n">{q["plr_db"]:.1f}</td><td class="n">{q["lra_lu"]:.1f}</td><td class="n">{q["playback_gain_db"]["Spotify (-14)"]:+.1f}</td>'
                        f'<td class="n">{"–" if wv is None else f"{wv:.2f}"}</td><td>{ok}</td></tr>')
    chip = lambda c, k: f'<span class="chip {c}">{t[k]}</span>'
    codec_rows = "".join(f'<tr><td>{E(k)}</td><td class="n">{v:.2f}</td><td>{chip("ok", "clean") if v < -0.3 else (chip("warn", "border") if v < 0 else chip("bad", "distorts"))}</td></tr>'
                         for k, v in (qfin.get("codec_decoded_true_peak") or {}).items() if v is not None)
    energy = lambda s: t["energy"].get(s.get("energy_key"), s["energy"])
    sec_rows = "".join(f'<tr class="{"hl" if s is w else ""}"><td class="n">{s["index"]}</td><td class="n">{mmss(s["start"])}–{mmss(s["end"])}</td>'
                       f'<td><span class="chip" style="color:{col(s["letter"])}">{s["letter"]}</span></td><td>{E(energy(s))}</td>'
                       f'<td class="n">{s["stats"][src]["lufs"]}</td><td class="n">{s["stats"][label]["lufs"]}</td>'
                       f'<td class="n">{s["stats"][src]["plr"]}</td><td class="n">{s["stats"][label]["plr"]}</td>'
                       f'<td class="n">{s["stats"][label]["plr"] - s["stats"][src]["plr"]:+.1f}</td></tr>' for s in sec)
    pr = D["pr"]; pred_html = ""
    if pr:
        pr_rows = "".join(f'<tr class="{"hl" if r["target"] == pr.get("loudest_clean") else ""}"><td class="n">{r["target"]:g}</td><td class="n">{r["reached"]:.2f}</td>'
                          f'<td class="n">{r["leveler_active_pct"]:.0f}%</td><td class="n">{r["clip_residual_db"]:.1f}</td>'
                          f'<td>{chip("ok", "clean") if not r["health"] else chip("bad", "squashed")}</td></tr>' for r in pr["rows"])
        pred_html = (f'<h2>{t["h_pred"]}</h2>{paras(N.get("prediction_notes") or auto_prediction(pr, t))}'
                     f'<div class="scroll"><table><tr>{ths(t["th_pred"])}</tr>{pr_rows}</table></div><p class="lede">{E(t["pred_lede"])}</p>')
    an = D["an"]; fo = an.get("forensics", {}); dh = fo.get("dynamics_history", {}); hf = fo.get("hf_ceiling", {}); md = fo.get("metadata", {})
    src_facts = [t["f_hist"].format(verdict=dh.get("verdict", "–"), n=dh.get("samples_near_peak", {}).get("0.5 dB", "–")),
                 t["f_cut"].format(khz=hf.get("cutoff_khz")) if hf.get("cutoff_khz") else t["f_nocut"],
                 t["f_meta"] + ", ".join(f"{k}={v}" for k, v in (md.get("tags") or {}).items()) +
                 (t["f_c2pa"].format(t=md["c2pa_content_credentials"].get("digitalSourceType", "")) if md.get("c2pa_content_credentials") else "")]
    def file_li(f):
        url = f.get("url") or (a.ab_url if a.ab_url and "A-B" in f["name"] else None)
        name = f'<code dir="ltr">{A(f["name"])}</code>'                     # a file name reads left to right, like a path
        if url: name = f'<a href="{A(url)}" target="_blank" rel="noopener">{name}</a>'
        return f'<li>{name} – {E(f["use"])}</li>'
    files = "".join(file_li(f) for f in (N.get("files") or (files_auto(a.deliv, t, label, D["langs"][0]) if a.deliv else [])))
    ab = (f'<a class="ab" href="{A(a.ab_url)}" target="_blank" rel="noopener"><span class="pl" aria-hidden="true">▶</span>'
          f'<span><b>{A(t["ab_link"])}</b><small>{A(t["ab_note"])}</small></span></a>') if a.ab_url else ""
    steps = "".join(f'<div class="step"><span class="i">{i+1:02d}</span><div><b>{E(s["what"])}</b><p>{E(s["why"])}</p>{"<p class=fx>" + E(s["effect"]) + "</p>" if s.get("effect") else ""}</div></div>'
                    for i, s in enumerate(N.get("steps", [])))
    chips = "".join(f'<span class="chip {c}">{E(x)}</span>' for x, c in                       # [text, status] pairs; a bare text is a plain chip
                    ((ch[0], ch[1] if len(ch) > 1 else "") if isinstance(ch, (list, tuple)) else (ch, "") for ch in N.get("chips") or []))
    gl = "".join(f"<dt>{E(k)}</dt><dd>{E(v)}</dd>" for k, v in t["glossary"] + t["gloss_more"])
    langsw = ('<div class="seg" role="group">' + "".join(f'<button data-l="{l}" lang="{l}"><i class="led"></i>{A(TXT[l]["lang_name"])}</button>' for l in D["langs"]) + "</div>"
              if len(D["langs"]) > 1 else "")
    switch = (f'<div class="sw"><div class="seg" role="group" title="{A(t["view_t"])}"><button data-v="artist"><i class="led"></i>{A(t["view_art"])}</button>'
              f'<button data-v="pro"><i class="led"></i>{A(t["view_pro"])}</button></div>{langsw}</div>')
    listen = t["listen_tip"].format(letter=w["letter"], t0=mmss(w["start"]), t1=mmss(w["end"]), label=label)
    plr_fin = t["lg_plr_fin"].split("{label}")
    spec_h = t["h_spec"].split("{label}")
    notes_h = f'<h2>{A(t["h_notes"])}</h2><div class="steps">{steps}</div>' if steps else ""
    return f"""<main class="wrap" dir="{t["dir"]}" lang="{lang}" data-lang="{lang}" data-title="{A(N["page_title"])}">
<div class="brandrow">{LOGO}<span class="brand">{BRAND}</span><span class="tag">{TAG}</span><span class="credit">{CREDIT}</span>{switch}<a class="repo" href="{REPO}" target="_blank" rel="noopener">GitHub &#8599;</a></div>
<div class="eyebrow">{A(t["eyebrow"])} · {E(N.get("date", ""))}</div>
<h1>{E(N["title"])}</h1>
<p class="lede">{E(N.get("artist", ""))} · {A(t["final"])}: {E(label)} · <span class="num">{qfin["lufs_i"]:.1f} LUFS · {qfin["true_peak_dbtp"]:.2f} dBTP</span></p>
{music_line(an, t)}
<section class="verdict"><h2>{A(t["h_bottom"])}</h2>{bullets(N.get("bottom_line"))}<div class="chips">{chips}</div></section>
{ab}

<h2>{A(t["h_files"])}</h2><ul class="plain files">{files}</ul>

<div class="art-only"><h2>{A(t["h_done"])}</h2><p class="lede">{A(t["done_lede"])}</p>{devices_html(ch, t, "art")}</div>
<div class="pro-only">{ears_html(t, D["ears"])}
<h2>{A(t["h_chain"])}</h2><p class="lede">{A(t["chain_lede"])}</p>{devices_html(ch, t, "pro")}
{notes_h}</div>

<h2>{A(t["h_before"])}</h2><p class="lede">{A(t["before_lede"])}</p>
{meters(qsrc, qfin, label, t)}
<figure>{svg_timeline(D["st_x"], D["st_y"], D["hop"], D["dur"], sec, label, t)}
<div class="legend"><span><i style="background:var(--src)"></i>{A(t["source"])}</span><span><i style="background:var(--fin)"></i>{E(label)}</span><span>{A(t["lg_sections"])}</span></div>
<figcaption>{A(t["cap_timeline"])}</figcaption></figure>
{clicks_html(t, D["ears"], D["cmp"], sec, label)}

<div class="art-only"><h2>{A(t["h_listen"])}</h2><p>{E(auto_sections(w, src, label, t))}</p><p>{E(listen)}</p>
<h2>{A(t["h_ready"])}</h2>{ready_html(qfin, t)}</div>

<div class="pro-only">
<h2>{A(t["h_sections"])}</h2>{paras(N.get("sections_notes") or [auto_sections(w, src, label, t)])}
<figure>{svg_bars(labels, [s["stats"][src]["plr"] for s in sec], [s["stats"][label]["plr"] for s in sec], src, label)}
<div class="legend"><span><i style="background:var(--src)"></i>{A(t["lg_plr_src"])}</span><span><i style="background:var(--fin)"></i>{A(plr_fin[0])}{E(label)}{A(plr_fin[1])}</span></div>
<figcaption>{A(t["cap_plr"])}</figcaption></figure>
<div class="scroll"><table><tr>{ths(t["th_sec"])}</tr>{sec_rows}</table></div>

<h2>{A(t["h_sound"])}</h2>{paras(N.get("sound_notes") or auto_sound(stt, t))}
<h3>{A(spec_h[0])}{E(label)}{A(spec_h[1])}</h3>{spec_block(D, D["spec_img"], "", t["alt_spec"])}
<h3>{A(t["h_diff"])}</h3>{spec_block(D, D["diff_img"], "diff", t["alt_diff"])}
<div class="legend"><span><i style="background:#ff9f5a"></i>{A(t["lg_added"])}</span><span><i style="background:#5b9dff"></i>{A(t["lg_reduced"])}</span><span>{A(t["lg_white"])}</span></div>
<figure>{svg_delta(OCT_L, D["oct_d"])}<figcaption>{A(t["cap_oct"])}</figcaption></figure>

<h2>{A(t["h_platforms"])}</h2>{paras(N.get("platform_notes") or auto_platforms(qfin, t))}
<div class="scroll"><table><tr>{ths(t["th_plat"])}</tr>
<tr><td>{A(t["p_spotify"])}</td><td class="n">{plat["Spotify (-14)"]:+.1f} dB</td></tr>
<tr><td>{A(t["p_youtube"])}</td><td class="n">{plat["YouTube (-14, down only)"]:+.1f} dB</td></tr>
<tr><td>{A(t["p_apple"])}</td><td class="n">{plat["Apple Music (-16, down only)"]:+.1f} dB</td></tr></table></div>
<h3>{A(t["h_codec"])}</h3>
<div class="scroll"><table><tr>{ths(t["th_codec"])}</tr>{codec_rows}</table></div>
{pred_html}
{last_html(t, D["cmp"], label)}

<h2>{A(t["h_all"])}</h2><div class="scroll"><table><tr>{ths(t["th_all"])}</tr>{"".join(ver_rows)}</table></div>

<h2>{A(t["h_source"])}</h2>{paras(N.get("source_notes"))}{bullets(src_facts)}
</div>

<h2>{A(t["h_recs"])}</h2>{bullets(N.get("recommendations"))}

<div class="pro-only"><h2>{A(t["h_gloss"])}</h2><dl class="gl">{gl}</dl></div>
<p class="lede" style="margin-top:28px">{A(t["footer"])}</p>
<p class="lede sig"><a href="{REPO}" target="_blank" rel="noopener">{BRAND} &#183; {TAG} &#183; {CREDIT} &#183; {REPO.split('//')[1]}</a></p>
</main>"""

SWITCH_JS = """<script>(function(){
var S={g:function(k){try{return localStorage.getItem(k)}catch(e){return null}},s:function(k,v){try{localStorage.setItem(k,v)}catch(e){}}};
var q=new URLSearchParams(location.search),M=[].slice.call(document.querySelectorAll('main[data-lang]')),L=M.map(function(m){return m.dataset.lang}),D=__DEF__;
var lang=[q.get('lang'),S.g('ms_lang'),D.lang].filter(function(l){return l&&L.indexOf(l)>=0})[0]||L[0];
var view=[q.get('view'),S.g('ms_view'),D.view].filter(function(v){return v==='artist'||v==='pro'})[0]||'artist';
function apply(){M.forEach(function(m){m.hidden=m.dataset.lang!==lang});document.documentElement.lang=lang;
 document.body.classList.toggle('v-artist',view==='artist');document.body.classList.toggle('v-pro',view==='pro');
 [].forEach.call(document.querySelectorAll('[data-v]'),function(b){var on=b.dataset.v===view;b.classList.toggle('on',on);b.setAttribute('aria-pressed',on)});
 [].forEach.call(document.querySelectorAll('[data-l]'),function(b){var on=b.dataset.l===lang;b.classList.toggle('on',on);b.setAttribute('aria-pressed',on)});
 var m=document.querySelector('main[data-lang="'+lang+'"]');if(m)document.title=m.dataset.title;}
document.addEventListener('click',function(e){var b=e.target.closest('[data-v],[data-l]');if(!b)return;
 if(b.dataset.v){view=b.dataset.v;S.s('ms_view',view)}else{lang=b.dataset.l;S.s('ms_lang',lang)}apply();});
apply();})();</script>"""

def main():
    ap = argparse.ArgumentParser()
    for k in ("source", "final", "label", "qc", "sections", "analysis", "notes", "out"): ap.add_argument("--" + k, required=True)
    ap.add_argument("--predict"); ap.add_argument("--stats"); ap.add_argument("--lang", default="en", help="he, en, or several comma-separated (the first is the default)")
    ap.add_argument("--view", choices=("artist", "pro"), default="artist", help="the level of detail the page opens in")
    ap.add_argument("--ears", help="ears.py listen output (first listen)"); ap.add_argument("--plan", help="plan.py plan.json")
    ap.add_argument("--compare", help="ears.py compare output (last listen)")
    ap.add_argument("--ab-url", help="link to the published A/B page (compare_page.py --web)")
    ap.add_argument("--deliv", help="the delivery folder: 'what you get' is listed from it when notes.json has no files")
    a = ap.parse_args()
    langs = [l.strip() for l in a.lang.split(",") if l.strip()]
    if not langs or any(l not in TXT for l in langs): raise SystemExit(f"--lang: supported languages are {sorted(TXT)}")
    NN = json.load(open(a.notes)); NN = NN if all(l in NN for l in langs) else {langs[0]: NN}
    missing = [l for l in langs if l not in NN]
    if missing: raise SystemExit(f'notes.json has no text for {missing}: give one object per language, {{"he": {{...}}, "en": {{...}}}}')
    J = lambda p: json.load(open(p)) if p else None
    qc = json.load(open(a.qc)); S = json.load(open(a.sections)); sec = S["sections"]
    src = S.get("source") or S["versions"][0]
    x, sr = L.read_stereo(a.source); y, sry = L.read_stereo(a.final); Ix, Iy = L.lufs(x, sr), L.lufs(y, sry)
    Sx = logspec(x, sr, Ix); Sy = logspec(y, sry, Iy); m = min(Sx.shape[1], Sy.shape[1]); Sx, Sy = Sx[:, :m], Sy[:, :m]
    cm_spec, cm_diff = cmaps(); top = np.percentile(Sy, 99.5)
    stt = json.load(open(a.stats)) if a.stats else {}
    PLAN, EARS = J(a.plan), J(a.ears)
    D = dict(langs=langs, qc=qc, sec=sec, src=src, stt=stt, an=json.load(open(a.analysis)), pr=J(a.predict), ears=EARS, cmp=J(a.compare),
             qsrc=qc.get(src) or next(v for k, v in qc.items() if not k.startswith("_") and "checks" not in v), qfin=qc[a.label],
             hop=1.0, dur=len(x)/sr, st_x=L.kweighted_blocks(x, sr, 3.0, 1.0), st_y=L.kweighted_blocks(y, sry, 3.0, 1.0),
             spec_img=png(Sy, cm_spec, top - 70, top), diff_img=png(Sy - Sx, cm_diff, -6, 6),
             oct_d=[b - c for b, c in zip(octaves(y, sry, Iy), octaves(x, sr, Ix))],
             chain={l: explain.chain(stt, PLAN, EARS, l) if stt else explain.source_chain(l) for l in langs})
    D["worst"] = worst_section(sec, src, a.label)
    bodies = [render(l, a, D, NN[l]) for l in langs]
    imgs = {}
    if len(langs) > 1:                                        # each picture once, whatever the number of languages
        def keep(mt):
            k = imgs.setdefault(mt.group(1), f"i{len(imgs)}"); return f'data-img="{k}"'
        bodies = [re.sub(r'src="(data:image/[^"]+)"', keep, b) for b in bodies]
    fonts = "&".join(dict.fromkeys(f"family={TXT[l]['font_css']}" for l in langs))
    head = (f'<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><title>{A(NN[langs[0]]["page_title"])}</title>\n'
            f'<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
            f'<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Chakra+Petch:wght@500;600;700&family=Heebo:wght@500;600;700&{fonts}&family=JetBrains+Mono:wght@400;600&display=swap">\n'
            f'<style>{CSS.replace("__FONT__", TXT[langs[0]]["font"])}</style>\n<body class="v-{a.view}">\n')
    imgjs = ("<script>var IMG=" + json.dumps({v: k for k, v in imgs.items()}) +
             ";[].forEach.call(document.querySelectorAll('img[data-img]'),function(i){i.src=IMG[i.dataset.img]});</script>") if imgs else ""
    page = head + "\n".join(b if i == 0 else b.replace("<main ", "<main hidden ", 1) for i, b in enumerate(bodies)) + imgjs + \
        SWITCH_JS.replace("__DEF__", json.dumps(dict(lang=langs[0], view=a.view))) + "\n</body>"
    open(a.out, "w", encoding="utf-8").write(page); print(a.out, f"{len(page)/1e6:.2f} MB")

if __name__ == "__main__":
    main()
