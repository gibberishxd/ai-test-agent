"""Where screenshots live (run 4, J6): local disk in development, any S3-compatible store
(MinIO, AWS S3, Cloudflare R2) in production. Tested with moto's in-process S3 fake."""

import boto3
import pytest
from moto import mock_aws

from worker.config import Settings
from worker.storage import LocalStorage, S3Storage, make_storage

BUCKET = "screenshots"


def s3_missing():
    from botocore.exceptions import ClientError

    return ClientError


@pytest.fixture
def s3():
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        yield S3Storage(
            bucket=BUCKET,
            region="us-east-1",
            endpoint_url=None,
            access_key="test",
            secret_key="test",
        )


@pytest.mark.parametrize("kind", ["local", "s3"])
def test_save_load_and_delete_a_runs_files(kind, tmp_path, request):
    storage = LocalStorage(tmp_path) if kind == "local" else request.getfixturevalue("s3")
    assert storage.save("run-1/page-001.png", b"png1") == "run-1/page-001.png"
    storage.save("run-1/agent-002.png", b"png2")
    storage.save("run-2/page-001.png", b"other")
    assert storage.load("run-1/page-001.png") == b"png1"
    assert storage.delete_prefix("run-1/") == 2
    with pytest.raises((FileNotFoundError, s3_missing())):
        storage.load("run-1/page-001.png")
    assert storage.load("run-2/page-001.png") == b"other"


def test_keys_cant_escape_their_place(tmp_path, s3):
    with pytest.raises(ValueError):
        LocalStorage(tmp_path).save("../outside.png", b"x")
    with pytest.raises(ValueError):
        s3.save("../outside.png", b"x")
    with pytest.raises(ValueError):
        s3.delete_prefix("")  # never "everything"


def test_settings_choose_the_storage(tmp_path):
    local = make_storage(Settings(_env_file=None, data_dir=str(tmp_path)))
    assert isinstance(local, LocalStorage)
    s3 = make_storage(
        Settings(
            _env_file=None,
            storage="s3",
            s3_bucket=BUCKET,
            s3_endpoint="http://minio:9000",
            s3_access_key="k",
            s3_secret_key="s",
        )
    )
    assert isinstance(s3, S3Storage) and s3.bucket == BUCKET


def test_a_missing_bucket_is_created_on_first_use():
    # Run 4, J6: the local production stack starts with an empty S3-compatible store.
    with mock_aws():
        storage = S3Storage(
            bucket="fresh", region="us-east-1", endpoint_url=None, access_key="t", secret_key="t"
        )
        storage.save("run-1/page-001.png", b"png")
        assert storage.load("run-1/page-001.png") == b"png"
