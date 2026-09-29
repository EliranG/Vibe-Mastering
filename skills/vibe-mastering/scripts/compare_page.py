#!/usr/bin/env python3
"""Build the live A/B page next to the versions.
  compare_page.py --dir DELIVERY_DIR --qc qc.json --heading "Song: mastering comparison" [--lang he | he,en] \
      --version "label|file name in DIR|flag|stats.json" ... [--plan plan.json] [--ears ears.json] [--sections sections.json] \
      [--view artist|pro] [--title "Page name"] [--web OUT_DIR]
Versions play sample-locked on one timeline (Web Audio), switch instantly, lossless (WAV decoded at file rate).
--version: flag is "rec" for exactly one version (the recommendation), "src" for the source (the first version without
stats is taken as the source anyway), empty otherwise; stats is that version's master.py --stats file. With stats, plan
and ears the page shows what went into each version and why (explain.py): one insert slot per device, in signal order.
Stats per version (loudness, peak) come from qc.json, keyed by label; sections.json labels must be the same labels.
--lang: one language, or several comma-separated - the first is the default and the page gets a language switch that
changes every label without reloading the audio. --heading and --title may be given once per language, in that order.
--view: the level of detail the page opens in (artist: plain words and the essentials; pro: every number, the analyzer,
the section table, side/dim/output). Viewers switch freely and the page remembers their choice; the audio is the same.
--web OUT_DIR builds the same page for publishing as an Artifact, so it opens from a link on any device: every version
is encoded to MP3 (ab-1.mp3, ...) in OUT_DIR next to index.html, because an Artifact file may be at most 15 MB and a
version at most 64 MB per publish - a 3.5 min WAV is about 60 MB. The bitrate is the highest of 320..128 kbps that fits.
All versions have the same length, so they get the same encoder delay and stay sample-locked to each other. Unless
--no-lossless, it also writes a 16-bit WAV copy of every version (ab-1.p1.wav, ab-1.p2.wav, ...: split under the file
limit, joined by the page) for the page's Lossless key, which loads them only when pressed. The files maps printed at
the end go to the Artifact tool's `files`: the first with the page, each further one to the same url (one call each)."""
import os, re, sys, json, argparse, html, subprocess
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import explain

BRAND, TAG, CREDIT, REPO = "Vibe-Mastering", "Claude Code skill", "by Eliran Geffen", "https://github.com/EliranG/Vibe-Mastering"
MAX_FILE, MAX_TOTAL = 14.5e6, 60e6          # bytes, under the Artifact limits (15 MB per file, 64 MB per version)
MP3_KBPS = (320, 256, 224, 192, 160, 128)

