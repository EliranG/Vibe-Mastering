#!/usr/bin/env python3
"""Plugins the user already owns (VST3), for the chain's `user_plugins` stage.
  plugins.py list [--grep TEXT]                       VST3 plugins on this machine, one line per plugin in each bundle
  plugins.py params PATH [--name NAME] [--grep TEXT]  its parameters: the name to set in the config, units, range, value now
  plugins.py try PATH --song SONG.wav [--name NAME] [--set param=value ...] [--seconds 20]
                                                      runs the loudest excerpt through it without its window: proves it
                                                      loads and runs here (a licence that needs its window fails now, not
                                                      mid-render) and reports the delay, polarity and level it adds
Every load runs in a child process with a time limit, because a plugin that waits for a dialog never returns.
VST3 only: Audio Units hung without a window in testing. In the config (master.py):
  "user_plugins": [{"path": ".../X.vst3", "name": null, "label": "My limiter", "role": "dynamics"|"tone",
                    "params": {"threshold_db": -3.0}}]
They run in order at the song's own rate, after the built-in optional stages and before the skill's own EQ,
compressors and peak control, which still guarantee the ceiling. plan.py puts a "dynamics" plugin through the same
bypass test as the built-in compressors; a "tone" plugin is the user's taste and stays as set."""
import sys, os, json, glob, argparse, subprocess, platform

HOME = os.environ.get("MASTER_SONG_HOME", os.path.expanduser("~/.local/share/master-song"))
FOLDERS = {"Darwin": ["/Library/Audio/Plug-Ins/VST3", "~/Library/Audio/Plug-Ins/VST3"],
           "Windows": [r"C:\Program Files\Common Files\VST3", r"C:\Program Files (x86)\Common Files\VST3"],
           "Linux": ["~/.vst3", "/usr/lib/vst3", "/usr/local/lib/vst3"]}.get(platform.system(), []) + [os.path.join(HOME, "plugins")]

def child(code, *args, timeout=40):
    """Run pedalboard code in a child process; returns its JSON result or {"error": ...}."""
    try:
        r = subprocess.run([sys.executable, "-c", code, *args], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"error": f"no answer within {timeout} s - the plugin may be waiting for a window or a licence dialog"}
    line = next((l for l in reversed(r.stdout.splitlines()) if l.startswith("{")), None)
    return json.loads(line) if line else {"error": (r.stderr.strip().splitlines() or ["no output"])[-1][:300]}

NAMES = """import sys, json, pedalboard
print(json.dumps({"names": pedalboard.VST3Plugin.get_plugin_names_for_file(sys.argv[1])}))"""

PARAMS = """import sys, json, pedalboard
p = pedalboard.load_plugin(sys.argv[1], plugin_name=sys.argv[2] or None, initialization_timeout=15)
out = []
for k, v in p.parameters.items():
    lo, hi, step = (list(v.range) + [None, None, None])[:3]
    vals = [] if isinstance(lo, (int, float)) else list(getattr(v, "valid_values", []) or [])
    out.append(dict(name=k, label=getattr(v, "label", None) or getattr(v, "name", ""), units=getattr(v, "units", ""),
                    min=lo, max=hi, step=step, now=getattr(v, "string_value", ""),
                    choices=vals if len(vals) <= 12 else [vals[0], "...", vals[-1], f"({len(vals)} steps)"]))
print(json.dumps({"plugin": p.name, "params": out}, default=str))"""

TRY = """import sys, json, os, numpy as np
sys.path.insert(0, sys.argv[5])
import mslib as L, pedalboard
from scipy.ndimage import uniform_filter1d
x, sr = L.read_stereo(sys.argv[3]); seg = int(min(float(sys.argv[4]), len(x)/sr)*sr)
e = uniform_filter1d(np.abs(x).mean(1), seg); c0 = int(np.clip(np.argmax(e) - seg//2, 0, len(x) - seg)); x = x[c0:c0+seg]
p = pedalboard.load_plugin(sys.argv[1], plugin_name=sys.argv[2] or None, parameter_values=json.loads(sys.argv[6]), initialization_timeout=15)
y = p(x.astype(np.float32), sr).astype(np.float64)
y2, lag, sign = L.align_to(x, y, sr)
print(json.dumps(dict(plugin=p.name, seconds=round(seg/sr, 1), lag_samples=lag, polarity=sign,
                      level_change_lu=round(L.lufs(y, sr) - L.lufs(x, sr), 2),
                      peak_change_db=round(L.true_peak_db(y, sr) - L.true_peak_db(x, sr), 2))))"""

def bundles():
    out = []
    for f in FOLDERS:
        out += sorted(glob.glob(os.path.join(os.path.expanduser(f), "**", "*.vst3"), recursive=True))
    return [b for b in dict.fromkeys(out) if not any(b.startswith(o + os.sep) for o in out if o != b)]

def value(s):
    try: return json.loads(s)
    except json.JSONDecodeError: return s

def main():
    ap = argparse.ArgumentParser(description="VST3 plugins the user owns"); sub = ap.add_subparsers(dest="cmd", required=True)
    l = sub.add_parser("list"); l.add_argument("--grep", default="")
    p = sub.add_parser("params"); p.add_argument("path"); p.add_argument("--name", default=""); p.add_argument("--grep", default="")
    t = sub.add_parser("try"); t.add_argument("path"); t.add_argument("--song", required=True); t.add_argument("--name", default="")
    t.add_argument("--set", action="append", default=[]); t.add_argument("--seconds", type=float, default=20)
    a = ap.parse_args()
    if a.cmd == "list":
        found = [b for b in bundles() if a.grep.lower() in b.lower()]
        if not found: print("no VST3 plugins found in: " + ", ".join(FOLDERS))
        for b in found:
            r = child(NAMES, b, timeout=30)
            names = r.get("names") or [os.path.basename(b)[:-5]]
            own = "the skill's own (free)" if os.sep + "master-song" + os.sep + "plugins" + os.sep in b else "yours"
            for n in names: print(f"{n}\t{own}\t{b}" + (f"\t({r['error']})" if "error" in r else ""))
        mine = [b for b in found if os.sep + "master-song" + os.sep + "plugins" + os.sep not in b]
        print(f"-> {len(mine)} plugin bundle(s) of the user's; offer them in the questions" if mine else "-> none of the user's own; say so in one line")
    elif a.cmd == "params":
        r = child(PARAMS, a.path, a.name)
        if "error" in r: raise SystemExit("could not load: " + r["error"])
        print(f"{r['plugin']}: {len(r['params'])} parameters")
        for q in r["params"]:
            if a.grep.lower() not in (q["name"] + " " + str(q["label"])).lower(): continue
            rng = f"{q['min']} .. {q['max']}" if isinstance(q["min"], (int, float)) else ("choices: " + ", ".join(map(str, q["choices"] or [])))
            print(f"  {q['name']:40s} {str(q['units'] or ''):12s} {rng:28s} now {q['now']}")
    else:
        params = {k: value(v) for k, v in (s.split("=", 1) for s in a.set)}
        r = child(TRY, a.path, a.name, a.song, str(a.seconds), os.path.dirname(os.path.abspath(__file__)), json.dumps(params), timeout=120)
        if "error" in r: raise SystemExit("did not run: " + r["error"])
        print(json.dumps(r, indent=1))

if __name__ == "__main__":
    main()
