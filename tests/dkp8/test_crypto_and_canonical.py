"""Canonical JSON and Ed25519 (RFC 8032 vectors; cross-check with OpenSSL when it is installed)."""
import shutil
import subprocess

import pytest

from dkp8 import ed25519
from dkp8.canonical import CanonicalError, canonical, digest, is_decimal

RFC8032 = [  # RFC 8032 §7.1 TEST 1-3: secret key, public key, message, signature
    ("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
     "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a", "",
     "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
    ("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
     "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c", "72",
     "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
    ("c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7",
     "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025", "af82",
     "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a"),
]


@pytest.mark.parametrize("sk,pk,msg,sig", RFC8032)
def test_rfc8032_vectors(sk, pk, msg, sig):
    sk, pk, msg, sig = map(bytes.fromhex, (sk, pk, msg, sig))
    assert ed25519.public_key(sk) == pk
    assert ed25519.sign(sk, msg) == sig
    assert ed25519.verify(pk, msg, sig)


def test_tampering_is_rejected():
    sk = bytes(range(32))
    pk, sig = ed25519.public_key(sk), ed25519.sign(sk, b"bundle")
    assert not ed25519.verify(pk, b"bundle!", sig)
    assert not ed25519.verify(pk, b"bundle", sig[:-1] + bytes([sig[-1] ^ 1]))
    bad_s = sig[:32] + (int.from_bytes(sig[32:], "little") + ed25519.L).to_bytes(32, "little")
    assert not ed25519.verify(pk, b"bundle", bad_s)          # non-canonical S (malleability) refused
    assert not ed25519.verify(pk[:31], b"bundle", sig)


@pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl not installed")
def test_signature_matches_openssl(tmp_path):
    seed = bytes.fromhex("1f" * 32)
    der = bytes.fromhex("302e020100300506032b657004220420") + seed            # PKCS#8 Ed25519 private key
    (tmp_path / "k.der").write_bytes(der)
    (tmp_path / "m").write_bytes(b"DKP-8 calibration bundle body")
    try:
        subprocess.run(["openssl", "pkeyutl", "-sign", "-inkey", str(tmp_path / "k.der"), "-keyform", "DER", "-rawin",
                        "-in", str(tmp_path / "m"), "-out", str(tmp_path / "s")], check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        pytest.skip("openssl without Ed25519 raw signing: " + exc.stderr.decode(errors="ignore")[:80])
    assert (tmp_path / "s").read_bytes() == ed25519.sign(seed, b"DKP-8 calibration bundle body")


def test_canonical_form_is_rfc8785_subset():
    assert canonical({"b": 1, "a": [True, None, "é\n"]}) == '{"a":[true,null,"é\\n"],"b":1}'.encode()
    assert canonical({"€": 1, "\U0001f600": 2, "a": 0}) == canonical({"a": 0, "\U0001f600": 2, "€": 1})
    # RFC 8785 sorts by UTF-16 code units: U+1F600 (surrogate 0xD83D) precedes U+FF5E, unlike code-point order.
    text = canonical({"～": 1, "\U0001f600": 2}).decode()
    assert text.index("\U0001f600") < text.index("～")
    assert digest({"x": "0.68"}) == digest({"x": "0.68"})


@pytest.mark.parametrize("bad", [{"x": 0.5}, {"x": float("nan")}, {1: "a"}, {"x": 2 ** 60}, {"x": {1, 2}}])
def test_canonical_refuses_ambiguous_values(bad):
    with pytest.raises(CanonicalError):
        canonical(bad)


def test_decimal_strings():
    assert all(is_decimal(x) for x in ("0", "0.68", "-12.5", "1000"))
    assert not any(is_decimal(x) for x in ("01", ".5", "1e3", "0.68 ", 0.68, "NaN"))
