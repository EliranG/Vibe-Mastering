#!/usr/bin/env python3
"""What went into each version, and why - one source for the A/B page and the report.

  chain(stats, plan=None, ears=None, lang="en") -> {"summary", "devices", "skipped"}
      stats  one version's master.py --stats output (its effective config is stats["cfg"])
      plan   plan.py's plan.json (every stage decision); ears  ears.py listen output (the evidence behind it)
  blurb(role, lang, **kw)   the one-line description of a version for the Artist view
  health_text(flag, lang)   a master.py health flag in plain words

  explain.py STATS.json [--plan plan.json] [--ears ears.json] [--lang en|he]   prints the chain (a quick check)

Every device has two wordings of the same facts: "pro" (settings, measured work, evidence) and "art" (plain words:
what it does for the song). The Artist and Pro views show one chain at two levels of detail; the audio is the same.
Negative numbers use a real minus sign; the pages isolate numbers for right-to-left text."""
import json, argparse

M = "−"
def num(x, d=1, sign=False):
    s = f"{x:+.{d}f}" if sign else f"{x:.{d}f}"
    return s.replace("-", M)
def hz(f):
    f = float(f)
    if f < 1000: return f"{f:.0f} Hz"
    v = f/1000
    return (f"{v:.0f}" if abs(v - round(v)) < 0.05 else f"{v:.1f}") + " kHz"
def gnum(x):                                                   # -2 -> "−2", -2.5 -> "−2.5"
    return f"{float(x):g}".replace("-", M)
def fill(_s, **kw):
    for k, v in kw.items(): _s = _s.replace("{" + k + "}", str(v))
    return _s

