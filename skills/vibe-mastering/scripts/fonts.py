"""The pages' fonts ship with the skill (assets/fonts, SIL Open Font License 1.1, from Google Fonts) and are embedded
into each page as it is built, so a page never calls a font server: it looks the same offline, and opening it tells
nobody anything.
  font_faces({"Heebo", "JetBrains Mono"})  ->  @font-face rules with the woff2 files inlined
assets/fonts/fonts.json lists each file with its family, weight (one weight, or a range for a variable font), subset
(latin or hebrew) and unicode-range."""
import os, json, base64

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "fonts")


def font_faces(families):
    faces = json.load(open(os.path.join(D, "fonts.json")))["faces"]
    out = []
    for f in faces:
        if f["family"] not in families: continue
        b64 = base64.b64encode(open(os.path.join(D, f["file"]), "rb").read()).decode()
        out.append(f"@font-face{{font-family:'{f['family']}';font-style:normal;font-weight:{f['weight']};font-display:swap;"
                   f"src:url(data:font/woff2;base64,{b64}) format('woff2');unicode-range:{f['unicode_range']}}}")
    return "\n".join(out)
