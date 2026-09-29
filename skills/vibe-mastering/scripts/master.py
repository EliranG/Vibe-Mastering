#!/usr/bin/env python3
"""Render one master.

  master.py IN.wav OUT.wav --config cfg.json [--set target_lufs=-12] [--stats out.json]

Signal flow (see references/chain.md):
  read -> normalize to input_norm_lufs
  -> [matchering]  reference match, base rate          (optional)
  -> [dyneq]       ZL Equalizer 2 dynamic bands        (optional)
  -> [tape]        CHOWTapeModel, polarity/latency fixed (optional)
  -> [user_plugins] VST3 plugins the user owns, in order, delay/polarity fixed (optional; plugins.py)
  -> 4x oversample -> HPF -> M/S EQ -> low-band comp -> glue comp
  -> gain -> leveling limiter -> soft clip -> true-peak limiter -> downsample
  -> TP trim -> fades -> TPDF dither -> 24-bit WAV at the source sample rate
"""
import sys, os, json, time, argparse, tempfile, numpy as np, soundfile as sf
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mslib as L
from scipy.signal import butter, sosfilt

PLUGINS = os.path.join(os.environ.get("MASTER_SONG_HOME", os.path.expanduser("~/.local/share/master-song")), "plugins")
HERE = os.path.dirname(os.path.abspath(__file__))

def load_cfg(path, sets):
    cfg = json.load(open(os.path.join(HERE, "..", "config", "default.json")))
    if path: deep_update(cfg, json.load(open(path)))
    for s in sets or []:
        k, v = s.split("=", 1); node = cfg; ks = k.split(".")
        for kk in ks[:-1]:
            if not isinstance(node.get(kk), dict): node[kk] = {}
            node = node[kk]
        try: node[ks[-1]] = json.loads(v)
        except json.JSONDecodeError: node[ks[-1]] = v          # plain strings, e.g. file paths
    mc = cfg.get("matchering")
    if mc and not (mc.get("reference") and os.path.exists(mc["reference"])):
        raise SystemExit(f"matchering.reference is not an existing file: {mc.get('reference')!r}")
    return cfg

def deep_update(a, b):
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(a.get(k), dict): deep_update(a[k], v)
        else: a[k] = v

def renorm(x, sr, target):
    g = target - L.lufs(x, sr); return x*10**(g/20), g

# ---------------- optional stages (base rate) ----------------
def stage_matchering(x, sr, mc, st):
    import matchering as mg, soxr
    ref, rsr = L.read_stereo(mc["reference"])
    with tempfile.TemporaryDirectory() as d:
        t44 = soxr.resample(x, sr, 44100, quality="VHQ") if sr != 44100 else x
        r44 = soxr.resample(ref, rsr, 44100, quality="VHQ") if rsr != 44100 else ref
        sf.write(f"{d}/t.wav", t44, 44100, subtype="FLOAT"); sf.write(f"{d}/r.wav", r44, 44100, subtype="FLOAT")
        mg.process(target=f"{d}/t.wav", reference=f"{d}/r.wav",
                   results=[mg.Result(f"{d}/o.wav", "FLOAT", use_limiter=False, normalize=False)])
        y44, _ = sf.read(f"{d}/o.wav", always_2d=True)
    y = soxr.resample(y44, 44100, sr, quality="VHQ") if sr != 44100 else y44
    y = np.pad(y, ((0, max(0, len(x)-len(y))), (0, 0)))[:len(x)]
    y, lag, sign = L.align_to(x, y, sr)
    st["matchering"] = dict(reference=os.path.basename(mc["reference"]), ref_lufs=round(L.lufs(ref, rsr), 2), lag=lag, polarity=sign)
    return y

def _band_level(x, sr, f, q, ch):
    s = {"mid": (x[:,0]+x[:,1])/2, "side": (x[:,0]-x[:,1])/2}.get(ch, x.mean(1))
    bw = 2*np.arcsinh(1/(2*q))/np.log(2); lo, hi = f/2**(bw/2), min(f*2**(bw/2), 0.45*sr)
    b = sosfilt(butter(2, [lo, hi], "bandpass", fs=sr, output="sos"), s)
    w = int(0.05*sr); from scipy.ndimage import uniform_filter1d
    return 10*np.log10(uniform_filter1d(b**2, w) + 1e-12)