T = {
 "en": dict(
    name=dict(matchering=("Reference match · Matchering", "Matched to your reference"),
              dyneq=("Dynamic EQ · ZL Equalizer 2", "Harshness control"),
              tape=("Tape saturation · CHOW Tape", "Analog tape warmth"),
              plugin=("{label} · your plugin", "Your plugin: {label}"),
              hpf=("Sub-sonic high-pass", "Rumble filter"),
              eq=("M/S EQ", "Tone balance"),
              lowcomp=("Low-band compressor", "Bass control"),
              glue=("Glue compressor", "Glue"),
              leveler=("Leveling limiter", "Loudness smoothing"),
              clipper=("Soft clipper", "Peak shaving"),
              limiter=("True-peak limiter", "Loudness and safety ceiling"),
              fade=("Fades", "Clean start and end"),
              mono_bass=("Mono bass (side high-pass)", "Bass in the center"),
              presence_eq=("Presence EQ", "Vocal presence"),
              static_cut=("Static cut", "Steady harsh spot"),
              loudness_cap=("Loudness cap", "Loudness limit")),
    art=dict(
        matchering="Your reference song's tone balance was used as the guide.",
        dyneq="A sharp edge {where} came and went in the song. This turns it down only in the moments it pokes out (up to {loud} dB) and leaves the rest alone.",
        tape="A touch of analog tape: rounder peaks and a slightly warmer top. A taste choice.",
        plugin_tone="Your own plugin, applied the way you set it.",
        plugin_dyn="Your compressor was tried with and without on this song and made it measurably cleaner, so it stays.",
        hpf="Removes inaudible rumble below {f} that only eats headroom.",
        eq="Small, broad moves (all within ±2 dB) that fix the balance the first listen measured.",
        lowcomp="Holds the bass steady so it doesn't push the loudness around.",
        glue="Gently glues the mix. It was tried with and without, and it helped.",
        leveler="Evens out the loudest moments before the final stage. It works {pct}% of the time.",
        clipper="Shaves the sharpest hits by a hair, which is cleaner than asking the limiter to do it.",
        limiter="Brings the song up to {lufs} LUFS and keeps every peak under {ceil} dBTP, so it won't distort after Spotify, Apple Music or YouTube encode it.",
        fade="A {ms} ms fade at the end, because the song stopped abruptly.",
        fade_in="A tiny fade-in so the first sample doesn't click."),
    eq_art=dict(deep=("More deep bass", "Tightened the deep bass"), bass=("Warmer low end", "Less bass mud"),
                box=("More body", "Cleared some boxiness"), mids=("Fuller mids", "Less honk in the mids"),
                pres=("Brought the vocal forward", "Softened a forward edge"), bite=("More bite and clarity", "Softened the sharpness"),
                air=("Added a little air", "Calmed the very top"), side_up="Widened the top end", side_dn="Narrowed the stereo image",
                mono="Kept the bass in the center", hp="Removed rumble", lp="Rolled off the very top"),
    where="around {f}",
    skip=dict(hpf="No rumble to remove.", mono_bass="The bass is already in the center.", dynamic_eq="No harsh moments that come and go.",
              fade_out="The song already ends cleanly.", lowcomp="The bass doesn't need taming.", lowcomp_dense="The song is already dense; more compression would only squash it.",
              glue="A compressor was tried with and without, made no measurable difference, and stayed out.",
              glue_dense="The song is already dense; more compression would only squash it.",
              tape="Optional color, not chosen for this version.", matchering="Optional, needs a reference song.",
              plugin="Your plugin was tried with and without and didn't improve this song.",
              leveler="Not needed at this loudness: it would have had nothing to do.", clipper="Not needed at this loudness: it would have had nothing to do.",
              presence_eq="The vocal already sits forward."),
    why=dict(
        subsonic="energy below 25 Hz {x} dB re the 25–120 Hz band, DC {dc}", no_subsonic="no real energy below 25 Hz ({x} dB re the bass)",
        stereo_bass="side vs mid below 80 Hz {x} dB", mono_enough="the bass is already mono: side vs mid below 80 Hz {x} dB",
        presence="2 kHz octave {x} dB vs 1 kHz",
        bump_dyn="{f} bump comes and goes: median {med} dB, p90 {p90} dB, over 2 dB {pct}% of the time",
        bump_static="{f} stands {x} dB above its neighbours almost all the time",
        no_bump="the first listen found no harsh bump of 2 dB or more", no_zl="the ZL plugin is not installed, so a static cut is used",
        abrupt="last 50 ms peak {x} dBFS", clean_end="the song ends cleanly (last 50 ms at {x} dBFS)",
        not_bass="the bass does not drive the peaks ({x}% of the loudest peaks come from below 120 Hz)",
        dense="the song is already dense or limited", taste="a taste choice: only when asked for",
        audition="bypass test at {probe} LUFS, with vs without: leveler {a}% vs {b}%, clipper residual {c} vs {d} dB, DR {e} vs {f}",
        keep=" - measurably cleaner, so it stays", drop=" - no measurable benefit, so it stays out",
        cap="the source is already limited at {x} LUFS, so no version goes past {cap} LUFS",
        pruned="idle at {t} LUFS: leveler {pct}% active (max {mx} dB), clipper residual {res} dB; without it the final limiter works {more} dB deeper",
        user_tone="your plugin, a taste choice: used as set"),
    pro=dict(
        dyneq="{f} · Q {q} · {ch} · range {range} dB · threshold {thr} dB (p{pct}) · {att}/{rel} ms",
        dyneq_meas="measured: {loud} dB when the band is loud, {quiet} dB when quiet",
        dyneq_static="cuts almost as much when quiet: acting as a static cut",
        tape="mode {mode} · drive {d} · saturation {s} · bias {b} · linear-phase 4× OS",
        tape_meas="level into make-up {lu} LU · latency {lag} samples, realigned",
        plugin="{role} · level into make-up {lu} LU · latency {lag} samples, realigned",
        comp="thr {thr} dB · ratio {ratio}:1 · knee {knee} · {att}/{rel} ms",
        comp_meas="gain reduction p95 {p95} dB · max {mx} dB",
        leveler="active {pct}% of the time · max {mx} dB · look-ahead {la} ms · release {rel} ms",
        clipper="{knee}% of samples in the knee · residual {res} dB (distortion; below −30 dB is inaudible)",
        limiter="max {mx} dB · p90 {p90} dB · over 1 dB {over}% of the time · look-ahead {la} ms · release {rel} ms",
        limiter_out="{gain} dB into the peak stage → {lufs} LUFS, TP {tp} dBTP (ceiling {ceil}) · {os}× oversampling · TPDF dither, 24-bit",
        fade="in {fi} ms · out {fo} ms",
        matchering="reference {ref} ({rl} LUFS) · 44.1 kHz, no limiter, no normalize · realigned {lag} samples",
        summary="target {t} LUFS · ceiling {c} dBTP · {os}× oversampling"),
    pro_why=dict(eq="Moves decided per song from the first listen, each within ±2 dB and broad; every band's measured reason is listed.",
                 leveler="Catches the loudest passages before the clipper, so the final limiter only has to work lightly.",
                 clipper="Short transients are shaved more cleanly by a soft clip than by a limiter; a residual below −30 dB is inaudible.",
                 limiter="True-peak ceiling {ceil} dBTP, Spotify's guideline for masters louder than −14 LUFS, confirmed with real codec encodes; oversampled so inter-sample peaks are caught."),
    forced="Forced on for comparison; the bypass test would leave it out: ",
    forced_art="Switched on only so you can hear it: on this song it did not measurably help, so the skill would leave it out.",
    role=dict(dynamics="dynamics", tone="tone"),
    ch=dict(mid="M", side="S", stereo="M+S"),
    types=dict(peak="Bell", highshelf="High shelf", lowshelf="Low shelf", hp="High-pass", lp="Low-pass"),
    source_summary=("the untouched source", "Your mix, untouched: the reference for everything else."),
    external=("no chain data for this file", "A file that was not rendered here."),
    health={"target loudness": "Didn't reach its target: the song pushes back, so a quieter target is cleaner.",
            "leveler active": "Audibly squashed: the leveler works more than half the time.",
            "clip residual": "The clipper may be audible.", "glue compressor": "Heavy glue compression.",
            "low-band compressor": "The bass may pump."},
    blurb=dict(rec="Recommended: the loudest version that stays clean.", quiet="The most dynamic: more room to breathe, a little less loud.",
               loud="Louder, for comparison: the limiter works harder here.", mid="A middle ground in loudness.",
               tape="Warm and dynamic: analog tape color.", matchering="Shaped after your reference song.",
               plugin="With your own plugin: {label}.", flagged="Flagged: {flag}")),
 "he": dict(
    name=dict(matchering=("התאמה לרפרנס · Matchering", "התאמה לשיר הרפרנס"),
              dyneq=("EQ דינמי · ZL Equalizer 2", "ריסון צרימה"),
              tape=("רוויית טייפ · CHOW Tape", "חום של טייפ אנלוגי"),
              plugin=("{label} · הפלאגין שלך", "הפלאגין שלך: {label}"),
              hpf=("סינון תת-קולי", "סינון רעמים"),
              eq=("EQ במיד/סייד", "איזון הצליל"),
              lowcomp=("קומפרסור בס", "שליטה בבס"),
              glue=("קומפרסור דבק", "הדבקה"),
              leveler=("לימיטר מיישר", "החלקת עוצמה"),
              clipper=("קליפר רך", "גילוח שיאים"),
              limiter=("לימיטר True Peak", "עוצמה ותקרת ביטחון"),
              fade=("פיידים", "התחלה וסוף נקיים"),
              mono_bass=("בס במונו (HPF בסייד)", "בס במרכז"),
              presence_eq=("EQ נוכחות", "נוכחות לשירה"),
              static_cut=("הורדה קבועה", "נקודה צורמת קבועה"),
              loudness_cap=("תקרת עוצמה", "מגבלת עוצמה")),
    art=dict(
        matchering="איזון הצליל של שיר הרפרנס שלך שימש כמצפן.",
        dyneq="חדות {where} באה והולכת לאורך השיר. זה מנמיך אותה רק ברגעים שהיא בולטת (עד {loud} dB), ומשאיר את כל השאר בשקט.",
        tape="נגיעה של טייפ אנלוגי: שיאים עגולים יותר וגבוהים מעט חמים יותר. בחירת טעם.",
        plugin_tone="הפלאגין שלך, בדיוק כפי שכיוונת אותו.",
        plugin_dyn="הקומפרסור שלך נבדק עם ובלי על השיר הזה, ובאופן מדיד שיפר – ולכן נשאר.",
        hpf="מסיר רעש תת-קולי מתחת ל-{f}, שלא שומעים אבל גוזל מקום.",
        eq="תיקונים קטנים ורחבים (כולם עד ±2 dB) שמאזנים את מה שנמדד בהאזנה הראשונה.",
        lowcomp="מחזיק את הבס יציב, כדי שלא ינדנד את העוצמה.",
        glue="מדביק את המיקס בעדינות. נבדק עם ובלי, ועזר.",
        leveler="מיישר את הרגעים החזקים ביותר לפני השלב האחרון. עובד {pct}% מהזמן.",
        clipper="מגלח את המכות החדות ביותר בשערה – נקי יותר מלהעמיס את זה על הלימיטר.",
        limiter="מביא את השיר ל-{lufs} LUFS ושומר על כל שיא מתחת ל-{ceil} dBTP, כדי שלא יתעוות אחרי הקידוד של ספוטיפיי, אפל מיוזיק ויוטיוב.",
        fade="פייד של {ms} ms בסוף, כי השיר נקטע בפתאומיות.",
        fade_in="פייד-אין זעיר, כדי שהדגימה הראשונה לא תקליק."),
    eq_art=dict(deep=("יותר בס עמוק", "הידוק הבס העמוק"), bass=("תחתונים חמים יותר", "פחות בוץ בבס"),
                box=("יותר גוף", "ניקוי 'קופסתיות'"), mids=("אמצע מלא יותר", "פחות 'אף' באמצע"),
                pres=("הבאת השירה קדימה", "ריכוך קצה בולט"), bite=("יותר חדות ובהירות", "ריכוך החדות"),
                air=("קצת יותר 'אוויר'", "הרגעת הגבוהים ביותר"), side_up="הרחבת הגבוהים", side_dn="צמצום רוחב הסטריאו",
                mono="הבס נשאר במרכז", hp="סינון רעמים", lp="ריכוך הקצה העליון"),
    where="סביב {f}",
    skip=dict(hpf="אין רעש תת-קולי להסיר.", mono_bass="הבס כבר במרכז.", dynamic_eq="לא נמצאה צרימה שבאה והולכת.",
              fade_out="השיר כבר נגמר נקי.", lowcomp="הבס לא צריך ריסון.", lowcomp_dense="השיר כבר צפוף; עוד דחיסה רק תמעך אותו.",
              glue="קומפרסור נבדק עם ובלי, לא שיפר באופן מדיד, ונשאר בחוץ.",
              glue_dense="השיר כבר צפוף; עוד דחיסה רק תמעך אותו.",
              tape="צבע אופציונלי, לא נבחר לגרסה הזו.", matchering="אופציונלי, צריך שיר רפרנס.",
              plugin="הפלאגין שלך נבדק עם ובלי ולא שיפר את השיר הזה.",
              leveler="לא נדרש בעוצמה הזו: לא היה לו מה לעשות.", clipper="לא נדרש בעוצמה הזו: לא היה לו מה לעשות.",
              presence_eq="השירה כבר יושבת קדימה."),
    why=dict(
        subsonic="אנרגיה מתחת ל-25 Hz: {x} dB ביחס לפס 25–120 Hz, DC {dc}", no_subsonic="אין אנרגיה ממשית מתחת ל-25 Hz ({x} dB ביחס לבס)",
        stereo_bass="סייד מול מיד מתחת ל-80 Hz: {x} dB", mono_enough="הבס כבר מונו: סייד מול מיד מתחת ל-80 Hz {x} dB",
        presence="אוקטבת 2 kHz ב-{x} dB מול 1 kHz",
        bump_dyn="בליטה ב-{f} שבאה והולכת: חציון {med} dB, p90 {p90} dB, מעל 2 dB ב-{pct}% מהזמן",
        bump_static="{f} בולט ב-{x} dB מעל הסביבה כמעט כל הזמן",
        no_bump="בהאזנה הראשונה לא נמצאה בליטה צורמת של 2 dB ומעלה", no_zl="פלאגין ZL לא מותקן, ולכן הורדה קבועה במקומו",
        abrupt="השיא ב-50 ms האחרונים: {x} dBFS", clean_end="השיר נגמר נקי (‎{x} dBFS ב-50 ms האחרונים)",
        not_bass="הבס לא מוביל את השיאים ({x}% מהשיאים החזקים מתחת ל-120 Hz)",
        dense="השיר כבר צפוף או עבר הגבלה", taste="בחירת טעם: רק לפי בקשה",
        audition="מבחן באייפס ב-{probe} LUFS, עם מול בלי: לימיטר מיישר {a}% מול {b}%, שארית קליפר {c} מול {d} dB, DR {e} מול {f}",
        keep=" – נקי יותר באופן מדיד, ולכן נשאר", drop=" – בלי תועלת מדידה, ולכן בחוץ",
        cap="המקור כבר מוגבל ב-{x} LUFS, ולכן אף גרסה לא עוברת {cap} LUFS",
        pruned="לא עבד ב-{t} LUFS: לימיטר מיישר פעיל {pct}% (עד {mx} dB), שארית קליפר {res} dB; בלעדיו הלימיטר הסופי עובד {more} dB עמוק יותר",
        user_tone="הפלאגין שלך, בחירת טעם: כפי שכוון"),
    pro=dict(
        dyneq="{f} · Q {q} · {ch} · טווח {range} dB · סף {thr} dB (p{pct}) · {att}/{rel} ms",
        dyneq_meas="נמדד: {loud} dB כשהפס חזק, {quiet} dB כשהוא שקט",
        dyneq_static="מוריד כמעט אותו דבר גם בשקט: מתנהג כהורדה קבועה",
        tape="מצב {mode} · דרייב {d} · רוויה {s} · ביאס {b} · 4× OS בפאזה ליניארית",
        tape_meas="שינוי עוצמה לפני פיצוי {lu} LU · השהיה {lag} דגימות, יושרה",
        plugin="{role} · שינוי עוצמה לפני פיצוי {lu} LU · השהיה {lag} דגימות, יושרה",
        comp="סף {thr} dB · יחס {ratio}:1 · ברך {knee} · {att}/{rel} ms",
        comp_meas="הנחתה p95 {p95} dB · מקסימום {mx} dB",
        leveler="פעיל {pct}% מהזמן · עד {mx} dB · look-ahead {la} ms · שחרור {rel} ms",
        clipper="{knee}% מהדגימות בברך · שארית {res} dB (עיוות; מתחת ל-‎−30 dB לא נשמע)",
        limiter="עד {mx} dB · p90 {p90} dB · מעל 1 dB ב-{over}% מהזמן · look-ahead {la} ms · שחרור {rel} ms",
        limiter_out="‏{gain} dB לתוך שלב השיאים ← {lufs} LUFS, שיא {tp} dBTP (תקרה {ceil}) · {os}× OS · דיתר TPDF, 24 ביט",
        fade="פייד-אין {fi} ms · פייד-אאוט {fo} ms",
        matchering="רפרנס {ref} ({rl} LUFS) · 44.1 kHz, בלי לימיטר ובלי נרמול · יושר {lag} דגימות",
        summary="יעד {t} LUFS · תקרה {c} dBTP · {os}× OS"),
    pro_why=dict(eq="תיקונים שנקבעו לשיר הזה מההאזנה הראשונה, כל אחד עד ±2 dB ורחב; לכל פס מופיעה הסיבה שנמדדה.",
                 leveler="תופס את הקטעים החזקים ביותר לפני הקליפר, כדי שהלימיטר הסופי יעבוד רק מעט.",
                 clipper="מכות קצרות מתגלחות נקי יותר בקליפר רך מאשר בלימיטר; שארית מתחת ל-‎−30 dB לא נשמעת.",
                 limiter="תקרת True Peak של {ceil} dBTP, ההנחיה של ספוטיפיי למאסטרים חזקים מ-‎−14 LUFS, שאומתה בקידוד אמיתי; ב-oversampling כדי לתפוס שיאים בין הדגימות."),
    forced="הופעל בכוח לצורך השוואה; מבחן הבאייפס היה משאיר אותו בחוץ: ",
    forced_art="הופעל רק כדי שאפשר יהיה לשמוע אותו: בשיר הזה הוא לא שיפר באופן מדיד, ולכן הסקיל היה משאיר אותו בחוץ.",
    role=dict(dynamics="דינמיקה", tone="גוון"),
    ch=dict(mid="M", side="S", stereo="M+S"),
    types=dict(peak="Bell", highshelf="High shelf", lowshelf="Low shelf", hp="High-pass", lp="Low-pass"),
    source_summary=("המקור, ללא שינוי", "המיקס שלך, בלי שום נגיעה: נקודת הייחוס לכל השאר."),
    external=("אין נתוני שרשרת לקובץ הזה", "קובץ שלא רונדר כאן."),
    health={"target loudness": "לא הגיע ליעד: השיר 'דוחף חזרה', ויעד שקט יותר ייצא נקי יותר.",
            "leveler active": "נמעך באופן שמיע: הלימיטר המיישר עובד יותר ממחצית הזמן.",
            "clip residual": "הקליפר עלול להישמע.", "glue compressor": "דחיסת דבק כבדה.",
            "low-band compressor": "הבס עלול 'לנשום'."},
    blurb=dict(rec="מומלץ: הגרסה הכי חזקה שנשארת נקייה.", quiet="הכי דינמית: יותר מקום לנשום, קצת פחות חזקה.",
               loud="חזקה יותר, להשוואה: הלימיטר עובד כאן קשה יותר.", mid="דרך האמצע בעוצמה.",
               tape="חמימה ודינמית: צבע של טייפ אנלוגי.", matchering="מעוצבת לפי שיר הרפרנס שלך.",
               plugin="עם הפלאגין שלך: {label}.", flagged="דגל: {flag}")),
}
CAT = dict(matchering="tone", dyneq="tone", tape="color", hpf="util", eq="tone", lowcomp="dyn", glue="dyn",
           leveler="dyn", clipper="peak", limiter="peak", fade="util")

