"""The ID card back (founder, 02-Oct-2026): cards are printed on plain PVC, and the RFID access card stays
separate so it can be reused, so the back no longer keeps an ink-free strip for a factory RFID serial and no
longer calls itself an access card."""
from pathlib import Path

from scripts import build_print_formats as build

BACK = build.card_back(Path("."))


def test_the_back_has_no_rfid_serial_strip() -> None:
    assert "Card serial" not in BACK and "serial channel" not in BACK and "RFID" not in BACK
    assert "left: 12mm" not in BACK and "left: 12.3mm" not in BACK


def test_the_back_uses_the_full_card_width() -> None:
    assert "left: 4.6mm; top: 4.6mm; width: 48.8mm;" in BACK
    assert "left: 0; bottom: 0; right: 0; height: 6mm" in BACK and "border-radius: 0 0 4.2mm 4.2mm" in BACK


def test_the_back_is_not_called_an_access_card_and_still_verifies() -> None:
    assert "125 kHz" not in BACK and "access card" not in BACK
    assert "verify.caryaar.com/v/" in BACK and "Authorised signatory" in BACK
    assert "—" not in BACK
