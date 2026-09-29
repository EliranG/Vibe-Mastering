"""Which ffmpeg the skill runs: $MASTER_SONG_FFMPEG if set, else the build bundled in the venv (imageio-ffmpeg: MP3,
Opus, Vorbis and, on macOS, AAC through AudioToolbox), else ffmpeg on the PATH. Bundling it means nobody has to
install ffmpeg by hand, and every machine encodes with the same codecs, so the codec QC is comparable."""
import os, shutil

def ffmpeg():
    if os.environ.get("MASTER_SONG_FFMPEG"): return os.environ["MASTER_SONG_FFMPEG"]
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg") or "ffmpeg"

FFMPEG = ffmpeg()
