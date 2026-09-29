"""Shared DSP for the master-song skill: HQ oversampling, RBJ biquads, compressors, look-ahead limiter,
loudness / true-peak / LRA measurement. Everything runs in float64."""
import os, numpy as np, soundfile as sf, pyloudnorm as pyln
from scipy.signal import sosfilt, butter, resample_poly, firwin, kaiserord
from scipy.ndimage import minimum_filter1d, uniform_filter1d
from numba import njit
from ffbin import FFMPEG

# ---------------- I/O ----------------
def read_stereo(path):
    x, sr = sf.read(path, always_2d=True)
    x = x.astype(np.float64)
    if x.shape[1] == 1: x = np.repeat(x, 2, 1)
    elif x.shape[1] > 2: x = x[:, :2]
    return x, sr

def write_pcm(path, y, sr, bits=24, seed=0):
    """TPDF dither at the target word length, then write PCM."""
    lsb = 1 / 2**(bits-1); rng = np.random.default_rng(seed)
    y = y + (rng.random(y.shape) - rng.random(y.shape)) * lsb
    sf.write(path, np.clip(y, -1, 1-lsb), sr, subtype=f'PCM_{bits}')

# ---------------- HQ oversampling ----------------
def os_factor(sr): return 4 if sr <= 50000 else 2

def hq_filter(sr, OS):
    """Linear-phase anti-image/anti-alias FIR, >=140 dB rejection from the base Nyquist."""
    osr = sr*OS
    passband = 21500 if sr == 48000 else (sr/2 - 2050 if sr < 50000 else 0.9*sr/2)
    ntaps, beta = kaiserord(140, (sr/2 - passband)/(osr/2)); ntaps |= 1
    return firwin(ntaps, (passband + sr/2)/2, window=('kaiser', beta), fs=osr)

class Oversampler:
    def __init__(self, sr, OS=None):
        self.sr, self.OS = sr, OS or os_factor(sr); self.osr = sr*self.OS
        self.h = hq_filter(sr, self.OS) if self.OS > 1 else np.ones(1)
    def up(self, x): return resample_poly(x, self.OS, 1, axis=0, window=self.h) if self.OS > 1 else x.copy()
    def down(self, x): return resample_poly(x, 1, self.OS, axis=0, window=self.h) if self.OS > 1 else x.copy()

# ---------------- measurement ----------------
def lufs(x, sr): return pyln.Meter(sr).integrated_loudness(x)

def true_peak_db(x, sr):
    ov = Oversampler(sr, 4)
    return 20*np.log10(np.abs(ov.up(x)).max() + 1e-12)

def kweighted_blocks(x, sr, win, hop):
    from scipy.signal import lfilter
    m = pyln.Meter(sr); y = x.copy()
    # filter along time (axis 0); pyloudnorm's apply_filter uses lfilter's default axis=-1 = channels
    for f in m._filters.values(): y = f.passband_gain * lfilter(f.b, f.a, y, axis=0)
    n, h = int(win*sr), int(hop*sr)
    c = np.cumsum(np.concatenate([np.zeros((1, y.shape[1])), y**2]), 0)
    idx = np.arange(0, len(y)-n, h)
    ms = ((c[idx+n] - c[idx]) / n).sum(1)
    return -0.691 + 10*np.log10(ms + 1e-20)

def lra(x, sr):
    """EBU Tech 3342 loudness range (3 s windows, abs gate -70, rel gate -20 LU, 10th-95th pct)."""
    st = kweighted_blocks(x, sr, 3.0, 0.1); st = st[st > -70]
    if len(st) < 2: return 0.0
    rel = 10*np.log10(np.mean(10**(st/10))) - 20; st = st[st > rel]
    return float(np.percentile(st, 95) - np.percentile(st, 10))

# ---------------- filters (RBJ cookbook, designed at the processing rate) ----------------
def _norm(b, a): s = np.array([list(b)+list(a)], float); return s / s[0, 3]
def peak(fs, f0, g, q):
    A=10**(g/40); w=2*np.pi*f0/fs; al=np.sin(w)/(2*q); c=np.cos(w)
    return _norm([1+al*A, -2*c, 1-al*A], [1+al/A, -2*c, 1-al/A])
