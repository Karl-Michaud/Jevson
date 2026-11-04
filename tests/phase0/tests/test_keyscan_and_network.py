from __future__ import annotations

import socket

import httpx
import pytest

from tests.phase0 import keyscan
from tests.phase0.tests.conftest import NetworkBlocked

SENTINEL = "sk-test-SENTINEL-0123456789abcdef"


def test_network_is_stubbed():
    with pytest.raises(NetworkBlocked):
        socket.create_connection(("example.com", 443), timeout=1)
    with pytest.raises(Exception):
        httpx.get("https://api.typesafe.ai/v1/systemone", timeout=1)


def _repo(tmp_path, leak: bool):
    (tmp_path / ".env").write_text(f'OTHER=1\nTYPESAFE_API_KEY="{SENTINEL}"\n')
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text(SENTINEL)          # excluded
    (tmp_path / "a.txt").write_text("nothing here")
    (tmp_path / "sub").mkdir()
    if leak:
        (tmp_path / "sub" / "raw.json").write_text(f'{{"auth": "Bearer {SENTINEL}"}}')
    return tmp_path


def test_scan_counts_zero_and_nonzero(tmp_path, capsys):
    root = _repo(tmp_path, leak=False)
    assert keyscan.main(root) == 0
    assert "files containing the key: 0" in capsys.readouterr().out
    (root / "sub" / "raw.json").write_text(SENTINEL)
    assert keyscan.main(root) == 1
    out = capsys.readouterr().out
    assert "files containing the key: 1" in out and SENTINEL not in out


def test_read_key_missing(tmp_path):
    (tmp_path / ".env").write_text("TYPESAFE_API_KEY=\n")
    with pytest.raises(RuntimeError):
        keyscan.read_key(tmp_path / ".env")


def test_unreadable_file_is_skipped(tmp_path, monkeypatch):
    root = _repo(tmp_path, leak=True)
    real = type(root).read_bytes

    def flaky(self):
        if self.name == "raw.json":
            raise OSError("locked")
        return real(self)

    monkeypatch.setattr(type(root), "read_bytes", flaky)
    assert keyscan.files_containing(root, SENTINEL) == []
