"""Reproduction packages of the deterministic bench (smoke scenario) and independence levels."""
import pytest

from dkp8 import reproduction as R
from dkp8 import trust


@pytest.fixture(scope="module")
def package(tmp_path_factory):
    path = tmp_path_factory.mktemp("repro") / "smoke.zip"
    return R.make_package(None, str(path)), path


def test_package_is_byte_stable_and_reproduces(package, tmp_path):
    info, path = package
    again = R.make_package(None, str(tmp_path / "again.zip"))
    assert again["sha256"] == info["sha256"] and again["result_id"] == info["result_id"]
    record = R.verify_package(str(path), "test-operator", "R1")
    assert record["body"]["match"] and record["body"]["level"] == "R1" and record["signature"] is None
    rep = R.assess([record], trust.canonical_store(), [info["result_id"]])
    assert rep["levels"] == {"R1": 1} and rep["independent_nodes"] == 0 and not rep["mismatches"]


def test_tampered_package_is_refused(package, tmp_path):
    import zipfile
    _, path = package
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(path) as src, zipfile.ZipFile(bad, "w") as dst:
        for name in src.namelist():
            data = src.read(name)
            if name == "config_resolved.json":
                data = data.replace(b'"seed"', b'"seed" ', 1)
            dst.writestr(name, data)
    with pytest.raises(ValueError, match="SHA256SUMS"):
        R.read_package(str(bad))


def test_r3_requires_a_registered_signed_node(package):
    _, path = package
    with pytest.raises(ValueError):
        R.verify_package(str(path), "someone", "R3")
    node = bytes.fromhex("44" * 32)
    rec = R.verify_package(str(path), "test-node", "R3", node_secret=node)
    assert R.assess([rec], trust.canonical_store())["independent_nodes"] == 0          # not registered
    store = trust.with_test_identities(trust.canonical_store(), bytes.fromhex("45" * 32), [node])
    rep = R.assess([rec], store)
    assert rep["independent_nodes"] == 1 and rep["authority_nodes"] == 0 and rep["test_identity_nodes"] == 1