def shelf(fs, f0, g, high, S=0.7):
    A=10**(g/40); w=2*np.pi*f0/fs; c=np.cos(w); al=np.sin(w)/2*np.sqrt((A+1/A)*(1/S-1)+2); sA=2*np.sqrt(A)*al
    if high: return _norm([A*((A+1)+(A-1)*c+sA), -2*A*((A-1)+(A+1)*c), A*((A+1)+(A-1)*c-sA)],
                          [(A+1)-(A-1)*c+sA, 2*((A-1)-(A+1)*c), (A+1)-(A-1)*c-sA])
    return _norm([A*((A+1)-(A-1)*c+sA), 2*A*((A-1)-(A+1)*c), A*((A+1)-(A-1)*c-sA)],
                 [(A+1)+(A-1)*c+sA, -2*((A-1)+(A+1)*c), (A+1)+(A-1)*c-sA])
def band_sos(fs, band):
    t = band['type']
    if t == 'peak': return peak(fs, band['f'], band['g'], band.get('q', 0.8))
    if t == 'highshelf': return shelf(fs, band['f'], band['g'], True, band.get('s', 0.7))
    if t == 'lowshelf': return shelf(fs, band['f'], band['g'], False, band.get('s', 0.7))
    if t in ('hp', 'lp'): return butter(band.get('order', 2), band['f'], 'high' if t == 'hp' else 'low', fs=fs, output='sos')
    raise ValueError(f"unknown EQ band type {t}")
def chain(sig, *soss):
    for s in soss: sig = sosfilt(s, sig, axis=0)
    return sig

def apply_ms_eq(u, fs, bands):
    """bands: list of {type,f,g,q|s|order,ch in mid/side/stereo}."""
    if not bands: return u
    M, S = (u[:,0]+u[:,1])/2, (u[:,0]-u[:,1])/2
    for b in bands:
        s = band_sos(fs, b); ch = b.get('ch', 'stereo')
        if ch in ('mid', 'stereo'): M = sosfilt(s, M)
        if ch in ('side', 'stereo'): S = sosfilt(s, S)
    return np.stack([M+S, M-S], 1)

# ---------------- dynamics ----------------
@njit(cache=True)
def comp_gain(det, fs, thr, ratio, knee, rms_ms, att_ms, rel_ms):
    """Feed-forward log-domain compressor (Giannoulis/Massberg/Reiss 2012): RMS detector, soft knee,
    branching attack/release smoothing. Returns gain in dB (<= 0) per sample."""
    n=det.shape[0]; out=np.empty(n); ms=0.0; g=0.0
    ar=np.exp(-1/(rms_ms*1e-3*fs)); aa=np.exp(-1/(att_ms*1e-3*fs)); rr=np.exp(-1/(rel_ms*1e-3*fs))
    for i in range(n):
        ms = ar*ms + (1-ar)*det[i]*det[i]
        d = 10*np.log10(ms+1e-12)-thr
        if 2*d < -knee: gc=0.0
        elif 2*abs(d) <= knee: gc=(1/ratio-1)*(d+knee/2)**2/(2*knee)
        else: gc=(1/ratio-1)*d
        g = aa*g+(1-aa)*gc if gc < g else rr*g+(1-rr)*gc
        out[i]=g
    return out

@njit(cache=True)
def release_follow(b_db, coef):
    n=b_db.shape[0]; c=np.empty(n); prev=0.0
    for i in range(n):
        r = prev*coef
        prev = b_db[i] if b_db[i] < r else r
        c[i]=prev
    return c

