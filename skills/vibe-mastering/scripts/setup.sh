#!/usr/bin/env bash
# master-song environment check / install. Free and local except --install-plugins (downloads from GitHub).
#   setup.sh                    check; create the Python venv if missing (PyPI only)
#   setup.sh --install-plugins  ALSO download + verify + extract the two open-source VST3s (macOS only).
#                               Downloading needs the user's explicit OK first (file names/sizes below).
# Everything lives under $MASTER_SONG_HOME (default ~/.local/share/master-song); nothing is installed system-wide.
set -u
B="${MASTER_SONG_HOME:-$HOME/.local/share/master-song}"; PY="$B/venv/bin/python"; ok=1
PKGS="numpy scipy numba pedalboard pyloudnorm soundfile soxr matchering mutagen matplotlib mosqito imageio-ffmpeg"
mkdir -p "$B/plugins" "$B/downloads"

if [[ ! -x "$PY" ]]; then
  echo "creating venv at $B/venv (PyPI: $PKGS)"
  if command -v uv >/dev/null 2>&1; then                      # tested path: uv with Python 3.12
    { uv venv -q --python 3.12 "$B/venv" && uv pip install -q --python "$PY" $PKGS; } || ok=0
  else                                                         # fallback: the newest local Python 3.10+
    base=""
    for c in python3.12 python3.11 python3.10 python3; do
      if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then base="$c"; break; fi
    done
    if [[ -z "$base" ]]; then
      echo "python venv: needs uv (https://docs.astral.sh/uv/) or Python 3.10+ (3.12 is the tested version)"; ok=0
    else
      echo "  uv not found; using $base ($("$base" -c 'import sys; print(sys.version.split()[0])'))"
      { "$base" -m venv "$B/venv" && "$PY" -m pip install -q --upgrade pip && "$PY" -m pip install -q $PKGS; } || ok=0
    fi
  fi
fi
if [[ -x "$PY" ]] && ! "$PY" -c "import imageio_ffmpeg" 2>/dev/null; then   # venvs made before ffmpeg was bundled
  echo "adding the bundled ffmpeg to the venv (PyPI: imageio-ffmpeg)"
  if command -v uv >/dev/null 2>&1; then uv pip install -q --python "$PY" imageio-ffmpeg || ok=0
  else "$PY" -m pip install -q imageio-ffmpeg || ok=0; fi
fi
"$PY" -c "import numpy, scipy, numba, pedalboard, pyloudnorm, soundfile, soxr, matchering, mutagen, matplotlib, mosqito, imageio_ffmpeg" 2>/dev/null \
  && echo "python venv: OK ($PY)" || { echo "python venv: BROKEN"; ok=0; }

# ffmpeg comes with the venv (imageio-ffmpeg); scripts/ffbin.py picks the same binary: $MASTER_SONG_FFMPEG, bundled, PATH
FF="${MASTER_SONG_FFMPEG:-$("$PY" -c 'import imageio_ffmpeg as f; print(f.get_ffmpeg_exe())' 2>/dev/null)}"
[[ -n "$FF" && -x "$FF" ]] || FF="$(command -v ffmpeg || true)"
if [[ -n "$FF" && -x "$FF" ]]; then
  echo "ffmpeg: OK ($FF)"
  for enc in aac_at libvorbis libopus libmp3lame; do
    "$FF" -hide_banner -encoders 2>/dev/null | grep -q " $enc " && echo "ffmpeg encoder $enc: OK" || echo "ffmpeg encoder $enc: MISSING (codec QC skips it)"
  done
else
  echo "ffmpeg: MISSING (needed for tagging, MP3 delivery and codec QC)"; ok=0
fi

install_pkg() {  # $1 url  $2 file  $3 sha256  $4 path of the .vst3 inside the expanded pkg
  local f="$B/downloads/$2" m x
  [[ -f "$f" ]] || curl -fsSL -o "$f" "$1" || { echo "  download failed: $2"; return 1; }
  [[ "$(shasum -a 256 "$f" | cut -d' ' -f1)" == "$3" ]] || { echo "  sha256 mismatch for $2 - not installing"; rm -f "$f"; return 1; }
  m="$(mktemp -d)"; x="$(mktemp -d)"
  hdiutil attach -nobrowse -readonly -mountpoint "$m" "$f" >/dev/null || return 1
  pkgutil --expand-full "$m"/*.pkg "$x/exp"; hdiutil detach "$m" -quiet
  cp -R "$x/exp/$4" "$B/plugins/" && echo "  installed $(basename "$4")"; rm -rf "$x"
}
if [[ " $* " == *" --install-plugins "* ]]; then
  if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "plugins: the automatic install is macOS-only; the tape and dynamic EQ stages are not available here"
  else
    [[ -d "$B/plugins/CHOWTapeModel.vst3" ]] || install_pkg \
      https://github.com/jatinchowdhury18/AnalogTapeModel/releases/download/v2.11.4/ChowTapeModel-Mac-2.11.4.dmg \
      ChowTapeModel-Mac-2.11.4.dmg 9b37e2b6cb6c0a839ee9c65e1a958834ca647b3edfc4bd144115c483b4d64f82 \
      'VST3.pkg/Payload/Library/Audio/Plug-Ins/VST3/CHOWTapeModel.vst3'
    if [[ "$(uname -m)" == "arm64" ]]; then
      [[ -d "$B/plugins/ZL Equalizer 2.vst3" ]] || install_pkg \
        https://github.com/ZL-Audio/ZLEqualizer/releases/download/1.4.0/ZL.Equalizer.2-1.4.0-macOS-arm64.dmg \
        ZL.Equalizer.2-1.4.0-macOS-arm64.dmg 15e8a2d951b446ed7d39ffeeb7b83a2fd0b41de95f0f1e0b84b198cb1ddc1bd9 \
        'ZL_Equalizer_2.vst3.pkg/Payload/ZL Equalizer 2.vst3'
    else
      echo "  ZL Equalizer: the pinned build is for Apple silicon only; the dynamic EQ stage is not available on this Mac"
    fi
  fi
fi
for p in "CHOWTapeModel.vst3" "ZL Equalizer 2.vst3"; do
  [[ -d "$B/plugins/$p" ]] && echo "plugin $p: OK" || echo "plugin $p: not installed (optional; macOS: needs --install-plugins with the user's OK: ChowTapeModel-Mac-2.11.4.dmg 27 MB, ZL.Equalizer.2-1.4.0-macOS-arm64.dmg 11 MB, both GitHub releases)"
done
[[ $ok == 1 ]] && echo "READY" || { echo "NOT READY"; exit 1; }