STR = {
 "en": dict(
    dir="ltr", lang_name="EN", page_title="Mastering comparison", file="A-B comparison.html",
    sub="All versions play together on one timeline, and switching between them is instant and sample-locked. The files are full WAVs, with no lossy compression.",
    sub_web="All versions play together on one timeline, and switching between them is instant and sample-locked. Here the files are MP3 at {kbps} kbps so the page loads quickly on a phone too; the full WAV files are in the mastering folder.",
    sub_web_lx="All versions play together on one timeline, and switching between them is instant and sample-locked. Here the files are MP3 at {kbps} kbps so the page loads quickly on a phone; the Lossless key loads lossless copies, and the full WAV files are in the mastering folder.",
    fallback="The browser does not load files automatically when the page is opened straight from disk. Select the numbered WAV files from this folder:",
    fallback_web="The files did not load. Reload the page; if it happens again, select the numbered WAV files from the mastering folder:",
    view_t="Level of detail. Artist and Pro show the same session; the audio is identical.", view_art="Artist", view_pro="Pro", lang_t="Language",
    play="▶ Play", pause="❚❚ Pause", back_t="Back 5 seconds", fwd_t="Forward 5 seconds",
    loop_t="Loop 10 seconds from the current position", loop="Loop 10 s",
    secloop_t="Loop the current section", secloop="Loop section", product="A/B monitor", position="Position", section_now="Section", tracks="Tracks",
    analyzer="Analyzer", master="Master", solo_t="Listen to this version", loading="Loading session...",
    monitor="Monitor", listen_label="Listening level", raw_btn="As delivered", spotify_btn="Normalized like Spotify (-14 LUFS)",
    ch_t="Mono sums left and right, so anything out of phase gets quieter or hollow; Side plays only what the stereo adds. Press a lit key again to return to stereo.",
    mono_btn="Mono", side_btn="Side", dim="Dim", dim_t="Turn the monitor down by 20 dB",
    out_label="Output", out_default="System output", out_names="Show device names…",
    out_names_t="Browsers show device names only after microphone access; nothing is recorded.",
    out_fail="This browser doesn't let a page choose the output; pick it in your system's sound settings.",
    note_raw="Each file plays at the level it was delivered at. A louder file always sounds \"better\" to the ear, so a fair comparison is made in the normalized mode.",
    note_spotify="Every version plays as it would on Spotify and YouTube (-14 LUFS). This is how you hear the real difference: density, punch and clarity, not just which one is louder.",
    note_mono="Mono: left and right are summed. What gets quieter or hollow here cancels between the channels (phase); phones, smart speakers and many club systems play like this.",
    note_side="Side: only the difference between left and right, meaning what the stereo adds. Reverbs and wide synths live here; the lead vocal and the bass should mostly disappear.",
    note_dim="Dim is on: the monitor is 20 dB down.",
    insp_pro="Inserts", insp_art="What's in this version", left_out="Checked and left out", insp_hint="Tap a slot to see why", source_name="Source",
    amt_light="light", amt_mod="moderate", amt_strong="strong", off_word="off",
    src_off="The source: nothing was applied.", not_here="Not used in this version.",
    spec_btn="Spectrogram", diff_btn="Difference from the source",
    legend_scope="Live stereo image (vectorscope) of what is playing: a vertical line = mono, a wide cloud = wide stereo, a horizontal spread = out of phase. The φ bar under it says it as a number: +1 is mono-safe, around 0 is wide, below 0 means parts cancel in mono (check with the Mono key).",
    scope_idle="Press play to see the stereo image", corr_t="Phase correlation: +1 mono-safe, 0 wide, below 0 cancels in mono",
    sec_head="Per-section numbers: the source vs the selected version",
    sec_legend="Sections are detected automatically where the song changes character; the same letter = a repeated section (a chorus, for example). PLR = how far the peaks sit above the loudness; a large drop = the section was compressed more.",
    blind="Blind test", reveal="Reveal versions",
    keys=["Keyboard:", "switch version", "Space", "play/pause", "±5 s", "loop", "loop section", "difference/spectrogram", "mono"],
    version="Version", rec="Recommended", spotify="Spotify", hidden="Hidden during the blind test",
    th=["#", "Time", "Section", "Energy", "LUFS source", "LUFS {v}", "PLR source", "PLR {v}", "PLR change"],
    legend_diff="Difference: {v} minus the source, at equal integrated loudness. Orange = added (up to +6 dB), blue = reduced (up to -6 dB), dark = unchanged. Compression looks like this: quiet sections turn orange (lifted relative to the rest) and loud ones bluish; a narrow blue band that appears only part of the time = a dynamic EQ at work.",
    legend_spec="Spectrogram of {v} (log frequency axis, 40 Hz to 20 kHz, loudness-normalized so every version is shown on the same scale).",
    energy=dict(loud="loud", medium="medium", quiet="quiet"),
    tempo="Tempo", key="Key", music_t="Estimated from the audio: half or double tempo, or a closely related key, is possible. Two keys = the two candidates came out almost equal.",
    level_src="Level", stream="Stream", volume="Volume", output_eng="Output", vu_ref="0 VU = −10 dBFS",
    codec_t="Hear it after encoding: {c}, decoded and aligned to the sample", codec_loading="Loading the stream preview…",
    codec_fail="The stream preview did not load: it plays from the link, or from a page served locally.",
    codec_src="The source has no stream preview; the masters do.",
    note_stream="Stream: you hear {c}, the master encoded and decoded the way the platform does it, aligned to the sample. Switch it on and off to hear what encoding changes.",
    unit_graph="Graph", unit_values="Values", model="Model", kind_builtin="built into the skill", kind_vst3_free="free VST3 plugin",
    kind_vst3_user="your VST3 plugin", kind_lib_free="free library", scope_label="Stereo image",
    click_t="Possible click at {t}: check by ear. An automatic scan; a sharp drum hit can trigger it too.",
    issue_link="Suggest an improvement ↗", issue_title="Suggestion: ",
    format="Format", lossless="Lossless", lx_t="Lossless copies (WAV, 16-bit, {mb} MB), loaded only when pressed: best on Wi-Fi. The 24-bit masters are in the mastering folder.",
    lx_loading="Loading the lossless files… {got} / {total} MB", lx_fail="The lossless files did not load; the MP3s keep playing.",
    note_lx="Lossless: every version plays from 16-bit WAV instead of MP3.",
    meter_analog="Analog", meter_digital="Digital", meter_t="Meters: analog VU needles, or a digital peak and loudness meter",
    dig_t="Peak bars in dBFS with a hold line; M = momentary loudness (0.4 s) and S = short-term (3 s) in LUFS, measured from what the page plays; PEAK = the highest sample since play started (tap to reset).",
    missing="Missing file: "),
 "he": dict(
    dir="rtl", lang_name="עב", page_title="השוואת מאסטרינג", file="השוואה A-B.html",
    sub="כל הגרסאות רצות יחד על אותו ציר זמן, ומעבר ביניהן מיידי ומסונכרן לדגימה. הקבצים הם WAV מלאים, ללא דחיסה.",
    sub_web="כל הגרסאות רצות יחד על אותו ציר זמן, ומעבר ביניהן מיידי ומסונכרן לדגימה. כאן הקבצים הם MP3 באיכות {kbps} kbps, כדי שהעמוד ייטען מהר גם בטלפון. קובצי ה-WAV המלאים נמצאים בתיקיית המאסטרינג.",
    sub_web_lx="כל הגרסאות רצות יחד על אותו ציר זמן, ומעבר ביניהן מיידי ומסונכרן לדגימה. כאן הקבצים הם MP3 באיכות {kbps} kbps, כדי שהעמוד ייטען מהר בטלפון; המקש ״ללא איבוד״ טוען עותקים ללא איבוד, וקובצי ה-WAV המלאים נמצאים בתיקיית המאסטרינג.",
    fallback="הדפדפן לא מאפשר טעינה אוטומטית כשהעמוד נפתח ישירות מהדיסק. אפשר לבחור את קובצי ה-WAV הממוספרים מהתיקייה הזו:",
    fallback_web="הקבצים לא נטענו. כדאי לרענן את העמוד; אם זה חוזר, אפשר לבחור כאן את קובצי ה-WAV הממוספרים מתיקיית המאסטרינג:",
    view_t="רמת הפירוט. אמן ומקצועי מציגים את אותו הסשן; האודיו זהה.", view_art="אמן", view_pro="מקצועי", lang_t="שפה",
    play="▶ נגן", pause="❚❚ עצור", back_t="5 שניות אחורה", fwd_t="5 שניות קדימה",
    loop_t="לופ של 10 שניות מהמיקום הנוכחי", loop="לופ 10 שנ׳",
    secloop_t="לופ על הקטע הנוכחי", secloop="לופ קטע", product="מוניטור A/B", position="מיקום", section_now="קטע", tracks="ערוצים",
    analyzer="אנלייזר", master="מאסטר", solo_t="להאזין לגרסה הזו", loading="טוען את הסשן...",
    monitor="מוניטור", listen_label="עוצמת האזנה", raw_btn="כמו שהקבצים", spotify_btn="מנורמל כמו ספוטיפיי (‎-14 LUFS)",
    ch_t="מונו מחבר את שני הערוצים, כך שכל מה שבהיפוך פאזה נחלש או נשמע חלול; סייד משמיע רק את מה שהסטריאו מוסיף. לחיצה נוספת על מקש דולק מחזירה לסטריאו.",
    mono_btn="מונו", side_btn="סייד", dim="Dim", dim_t="הנמכת המוניטור ב-20 dB",
    out_label="יציאה", out_default="יציאת המערכת", out_names="להציג שמות התקנים…",
    out_names_t="הדפדפן מציג שמות התקנים רק אחרי הרשאת מיקרופון; שום דבר לא מוקלט.",
    out_fail="הדפדפן הזה לא מאפשר לעמוד לבחור יציאה; אפשר לבחור אותה בהגדרות הסאונד של המערכת.",
    note_raw="כל קובץ מתנגן בעוצמה שבה הוא נמסר. שימו לב: קובץ חזק יותר תמיד נשמע ״טוב יותר״ לאוזן, ולכן השוואה הוגנת נעשית במצב המנורמל.",
    note_spotify="כל גרסה מתנגנת כמו בספוטיפיי ויוטיוב (‎-14 LUFS). כך שומעים את ההבדל האמיתי: צפיפות, פאנץ׳ ובהירות, ולא רק מה חזק יותר.",
    note_mono="מונו: הערוץ השמאלי והימני מחוברים. מה שנחלש או נשמע חלול כאן מבטל את עצמו בין הערוצים (פאזה); טלפונים, רמקולים חכמים והרבה מערכות במועדונים מנגנים ככה.",
    note_side="סייד: רק ההפרש בין שמאל לימין, כלומר מה שהסטריאו מוסיף. ריברבים וסינתים רחבים גרים כאן; השירה הראשית והבס אמורים כמעט להיעלם.",
    note_dim="Dim פעיל: המוניטור מונמך ב-20 dB.",
    insp_pro="שרשרת עיבוד", insp_art="מה יש בגרסה הזו", left_out="נבדק ונשאר בחוץ", insp_hint="לחיצה על שלב מציגה למה", source_name="מקור",
    amt_light="קל", amt_mod="בינוני", amt_strong="חזק", off_word="כבוי",
    src_off="המקור: לא הופעל עליו כלום.", not_here="לא בשימוש בגרסה הזו.",
    spec_btn="ספקטרוגרמה", diff_btn="הפרש מהמקור",
    legend_scope="תמונת הסטריאו החיה (וקטורסקופ) של מה שמתנגן: קו אנכי = מונו, ענן רחב = סטריאו רחב, פריסה אופקית = היפוך פאזה. פס ה-φ שמתחתיה אומר את זה במספר: ‎+1 בטוח במונו, סביב 0 רחב, מתחת ל-0 חלקים מתבטלים במונו (כדאי לבדוק במקש מונו).",
    scope_idle="לחיצה על נגן מציגה את תמונת הסטריאו", corr_t="קורלציית פאזה: ‎+1 בטוח במונו, 0 רחב, מתחת ל-0 מתבטל במונו",
    sec_head="נתונים לפי קטע: המקור מול הגרסה הנבחרת",
    sec_legend="הקטעים מזוהים אוטומטית לפי שינוי אופי בשיר; אות זהה = קטע שחוזר (למשל פזמון). PLR = כמה השיאים מעל העוצמה; ירידה גדולה = הקטע נדחס יותר.",
    blind="בדיקה עיוורת", reveal="חשיפת הגרסאות",
    keys=["מקלדת:", "מעבר גרסה", "רווח", "נגן/עצור", "‎±5 שנ׳", "לופ", "לופ קטע", "הפרש/ספקטרוגרמה", "מונו"],
    version="גרסה", rec="מומלץ", spotify="ספוטיפיי", hidden="מוסתר בזמן בדיקה עיוורת",
    th=["#", "זמן", "קטע", "עוצמה", "LUFS מקור", "LUFS {v}", "PLR מקור", "PLR {v}", "שינוי PLR"],
    legend_diff="הפרש {v} פחות המקור, בעוצמה כוללת שווה: כתום = נוסף (עד ‎+6 dB), כחול = הורד (עד ‎-6 dB), כהה = ללא שינוי. דחיסה נראית כך: קטעים שקטים כתומים (הורמו יחסית) וקטעים חזקים כחלחלים; פס כחול צר שמופיע רק בחלק מהזמן = EQ דינמי בפעולה.",
    legend_spec="ספקטרוגרמה של {v} (ציר תדר לוגריתמי 40 Hz עד 20 kHz, בעוצמה מנורמלת כדי שכל הגרסאות יושוו באותה סקאלה).",
    energy=dict(loud="שיא", medium="בינוני", quiet="שקט"),
    tempo="טמפו", key="סולם", music_t="הערכה מתוך האודיו: ייתכן חצי או כפול טמפו, או סולם קרוב. שני סולמות = שני המועמדים יצאו כמעט שווים.",
    level_src="עוצמה", stream="סטרים", volume="ווליום", output_eng="יציאה", vu_ref="‎0 VU = −10 dBFS",
    codec_t="לשמוע אחרי קידוד: {c}, מפוענח ומיושר לדגימה", codec_loading="טוען את תצוגת הסטרים…",
    codec_fail="תצוגת הסטרים לא נטענה: היא עובדת מהקישור או מעמוד שמוגש משרת מקומי.",
    codec_src="למקור אין תצוגת סטרים; למאסטרים יש.",
    note_stream="סטרים: שומעים {c}, המאסטר מקודד ומפוענח כמו שהפלטפורמה עושה, מיושר לדגימה. כדאי להדליק ולכבות כדי לשמוע מה הקידוד משנה.",
    unit_graph="גרף", unit_values="ערכים", model="דגם", kind_builtin="מובנה בסקיל", kind_vst3_free="פלאגין VST3 חינמי",
    kind_vst3_user="פלאגין VST3 שלך", kind_lib_free="ספרייה חינמית", scope_label="תמונת סטריאו",
    click_t="קליק אפשרי ב-{t}: לבדוק באוזן. סריקה אוטומטית; גם מכת תוף חדה יכולה להפעיל אותה.",
    issue_link="הצעה לשיפור ↗", issue_title="הצעה: ",
    format="פורמט", lossless="ללא איבוד", lx_t="עותקים ללא איבוד (WAV, ‏16 ביט, {mb} MB), נטענים רק בלחיצה, עדיף ב-Wi-Fi. מאסטרי ה-24 ביט נמצאים בתיקיית המאסטרינג.",
    lx_loading="טוען קבצים ללא איבוד… {got} / {total} MB", lx_fail="הקבצים ללא איבוד לא נטענו; ה-MP3 ממשיך להתנגן.",
    note_lx="ללא איבוד: כל הגרסאות מתנגנות מ-WAV של 16 ביט במקום MP3.",
    meter_analog="אנלוגי", meter_digital="דיגיטלי", meter_t="מדים: מחוגי VU אנלוגיים, או מד דיגיטלי של שיא ועוצמה",
    dig_t="פסי שיא ב-dBFS עם קו החזקה; M = עוצמה רגעית (0.4 שנ׳) ו-S = לטווח קצר (3 שנ׳) ב-LUFS, נמדדות ממה שהעמוד מנגן; PEAK = הדגימה הגבוהה ביותר מאז תחילת הניגון (לחיצה מאפסת).",
    missing="חסר קובץ: "),
}

