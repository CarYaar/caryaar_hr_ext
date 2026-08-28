import base64
import io

import qrcode


def qr_data_uri(url: str) -> str:
    """PNG QR as a data URI, for jinja print formats and web templates."""
    img = qrcode.make(url, box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
