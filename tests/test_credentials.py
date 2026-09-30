import json
from unittest.mock import MagicMock, patch

import pytest
from core.credentials import CredentialStore, calc_fingerprint


def test_credential_store_local_read_json(tmp_path):
    store = CredentialStore(credentials_dir=tmp_path)
    store.set("test_service", {"cookie": "a1=xyz; session=123", "token": "tok_abc"})

    data = store.get("test_service")
    assert data["cookie"] == "a1=xyz; session=123"
    assert data["token"] == "tok_abc"

def test_credential_store_local_read_txt(tmp_path):
    store = CredentialStore(credentials_dir=tmp_path)
    txt_file = tmp_path / "legacy_token.txt"
    txt_file.write_text("raw_secret_cookie_string", encoding="utf-8")

    data = store.get("legacy_token")
    assert data["cookie"] == "raw_secret_cookie_string"
    assert data["token"] == "raw_secret_cookie_string"

def test_credential_store_path_traversal_rejected(tmp_path):
    store = CredentialStore(credentials_dir=tmp_path)
    with pytest.raises(ValueError):
        store.get("../etc/passwd")

    with pytest.raises(ValueError):
        store.get(r"..\windows\win.ini")

    with pytest.raises(ValueError):
        store.set("../evil", "data")

    with pytest.raises(ValueError):
        store.get("service/subaccount")

def test_credential_store_atomic_write(tmp_path):
    store = CredentialStore(credentials_dir=tmp_path)
    store.set("atomic_key", {"key": "val123"})
    json_path = tmp_path / "atomic_key.json"
    assert json_path.exists()
    content = json.loads(json_path.read_text(encoding="utf-8"))
    assert content["key"] == "val123"

def test_credential_store_fingerprint():
    cookie = "very_secret_cookie_data_here"
    fp = calc_fingerprint(cookie)
    assert len(fp) == 8
    # Same value gives same fingerprint
    assert calc_fingerprint(cookie) == fp
    # Never leaks original cookie string
    assert "secret" not in fp

def test_credential_store_oss_fallback(tmp_path):
    store = CredentialStore(credentials_dir=tmp_path)
    mock_obj = MagicMock()
    mock_obj.read.return_value = b'{"cookie": "oss_cookie_val"}'

    mock_bucket = MagicMock()
    mock_bucket.get_object.return_value = mock_obj

    with patch("oss2.Bucket", return_value=mock_bucket):
        with patch("app.config.OSS_ACCESS_KEY_ID", "mock_key_id"):
            with patch("app.config.OSS_ACCESS_KEY_SECRET", "mock_key_secret"):
                with patch("app.config.OSS_BUCKET", "mock_bucket"):
                    data = store.get("juguang")
                    assert data.get("cookie") == "oss_cookie_val"
