"""TOTP helpers — thin wrapper around pyotp (fitops[server] required)."""

from __future__ import annotations


def generate_secret() -> str:
    import pyotp

    return pyotp.random_base32()


def verify(secret: str, code: str) -> bool:
    import pyotp

    return pyotp.TOTP(secret).verify(code.strip(), valid_window=1)


def provisioning_uri(secret: str, account: str = "FitOps") -> str:
    import pyotp

    return pyotp.TOTP(secret).provisioning_uri(
        name=account, issuer_name="FitOps Dashboard"
    )


def print_qr(uri: str) -> None:
    """Print an ASCII QR code to the terminal (no PIL required)."""
    import qrcode

    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_L)
    qr.add_data(uri)
    qr.make(fit=True)
    qr.print_ascii(invert=True)
