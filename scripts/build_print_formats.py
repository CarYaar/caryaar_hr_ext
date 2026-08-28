#!/usr/bin/env python3
"""Generate fixtures/print_format.json — the three identity print formats.

CY Card Front / CY Card Back (Employee, CR80 58x89.6mm incl. 2mm bleed)
and CY Internship Certificate (A4 landscape). Design source: the approved
canvas (admin-studio theme). Fonts are subset to Latin and embedded as
base64 so the PDFs need nothing from the bench image.

Targets wkhtmltopdf (the bench's PDF generator): absolute mm positioning,
-webkit- prefixes, no flexbox, no writing-mode (rotation via transform).
Frappe lifts page-width/page-height/margins from the `.print-format` CSS
rule into wkhtmltopdf options (frappe.utils.pdf.read_options_from_html).

Run:  python3 scripts/build_print_formats.py \
        --fonts /Users/sahaib/caryaar/caryaar-brand-kit/assets/fonts
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import pathlib
import re

from fontTools import subset

UNICODES = "U+0020-007E,U+00A0-00FF,U+2018-2019,U+201C-201D,U+20B9"
VERIFY = "https://verify.caryaar.com"

# wkhtmltopdf on the bench ignores @font-face entirely (data URI and
# file:// both tested 28-Aug); fonts resolve ONLY via fontconfig. The app
# ships subset TTFs in caryaar_hr_ext/fonts/ and installs them to
# ~/.fonts on every migrate (utils/fonts.py). fontconfig registers the
# ExtraBold cut as its own family, hence 'Outfit ExtraBold' below.
FONT_NOTE = "/* fonts resolve via fontconfig; installed by after_migrate hook */"

# palette
INK = "#1A1A2E"
ENGINE = "#6D28D9"
DEPTH = "#1E0A3C"
AMBER = "#F59E0B"
GHOST = "#F5F3FF"
LAVENDER = "#E8D5F5"
MIST = "#C4B5FD"
GREY = "#6B6980"
BODY = "#4B4960"


def subset_b64(path: pathlib.Path) -> str:
    options = subset.Options()
    font = subset.load_font(str(path), options)
    ss = subset.Subsetter(options)
    ss.populate(unicodes=subset.parse_unicodes(UNICODES))
    ss.subset(font)
    buf = io.BytesIO()
    font.save(buf)
    return base64.b64encode(buf.getvalue()).decode()


def font_css(fonts_dir: pathlib.Path, faces: list[tuple[str, str, int]]) -> str:
    out = []
    for fname, family, weight in faces:
        b64 = subset_b64(fonts_dir / fname)
        out.append(
            f"@font-face {{ font-family: '{family}'; font-weight: {weight}; "
            f"src: url(data:font/ttf;base64,{b64}) format('truetype'); }}"
        )
    return "\n".join(out)


def wordmark_png(width_mm: float, px: int = 1400) -> str:
    """Certificate wordmark as a PNG data URI. wkhtmltopdf renders the
    inline SVG on the card front but silently drops it on the certificate
    sheet; a raster img is deterministic everywhere."""
    import base64 as _b64

    import cairosvg

    src = pathlib.Path(
        "/Users/sahaib/caryaar/caryaar-brand-kit/public/brand/horizontal/wordmark-original.svg"
    ).read_bytes()
    png = cairosvg.svg2png(bytestring=src, output_width=px)
    b64 = _b64.b64encode(png).decode()
    return (
        f'<img src="data:image/png;base64,{b64}" style="width: {width_mm}mm; display: block;">'
    )


def wordmark_svg(color: str, width_mm: float) -> str:
    src = pathlib.Path(
        "/Users/sahaib/caryaar/caryaar-brand-kit/public/brand/horizontal/wordmark-original.svg"
    ).read_text()
    inner = re.search(r"<svg[^>]*>(.*)</svg>", src, re.S).group(1)
    inner = re.sub(r"<style.*?</style>", "", inner, flags=re.S)
    inner = inner.replace('class="st0"', f'fill="{color}"')
    return (
        f'<svg viewBox="0 0 1568.01 349.5" style="width: {width_mm}mm; display: block;">'
        + inner
        + "</svg>"
    )


PERSON_ICON = (
    '<svg viewBox="0 0 24 24" style="width: 10mm; height: 10mm;" fill="none" '
    f'stroke="{MIST}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">'
    '<circle cx="12" cy="8" r="4"></circle><path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7"></path></svg>'
)


def page_css(w: str, h: str, extra: str = "") -> str:
    return (
        f".print-format {{ page-width: {w}; page-height: {h}; margin-top: 0mm; "
        f"margin-bottom: 0mm; margin-left: 0mm; margin-right: 0mm; {extra} }}\n"
        ".print-format { padding: 0 !important; }\n"
        ".letter-head, .print-heading { display: none !important; }\n"
        "body { margin: 0; padding: 0; }\n"
        "* { -webkit-print-color-adjust: exact; box-sizing: border-box; }"
    )


def card_front(fonts_dir: pathlib.Path) -> str:
    fonts = FONT_NOTE
    wm = wordmark_svg(ENGINE, 25.7)
    return f"""<style>
{fonts}
{page_css("58mm", "89.6mm")}
.card {{ position: relative; width: 58mm; height: 89.6mm; background: {GHOST};
  font-family: 'DM Sans', sans-serif; color: {INK}; overflow: hidden;
  border-radius: 4.2mm; }}
