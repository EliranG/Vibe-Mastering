#!/usr/bin/env python3
"""A release signature for the final folder: enough to re-render the same master later and to prove which file shipped.
  signature.py --source SRC.wav --final FINAL.wav --stats stats_final.json [--also FILE ...] --out "<final folder>/release-signature.json"
Holds: the sha256, length and loudness of the source and of every delivered file; the effective config of the render
(from master.py's stats, so no other file is needed); the stages that ran and what was pruned; the skill's version
(plugin.json when the skill runs from the plugin package, and the git commit when it is a checkout); the versions of the
Python libraries, ffmpeg and every VST3 plugin in the chain; and the exact command that renders it again."""
import sys, os, json, hashlib, argparse, platform, subprocess, datetime, plistlib, importlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mslib as L
from ffbin import FFMPEG

HERE = os.path.dirname(os.path.abspath(__file__)); SKILL = os.path.dirname(HERE)

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""): h.update(chunk)
    return h.hexdigest()

def audio(path, measure=True):
    import soundfile as sf
    info = sf.info(path); d = dict(name=os.path.basename(path), sha256=sha256(path), bytes=os.path.getsize(path),
                                    sample_rate=info.samplerate, frames=info.frames, format=info.subtype)
    if measure:
        x, sr = L.read_stereo(path); d.update(lufs=round(L.lufs(x, sr), 2), true_peak_dbtp=round(L.true_peak_db(x, sr), 2))
    return d

def skill_version():
    v = {}
    for up in (SKILL, os.path.dirname(os.path.dirname(SKILL))):              # skills/master-song -> plugin root
        pj = os.path.join(up, ".claude-plugin", "plugin.json")
        if os.path.exists(pj): v["plugin_version"] = json.load(open(pj)).get("version"); break
    r = subprocess.run(["git", "-C", SKILL, "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    if r.returncode == 0: v["git_commit"] = r.stdout.strip()
    h = hashlib.sha256()                                      # identifies the exact code even without a version or git
    for sub in ("scripts", "config"):
        for name in sorted(os.listdir(os.path.join(SKILL, sub))):
            if name.endswith((".py", ".json", ".sh")):
                h.update(f"{sub}/{name}".encode()); h.update(open(os.path.join(SKILL, sub, name), "rb").read())
    v["code_sha256"] = h.hexdigest(); v["path"] = SKILL
    return v

def bundle_version(path):
    try:
        info = plistlib.load(open(os.path.join(path, "Contents", "Info.plist"), "rb"))
        return info.get("CFBundleShortVersionString") or info.get("CFBundleVersion")
    except (OSError, plistlib.InvalidFileException): return None

def tools(cfg):
    t = dict(python=platform.python_version(), machine=f"{platform.system()} {platform.machine()}")
    for m in ("numpy", "scipy", "soundfile", "soxr", "pedalboard", "numba", "matchering", "pyloudnorm"):
        try: t[m] = importlib.import_module(m).__version__
        except Exception: pass
    r = subprocess.run([FFMPEG, "-version"], capture_output=True, text=True); t["ffmpeg"] = r.stdout.split("\n")[0] if r.returncode == 0 else None
    home = os.environ.get("MASTER_SONG_HOME", os.path.expanduser("~/.local/share/master-song"))
    plugins = {}
    if cfg.get("dyneq"): plugins["ZL Equalizer 2"] = bundle_version(os.path.join(home, "plugins", "ZL Equalizer 2.vst3"))
    if cfg.get("tape"): plugins["CHOWTapeModel"] = bundle_version(os.path.join(home, "plugins", "CHOWTapeModel.vst3"))
    for pc in cfg.get("user_plugins") or []: plugins[pc.get("label") or os.path.basename(pc["path"])] = bundle_version(pc["path"])
    if plugins: t["plugins"] = plugins
    return t

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--source", required=True); ap.add_argument("--final", required=True)
    ap.add_argument("--stats", required=True); ap.add_argument("--also", action="append", default=[]); ap.add_argument("--out", required=True)
    a = ap.parse_args(); st = json.load(open(a.stats)); cfg = st.get("cfg") or {}
    if not cfg: raise SystemExit("the stats have no 'cfg' - render with the current master.py so the config travels with them")
    sig = dict(created=datetime.datetime.now().astimezone().isoformat(timespec="seconds"), skill=skill_version(),
               source=audio(a.source), final=audio(a.final), delivered=[audio(p, measure=False) if p.lower().endswith((".wav", ".flac")) else
                                                                      dict(name=os.path.basename(p), sha256=sha256(p), bytes=os.path.getsize(p)) for p in a.also],
               render=dict(target_lufs=st.get("target_lufs"), lufs=st.get("lufs"), true_peak_dbtp=st.get("true_peak_dbtp"), chain_used=st.get("chain_used"),
                           pruned=st.get("pruned"), oversampling=st.get("oversampling"), health=st.get("health"), config=cfg),
               tools=tools(cfg),
               reproduce=("save render.config as config.json, then: python scripts/master.py \"<source>\" \"<out>.wav\" --config config.json "
                          "(the source must match source.sha256; the same versions give the same audio)"))
    json.dump(sig, open(a.out, "w"), ensure_ascii=False, indent=1)
    print(f"{a.out}: source {sig['source']['sha256'][:12]}..., final {sig['final']['sha256'][:12]}..., skill {sig['skill'].get('plugin_version') or sig['skill'].get('git_commit') or 'code ' + sig['skill']['code_sha256'][:12]}")

if __name__ == "__main__":
    main()
