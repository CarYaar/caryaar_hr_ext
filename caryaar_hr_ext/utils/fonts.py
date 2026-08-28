"""Install the app's brand fonts where wkhtmltopdf can see them.

The bench's wkhtmltopdf ignores @font-face (data URI and file:// both
tested); it resolves fonts only through fontconfig. This copies the
subset TTFs shipped in caryaar_hr_ext/fonts/ into ~/.fonts (frappe user,
no root needed) and refreshes the cache. Runs on every migrate so a
recreated container heals itself. Fonts are cosmetic: never block a
migrate over them.
"""
import pathlib
import shutil
import subprocess


def install_fonts():
    try:
        src = pathlib.Path(__file__).resolve().parent.parent / "fonts"
        dst = pathlib.Path.home() / ".fonts"
        dst.mkdir(exist_ok=True)
        changed = False
        for ttf in src.glob("*.ttf"):
            target = dst / ttf.name
            if not target.exists() or target.stat().st_size != ttf.stat().st_size:
                shutil.copy2(ttf, target)
                changed = True
        if changed:
            subprocess.run(["fc-cache", "-f"], check=False, capture_output=True)
    except Exception:
        pass