CODECS = {"ogg160": (["-c:a", "libvorbis", "-b:a", "160k"], "ogg", dict(en="Spotify (Ogg 160)", he="ספוטיפיי (Ogg 160)")),
          "opus128": (["-c:a", "libopus", "-b:a", "128k"], "opus", dict(en="YouTube (Opus 128)", he="יוטיוב (Opus 128)")),
          "aac256": (["-c:a", "aac_at", "-b:a", "256k"], "m4a", dict(en="Apple Music (AAC 256)", he="אפל מיוזיק (AAC 256)"))}

def codec_twin(src, out, codec):
    """What a listener gets from a platform: `src` encoded with `codec`, decoded at its own rate, aligned to it to the
    sample (a lag or polarity flip would break the instant A/B switch) and saved as FLAC. Returns the measured lag."""
    import tempfile, numpy as np, soundfile as sf, mslib as L
    from ffbin import FFMPEG
    args, ext, _ = CODECS[codec]
    x, sr = L.read_stereo(src)
    with tempfile.TemporaryDirectory() as d:
        subprocess.run([FFMPEG, "-v", "error", "-y", "-i", src, *args, f"{d}/e.{ext}"], check=True)
        subprocess.run([FFMPEG, "-v", "error", "-y", "-i", f"{d}/e.{ext}", "-c:a", "pcm_f32le", "-ar", str(sr), f"{d}/d.wav"], check=True)
        y, _ = sf.read(f"{d}/d.wav", always_2d=True)
    y = np.pad(y, ((0, max(0, len(x) - len(y))), (0, 0)))[:len(x)]
    y, lag, sign = L.align_to(x, y, sr)
    os.makedirs(os.path.dirname(out), exist_ok=True); sf.write(out, np.clip(y, -1, 1), sr, subtype="PCM_24", format="FLAC")
    return lag

