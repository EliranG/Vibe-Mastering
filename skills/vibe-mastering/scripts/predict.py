#!/usr/bin/env python3
"""Predict, before rendering, how hard the peak stage works at each loudness target.
  predict.py SONG [--config cfg.json] [--set k=v ...] [--targets=-12,-11,-10,-9] [--os 2] [--json out.json]
(note the "=": a value starting with "-" is otherwise read as an option)
Runs the same chain code as master.py (prepare + peak_stage) once per target, at reduced oversampling, and reports
what each target would cost: reached loudness, leveler activity, clip residual, health flags. Accuracy against full
renders is recorded in references/chain.md; use it to choose which versions to render and which to recommend."""
import sys, os, json, time, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import master as M

_JOB = None
def _one(t):
    u, ov, n_in, cfg, comp = _JOB; s = dict(comp)
    M.peak_stage(u, ov, n_in, cfg, t, s, log=False)
    return dict(target=t, reached=s["lufs"], leveler_active_pct=s["leveler_active_pct"], leveler_gr_max_db=s["leveler_gr_max_db"],
                clip_residual_db=s["clip_residual_db"], limiter_gr_p90_db=s["limiter_gr_p90_db"], health=s["health"])

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("src"); ap.add_argument("--config"); ap.add_argument("--set", action="append")
    ap.add_argument("--targets", default="-12,-11,-10,-9"); ap.add_argument("--os", type=int, default=2); ap.add_argument("--json")
    a = ap.parse_args(); cfg = M.load_cfg(a.config, a.set); t0 = time.time(); st = {}
    x, sr, n_in, _ = M.read_padded(a.src, cfg, st)
    u, ov = M.prepare(x, sr, cfg, st, OS=a.os); del x
    global _JOB; _JOB = (u, ov, n_in, cfg, {k: st[k] for k in ("lowcomp_gr_db", "glue_gr_db") if k in st})
    targets = sorted(float(v) for v in a.targets.split(","))
    import multiprocessing as mp                                    # fork: workers share the prepared signal
    import numpy as np
    M.L.comp_gain(np.zeros(64), 1000.0, -20.0, 2.0, 6.0, 10.0, 30.0, 200.0); M.L.release_follow(np.zeros(8), 0.5)
    # ^ load the numba functions in the parent first: when no compressor ran here (lowcomp and glue both off), the first
    #   numba load happened inside the forked workers and deadlocked them (measured: 0% CPU after 7 min)
    with mp.get_context("fork").Pool(len(targets)) as pool: rows = pool.map(_one, targets)
    for r in rows:
        print(f"target {r['target']:6.1f} -> {r['reached']:6.2f} LUFS | leveler {r['leveler_active_pct']:5.1f}% (max {r['leveler_gr_max_db']:.1f} dB) | "
              f"clip residual {r['clip_residual_db']:6.1f} dB | {'clean' if not r['health'] else 'FLAGS: ' + '; '.join(h.split(' - ')[0] for h in r['health'])}", flush=True)
    clean = [r["target"] for r in rows if not r["health"]]
    rec = max(clean) if clean else None
    print(f"loudest clean target: {rec}  (oversampling {a.os}x, compressors: low p95 {st.get('lowcomp_gr_db', {}).get('p95')} / "
          f"glue p95 {st.get('glue_gr_db', {}).get('p95')} dB, {time.time()-t0:.0f} s)")
    if a.json: json.dump(dict(rows=rows, loudest_clean=rec, oversampling=a.os, compressors={k: st.get(k) for k in ("lowcomp_gr_db", "glue_gr_db")}),
                         open(a.json, "w"), ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))

if __name__ == "__main__":
    main()
