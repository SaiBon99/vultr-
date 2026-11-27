"""Generate the receipt Ed25519 key (PKCS8 PEM). Prints only the public key (base64) and key_id.

Default output: infra/keys/receipt_ed25519.pem (git-ignored). Refuses to overwrite without --force.
Run: uv run --no-project --with cryptography python infra/scripts/keygen_ed25519.py [--out DIR] [--force]
"""
import argparse
import base64
import hashlib
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

DEFAULT_DIR = Path(__file__).resolve().parent.parent / "keys"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=DEFAULT_DIR, help="output directory")
    ap.add_argument("--force", action="store_true", help="overwrite an existing key")
    args = ap.parse_args()
    path = args.out / "receipt_ed25519.pem"
    if path.exists() and not args.force:
        print(f"refusing to overwrite {path}; pass --force", file=sys.stderr)
        return 1
    args.out.mkdir(parents=True, exist_ok=True)
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    path.write_bytes(pem)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    print(f"wrote {path}")
    print(f"public_key_b64={base64.b64encode(raw).decode()}")
    print(f"key_id={hashlib.sha256(raw).hexdigest()[:16]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