def lossless_parts(src, out_dir, stem):
    """A lossless copy for the web page: 16-bit WAV at the file's own rate (a 16-bit file is copied bit for bit, a
    24-bit or float one gets TPDF dither), split into parts under the Artifact file limit. The page joins the bytes
    before decoding, so the parts decode as one file with no seam. WAV and not FLAC: Artifacts do not serve .flac, and
    plain PCM WAV is the one lossless format every browser's decodeAudioData takes. Returns (part names, total bytes)."""
    import numpy as np, soundfile as sf
    info = sf.info(src)
    if info.subtype == "PCM_16": q, sr = sf.read(src, dtype="int16", always_2d=True)
    else:
        x, sr = sf.read(src, dtype="float64", always_2d=True); rng = np.random.default_rng(0)
        q = np.clip(np.round(x*32768 + rng.random(x.shape) - rng.random(x.shape)), -32768, 32767).astype(np.int16)
    tmp = os.path.join(out_dir, f".{stem}.wav"); sf.write(tmp, q, sr, subtype="PCM_16", format="WAV")
    data = open(tmp, "rb").read(); os.remove(tmp); step = int(MAX_FILE); names = []
    for k in range(0, len(data), step):
        names.append(f"{stem}.p{k//step + 1}.wav"); open(os.path.join(out_dir, names[-1]), "wb").write(data[k:k + step])
    return names, len(data)