def health_text(flag, lang):
    for k, v in T[lang]["health"].items():
        if flag.startswith(k): return v
    return flag

def blurb(role, lang, **kw):
    return fill(T[lang]["blurb"][role], **kw)

def decision_why(d, m, lang):
    """A plan.py decision's reason in the page's language, rebuilt from the first listen's measurements."""
    w, s, m = T[lang]["why"], d["stage"], m or {}
    au = d.get("audition")
    try:
        if au: return fill(w["audition"], probe=num(au["probe_lufs"], 0), a=au["on"]["leveler_active_pct"], b=au["off"]["leveler_active_pct"],
                           c=num(au["on"]["clip_residual_db"]), d=num(au["off"]["clip_residual_db"]), e=au["on"]["dr"], f=au["off"]["dr"]) + (w["keep"] if d["used"] else w["drop"])
        if s == "hpf": return fill(w["subsonic"] if d["used"] else w["no_subsonic"], x=num(m["sub25_re_bass_db"]), dc=m.get("dc"))
        if s == "mono_bass": return fill(w["stereo_bass"] if d["used"] else w["mono_enough"], x=num(m["side_minus_mid_below80_db"]))
        if s == "presence_eq":
            o = m["octaves"]; return fill(w["presence"], x=num(o["2000"]["mid_re_total_db"] - o["1000"]["mid_re_total_db"], 1, True))
        if s in ("dynamic_eq", "static_cut") and d.get("f_hz"):
            f = min(m.get("hf_bump_time", {}), key=lambda k: abs(float(k) - d["f_hz"]), default=None)
            bt = m["hf_bump_time"][f] if f else None
            if s == "static_cut": return fill(w["bump_static"], f=hz(d["f_hz"]), x=num(m["hf_bumps_db"].get(f, 0)))
            txt = fill(w["bump_dyn"], f=hz(d["f_hz"]), med=num(bt["median"]), p90=num(bt["p90"]), pct=bt["over2_pct"])
            return txt + ("" if d["used"] else "; " + w["no_zl"])
        if s == "dynamic_eq": return w["no_bump"]
        if s == "fade_out": return fill(w["abrupt"] if d["used"] else w["clean_end"], x=num(m["tail_peak_db"]))
        if s in ("lowcomp", "glue") and not d["used"]:
            if "dense" in d["why"]: return w["dense"]
            return fill(w["not_bass"], x=m["bass_share_of_peaks_pct"])
        if s in ("tape", "matchering") and not d["used"]: return w["taste"]
        if s == "loudness_cap": return fill(w["cap"], x=num(m["lufs"]), cap=d["why"].split("at or below ")[-1].split(" ")[0].replace("-", M))
        if s == "user_plugin" and d["used"]: return w["user_tone"]
    except (KeyError, TypeError, ValueError, IndexError): pass
    return d["why"]

