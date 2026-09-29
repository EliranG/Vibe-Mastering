#!/usr/bin/env python3
"""Choose the chain for this song: only the tools its first listen asks for, and only the ones that prove they help.
  plan.py SONG --ears <work>/ears.json --out <work>/config.json [--plan <work>/plan.json] [--config draft.json]
          [--probe -10] [--no-audition]
--ears is the output of `ears.py listen`. --config is an optional draft holding the song's tonal EQ moves (decided per
song from the evidence, references/eq.md); plan.py adds or removes everything else and writes the final config.

How each stage is decided (references/chain.md section 8 has the rules, thresholds and the measurements behind them):
  sub-sonic high-pass   on only when there is real energy below 25 Hz relative to the bass, or DC
  mono bass (side HP)   on only when the bass has real stereo content below 80 Hz
  presence EQ           +1 dB at 3.2 kHz (mid) only when the 2 kHz octave sits 3 dB or more under 1 kHz
  dynamic EQ            one band per harsh bump that comes and goes (needs the ZL plugin; otherwise a static cut)
  static cut            a harsh bump that is there all the time gets a fixed cut instead
  fade-out              only on an abrupt end
  low-band compressor   a candidate only when the bass drives the peaks; glue a candidate unless the song is
                        already dense. A candidate is then auditioned: the chain runs with and without it at the probe
                        loudness (loudness-matched by construction) and it stays only if it makes that loudness
                        measurably cleaner - the bypass test an engineer does by ear.
  tape / Matchering     never automatic: they are taste, chosen by the user.
  the user's plugins    `user_plugins` in the draft config (plugins.py): a "tone" one is taste and stays as set; a
                        "dynamics" one (compressor, limiter) faces the same bypass test as the built-in compressors,
                        against the finished chain, and is dropped with its numbers when it does not help.
Everything left out is written to plan.json with the reason, so the report can say what was not used and why."""
import sys, os, json, argparse, copy, time, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import master as M, ears

KEEP_IF_LEVELER_DROPS = 5.0     # percentage points of leveler activity the stage must save at the probe loudness...
KEEP_IF_CLIP_DROPS = 3.0        # ...or dB of clipper residual...
KEEP_IF_DR_GAINS = 1.0          # ...or DR points it preserves - otherwise it is left out (judgement; chain.md section 8)
PRESENCE = {"type": "peak", "f": 3200, "g": 1.0, "q": 0.8, "ch": "mid"}

def zl_installed(): return os.path.isdir(os.path.join(M.PLUGINS, "ZL Equalizer 2.vst3"))

def bump_groups(freqs):
    """Adjacent third-octave bumps (e.g. 10 and 12.7 kHz) become one band between them."""
    groups = []
    for f in sorted(freqs):
        if groups and f/groups[-1][-1] < 2**(1/3)*1.05: groups[-1].append(f)
        else: groups.append([f])
    return groups