.nb {{ background: #FFFFFF; border: 0.3mm solid {INK}; border-radius: 1.8mm; }}
.lbl {{ font-size: 6pt; font-weight: 700; letter-spacing: 0.1mm; color: {GREY};
  text-transform: uppercase; white-space: nowrap; line-height: 1.25; }}
.val {{ font-size: 6.5pt; font-weight: normal; white-space: nowrap; line-height: 1.25; }}
td {{ padding: 0; }}
</style>
<div class="print-format">
<div class="card">
  <div class="nb" style="position: absolute; left: 5.2mm; top: 5mm; width: 47.6mm; height: 11mm;
       -webkit-box-shadow: 0.5mm 0.5mm 0 0 {INK};">
    <div style="width: 25.7mm; margin: 3.1mm auto 0;">{wm}</div>
  </div>
  <div class="nb" style="position: absolute; left: 16.75mm; top: 17.4mm; width: 24.5mm; height: 23.6mm;
       -webkit-box-shadow: 0.6mm 0.6mm 0 0 {INK}; text-align: center;">
    {{% if doc.image and doc.image.startswith("/files/") %}}
      <img src="{{{{ doc.image }}}}" style="width: 100%; height: 100%; object-fit: cover; border-radius: 1.5mm;">
    {{% else %}}
      <div style="margin-top: 6.8mm;">{PERSON_ICON}</div>
    {{% endif %}}
  </div>
  <div style="position: absolute; left: 0; top: 43.6mm; width: 58mm; text-align: center;
       font-family: 'Outfit ExtraBold', 'Outfit', sans-serif; font-weight: normal; font-size: 10.6pt;">
    {{{{ doc.employee_name }}}}</div>
  <div style="position: absolute; left: 5mm; top: 49.2mm; width: 48mm; text-align: center;">
    <span style="display: inline-block; background: {AMBER}; border: 0.3mm solid {INK};
      border-radius: 1mm; -webkit-box-shadow: 0.35mm 0.35mm 0 0 {INK}; padding: 0.7mm 2.2mm;
      font-size: 4.4pt; font-weight: 700; letter-spacing: 0.25mm; text-transform: uppercase; line-height: 1.3;">
      {{{{ doc.designation or "Team member" }}}}</span>
  </div>
  <div class="nb" style="position: absolute; left: 6.5mm; top: 58.6mm; width: 45mm;
       -webkit-box-shadow: 0.5mm 0.5mm 0 0 {INK}; padding: 1.2mm 2mm 1.6mm; box-sizing: border-box;">
    <div style="overflow: hidden; border-bottom: 0.2mm solid {LAVENDER}; padding: 0.9mm 0;">
      <span class="lbl" style="float: left;">Employee id</span>
      <span class="val" style="float: right; font-weight: 700;">{{{{ doc.name }}}}</span></div>
    <div style="overflow: hidden; border-bottom: 0.2mm solid {LAVENDER}; padding: 0.9mm 0;">
      <span class="lbl" style="float: left;">Phone</span>
      <span class="val" style="float: right;">{{{{ doc.cell_number or "" }}}}</span></div>
    <div style="overflow: hidden; padding: 0.9mm 0 0.3mm;">
      <span class="lbl" style="float: left;">Blood group</span>
      <span class="val" style="float: right; font-weight: 700; color: {ENGINE};">{{{{ doc.blood_group or "" }}}}</span></div>
  </div>
  <div style="position: absolute; left: 0; bottom: 7.75mm; width: 58mm; height: 0.3mm; background: {INK};"></div>
  <div style="position: absolute; left: 0; bottom: 0; width: 58mm; height: 7.75mm; background: {ENGINE}; border-radius: 0 0 4.2mm 4.2mm;">
    <span style="position: absolute; left: 5.2mm; top: 2.1mm; color: #FFFFFF; font-size: 4.8pt; font-weight: 500;">www.caryaar.com</span>
    <span style="position: absolute; right: 5.2mm; top: 2.1mm; color: {MIST}; font-size: 4.8pt; font-weight: 700;">{{{{ doc.cy_card_serial or "" }}}}</span>
  </div>
</div>
</div>"""


def card_back(fonts_dir: pathlib.Path) -> str:
    fonts = FONT_NOTE
    return f"""<style>
{fonts}
{page_css("58mm", "89.6mm")}
.card {{ position: relative; width: 58mm; height: 89.6mm; background: #FFFFFF;
  font-family: 'DM Sans', sans-serif; color: {INK}; overflow: hidden;
  border-radius: 4.2mm; border: 0.15mm solid #E9E7F2; }}
.lbl {{ font-size: 4.2pt; font-weight: 700; letter-spacing: 0.25mm; color: {GREY};
  text-transform: uppercase; white-space: nowrap; }}
.small {{ font-size: 4.8pt; line-height: 1.5; }}
</style>
<div class="print-format">
<div class="card">
  <!-- serial channel: left 12mm stays ink free for the factory RFID serial;
       only the label (top 24mm) and the boundary hairline are ours -->
  <div style="position: absolute; left: 2.2mm; top: 21mm; width: 20mm; height: 3mm;
       -webkit-transform: rotate(-90deg); -webkit-transform-origin: left top;
       font-size: 4.4pt; font-weight: 700; letter-spacing: 0.4mm; color: {GREY};
       text-transform: uppercase; white-space: nowrap;">Card serial</div>
  <div style="position: absolute; left: 12mm; top: 0; width: 0.3mm; height: 89.6mm; background: {INK};"></div>
  <div style="position: absolute; left: 13.6mm; top: 4.6mm; width: 41mm;">
    <div style="font-family: 'Outfit ExtraBold', 'Outfit', sans-serif; font-weight: normal; font-size: 6.4pt; line-height: 1.3;">This card belongs to CarYaar Auto Pvt. Ltd.</div>
    <div class="small" style="color: {BODY}; margin-top: 1mm;">If found, please return it to the address below or call us. The finder's courtesy is appreciated.</div>
    <div style="background: {LAVENDER}; border: 0.3mm solid {INK}; border-radius: 1.5mm;
         -webkit-box-shadow: 0.35mm 0.35mm 0 0 {INK}; padding: 1.6mm 2mm; margin-top: 2mm;">
      <div class="lbl" style="color: {ENGINE};">Office address</div>
      <div class="small" style="margin-top: 0.5mm;">#103, CarYaar, Gopala Residency C.H.S., Plot no 27, MAFCO Rd, Sector 24, Vashi, Navi Mumbai, Maharashtra 400703</div>
      <div class="small" style="margin-top: 0.7mm;">+91 98676 59660 &middot; contactus@caryaar.com</div>
    </div>
    <table style="width: 100%; border-collapse: collapse; margin-top: 2mm;">
      <tr>
        <td style="width: 50%;"><div class="lbl">Issued</div>
          <div style="font-size: 5.4pt; font-weight: 700;">{{{{ frappe.utils.format_date(doc.cy_card_issued_on, "MMM yyyy") if doc.cy_card_issued_on else "" }}}}</div></td>
        <td><div class="lbl">Valid through</div>
          <div style="font-size: 5.4pt; font-weight: 700;">{{{{ frappe.utils.format_date(doc.cy_card_valid_through, "MMM yyyy") if doc.cy_card_valid_through else "" }}}}</div></td>
      </tr>
    </table>
    <table style="width: 100%; border-collapse: collapse; margin-top: 1.4mm;">
      <tr><td class="lbl">Emergency</td>
          <td style="text-align: right; font-size: 5.4pt; font-weight: 700;">{{{{ doc.emergency_phone_number or "" }}}}</td></tr>
    </table>
    <table style="border-collapse: collapse; margin-top: 2mm;"><tr>
      <td style="vertical-align: top;">
        <div style="background: #FFFFFF; border: 0.3mm solid {INK}; border-radius: 1.5mm;
             -webkit-box-shadow: 0.35mm 0.35mm 0 0 {INK}; padding: 1mm; width: 15mm; height: 15mm;">
          <img src="{{{{ qr_data_uri('https://verify.caryaar.com/v/' ~ (doc.cy_card_serial or 'unassigned')) }}}}" style="width: 12.6mm; height: 12.6mm; display: block;">
        </div></td>
      <td style="vertical-align: middle; padding-left: 1.8mm;">
        <div class="small" style="color: {BODY};">Scan to verify this card.</div>
        <div class="small" style="font-weight: 700; color: {ENGINE};">verify.caryaar.com</div></td>
    </tr></table>
    <div style="text-align: right; margin-top: 2.2mm;">
      <div style="display: inline-block; width: 17mm; height: 0.3mm; background: {INK};"></div>
      <div class="small" style="color: {GREY};">Authorised signatory</div>
    </div>
  </div>
  <div style="position: absolute; left: 12.3mm; bottom: 0; right: 0; height: 6mm; background: {ENGINE}; text-align: center; border-radius: 0 0 4.2mm 0;">
    <span style="display: inline-block; margin-top: 1.7mm; color: #FFFFFF; font-size: 4.2pt; font-weight: 500; letter-spacing: 0.15mm;">125 kHz access card &middot; do not punch or bend</span>
  </div>
</div>
</div>"""


def certificate(fonts_dir: pathlib.Path) -> str:
    fonts = FONT_NOTE
    wm = wordmark_png(58)
    sig = pathlib.Path(__file__).resolve().parent.joinpath("signature_b64.txt").read_text().strip()
    return f"""<style>
{fonts}
{page_css("297mm", "210mm")}
.page {{ position: relative; width: 297mm; height: 210mm; background: {GHOST};
  font-family: 'DM Sans', sans-serif; color: {INK}; overflow: hidden; }}
</style>
<div class="print-format">
<div class="page">
  <div style="position: absolute; left: 10mm; top: 9.5mm; width: 277mm; height: 191mm;
       background: #FFFFFF; border: 0.75mm solid {DEPTH};">
    <div style="position: absolute; left: 2.5mm; top: 2.5mm; right: 2.5mm; bottom: 2.5mm;
         border: 0.25mm solid {AMBER};"></div>
    <div style="position: absolute; left: 0; top: 0; width: 30mm; height: 2.5mm; background: {ENGINE};"></div>
    <div style="position: absolute; left: 0; top: 0; width: 2.5mm; height: 30mm; background: {ENGINE};"></div>
    <div style="position: absolute; right: 0; bottom: 0; width: 30mm; height: 2.5mm; background: {ENGINE};"></div>
    <div style="position: absolute; right: 0; bottom: 0; width: 2.5mm; height: 30mm; background: {ENGINE};"></div>
    {{% if doc.docstatus == 2 %}}
    <div style="position: absolute; left: 30mm; top: 80mm; width: 220mm; text-align: center;
         -webkit-transform: rotate(-18deg); font-family: 'Outfit ExtraBold', 'Outfit', sans-serif; font-weight: normal;
         font-size: 34mm; color: rgba(231, 76, 60, 0.22); letter-spacing: 4mm;">REVOKED</div>
    {{% endif %}}
    <div style="position: absolute; left: 109.5mm; top: 11mm; width: 58mm; height: 13mm;">{wm}</div>
    <div style="position: absolute; left: 0; top: 31.5mm; width: 277mm; text-align: center; font-weight: 700;
         font-size: 10.5pt; letter-spacing: 1.1mm; color: {ENGINE}; text-transform: uppercase;">Internship program</div>
    <div style="position: absolute; left: 0; top: 37mm; width: 277mm; text-align: center;
         font-family: 'Outfit ExtraBold', 'Outfit', sans-serif; font-weight: normal; font-size: 40pt;">Certificate of completion</div>
    <div style="position: absolute; left: 0; top: 60mm; width: 277mm; text-align: center;
         font-size: 12.5pt; color: {BODY};">This is to certify that</div>
    <div style="position: absolute; left: 0; top: 67mm; width: 277mm; text-align: center;
         font-family: 'Outfit', sans-serif; font-weight: 700; font-size: 29pt; color: {DEPTH};">{{{{ doc.intern_name }}}}</div>
    <div style="position: absolute; left: 106mm; top: 84mm; width: 65mm; height: 0.75mm; background: {AMBER};"></div>
    <div style="position: absolute; left: 43.5mm; top: 90mm; width: 190mm; text-align: center;
         font-size: 12.5pt; line-height: 1.65; color: {BODY};">has successfully completed an internship as
      {{{{ doc.role_title }}}} at CarYaar Auto Pvt. Ltd. from
      {{{{ frappe.utils.format_date(doc.start_date, "d MMM yyyy") }}}} to
      {{{{ frappe.utils.format_date(doc.end_date, "d MMM yyyy") }}}}, contributing with
      dedication, professional conduct and genuine curiosity.</div>
    <table style="position: absolute; left: 16mm; right: 16mm; bottom: 12mm; width: 245mm;
         border-collapse: collapse;"><tr>
      <td style="width: 33%; vertical-align: bottom;">
        <div style="font-size: 11pt; font-weight: 700;">{{{{ frappe.utils.format_date(doc.issued_on, "d MMM yyyy") if doc.issued_on else "" }}}}</div>
        <div style="width: 48mm; height: 0.5mm; background: {INK}; margin-top: 1.5mm;"></div>
        <div style="font-size: 9.5pt; color: {GREY}; margin-top: 1.5mm;">Date of issue</div></td>
      <td style="width: 34%; text-align: center; vertical-align: bottom;">
        <img src="{{{{ qr_data_uri('https://verify.caryaar.com/c/' ~ doc.name) }}}}" style="width: 20mm; height: 20mm;">
        <div style="font-size: 10pt; font-weight: 700; margin-top: 1mm;">Certificate no. {{{{ doc.name }}}}</div>
        <div style="font-size: 9pt; color: {GREY};">Verify: verify.caryaar.com/c/{{{{ doc.name }}}}</div></td>
      <td style="width: 33%; text-align: center; vertical-align: bottom;">
        <img src="data:image/png;base64,{sig}" style="height: 10mm; display: block; margin: 0 auto 1mm;">
        <div style="margin: 0 auto; width: 56mm; height: 0.5mm; background: {INK};"></div>
        <div style="font-size: 10.5pt; font-weight: 700; margin-top: 1.5mm;">Sahaib Singh Arora</div>
        <div style="font-size: 9pt; color: {GREY};">Founder, CarYaar</div></td>
    </tr></table>
  </div>
</div>
</div>"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fonts", required=True)
    args = ap.parse_args()
    fonts_dir = pathlib.Path(args.fonts)

    records = [
        {
            "doctype": "Print Format",
            "name": "CY Card Front",
            "doc_type": "Employee",
            "module": "Caryaar Hr Ext",
            "print_format_type": "Jinja",
            "custom_format": 1,
            "standard": "No",
            "disabled": 0,
            "font_size": 0,
            "margin_top": 0.0, "margin_bottom": 0.0, "margin_left": 0.0, "margin_right": 0.0,
            "html": card_front(fonts_dir),
        },
        {
            "doctype": "Print Format",
            "name": "CY Card Back",
            "doc_type": "Employee",
            "module": "Caryaar Hr Ext",
            "print_format_type": "Jinja",
            "custom_format": 1,
            "standard": "No",
            "disabled": 0,
            "font_size": 0,
            "margin_top": 0.0, "margin_bottom": 0.0, "margin_left": 0.0, "margin_right": 0.0,
            "html": card_back(fonts_dir),
        },
        {
            "doctype": "Print Format",
            "name": "CY Internship Certificate",
            "doc_type": "Internship Certificate",
            "module": "Caryaar Hr Ext",
            "print_format_type": "Jinja",
            "custom_format": 1,
            "standard": "No",
            "disabled": 0,
            "font_size": 0,
            "margin_top": 0.0, "margin_bottom": 0.0, "margin_left": 0.0, "margin_right": 0.0,
            "html": certificate(fonts_dir),
        },
    ]
    out = pathlib.Path(__file__).resolve().parent.parent / "caryaar_hr_ext" / "fixtures" / "print_format.json"
    out.write_text(json.dumps(records, indent=1))
    sizes = [len(r["html"]) for r in records]
    print(f"wrote {out} html sizes: {sizes}")


if __name__ == "__main__":
    main()