def eq_art(b, t):
    typ, f, g, ch = b["type"], float(b["f"]), b.get("g", 0.0), b.get("ch", "stereo")
    e = t["eq_art"]
    if typ == "hp": return e["mono"] if ch == "side" else e["hp"]
    if typ == "lp": return e["lp"]
    if ch == "side": return e["side_up"] if g > 0 else e["side_dn"]
    reg = "deep" if f < 90 else "bass" if f < 220 else "box" if f < 700 else "mids" if f < 2000 else "pres" if f < 5000 else "bite" if f < 9000 else "air"
    if typ == "highshelf" and f >= 7000: reg = "air"
    return e[reg][0 if g > 0 else 1]

def band_why(b, cfg, D, m, lang):
    w = b.get("why")
    if isinstance(w, dict): return w.get(lang) or next(iter(w.values()), "")
    if w: return w
    if b["type"] == "hp" and b.get("ch") == "side" and "mono_bass" in D: return decision_why(D["mono_bass"], m, lang)
    if b["type"] == "peak" and 2500 <= b["f"] <= 4000 and b.get("g", 0) > 0 and "presence_eq" in D: return decision_why(D["presence_eq"], m, lang)
    for k, v in (cfg.get("_why") or {}).items():       # older drafts: reasons keyed like "peak_45_mid", "shelf_12k_mid"
        for tok in k.split("_"):
            try: fk = float(tok[:-1])*1000 if tok.endswith("k") else float(tok)
            except ValueError: continue
            if abs(fk - b["f"]) < 1 and (b.get("ch", "stereo") in k or not any(c in k for c in ("mid", "side", "stereo"))): return v
    return ""