def stage_dyneq(x, sr, dc, st):
    import pedalboard
    zl = pedalboard.load_plugin(f"{PLUGINS}/ZL Equalizer 2.vst3")
    zl.filter_structure_filter_structure = dc.get("structure", "Minimum Phase")
    info = []
    for i, b in enumerate(dc["bands"]):
        lv = _band_level(x, sr, b["f"], b.get("q", 1.0), b.get("ch", "mid"))
        thr = b["threshold"] if isinstance(b.get("threshold"), (int, float)) else float(np.percentile(lv, b.get("pct", 85)))
        for k, v in {f"filter_status{i}_filter_status": "On", f"filter_type{i}_filter_type": "Peak",
                     f"lrmode{i}_lrmode": {"mid": "Mid", "side": "Side"}.get(b.get("ch", "mid"), "Stereo"),
                     f"freq{i}_freq": float(b["f"]), f"q{i}_q": float(b.get("q", 1.0)), f"gain{i}_gain": 0.0,
                     f"target_gain{i}_target_gain": float(b["range_db"]), f"dynamic_on{i}_dynamic_on": True,
                     f"threshold_db_{i}_threshold_db": round(max(-80.0, min(0.0, thr)), 1),
                     f"knee_width{i}_knee_width": float(b.get("knee", 6.0)), f"attack{i}_attack": float(b.get("att_ms", 5.0)),
                     f"release{i}_release": float(b.get("rel_ms", 120.0)),
                     f"side_freq{i}_side_freq": float(b["f"]), f"side_q{i}_side_q": float(b.get("q", 1.0))}.items():
            setattr(zl, k, v)
        info.append(dict(f=b["f"], q=b.get("q", 1.0), ch=b.get("ch", "mid"), range_db=b["range_db"], threshold_db=round(thr, 1), lv=lv, pct=b.get("pct", 85)))
    y = zl(x.astype(np.float32), sr).astype(np.float64)
    y, lag, sign = L.align_to(x, y, sr)
    for b in info:  # measured effect: band level change when the band is loud vs quiet
        lv, ly = b.pop("lv"), _band_level(y, sr, b["f"], b["q"], b["ch"])
        d = ly - lv; b["change_when_loud_db"] = round(float(np.median(d[lv > b["threshold_db"]])), 2)
        b["change_when_quiet_db"] = round(float(np.median(d[lv < np.percentile(lv, 50)])), 2)
    st["dyneq"] = dict(bands=info, lag=lag, polarity=sign)
    return y

def stage_tape(x, sr, tc, st):
    import pedalboard
    ct = pedalboard.load_plugin(f"{PLUGINS}/CHOWTapeModel.vst3")
    osf = float(tc.get("oversampling", 4))
    for k, v in dict(wow_flutter_on_off=False, degrade_on_off=False, chew_on_off=False, loss_on_off=bool(tc.get("loss", False)),
                     tone_on_off=False, compression_on_off=False, input_filters_on_off=False, tape_on_off=True,
                     tape_mode=tc.get("mode", "STN"), oversampling_factor=osf, oversampling_factor_render=osf,
                     oversampling_mode="Linear Phase", oversampling_mode_render="Linear Phase",
                     tape_drive=float(tc.get("drive", 0.3)), tape_saturation=float(tc.get("saturation", 0.3)),
                     tape_bias=float(tc.get("bias", 0.5)), dry_wet=100.0).items():
        setattr(ct, k, v)
    y = ct(x.astype(np.float32), sr).astype(np.float64)
    y, lag, sign = L.align_to(x, y, sr)                    # the model rotates bass phase; align on content above 200 Hz
    st["tape"] = dict(drive=tc.get("drive", 0.3), saturation=tc.get("saturation", 0.3), lag=lag, polarity=sign,
                      level_change_before_makeup_lu=round(L.lufs(y, sr) - L.lufs(x, sr), 2))
    return y

def stage_user_plugin(x, sr, pc, st):
    """A VST3 plugin the user owns (plugins.py lists it, its parameters, and proves it runs without its window).
    Delay and polarity it adds are measured against its input and undone, as for tape."""
    import pedalboard
    p = pedalboard.load_plugin(pc["path"], plugin_name=pc.get("name") or None, parameter_values=pc.get("params") or {},
                               initialization_timeout=15)
    y = p(x.astype(np.float32), sr).astype(np.float64)
    y, lag, sign = L.align_to(x, y, sr)
    st.setdefault("user_plugins", []).append(dict(label=pc.get("label") or p.name, role=pc.get("role", "tone"), lag=lag, polarity=sign,
                                                 level_change_before_makeup_lu=round(L.lufs(y, sr) - L.lufs(x, sr), 2)))
    return y

