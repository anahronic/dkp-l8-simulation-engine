"""Offline privacy, corpus coverage and deterministic ZIP regressions."""
import io
import json
import tarfile
import zipfile
from pathlib import Path

import pytest

from deploy.local.check_public import check_blob, private_passages
from keeper.corpus import build, site_fragments
from lab.tools import build_web_bundle
from tests.keeper.test_gateway import setup, corpus_path


def test_zip_platform_metadata_is_explicit(tmp_path, monkeypatch):
    # Simulate each platform's ZipInfo default; builder must override both.
    original = zipfile.ZipInfo
    def with_platform(platform):
        class info(original):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.create_system = platform
        return info
    monkeypatch.setattr(build_web_bundle, "files", lambda: ["requirements.txt"])
    built = []
    for platform in (0, 3):
        monkeypatch.setattr(zipfile, "ZipInfo", with_platform(platform))
        build_web_bundle.build(str(tmp_path / str(platform)))
        built.append((tmp_path / str(platform) / "lab-bundle.zip").read_bytes())
    monkeypatch.setattr(zipfile, "ZipInfo", original)
    assert built[0] == built[1]
    with zipfile.ZipFile(io.BytesIO(built[0])) as archive:
        item = archive.infolist()[0]
        assert item.create_system == 3 and item.external_attr == 0o100644 << 16
        assert item.date_time == (1980, 1, 1, 0, 0, 0)


@pytest.mark.parametrize("name,data", [
    ("PRIVATE_DO_NOT_PUBLISH/file", b"x"), ("public.js", b"search_ru"),
    ("ru-sources/text.md", b"x"), ("corpus.jsonl", b"x"),
    ("renamed.txt", "Секретный полный перевод протокола ".encode() * 10),
])
def test_public_tarball_rejects_private_names_and_content(tmp_path, name, data):
    private = tmp_path / "private.jsonl"
    private.write_text(json.dumps({"search_ru": "Секретный полный перевод протокола " * 10}), encoding="utf-8")
    spans = private_passages(private)
    zipped = io.BytesIO()
    with zipfile.ZipFile(zipped, "w") as archive:
        archive.writestr(name, data)
    tarred = io.BytesIO()
    with tarfile.open(fileobj=tarred, mode="w:gz") as archive:
        item = tarfile.TarInfo("nested.zip")
        item.size = len(zipped.getvalue())
        archive.addfile(item, io.BytesIO(zipped.getvalue()))
    with pytest.raises(ValueError):
        check_blob("widget.tar.gz", tarred.getvalue(), spans)


def test_clean_public_bundle_is_accepted():
    zipped = io.BytesIO()
    with zipfile.ZipFile(zipped, "w") as archive:
        archive.writestr("index.html", "<p>Public Dikenocracy page</p>")
    check_blob("site.zip", zipped.getvalue())


def test_site_reference_text_and_exclusions(tmp_path):
    (tmp_path / "pages").mkdir()
    (tmp_path / "index.html").write_text(
        "<html><script>PRIVATE_SCRIPT</script><main><h1>Dikenocracy</h1><p>Public project explanation.</p>"
        "<form><input value='SECRET'><p>PRIVATE_FORM</p></form><div hidden>PRIVATE_HIDDEN</div>"
        "<p>Visible reference.</p></main></html>", encoding="utf-8")
    (tmp_path / "pages/about.html").write_text("<h1>About Dikenocracy</h1><p>Public about text.</p>", encoding="utf-8")
    fragments, routes = site_fragments(str(tmp_path))
    assert len(fragments) == 2
    assert all(f["url"] and f["sha256"] and f["revision"]["file_sha256"] for f in fragments)
    assert "PRIVATE" not in json.dumps(fragments) and "SECRET" not in json.dumps(fragments)
    assert "Visible reference." in fragments[0]["text"]
    assert any(r["route"] == "/shadoo/" and r["excluded"] for r in routes)


def test_public_fragment_endpoint_and_no_visitor_writes(setup):
    client, fake, app = setup(down=True)
    from urllib.parse import quote
    source = next(f for f in app.state.index.frags if f["document_id"] == "GLOSSARY")
    source["search_ru"] = "Приватный текст перевода не должен присутствовать в JSON."
    route = "/api/keeper/v1/sources/" + quote(source["fid"], safe="")
    response = client.get(route)
    assert response.status_code == 200 and response.json()["text"] == source["text"]
    assert "search_ru" not in response.text and source["search_ru"] not in response.text
    assert client.post(route, json={"text": "replacement"}).status_code == 405
    assert client.put(route, json={"text": "replacement"}).status_code == 405
    assert client.get(route).json()["sha256"] == source["sha256"]
    assert not fake.requests


def test_runtime_and_rollback_configuration():
    root = Path("deploy/server")
    keeper = (root / "units/dkp-keeper.service").read_text()
    assert "User=dkpkeeper" in keeper and "Group=dkpkeeper" in keeper
    assert "ReadOnlyPaths=/opt/dkp-lab /var/lib/dkp-corpus" in keeper
    assert "ReadWritePaths=/var/lib/dkp-keeper\n" in keeper
    assert "InaccessiblePaths=/var/lib/dkp-lab" in keeper
    assert "IPAddressDeny=any" in keeper and "IPAddressAllow=localhost" in keeper
    for name in ("dkp-lab-api", "dkp-lab-worker"):
        unit = (root / f"units/{name}.service").read_text()
        assert "ReadWritePaths=/var/lib/dkp-lab/lab\n" in unit
        assert "ReadOnlyPaths=/opt/dkp-lab /var/lib/dkp-corpus" in unit
    for name in ("30_app.sh", "99_rollback.sh"):
        script = (root / name).read_text()
        assert "-o root -g dkplab -m 0640" in script
        assert "/var/lib/dkp-corpus/corpus.jsonl" in script
        assert ".dkp-units" in script


def test_site_restore_keeps_file_modes_and_checks_nginx_can_read():
    # LAB-ERR 2026-10-20: tar under the kit's umask 077 restored pages as 0600 and nginx answered 403.
    root = Path("deploy/server")
    common = (root / "common.sh").read_text()
    assert "umask 077" in common
    assert "--no-same-owner --preserve-permissions" in common and "! -perm -o=r" in common
    site, rollback = (root / "50_site.sh").read_text(), (root / "99_rollback.sh").read_text()
    assert site.count("check_web_readable") == 2 and 'restore_site "$backup.tar.gz"' in site
    assert 'restore_site "$backup.tar.gz"\n    check_web_readable' in rollback
    for script in (site, rollback):
        assert "--directory /var/www/html --no-same-owner\n" not in script and "--directory /var/www/html --no-same-owner;" not in script