# The faceplate of each unit on the pages: a model name (a generic code for the skill's own DSP, the real name of a
# real plugin, so it is always clear which plugin ran) and the numbers its graph is drawn from.
MODELS = dict(eq=("MS-5", "builtin"), hpf=("HP-25", "builtin"), lowcomp=("LB-2", "builtin"), glue=("GC-2", "builtin"),
              leveler=("LV-3", "builtin"), clipper=("SC-1", "builtin"), limiter=("TP-4", "builtin"), fade=("FD-1", "builtin"),
              dyneq=("ZL Equalizer 2", "vst3_free"), tape=("CHOW Tape Model", "vst3_free"), matchering=("Matchering 2", "lib_free"))

def unit(id_, st, cfg):
    pk = cfg.get("peak") or {}; ceil = cfg.get("ceiling_dbtp", -2.0); lim = ceil - pk.get("os_margin_db", 0.3)
    clip = lim + pk.get("clip_above_lim_db", 1.5); lev = clip + pk.get("clip_max_depth_db", 2.0)
    if id_.startswith("plugin:"):
        lab = id_.split(":", 1)[1]
        pc = next((q for q in cfg.get("user_plugins") or [] if (q.get("label") or "") == lab), {})
        up = next((q for q in st.get("user_plugins") or [] if q.get("label") == lab), {})
        return dict(model=lab, kind="vst3_user", data=dict(params=pc.get("params") or {}, role=up.get("role"), lu=up.get("level_change_before_makeup_lu")))
    model, kind = MODELS.get(id_, (id_, "builtin"))
    comp = lambda k: dict(thr=(cfg.get(k) or {}).get("thr"), ratio=(cfg.get(k) or {}).get("ratio"), knee=(cfg.get(k) or {}).get("knee"),
                          att=(cfg.get(k) or {}).get("att_ms"), rel=(cfg.get(k) or {}).get("rel_ms"), xover=(cfg.get(k) or {}).get("xover_hz"),
                          p95=(st.get(f"{k}_gr_db") or {}).get("p95"), max=(st.get(f"{k}_gr_db") or {}).get("max"))
    data = {
        "eq": lambda: dict(bands=[{k: b[k] for k in ("type", "f", "g", "q", "s", "order", "ch") if k in b} for b in cfg.get("eq") or []]),
        "dyneq": lambda: dict(bands=[dict(f=b["f"], q=b.get("q", 1), range=b.get("range_db"), thr=b.get("threshold_db"),
                                          loud=b.get("change_when_loud_db"), quiet=b.get("change_when_quiet_db")) for b in (st.get("dyneq") or {}).get("bands", [])]),
        "hpf": lambda: dict(f=cfg.get("hpf_hz"), order=2),
        "lowcomp": lambda: comp("lowcomp"), "glue": lambda: comp("glue"),
        "leveler": lambda: dict(ceil=round(lev, 2), gr_max=st.get("leveler_gr_max_db"), active=st.get("leveler_active_pct"),
                                la=pk.get("lev_lookahead_ms"), rel=pk.get("lev_release_ms")),
        "clipper": lambda: dict(thr=round(clip, 2), knee_pct=st.get("clip_knee_pct"), res=st.get("clip_residual_db")),
        "limiter": lambda: dict(ceil=ceil, lim=round(lim, 2), gr_max=st.get("limiter_gr_max_db"), p90=st.get("limiter_gr_p90_db"),
                                over1=st.get("limiter_over1db_pct"), la=pk.get("lim_lookahead_ms"), rel=pk.get("lim_release_ms"), os=st.get("oversampling", 4)),
        "fade": lambda: dict(fin=cfg.get("fade_in_ms", 5), fout=st.get("fade_out_ms") or 0),
        "tape": lambda: dict(drive=(st.get("tape") or {}).get("drive"), sat=(st.get("tape") or {}).get("saturation"),
                             bias=(cfg.get("tape") or {}).get("bias", 0.5), mode=(cfg.get("tape") or {}).get("mode", "STN")),
        "matchering": lambda: dict(ref=(st.get("matchering") or {}).get("reference")),
    }.get(id_, dict)()
    return dict(model=model, kind=kind, data=data)