# ---------------- main chain ----------------
def prepare(x, sr, cfg, st, OS=None):
    """Everything before the peak stage: normalize, optional stages, oversample, HPF, M/S EQ, low-band comp, glue.
    Returns (u, ov): the oversampled signal and its Oversampler. OS=1 is the fast preview used by predict.py."""
    norm = cfg["input_norm_lufs"]; x, g0 = renorm(x, sr, norm); st["input_norm_gain_db"] = round(g0, 2)
    for name, fn in (("matchering", stage_matchering), ("dyneq", stage_dyneq), ("tape", stage_tape)):
        if cfg.get(name):
            t = time.time(); x = fn(x, sr, cfg[name], st); x, _ = renorm(x, sr, norm)
            st[name]["seconds"] = round(time.time()-t, 1)
    for pc in cfg.get("user_plugins") or []:
        t = time.time(); x = stage_user_plugin(x, sr, pc, st); x, _ = renorm(x, sr, norm)
        st["user_plugins"][-1]["seconds"] = round(time.time()-t, 1)
    ov = L.Oversampler(sr, OS); fs = ov.osr; u = ov.up(x); del x
    if cfg.get("hpf_hz"): u = L.chain(u, butter(2, cfg["hpf_hz"], "hp", fs=fs, output="sos"))
    u = L.apply_ms_eq(u, fs, cfg.get("eq"))
    lc = cfg["lowcomp"]
    if lc:
        lp = butter(2, lc["xover_hz"], "lp", fs=fs, output="sos"); low = L.chain(u, lp, lp)   # LR4
        gl = L.comp_gain(np.max(np.abs(low), 1), fs, lc["thr"], lc["ratio"], lc["knee"], lc["rms_ms"], lc["att_ms"], lc["rel_ms"])
        u += (10**(gl/20)-1)[:, None]*low; del low
        st["lowcomp_gr_db"] = dict(max=round(-gl.min(), 2), p95=round(-np.percentile(gl, 5), 2), median=round(-np.median(gl), 2))
    gc = cfg["glue"]
    if gc:
        sc = L.chain(u, butter(2, gc["sc_hpf_hz"], "hp", fs=fs, output="sos"))
        gg = L.comp_gain(np.max(np.abs(sc), 1), fs, gc["thr"], gc["ratio"], gc["knee"], gc["rms_ms"], gc["att_ms"], gc["rel_ms"]); del sc
        u *= 10**(gg/20)[:, None]
        st["glue_gr_db"] = dict(max=round(-gg.min(), 2), p95=round(-np.percentile(gg, 5), 2), median=round(-np.median(gg), 2))
    return u, ov

