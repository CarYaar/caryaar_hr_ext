"""Employee photo for print formats, as an embedded data URI.

Print formats render server-side for an authenticated user, so private
files are fine to include (unlike the public verify page, which keeps
its /files/-only guard). The photo is EXIF-rotated and downscaled so a
5 MB phone photo does not become a 5 MB card PDF. Returns "" when there
is no usable photo; the template then falls back to the placeholder.
"""
import base64
import io

import frappe


def photo_data_uri(path):
    try:
        if not path or path.startswith("http"):
            return ""
        rows = frappe.get_all("File", filters={"file_url": path}, fields=["name"], limit=1)
        if rows:
            content = frappe.get_doc("File", rows[0].name).get_content()
        else:
            from frappe.utils.file_manager import get_file

            content = get_file(path)[1]
        if isinstance(content, str):
            content = content.encode()

        from PIL import Image, ImageOps

        img = Image.open(io.BytesIO(content))
        img = ImageOps.exif_transpose(img)
        img.thumbnail((700, 900))
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=88)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ""