def dev(id_, t, on=True, amt=None, val="", pro=(), why_pro="", why_art="", art=(), label=None, cat=None):
    n = t["name"]["plugin" if id_.startswith("plugin:") else id_]
    return dict(id=id_, cat=cat or CAT.get(id_, "color"), on=on, amt=None if amt is None else round(max(0.0, min(1.0, amt)), 2),
                name=dict(pro=fill(n[0], label=label or ""), art=fill(n[1], label=label or "")), val=val,
                pro=[p for p in pro if p], art=[a for a in art if a], why=dict(pro=why_pro, art=why_art))

def chain(st, plan=None, ears=None, lang="en"):
    """The devices of one rendered version, in signal order, plus what was checked and left out."""
    t = T[lang]; w = t["why"]; P = t["pro"]; A = t["art"]
    cfg = st.get("cfg") or {}; pk = cfg.get("peak") or {}
    m = (ears or {}).get("measurements") or {}
    D = {}
    for d in (plan or {}).get("decisions", []): D.setdefault(d["stage"], d)
    out, skipped = [], []
    if st.get("matchering"):
        mc = st["matchering"]
        out.append(dev("matchering", t, val=mc.get("reference", ""), pro=[fill(P["matchering"], ref=mc.get("reference", ""), rl=num(mc.get("ref_lufs", 0)), lag=mc.get("lag", 0))],
                       why_pro=decision_why(D["matchering"], m, lang) if "matchering" in D and D["matchering"]["used"] else "", why_art=A["matchering"]))
    if st.get("dyneq"):
        bands = st["dyneq"]["bands"]; cb = (cfg.get("dyneq") or {}).get("bands") or [{}]*len(bands)
        loud = min((b.get("change_when_loud_db", 0) for b in bands), default=0)
        lines = []
        for b, c in zip(bands, cb):
            lines.append(fill(P["dyneq"], f=hz(b["f"]), q=b.get("q", 1), ch=t["ch"].get(b.get("ch"), b.get("ch")), range=num(b["range_db"], 0), thr=num(b["threshold_db"]),
                              pct=b.get("pct", ""), att=c.get("att_ms", 5), rel=c.get("rel_ms", 120)))
            lq, lw = b.get("change_when_quiet_db"), b.get("change_when_loud_db")
            if lw is not None: lines.append(fill(P["dyneq_meas"], loud=num(lw, 2), quiet=num(lq or 0, 2)) + (" · " + P["dyneq_static"] if lq is not None and lw < 0 and lq <= 0.7*lw else ""))
        ev = [decision_why(d, m, lang) for d in (plan or {}).get("decisions", []) if d["stage"] == "dynamic_eq" and d["used"]]
        where = " / ".join(fill(t["where"], f=hz(b["f"])) for b in bands)
        out.append(dev("dyneq", t, amt=abs(loud)/4, val=" · ".join(f"{hz(b['f'])} {num(b.get('change_when_loud_db', b['range_db']), 1)} dB" for b in bands),
                       pro=lines, why_pro="; ".join(ev), why_art=fill(A["dyneq"], where=where, loud=num(abs(loud), 1))))
    if st.get("tape"):
        tp, tc = st["tape"], cfg.get("tape") or {}
        out.append(dev("tape", t, amt=float(tp.get("drive", 0.3)), val=f"drive {tp.get('drive')} · sat {tp.get('saturation')}",
                       pro=[fill(P["tape"], mode=tc.get("mode", "STN"), d=tp.get("drive"), s=tp.get("saturation"), b=tc.get("bias", 0.5)),
                            fill(P["tape_meas"], lu=num(tp.get("level_change_before_makeup_lu", 0), 2), lag=tp.get("lag", 0))],
                       why_pro=w["taste"], why_art=A["tape"]))
    for i, up in enumerate(st.get("user_plugins") or []):
        pcs = cfg.get("user_plugins") or []; pc = pcs[i] if i < len(pcs) else {}
        dyn = up.get("role") == "dynamics"
        dd = next((d for d in (plan or {}).get("decisions", []) if d["stage"] == "user_plugin" and d.get("label") == up.get("label")), None)
        params = " · ".join(f"{k} {v}" for k, v in list((pc.get("params") or {}).items())[:6])
        forced = bool(dd) and not dd["used"]                   # in the render although the bypass test would leave it out
        why_p = (t["forced"] + decision_why(dd, m, lang)) if forced else (decision_why(dd, m, lang) if dd else "")
        out.append(dev(f"plugin:{up.get('label')}", t, label=up.get("label"), cat="dyn" if dyn else "color", val=t["role"].get(up.get("role"), up.get("role")),
                       amt=min(1.0, abs(up.get("level_change_before_makeup_lu") or 0)/4) if dyn else None,
                       pro=[fill(P["plugin"], role=t["role"].get(up.get("role"), ""), lu=num(up.get("level_change_before_makeup_lu", 0), 2), lag=up.get("lag", 0)), params],
                       why_pro=why_p, why_art=(t["forced_art"] if forced else A["plugin_dyn"] if dyn else A["plugin_tone"])))
    if cfg.get("hpf_hz"):
        out.append(dev("hpf", t, val=hz(cfg["hpf_hz"]), pro=[f"{hz(cfg['hpf_hz'])} · 12 dB/oct"],
                       why_pro=decision_why(D["hpf"], m, lang) if "hpf" in D else "", why_art=fill(A["hpf"], f=hz(cfg["hpf_hz"]))))
    eq = cfg.get("eq") or []
    if eq:
        lines, arts = [], []
        for b in eq:
            q = f"Q {b['q']}" if "q" in b else (f"S {b['s']}" if "s" in b else f"{6*b.get('order', 2)} dB/oct")
            g = f" {num(b['g'], 1, True)} dB" if "g" in b else ""
            why = band_why(b, cfg, D, m, lang)
            lines.append(f"{t['types'].get(b['type'], b['type'])} {hz(b['f'])}{g} · {q} · {t['ch'].get(b.get('ch', 'stereo'))}" + (f"\n{why}" if why else ""))
            arts.append(eq_art(b, t))
        gains = [abs(b.get("g", 0)) for b in eq]
        out.append(dev("eq", t, amt=max(gains + [0])/4, val=f"{len(eq)} " + ("bands" if lang == "en" else "פסים"), pro=lines,
                       why_pro=t["pro_why"]["eq"], why_art=A["eq"], art=list(dict.fromkeys(arts))))
    for k in ("lowcomp", "glue"):
        if cfg.get(k):
            c, gr = cfg[k], st.get(f"{k}_gr_db") or {}
            out.append(dev(k, t, amt=(gr.get("p95") or 0)/3, val=f"GR p95 {num(gr.get('p95', 0))} dB",
                           pro=[fill(P["comp"], thr=num(c["thr"]), ratio=c["ratio"], knee=c["knee"], att=c["att_ms"], rel=c["rel_ms"]),
                                fill(P["comp_meas"], p95=num(gr.get("p95", 0)), mx=num(gr.get("max", 0)))],
                           why_pro=decision_why(D[k], m, lang) if k in D else "", why_art=A[k]))
    used = st.get("peak_stages_used") or ["leveler", "clipper", "limiter"]
    pr = st.get("pruned") or {}
    if "leveler" in used:
        out.append(dev("leveler", t, amt=max((st.get("leveler_active_pct") or 0)/30, (st.get("leveler_gr_max_db") or 0)/6), val=f"{st.get('leveler_active_pct', 0)}% · {num(st.get('leveler_gr_max_db', 0))} dB",
                       pro=[fill(P["leveler"], pct=st.get("leveler_active_pct", 0), mx=num(st.get("leveler_gr_max_db", 0)), la=pk.get("lev_lookahead_ms", 3), rel=pk.get("lev_release_ms", 200))],
                       why_pro=t["pro_why"]["leveler"], why_art=fill(A["leveler"], pct=st.get("leveler_active_pct", 0))))
    if "clipper" in used:
        out.append(dev("clipper", t, amt=(st.get("clip_knee_pct") or 0)/8, val=f"{st.get('clip_knee_pct', 0)}%",
                       pro=[fill(P["clipper"], knee=st.get("clip_knee_pct", 0), res=num(st.get("clip_residual_db") or 0))], why_pro=t["pro_why"]["clipper"], why_art=A["clipper"]))
    ceil = cfg.get("ceiling_dbtp", -2)
    out.append(dev("limiter", t, amt=(st.get("limiter_gr_max_db") or 0)/6, val=f"{num(st.get('limiter_gr_max_db', 0))} dB",
                   pro=[fill(P["limiter"], mx=num(st.get("limiter_gr_max_db", 0)), p90=num(st.get("limiter_gr_p90_db", 0)), over=st.get("limiter_over1db_pct", 0),
                             la=pk.get("lim_lookahead_ms", 1.5), rel=pk.get("lim_release_ms", 80)),
                        fill(P["limiter_out"], gain=num(st.get("gain_into_peak_stage_db", 0), 1, True), lufs=num(st.get("lufs", 0)), tp=num(st.get("true_peak_dbtp", 0), 2),
                             ceil=gnum(ceil), os=st.get("oversampling", 4))],
                   why_pro=fill(t["pro_why"]["limiter"], ceil=gnum(ceil)), why_art=fill(A["limiter"], lufs=gnum(st.get("target_lufs", st.get("lufs", 0))), ceil=gnum(ceil))))
    fo, fi = st.get("fade_out_ms") or 0, cfg.get("fade_in_ms", 5)
    out.append(dev("fade", t, val=f"{fo} ms" if fo else f"{fi} ms", pro=[fill(P["fade"], fi=fi, fo=fo)],
                   why_pro=decision_why(D["fade_out"], m, lang) if fo and "fade_out" in D else "", why_art=fill(A["fade"], ms=fo) if fo else A["fade_in"]))
    # what was checked and left out, with the reason
    for s in pr.get("stages", []):
        skipped.append(dict(id=s, name=dict(pro=t["name"][s][0], art=t["name"][s][1]), why=dict(art=t["skip"][s], pro=fill(w["pruned"],
                            t=num(st.get("target_lufs", 0), 0), pct=pr.get("leveler_active_pct", "?"), mx=num(pr.get("leveler_gr_max_db", 0)),
                            res=num(pr["clip_residual_db"]) if pr.get("clip_residual_db") is not None else "?",
                            more=num(pr.get("limiter_change_db", 0), 2, True)) if "limiter_change_db" in pr else pr.get("why", ""))))
    have = {d["id"] for d in out}
    for d in (plan or {}).get("decisions", []):
        s = d["stage"]
        if d["used"] and s != "user_plugin": continue
        key = {"hpf": "hpf", "tape": "tape", "matchering": "matchering"}.get(s, s)
        if key in have or s in ("static_cut", "loudness_cap"): continue
        if s == "user_plugin":
            if d["used"]: continue
            name = (fill(t["name"]["plugin"][0], label=d.get("label", "")), fill(t["name"]["plugin"][1], label=d.get("label", "")))
            art = t["skip"]["plugin"]
        elif s in ("lowcomp", "glue"):
            name = t["name"][s]; art = t["skip"][s + "_dense"] if "dense" in d["why"] else t["skip"][s]
        elif s == "fade_out":
            continue                                                  # the fade device already says it
        else:
            name = t["name"].get(s, (s, s)); art = t["skip"].get(s, "")
        skipped.append(dict(id=s if s != "user_plugin" else f"plugin:{d.get('label')}", name=dict(pro=name[0], art=name[1]), why=dict(pro=decision_why(d, m, lang), art=art)))
    for d in out: d.update(unit(d["id"], st, cfg))
    notes = [health_text(h, lang) for h in st.get("health") or []]
    cap = D.get("loudness_cap")
    summary = dict(pro=fill(P["summary"], t=gnum(st.get("target_lufs", cfg.get("target_lufs", 0))), c=gnum(ceil), os=st.get("oversampling", 4)),
                   flags=notes, cap=decision_why(cap, m, lang) if cap else "")
    return dict(summary=summary, devices=out, skipped=skipped)

