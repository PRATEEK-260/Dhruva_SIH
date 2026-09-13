"""QR transport for the capsule.

CLAUDE.md is explicit that the wire format is identical across QR, Bluetooth and
SMS — this module adds only the QR-specific step of turning that already-encoded
string into a scannable image. Encoding, the base32 alphabet, and the
QR-alphanumeric-safety guarantee all live in dhruva.codec.codec and are tested
there (TestTransports.test_base32_is_qr_alphanumeric_safe); this file does not
duplicate any of it.
"""

from __future__ import annotations

import io

import segno

from dhruva.codec.codec import Capsule, encode, to_base32


def qr_svg(capsule: Capsule, *, scale: int = 4) -> str:
    """Render the capsule as a self-contained SVG string. No filesystem write,
    no network — matches the decoder's own purity requirement, since this is the
    thing a shore-side tool renders and a phone camera reads back.

    error="m" (15% recovery) is segno's default and is what a QR printed on
    paper or shown on a possibly-scratched phone screen needs; "h" would shrink
    the payload margin for no benefit here since the capsule is fixed-size.

    Alphanumeric mode is automatic: to_base32 already guarantees an uppercase,
    A-Z-and-digits-only alphabet, so segno never fails over to the denser byte
    mode that a lowercase or padded string would force.
    """
    payload = to_base32(encode(capsule))
    qr = segno.make(payload, error="m")
    # segno's SVG writer wants a binary stream (it writes bytes, matching the
    # "filename or file-like object supporting to write bytes" contract), not
    # StringIO — hence BytesIO and an explicit decode of its declared encoding.
    buf = io.BytesIO()
    qr.save(buf, kind="svg", scale=scale, xmldecl=True)
    return buf.getvalue().decode("utf-8")