def batches(files, cap=MAX_TOTAL):
    """Split the files map into publishes of at most `cap` bytes each, in order (the MP3s first, so the first publish plays)."""
    out, cur, size = [], {}, 0
    for n, p in files.items():
        b = os.path.getsize(p)
        if cur and size + b > cap: out.append(cur); cur, size = {}, 0
        cur[n] = p; size += b
    return out + ([cur] if cur else [])

def mp3_web(V, src_dir, out_dir, lossless=True):
    """Encode every version for the web page; returns (kbps, {published name: path})."""
    import soundfile as sf
    from ffbin import FFMPEG
    dur = sf.info(os.path.join(src_dir, V[0]["file"])).duration
    n = len(V) + sum(1 for v in V if v.get("tw"))                  # the codec previews count against the Artifact limit too
    fit = min(MAX_FILE, MAX_TOTAL/n)*8/dur/1000
    kbps = next((b for b in MP3_KBPS if b <= fit), MP3_KBPS[-1])
    os.makedirs(out_dir, exist_ok=True); jobs = []
    for i, v in enumerate(V):
        name = f"ab-{i+1}.mp3"
        jobs.append((name, [FFMPEG, "-v", "error", "-y", "-i", os.path.join(src_dir, v["file"]), "-map_metadata", "-1",
                            "-c:a", "libmp3lame", "-b:a", f"{kbps}k", os.path.join(out_dir, name)]))
        v["show"], v["src_file"], v["file"] = v["title"], v["file"], name
        if v.get("tw"):
            tname = f"ab-{i+1}s.mp3"
            jobs.append((tname, [FFMPEG, "-v", "error", "-y", "-i", os.path.join(src_dir, v["tw"]["file"]), "-map_metadata", "-1",
                                 "-c:a", "libmp3lame", "-b:a", f"{kbps}k", os.path.join(out_dir, tname)]))
            v["tw"]["src_file"], v["tw"]["file"] = v["tw"]["file"], tname
    with ThreadPoolExecutor(4) as ex: list(ex.map(lambda j: subprocess.run(j[1], check=True), jobs))
    files = {n: os.path.abspath(os.path.join(out_dir, n)) for n, _ in jobs}
    if lossless:                                                   # the Lossless key: 16-bit WAV copies, loaded only when pressed
        srcs = [(v, os.path.join(src_dir, v["src_file"]), f"ab-{i+1}") for i, v in enumerate(V)] + \
               [(v["tw"], os.path.join(src_dir, v["tw"]["src_file"]), f"ab-{i+1}s") for i, v in enumerate(V) if v.get("tw")]
        with ThreadPoolExecutor(4) as ex: made = list(ex.map(lambda t: lossless_parts(t[1], out_dir, t[2]), srcs))
        total = sum(os.path.getsize(p) for p in files.values()) + sum(b for _, b in made)
        if total > 240e6:                                          # an Artifact version holds 256 MB: drop the twins' copies first
            print(f"lossless: {total/1e6:.0f} MB in all is too much for one Artifact; the stream previews stay MP3")
            for (o, _, stem), (names, _) in zip(srcs, made):
                if stem.endswith("s"): [os.remove(os.path.join(out_dir, n)) for n in names]
            srcs, made = [t for t in srcs if not t[2].endswith("s")], [m for t, m in zip(srcs, made) if not t[2].endswith("s")]
        for (o, _, _), (names, b) in zip(srcs, made):
            o["lx"] = dict(parts=names, bytes=b); files.update({n: os.path.abspath(os.path.join(out_dir, n)) for n in names})
    big = [f"{n} {os.path.getsize(p)/1e6:.1f} MB" for n, p in files.items() if os.path.getsize(p) > MAX_FILE]
    if big: raise SystemExit(f"too large for an Artifact: {big}")
    return kbps, files