def audition(src, cfg, stage, probe, off=None):
    """Render the peak stage at the probe loudness with the stage on and off (2x oversampling, as predict.py).
    off(config) switches it off when setting config[stage] to None is not how (a plugin in a list)."""
    out = {}
    for on in (True, False):
        c = copy.deepcopy(cfg)
        if not on:
            if off: off(c)
            else: c[stage] = None
        st = {}; x, sr, n_in, _ = M.read_padded(src, c, st)
        u, ov = M.prepare(x, sr, c, st, OS=2); del x
        y = M.peak_stage(u, ov, n_in, c, probe, st, log=False)
        out["on" if on else "off"] = dict(leveler_active_pct=st["leveler_active_pct"], clip_residual_db=st["clip_residual_db"], dr=ears.dr_tt(y, sr),
                                          gr_p95_db=st.get(f"{stage}_gr_db", {}).get("p95"), reached=st["lufs"])
    d_lev = out["on"]["leveler_active_pct"] - out["off"]["leveler_active_pct"]
    d_clip = out["on"]["clip_residual_db"] - out["off"]["clip_residual_db"]
    d_dr = (out["on"]["dr"] or 0) - (out["off"]["dr"] or 0)
    healthy = (out["on"]["gr_p95_db"] or 0) <= 3
    keep = healthy and (d_lev <= -KEEP_IF_LEVELER_DROPS or d_clip <= -KEEP_IF_CLIP_DROPS or d_dr >= KEEP_IF_DR_GAINS)
    return keep, dict(probe_lufs=probe, **out, leveler_change_pts=round(d_lev, 1), clip_residual_change_db=round(d_clip, 1), dr_change=round(d_dr, 1))

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("src"); ap.add_argument("--ears", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--plan"); ap.add_argument("--config"); ap.add_argument("--probe", type=float)
    ap.add_argument("--no-audition", action="store_true")
    a = ap.parse_args(); t0 = time.time()
    E = json.load(open(a.ears)); m, F = E["measurements"], {f["id"]: f for f in E["findings"]}
    cfg = M.load_cfg(a.config, None); probe = a.probe if a.probe is not None else cfg["target_lufs"]
    if not a.config: cfg["eq"] = []                          # no draft: the tonal EQ starts neutral
    D = []                                                  # decisions: stage, used, why
    say = lambda stage, used, why, **kw: D.append(dict(stage=stage, used=used, why=why, **kw))

    # static decisions straight from the first listen
    if "subsonic" in F: cfg["hpf_hz"] = cfg.get("hpf_hz") or 25; say("hpf", True, F["subsonic"]["evidence"])
    else: cfg["hpf_hz"] = None; say("hpf", False, f"no real energy below 25 Hz ({m['sub25_re_bass_db']} dB re the bass)")
    eq = [b for b in (cfg.get("eq") or []) if not (b.get("type") == "hp" and b.get("ch") == "side")]
    if "stereo_bass" in F: eq.append({"type": "hp", "f": 100, "order": 2, "ch": "side"}); say("mono_bass", True, F["stereo_bass"]["evidence"])
    else: say("mono_bass", False, f"the bass is already mono enough: side vs mid below 80 Hz {m['side_minus_mid_below80_db']} dB")
    if "presence_dip" in F:
        if not any(b.get("type") == "peak" and 2500 <= b["f"] <= 4000 and b.get("g", 0) > 0 for b in eq):
            eq.append(dict(PRESENCE))
        say("presence_eq", True, F["presence_dip"]["evidence"])
    cfg["eq"] = eq
    bumps = [k for k in F if k.startswith("bump_")]
    dyn = [float(k.split("_")[1]) for k in bumps if F[k]["tool"] == "dyneq"]
    stat = [float(k.split("_")[1]) for k in bumps if F[k]["tool"] == "static_eq"]
    bands = []
    for g in bump_groups(dyn):
        fc = float(np.sqrt(g[0]*g[-1])); q = 2.5 if len(g) > 1 else 3.0
        ev = "; ".join(F[f"bump_{f:.0f}"]["evidence"] for f in g)
        if zl_installed():
            bands.append({"f": round(fc), "q": q, "ch": "stereo", "range_db": -3, "threshold": "auto", "pct": 60, "att_ms": 5, "rel_ms": 120})
            say("dynamic_eq", True, ev, f_hz=round(fc))
        else:
            stat += g; say("dynamic_eq", False, ev + " - the ZL plugin is not installed, so a static cut is used instead", f_hz=round(fc))
    cfg["dyneq"] = {"bands": bands} if bands else None
    for f in stat:
        med = m["hf_bump_time"].get(f"{f:.0f}", {}).get("median", 2.0)
        cfg["eq"].append({"type": "peak", "f": round(f), "g": -round(min(2.0, max(1.0, med)), 1), "q": 2.0, "ch": "stereo"})
        say("static_cut", True, F[f"bump_{f:.0f}"]["evidence"], f_hz=round(f))
    if not bumps: say("dynamic_eq", False, "the first listen found no harsh bump of 2 dB or more")
    cfg["fade_out_ms"] = 1000 if "abrupt_end" in F else 0
    say("fade_out", "abrupt_end" in F, F["abrupt_end"]["evidence"] if "abrupt_end" in F else f"the song ends cleanly (last 50 ms at {m['tail_peak_db']} dBFS)")

    # compressors: candidates first, then the bypass test
    dense = "already_dense" in F
    for stage, cand in (("lowcomp", "bass_drives_peaks" in F and not dense), ("glue", not dense)):
        base = cfg.get(stage) or M.load_cfg(None, None)[stage]
        if not cand:
            cfg[stage] = None
            if dense: why = f"the song is already dense - more compression would only squash it ({F['already_dense']['evidence']})"
            else: why = f"the bass does not drive the peaks ({m['bass_share_of_peaks_pct']}% of the loudest peaks come from below 120 Hz)"
            say(stage, False, why); continue
        cfg[stage] = base
        if a.no_audition: say(stage, True, "candidate kept without a bypass test (--no-audition)"); continue
        keep, ev = audition(a.src, cfg, stage, probe)
        if not keep: cfg[stage] = None
        say(stage, keep, (f"bypass test at {probe:g} LUFS, with it vs without: leveler {ev['on']['leveler_active_pct']}% vs {ev['off']['leveler_active_pct']}% "
                          f"of the time, clipper residual {ev['on']['clip_residual_db']} vs {ev['off']['clip_residual_db']} dB, DR {ev['on']['dr']} vs {ev['off']['dr']} - "
                          + ("it makes the loudness measurably cleaner or keeps more dynamics, so it stays" if keep else "no measurable benefit, so it stays out")), audition=ev)
    # plugins the user owns, tested against the finished chain
    for pc in list(cfg.get("user_plugins") or []):
        lab = pc.get("label") or os.path.basename(pc["path"])
        if pc.get("role") != "dynamics":
            say("user_plugin", True, "the user's own plugin, a taste choice: used as set", label=lab); continue
        if a.no_audition: say("user_plugin", True, "candidate kept without a bypass test (--no-audition)", label=lab); continue
        keep, ev = audition(a.src, cfg, "user_plugin", probe, off=lambda c, pc=pc: c.update(user_plugins=[q for q in c.get("user_plugins") or [] if q != pc]))
        if not keep: cfg["user_plugins"] = [q for q in cfg["user_plugins"] if q != pc]
        say("user_plugin", keep, (f"bypass test at {probe:g} LUFS, with it vs without: leveler {ev['on']['leveler_active_pct']}% vs {ev['off']['leveler_active_pct']}% "
                                  f"of the time, clipper residual {ev['on']['clip_residual_db']} vs {ev['off']['clip_residual_db']} dB, DR {ev['on']['dr']} vs {ev['off']['dr']} - "
                                  + ("it makes the loudness measurably cleaner or keeps more dynamics, so it stays" if keep else "no measurable benefit, so it stays out")), label=lab, audition=ev)
    if dense:
        cap = float(np.floor(m["lufs"]*2)/2)
        cfg["_target_cap_lufs"] = cap
        say("loudness_cap", True, f"the song is already limited at {m['lufs']} LUFS: going louder would only add limiting, so versions stay at or below {cap:g} LUFS")
    for stage in ("tape", "matchering"):
        if not cfg.get(stage): say(stage, False, "a taste choice: used only when the user asks for it")
    cfg["_plan"] = [f"{d['stage']}: {'on' if d['used'] else 'off'} - {d['why']}" for d in D]
    json.dump(cfg, open(a.out, "w"), ensure_ascii=False, indent=1)
    plan = dict(song=m["file"], probe_lufs=probe, decisions=D, seconds=round(time.time() - t0, 1))
    if a.plan: json.dump(plan, open(a.plan, "w"), ensure_ascii=False, indent=1)
    for d in D: print(f"  {'ON ' if d['used'] else 'off'}  {d['stage']:12s} {d['why']}")
    print(f"config -> {a.out} ({plan['seconds']} s)")

if __name__ == "__main__":
    main()