def limiter(u, fs, ceil, la_ms, rel_ms):
    """Look-ahead brickwall: sliding min over the look-ahead window, exponential release, boxcar ramp.
    The output is provably <= ceil at this sample rate. Returns (y, GR dB per sample, latency samples)."""
    D = max(1, int(la_ms*1e-3*fs))
    greq = np.minimum(1.0, ceil/np.maximum(np.max(np.abs(u),1),1e-12))
    b = minimum_filter1d(greq, D+1, origin=D//2)
    cdb = release_follow(20*np.log10(b), np.exp(-1/(rel_ms*1e-3*fs)))
    G = uniform_filter1d(10**(cdb/20), D+1, origin=D//2)
    y = np.zeros_like(u); y[D:] = u[:-D]*G[D:,None]
    return y, -20*np.log10(G), D

def soft_clip(v, c, knee_db=3.0):
    """Linear below c-knee, tanh into c above. Returns residual energy (dB re signal) and % samples in knee."""
    k = c*10**(-knee_db/20); a = np.abs(v); over = a > k
    if not over.any(): return v, -np.inf, 0.0
    before = v[over].copy()
    v[over] = np.sign(v[over])*(k+(c-k)*np.tanh((a[over]-k)/(c-k)))
    res = float(10*np.log10(np.sum((before-v[over])**2)/np.sum(v**2)))
    return v, res, float(100*over.mean())

def align_to(ref, y, sr, seconds=10.0, hp_hz=200.0, max_lag=2000):
    """Integer lag + polarity of y against ref, measured above hp_hz on the loudest excerpt, within +/-max_lag.
    High-passed on purpose: a process may rotate only the bass phase (CHOWTapeModel does: < 150 Hz looks inverted
    and ~160 samples late while everything above 200 Hz is at lag 0, normal polarity). A full-band correlation
    follows the bass and would shift and flip the whole signal."""
    from scipy.signal import correlate, sosfiltfilt
    n = len(ref); seg = int(min(seconds*sr, n/3))
    e = uniform_filter1d(np.abs(ref).mean(1), seg); c0 = int(np.clip(np.argmax(e) - seg//2, 0, n - seg))
    hp = butter(4, hp_hz, 'high', fs=sr, output='sos')
    a, b = sosfiltfilt(hp, ref[c0:c0+seg, 0]), sosfiltfilt(hp, y[c0:c0+seg, 0])
    c = correlate(b, a, 'full', method='fft'); mid = len(a)-1; w = c[mid-max_lag:mid+max_lag+1]
    i = int(np.argmax(np.abs(w))); lag = i - max_lag; sign = float(np.sign(w[i]))
    out = np.zeros_like(y)
    if lag >= 0: out[:n-lag] = y[lag:]
    else: out[-lag:] = y[:n+lag]
    return out*sign, lag, sign

# ---------------- tags ----------------
def tag_file(path, title=None, artist=None):
    """Write title/artist in place without touching the audio. ffmpeg stream-copies with a RIFF INFO list (WAV) /
    ID3 (MP3); mutagen then writes an ID3v2.3 tag in UTF-16 (a WAV 'id3 ' chunk), which most players read and which
    carries Hebrew safely. ffmpeg's WAV muxer has no ID3 option - it silently ignores one - hence mutagen."""
    import subprocess, tempfile, shutil
    if not (title or artist): return
    ext = os.path.splitext(path)[1].lower()
    fd, tmp = tempfile.mkstemp(suffix=ext, dir=os.path.dirname(os.path.abspath(path))); os.close(fd)
    cmd = [FFMPEG, "-v", "error", "-y", "-i", path, "-map", "0:a", "-c", "copy", "-map_metadata", "-1", "-fflags", "+bitexact"]
    for k, v in (("title", title), ("artist", artist)):
        if v: cmd += ["-metadata", f"{k}={v}"]
    subprocess.run(cmd + [tmp], check=True); shutil.copymode(path, tmp); shutil.move(tmp, path)  # keep permissions
    if ext in (".wav", ".mp3"):
        from mutagen.id3 import ID3, TIT2, TPE1
        f = __import__("mutagen.wave", fromlist=["WAVE"]).WAVE(path) if ext == ".wav" else __import__("mutagen.mp3", fromlist=["MP3"]).MP3(path)
        if f.tags is None: f.add_tags()
        f.tags.delall("TIT2"); f.tags.delall("TPE1")
        if title: f.tags.add(TIT2(encoding=1, text=title))
        if artist: f.tags.add(TPE1(encoding=1, text=artist))
        f.save(v2_version=3)