def js(o): return json.dumps(o, ensure_ascii=False).replace("</", "<\\/")

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dir", required=True); ap.add_argument("--qc", required=True)
    ap.add_argument("--heading", action="append", required=True); ap.add_argument("--version", action="append", required=True)
    ap.add_argument("--lang", default="en", help="he, en, or several comma-separated (the first is the default)")
    ap.add_argument("--view", choices=("artist", "pro"), default="artist", help="the level of detail the page opens in")
    ap.add_argument("--plan", help="plan.py plan.json (why each stage was used or left out)")
    ap.add_argument("--ears", help="ears.py listen output (the evidence behind the decisions)")
    ap.add_argument("--name", help="output file name (default: 'A-B comparison.html' / 'השוואה A-B.html')")
    ap.add_argument("--sections", help="sections.json from sections.py (labels must match)")
    ap.add_argument("--title", action="append", help="the page name (browser tab, Artifact gallery); once per language")
    ap.add_argument("--web", metavar="OUT_DIR", help="build the page with MP3 copies in OUT_DIR, for publishing as an Artifact")
    ap.add_argument("--codec", choices=sorted(CODECS), help="add a 'hear it after encoding' copy of every master (FLAC in DIR/codec-preview)")
    ap.add_argument("--analysis", help="analyze.py output: shows the estimated key and tempo in the transport")
    ap.add_argument("--no-lossless", action="store_true", help="--web without the lossless WAV copies (one publish instead of three or four)")
    a = ap.parse_args()
    langs = [l.strip() for l in a.lang.split(",") if l.strip()]
    bad = [l for l in langs if l not in STR]
    if bad or not langs: raise SystemExit(f"--lang: supported languages are {sorted(STR)}, got {bad or a.lang}")
    per = lambda vals: {l: (vals[i] if vals and i < len(vals) else (vals[0] if vals else None)) for i, l in enumerate(langs)}
    heads, titles = per(a.heading), per(a.title)
    J = lambda p: json.load(open(p)) if p else None
    qc, PLAN, EARS = json.load(open(a.qc)), J(a.plan), J(a.ears)
    V, meta = [], []
    for k, spec in enumerate(a.version):
        label, fname, flag, stats = (spec.split("|") + ["", "", ""])[:4]
        if not os.path.exists(os.path.join(a.dir, fname)): raise SystemExit(f"missing in dir: {fname}")
        q = qc[label]; st = J(stats) if stats else None
        src = flag == "src" or (st is None and not any(m.get("source") for m in meta) and k == 0)
        chains = {l: explain.chain(st, PLAN, EARS, l) if st else (explain.source_chain(l) if src else explain.external_chain(l)) for l in langs}
        ups = [u for u in (st or {}).get("user_plugins") or [] if u.get("role") != "dynamics"]
        meta.append(dict(title=label, rec=flag == "rec", source=src, target=(st or {}).get("target_lufs") if st else None,
                         tape=bool((st or {}).get("tape")), matchering=bool((st or {}).get("matchering")),
                         plugin=ups[0]["label"] if ups else None, flags=(st or {}).get("health") or []))
        V.append(dict(file=fname, title=label, lufs=q["lufs_i"], tp=q["true_peak_dbtp"], plr=q["plr_db"], lra=q["lra_lu"], rec=flag == "rec", src=src, chain=chains))
    if sum(v["rec"] for v in V) != 1: raise SystemExit("mark exactly one --version as rec")
    if a.codec:
        for v in V:
            if v["src"]: continue
            rel = os.path.join("codec-preview", f"{os.path.splitext(v['file'])[0]} - {a.codec}.flac"); out = os.path.join(a.dir, rel)
            if not os.path.exists(out) or os.path.getmtime(out) < os.path.getmtime(os.path.join(a.dir, v["file"])):
                print(f"codec preview {a.codec}: {v['title']} (lag {codec_twin(os.path.join(a.dir, v['file']), out, a.codec)} samples)")
            v["tw"] = dict(file=rel, codec=a.codec)
    for l in langs:
        for v, b in zip(V, explain.blurbs(meta, l)): v.setdefault("blurb", {})[l] = b
    I18N = {l: dict(STR[l]) for l in langs}
    for l in langs:
        if a.codec: I18N[l]["codec_name"] = CODECS[a.codec][2][l]
    AN = J(a.analysis) or {}
    kd = AN.get("key_detail") or {}
    short = lambda name: name.split()[0] + ("m" if name.endswith("minor") else "") if name else None
    music = dict(key=kd.get("short"), key_name=AN.get("key"), bpm=AN.get("tempo_bpm"),   # two candidates this close: show both
                 key_alt=short(kd.get("runner_up")) if kd.get("confidence") is not None and kd["confidence"] < 0.03 else None)
    files = None
    if a.web:
        kbps, files = mp3_web(V, a.dir, a.web, lossless=not a.no_lossless)
        lx = any(v.get("lx") for v in V); lxmb = sum(v["lx"]["bytes"] for v in V if v.get("lx"))/1e6
        for v in V:
            v.pop("src_file", None); (v.get("tw") or {}).pop("src_file", None)
        for l in langs:
            I18N[l]["sub"], I18N[l]["fallback"] = STR[l]["sub_web_lx" if lx else "sub_web"].format(kbps=kbps), STR[l]["fallback_web"]
            I18N[l]["lx_t"] = STR[l]["lx_t"].replace("{mb}", f"{lxmb:.0f}")
    for l in langs:
        I18N[l]["heading"] = heads[l]; I18N[l]["doc_title"] = titles[l] or STR[l]["page_title"]
        for k in ("sub_web", "sub_web_lx", "fallback_web", "file", "page_title"): I18N[l].pop(k, None)
    t = I18N[langs[0]]
    tpl = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "compare_template.html"), encoding="utf-8").read()
    for k, v in t.items():
        if isinstance(v, str): tpl = tpl.replace("{{" + k + "}}", html.escape(v))
    tpl = tpl.replace("{{lang}}", langs[0])
    html_ = (tpl.replace("__VERSIONS_JSON__", js(V)).replace("__I18N_JSON__", js(I18N))
                .replace("__DEFAULTS_JSON__", js(dict(lang=langs[0], view=a.view, music=music, repo=REPO,
                                                      clicks=((EARS or {}).get("measurements") or {}).get("clicks") or [])))
                .replace("__PAGE_TITLE__", html.escape(t["doc_title"])).replace("__HEADING__", html.escape(t["heading"]))
                .replace("__BRAND__", BRAND).replace("__TAG__", TAG).replace("__CREDIT__", CREDIT).replace("__REPO__", REPO)
                .replace("__SECTIONS_JSON__", js(json.load(open(a.sections))) if a.sections else "null"))
    left = sorted(set(re.findall(r"\{\{\w+\}\}", html_)))
    if left: raise SystemExit(f"template placeholders without a string: {left}")
    out = os.path.join(a.web or a.dir, a.name or ("index.html" if a.web else STR[langs[0]]["file"]))
    open(out, "w", encoding="utf-8").write(html_); print(out)
    if files:
        B = batches(files)
        print(f"MP3 {kbps} kbps{' + lossless WAV' if any(v.get('lx') for v in V) else ''}, {sum(os.path.getsize(p) for p in files.values())/1e6:.1f} MB in total, {len(B)} publish(es)")
        for i, b in enumerate(B):                                  # the page with the first map; the rest to the same url, one call each
            print(f"files map {i+1} of {len(B)} ({sum(os.path.getsize(p) for p in b.values())/1e6:.1f} MB): " + json.dumps(b, ensure_ascii=False))

if __name__ == "__main__":
    main()