def source_chain(lang):
    t = T[lang]; return dict(summary=dict(pro=t["source_summary"][0], art=t["source_summary"][1], flags=[], cap=""), devices=[], skipped=[], source=True)

def external_chain(lang):
    t = T[lang]; return dict(summary=dict(pro=t["external"][0], art=t["external"][1], flags=[], cap=""), devices=[], skipped=[], external=True)

def blurbs(V, lang):
    """The Artist view's one-liner per version. V: dicts with title, rec, target (None = the source), tape, matchering, plugin, flags."""
    masters = [v for v in V if v.get("target") is not None]
    lo = min((v["target"] for v in masters), default=None); rec = next((v for v in V if v.get("rec")), None)
    out = []
    for v in V:
        if v.get("target") is None: out.append(T[lang]["source_summary"][1] if v.get("source") else T[lang]["external"][1]); continue
        if v.get("flags"): out.append(blurb("flagged", lang, flag=health_text(v["flags"][0], lang))); continue
        if v.get("rec"): out.append(blurb("rec", lang)); continue
        if v.get("tape"): out.append(blurb("tape", lang)); continue
        if v.get("matchering"): out.append(blurb("matchering", lang)); continue
        if v.get("plugin"): out.append(blurb("plugin", lang, label=v["plugin"])); continue
        if rec and v["target"] > rec.get("target", 0): out.append(blurb("loud", lang)); continue
        out.append(blurb("quiet", lang) if v["target"] == lo else blurb("mid", lang))
    return out

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("stats"); ap.add_argument("--plan"); ap.add_argument("--ears"); ap.add_argument("--lang", default="en")
    a = ap.parse_args(); J = lambda p: json.load(open(p)) if p else None
    c = chain(J(a.stats), J(a.plan), J(a.ears), a.lang)
    print(c["summary"]["pro"] + ("  |  " + "; ".join(c["summary"]["flags"]) if c["summary"]["flags"] else ""))
    for i, d in enumerate(c["devices"], 1):
        amt = "" if d["amt"] is None else f"{d['amt']:.2f}"
        print(f"{i:2d} {d['name']['pro']:32s} {d['val']:24s} {amt}")
        for p in d["pro"]: print("      " + p)
        if d["why"]["pro"]: print("      why: " + d["why"]["pro"])
    for s in c["skipped"]: print(f"   off {s['name']['pro']:28s} {s['why']['pro']}")

if __name__ == "__main__":
    main()