def peak_stage(u, ov, n_in, cfg, target, st, log=True, use=("leveler", "clipper")):
    """Leveling limiter -> soft clip -> true-peak limiter, with the loudness search. Does not modify u.
    `use` lists the optional stages in front of the final limiter; the final true-peak limiter always runs."""
    sr, fs = ov.sr, ov.osr; pk = cfg["peak"]; ceil_tp = cfg["ceiling_dbtp"]
    lim_ceil = 10**((ceil_tp - pk["os_margin_db"])/20)
    c = lim_ceil*10**(pk["clip_above_lim_db"]/20); lev_ceil = c*10**(pk["clip_max_depth_db"]/20)
    def finish(pre_db):
        if "leveler" in use: v, grA, DA = L.limiter(u*10**(pre_db/20), fs, lev_ceil, pk["lev_lookahead_ms"], pk["lev_release_ms"])
        else: v, grA, DA = u*10**(pre_db/20), np.zeros(1), 0
        if "clipper" in use: v, res, knee_pct = L.soft_clip(v, c)
        else: res, knee_pct = None, 0.0
        y, grC, DC = L.limiter(v, fs, lim_ceil, pk["lim_lookahead_ms"], pk["lim_release_ms"])
        y = ov.down(y)[(DA+DC)//ov.OS:][:n_in]
        tp = L.true_peak_db(y, sr)                           # downsampling can add a little; trim inside the loop
        trim = min(0.0, ceil_tp - 0.05 - tp); y *= 10**(trim/20)
        return y, dict(tp_trim_db=round(trim, 2), leveler_gr_max_db=round(float(grA.max()), 2),
                       leveler_active_pct=round(float(100*(grA > 0.1).mean()), 1),
                       clip_residual_db=None if res is None else round(res, 1), clip_knee_pct=round(knee_pct, 2),
                       limiter_gr_max_db=round(float(grC.max()), 2), limiter_gr_p90_db=round(float(np.percentile(grC, 90)), 2),
                       limiter_over1db_pct=round(float(100*(grC > 1).mean()), 1))
    # Loudness search: secant steps on the measured gain->LUFS slope. When the peak stage saturates the slope falls
    # towards 0 (more gain, almost no more loudness); stop there and report the target as unreachable.
    pre = target - L.lufs(ov.down(u)[:n_in], sr); hist = []
    for it in range(8):
        y, fst = finish(pre); Lo = L.lufs(y, sr); hist.append((pre, Lo))
        if log: print(f"  iter {it}: gain {pre:+.2f} dB -> {Lo:.2f} LUFS", file=sys.stderr, flush=True)
        if abs(Lo - target) < 0.05: break
        slope = 1.0
        if len(hist) > 1 and abs(hist[-1][0] - hist[-2][0]) > 1e-3:
            slope = (hist[-1][1] - hist[-2][1]) / (hist[-1][0] - hist[-2][0])
        if slope < 0.25 and Lo < target: break                 # saturated: extra gain only adds distortion
        pre += (target - Lo) / min(1.0, max(slope, 0.25))
    best = min(range(len(hist)), key=lambda i: abs(hist[i][1] - target))
    if best != len(hist) - 1: pre = hist[best][0]; y, fst = finish(pre)   # keep the closest render, report its gain
    Lf = L.lufs(y, sr)
    st.update(fst); st.update(gain_into_peak_stage_db=round(pre, 2), lufs=round(Lf, 2), target_lufs=target,
                              target_reached=bool(abs(Lf - target) < 0.2),
                              loudness_search=[[round(g, 2), round(l, 2)] for g, l in hist])
    st["peak_stages_used"] = [s for s in ("leveler", "clipper") if s in use] + ["limiter"]
    st["health"] = health(st)
    return y

def prune_idle(u, ov, n_in, cfg, target, st, y):
    """An engineer does not leave a processor in the chain that does nothing. When the leveler or the clipper barely
    worked at this loudness, render again without it and keep that version only if it still reaches the target cleanly
    AND the final limiter does not have to take over real work (its deepest reduction may grow by at most 1 dB). The
    clipper exists to shave short transients more cleanly than a limiter: removing one that shaved a few peaks by
    several dB and handing them to the limiter is not pruning (measured: limiter max 1.39 -> 3.6-4.1 dB)."""
    lev_idle = st["leveler_active_pct"] < 1.0 and st["leveler_gr_max_db"] < 1.0
    clip_idle = st["clip_residual_db"] is not None and st["clip_residual_db"] < -45
    tries = [t for t in ([["leveler", "clipper"]] if lev_idle and clip_idle else []) + ([["leveler"]] if lev_idle else []) +
             ([["clipper"]] if clip_idle and not lev_idle else [])]
    for idle in tries:
        s2 = {k: v for k, v in st.items() if k.endswith("_gr_db") or k in ("source", "input_norm_gain_db", "dyneq", "tape", "matchering", "user_plugins")}
        y2 = peak_stage(u, ov, n_in, cfg, target, s2, log=False, use=tuple(s for s in ("leveler", "clipper") if s not in idle))
        more = s2["limiter_gr_max_db"] - st["limiter_gr_max_db"]
        if s2["target_reached"] and not s2["health"] and more <= 1.0:
            s2["pruned"] = dict(stages=idle, why=f"idle at {target:g} LUFS: leveler {st['leveler_active_pct']}% active (max {st['leveler_gr_max_db']} dB), "
                                                   f"clipper residual {st['clip_residual_db']} dB; without them the final limiter works {more:+.2f} dB deeper",
                                leveler_active_pct=st["leveler_active_pct"], leveler_gr_max_db=st["leveler_gr_max_db"],
                                clip_residual_db=st["clip_residual_db"], limiter_change_db=round(more, 2))
            return y2, s2
        st.setdefault("prune_rejected", []).append(dict(stages=idle, limiter_max_change_db=round(more, 2),
                                                        reason="the final limiter would have to take over their work" if more > 1.0 else "target not reached cleanly"))
    return y, st

def health(st):
    return [w for w, bad in [
        ("target loudness not reached - the chain is pushing back; pick a quieter target", not st["target_reached"]),
        ("leveler active >50% of the time - audibly squashed", st["leveler_active_pct"] > 50),
        ("clip residual above -30 dB - distortion may be audible", (st["clip_residual_db"] if st["clip_residual_db"] is not None else -99) > -30),
        ("glue compressor p95 >3 dB - heavy for mastering", st.get("glue_gr_db", {}).get("p95", 0) > 3),
        ("low-band compressor p95 >3 dB - bass may pump", st.get("lowcomp_gr_db", {}).get("p95", 0) > 3)] if bad]

def read_padded(src, cfg, st):
    x, sr = L.read_stereo(src); n_in = len(x)
    st["source"] = dict(sr=sr, seconds=round(n_in/sr, 2), lufs=round(L.lufs(x, sr), 2))
    end_peak = 20*np.log10(np.abs(x[-int(0.05*sr):]).max() + 1e-12)
    fade_out_ms = cfg["fade_out_ms"] if cfg["fade_out_ms"] != "auto" else (1000 if end_peak > -50 else 0)
    x = np.concatenate([x, np.zeros((int(0.25*sr), 2))])  # room for plugin + look-ahead latency
    return x, sr, n_in, fade_out_ms

def dumps(st): return json.dumps(st, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("src"); ap.add_argument("dst")
    ap.add_argument("--config"); ap.add_argument("--set", action="append"); ap.add_argument("--stats")
    a = ap.parse_args(); cfg = load_cfg(a.config, a.set); t_start = time.time(); st = {}
    x, sr, n_in, fade_out_ms = read_padded(a.src, cfg, st)
    u, ov = prepare(x, sr, cfg, st); del x
    y = peak_stage(u, ov, n_in, cfg, cfg["target_lufs"], st)
    if cfg["peak"].get("prune_idle", True): y, st = prune_idle(u, ov, n_in, cfg, cfg["target_lufs"], st, y)
    st["chain_used"] = ([] if not cfg.get("matchering") else ["matchering"]) + ([] if not cfg.get("dyneq") else ["dynamic EQ"]) + \
        ([] if not cfg.get("tape") else ["tape"]) + [f"plugin: {pc.get('label') or os.path.basename(pc['path'])}" for pc in cfg.get("user_plugins") or []] + \
        ([f"high-pass {cfg['hpf_hz']} Hz"] if cfg.get("hpf_hz") else []) + \
        [f"EQ: {len(cfg.get('eq') or [])} band(s)"] + [n for n, k in (("low-band compressor", "lowcomp"), ("glue compressor", "glue")) if cfg.get(k)] + \
        st["peak_stages_used"]
    fi = int(cfg["fade_in_ms"]*1e-3*sr); fo = int(fade_out_ms*1e-3*sr)
    if fi: y[:fi] *= (np.sin(np.linspace(0, np.pi/2, fi))**2)[:, None]
    if fo: y[-fo:] *= np.cos(np.linspace(0, np.pi/2, fo))[:, None]
    L.write_pcm(a.dst, y, sr, 24)
    st.update(lufs=round(L.lufs(y, sr), 2), true_peak_dbtp=round(L.true_peak_db(y, sr), 2), fade_out_ms=fade_out_ms,
              oversampling=ov.OS, fir_taps=len(ov.h), seconds=round(time.time()-t_start, 1))
    st["target_reached"] = bool(abs(st["lufs"] - cfg["target_lufs"]) < 0.2); st["health"] = health(st)
    st["cfg"] = {k: v for k, v in cfg.items() if k != "_about"}
    if a.stats: open(a.stats, "w").write(dumps(st))
    # one line for the conversation; the full stats are in --stats (explain.py prints them as a chain)
    print(f"{os.path.basename(a.dst)}: {st['lufs']} LUFS, TP {st['true_peak_dbtp']} dBTP, limiter max {st['limiter_gr_max_db']} dB, "
          f"ran: {', '.join(st['chain_used'])}" + (f", pruned: {', '.join(st['pruned']['stages'])}" if st.get("pruned") else "") +
          (" | HEALTH: " + "; ".join(st["health"]) if st["health"] else " | health ok"))
    if not a.stats: print(dumps(st))

if __name__ == "__main__":
    main()
