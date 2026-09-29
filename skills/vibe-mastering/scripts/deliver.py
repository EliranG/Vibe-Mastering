#!/usr/bin/env python3
"""Distribution copies of a finished master.
  deliver.py MASTER.wav OUT.wav [--rate 44100] [--bits 16] [--ceiling -2] [--mp3 OUT.mp3] [--title T] [--artist A]
WAV: sample-rate conversion with soxr VHQ, true peak re-checked after SRC (SRC moves inter-sample peaks), TPDF dither.
MP3: LAME 320 kbps CBR, highest-quality algorithm, encoded from a float 44.1 kHz soxr conversion (no extra dither
or ffmpeg resampler); decoded true peak is reported. Tags (title/artist) go on every output; the audio is untouched."""
import sys, os, argparse, subprocess, tempfile, numpy as np, soundfile as sf
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mslib as L
from ffbin import FFMPEG

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("src"); ap.add_argument("dst", nargs="?")
    ap.add_argument("--rate", type=int, default=44100); ap.add_argument("--bits", type=int, default=16, choices=[16, 24])
    ap.add_argument("--ceiling", type=float, default=-2.0); ap.add_argument("--mp3")
    ap.add_argument("--title"); ap.add_argument("--artist"); a = ap.parse_args()
    import soxr
    x, sr = L.read_stereo(a.src)
    y = soxr.resample(x, sr, a.rate, quality="VHQ") if a.rate != sr else x
    tp = L.true_peak_db(y, a.rate)
    if tp > a.ceiling - 0.05: y = y*10**((a.ceiling - 0.05 - tp)/20)
    if a.dst:
        L.write_pcm(a.dst, y, a.rate, a.bits, seed=1); L.tag_file(a.dst, a.title, a.artist)
        z, _ = L.read_stereo(a.dst)
        print(f"{os.path.basename(a.dst)}: {a.bits}-bit {a.rate} Hz | TP after SRC {tp:.2f} -> {L.true_peak_db(z, a.rate):.2f} dBTP | "
              f"{L.lufs(z, a.rate):.2f} LUFS | {len(z)/a.rate:.3f} s")
    if a.mp3:
        with tempfile.TemporaryDirectory() as d:
            sf.write(f"{d}/f.wav", y, a.rate, subtype="FLOAT")
            cmd = [FFMPEG, "-v", "error", "-y", "-i", f"{d}/f.wav", "-c:a", "libmp3lame", "-b:a", "320k", "-compression_level", "0",
                   "-id3v2_version", "3", "-map_metadata", "-1", "-fflags", "+bitexact"]
            for k, v in (("title", a.title), ("artist", a.artist)):
                if v: cmd += ["-metadata", f"{k}={v}"]
            subprocess.run(cmd + [a.mp3], check=True)
            subprocess.run([FFMPEG, "-v", "error", "-y", "-i", a.mp3, "-c:a", "pcm_f32le", f"{d}/dec.wav"], check=True)
            z, zsr = sf.read(f"{d}/dec.wav", always_2d=True)
        print(f"{os.path.basename(a.mp3)}: MP3 320k CBR {a.rate} Hz | decoded TP {L.true_peak_db(z, zsr):.2f} dBTP | "
              f"{L.lufs(z, zsr):.2f} LUFS | overs >0 dBFS: {int((np.abs(z) > 1).sum())}")

if __name__ == "__main__":
    main()
