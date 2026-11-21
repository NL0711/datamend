"""The AWS training target: one short-lived EC2 instance in the caller's account. A FAKE client replaces boto3 (no test needs boto3 or the network)
and every value that looks like a credential is an obvious fake. The trainer script embedded in the user-data is extracted and really run."""
import asyncio
import gzip
import io
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete

from backend.app.config import settings
from backend.app.db.database import async_session_factory
from backend.app.pipeline import aws_trigger, training
from backend.app.pipeline.models import (AuditItem, Correction, IngestJob, ModelVersion, Observation, PipelineStation, Proposal, TrainingJob,
                                          TrainingSnapshot)
from backend.app.validation.models import Review, ValidationRun
from tests.test_pipeline_train import add_snapshot, labelled_rows

TOKEN = "q" * 32
H = {"X-Admin-Token": TOKEN}
KEY, SECRET, SESSION = "AKIAFAKEFAKEFAKEFAKE", "FAKE-SECRET-NOT-REAL-0000", "FAKE-SESSION-TOKEN-NOT-REAL"
MINE = {"X-Aws-Access-Key-Id": KEY, "X-Aws-Secret-Access-Key": SECRET, "X-Aws-Session-Token": SESSION, "X-Aws-Region": "ap-southeast-2", "X-Aws-Bucket": "fake-bucket-one"}
OTHER = {**MINE, "X-Aws-Access-Key-Id": "AKIAOTHEROTHEROTHER00", "X-Aws-Secret-Access-Key": "OTHER-FAKE-SECRET-0000"}
SECRETS = (KEY, SECRET, SESSION, "OTHER-FAKE-SECRET-0000")


class FakeClientError(Exception):
    """Looks like botocore's ClientError (a .response with an Error Code); its text carries a secret on purpose, to prove it is never shown."""
    def __init__(self, code):
        super().__init__(f"An error occurred ({code}) calling the op with {SECRET} and {SESSION} at https://x.example/?X-Amz-Signature=abc")
        self.response = {"Error": {"Code": code, "Message": f"leaks {SECRET}"}}


class FakeAws:
    """An in-memory S3, EC2 and SSM. Instances belong to the access key that started them (another key cannot see them)."""

    def __init__(self):
        self.objects, self.buckets, self.instances = {}, {"fake-bucket-one"}, {}
        self.run_args, self.terminated, self.deleted, self.calls, self.accounts = [], [], [], [], []
        self.fail = {}                      # operation name -> error code to raise
        self.head_delay = 0.0
        self.n = 0

    def client(self, service, account):
        self.accounts.append((service, account.key_id, account.region, account.bucket))
        return {"s3": FakeS3, "ec2": FakeEc2, "ssm": FakeSsm}[service](self, account)

    def raise_if(self, op):
        if op in self.fail:
            raise FakeClientError(self.fail[op])


class _Base:
    def __init__(self, fake, account):
        self.fake, self.account = fake, account

    def _enter(self, op):
        self.fake.calls.append(op)
        self.fake.raise_if(op)


class FakeS3(_Base):
    def _bucket(self, bucket):
        if bucket not in self.fake.buckets:
            raise FakeClientError("NoSuchBucket")

    def put_object(self, Bucket, Key, Body, **kw):
        self._enter("put_object"); self._bucket(Bucket)
        self.fake.objects[(Bucket, Key)] = Body

    def generate_presigned_url(self, ClientMethod, Params, ExpiresIn):
        self._enter("presign")
        assert ExpiresIn == 3600
        return f"https://{Params['Bucket']}.s3.fake.example/{Params['Key']}?X-Amz-Method={ClientMethod}&X-Amz-Signature=FAKESIGNATURE"

    def head_object(self, Bucket, Key):
        self._enter("head_object"); self._bucket(Bucket)
        time.sleep(self.fake.head_delay)
        if (Bucket, Key) not in self.fake.objects:
            raise FakeClientError("404")
        return {}

    def get_object(self, Bucket, Key):
        self._enter("get_object"); self._bucket(Bucket)
        return {"Body": io.BytesIO(self.fake.objects[(Bucket, Key)])}

    def delete_object(self, Bucket, Key):
        self.fake.deleted.append(Key)
        self.fake.objects.pop((Bucket, Key), None)


class FakeSsm(_Base):
    def get_parameter(self, Name):
        self._enter("get_parameter")
        assert Name == "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
        return {"Parameter": {"Value": "ami-0123456789abcdef0"}}


class FakeEc2(_Base):
    def run_instances(self, **kw):
        self._enter("run_instances")
        self.fake.run_args.append(kw)
        self.fake.n += 1
        iid = f"i-0abc{self.fake.n:012x}"
        tags = {t["Key"]: t["Value"] for t in kw["TagSpecifications"][0]["Tags"]}
        self.fake.instances[iid] = {"owner": self.account.key_id, "state": "running", "tags": tags}
        return {"Instances": [{"InstanceId": iid}]}

    def describe_instances(self, InstanceIds):
        self._enter("describe_instances")
        inst = self.fake.instances.get(InstanceIds[0])
        if inst is None or inst["owner"] != self.account.key_id:
            raise FakeClientError("InvalidInstanceID.NotFound")
        return {"Reservations": [{"Instances": [{"InstanceId": InstanceIds[0], "State": {"Name": inst["state"]},
                                                  "Tags": [{"Key": k, "Value": v} for k, v in inst["tags"].items()]}]}]}

    def terminate_instances(self, InstanceIds):
        self._enter("terminate_instances")
        self.fake.terminated.append(InstanceIds[0])
        self.fake.instances[InstanceIds[0]]["state"] = "shutting-down"


@pytest.fixture
def fake(monkeypatch):
    f = FakeAws()
    monkeypatch.setattr(aws_trigger, "make_client", f.client)
    for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(settings, "AWS_TRAIN_BUCKET", "")
    monkeypatch.setattr(settings, "AWS_REGION", "ap-southeast-2")
    return f


@pytest_asyncio.fixture(autouse=True)
async def _clean(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_TOKEN", TOKEN)
    monkeypatch.setattr(training, "_ended_seen", {})
    async with async_session_factory() as s:
        for model in (Correction, Proposal, AuditItem, TrainingJob, ModelVersion, TrainingSnapshot, Review, Observation, PipelineStation, IngestJob):
            await s.execute(delete(model))
        await s.execute(delete(ValidationRun).where(ValidationRun.source == "pipeline"))
        await s.commit()
    yield
    training._refresh_locks.clear()                  # job ids restart in every test and each test has its own event loop: a lock must not outlive its loop


def extract_trainer(user_data: str) -> bytes:
    m = re.search(r"echo '([A-Za-z0-9+/=]+)' \| base64 -d \| gunzip > train\.py", user_data)
    assert m, "the trainer is not in the user-data"
    import base64
    return gzip.decompress(base64.b64decode(m.group(1)))


async def start(client, sid, headers=MINE, **body):
    return await client.post("/api/pipeline/train", headers={**H, **headers}, json={"snapshot_id": sid, "target": "aws", **body})


def finish(fake, job, state="terminated"):
    """What the instance does: run the trainer from its user-data on the uploaded snapshot, upload result.json, power off."""
    ud = fake.run_args[-1]["UserData"]
    snap = fake.objects[("fake-bucket-one", f"datamend/train/{job['id']}/snapshot.jsonl.gz")]
    return ud, snap


def run_trainer(user_data, snapshot_gz, folder: Path) -> dict:
    (folder / "train.py").write_bytes(extract_trainer(user_data))
    (folder / "snapshot.jsonl.gz").write_bytes(snapshot_gz)
    run = subprocess.run([sys.executable, "train.py"], cwd=folder, capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stderr
    return json.loads((folder / "result.json").read_text())


# ---------------------------------------------------------------------------------------------- start
@pytest.mark.asyncio
async def test_byo_credentials_work_with_the_server_unconfigured_and_the_instance_is_locked_down(async_client: AsyncClient, fake):
    sid = await add_snapshot(labelled_rows())
    r = await start(async_client, sid, instance_type="t3.small", max_minutes=45)
    assert r.status_code == 202
    job = r.json()
    assert job["target"] == "aws" and job["status"] == "running" and re.fullmatch(r"aws:ap-southeast-2:i-[0-9a-f]+", job["slug"])
    assert "gpu_note" not in job and job["instance_type"] == "t3.small" and job["max_minutes"] == 45
    assert all(a[1] == KEY and a[2] == "ap-southeast-2" and a[3] == "fake-bucket-one" for a in fake.accounts)    # the caller's account, not the server's
    a = fake.run_args[0]
    assert a["MaxCount"] == 1 and a["MinCount"] == 1 and a["ImageId"] == "ami-0123456789abcdef0" and a["InstanceType"] == "t3.small"
    assert a["MetadataOptions"]["HttpTokens"] == "required" and a["InstanceInitiatedShutdownBehavior"] == "terminate"
    ebs = a["BlockDeviceMappings"][0]["Ebs"]
    assert ebs["VolumeType"] == "gp3" and ebs["DeleteOnTermination"] is True and ebs["VolumeSize"] <= 16
    for spec in a["TagSpecifications"]:
        assert {t["Key"]: t["Value"] for t in spec["Tags"]} == {"datamend-job": str(job["id"]), "datamend-managed": "true"}
    assert not {"KeyName", "SecurityGroups", "SecurityGroupIds", "IamInstanceProfile", "NetworkInterfaces", "InstanceMarketOptions"} & set(a)
    ud = a["UserData"]
    assert len(ud.encode()) < 16000
    assert ud.splitlines()[0] == "#!/bin/bash" and ud.splitlines()[1] == "shutdown -h +45"                # the hard time cap comes first
    assert ud.count("https://") == 2 and "X-Amz-Method=get_object" in ud and "X-Amz-Method=put_object" in ud
    assert not any(s in ud for s in (KEY, SECRET, SESSION)) and "AWS_" not in ud
    assert ("fake-bucket-one", f"datamend/train/{job['id']}/snapshot.jsonl.gz") in fake.objects
    for text in (r.text, json.dumps(a["TagSpecifications"])):
        assert not any(s in text for s in (KEY, SECRET, SESSION))
    async with async_session_factory() as s:                                                          # nothing secret in the database
        stored = str((await s.execute(TrainingJob.__table__.select())).all())
        assert not any(x in stored for x in (KEY, SECRET, SESSION, "https://"))


@pytest.mark.asyncio
async def test_spot_and_gpu_options(async_client: AsyncClient, fake):
    sid = await add_snapshot(labelled_rows())
    job = (await start(async_client, sid, instance_type="g4dn.xlarge", spot=True)).json()
    assert job["status"] == "running" and "does not use a GPU" in job["gpu_note"] and "only costs more" in job["gpu_note"]
    a = fake.run_args[0]
    assert a["InstanceMarketOptions"]["MarketType"] == "spot" and a["InstanceType"] == "g4dn.xlarge"
    assert a["UserData"].splitlines()[1] == "shutdown -h +30"                                           # the default cap


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{"instance_type": "p4d.24xlarge"}, {"instance_type": "t3.medium; rm -rf"}, {"instance_type": ""},
                                   {"max_minutes": 121}, {"max_minutes": 0}, {"max_minutes": -5}])
async def test_instance_allowlist_and_time_cap_are_enforced_before_anything_happens(async_client: AsyncClient, fake, body):
    sid = await add_snapshot(labelled_rows())
    r = await start(async_client, sid, **body)
    assert r.status_code == 400
    assert fake.calls == [] and fake.run_args == [] and fake.objects == {}
    assert (await async_client.get("/api/pipeline/train/jobs")).json()["jobs"] == []
    assert (await start(async_client, sid, max_minutes=120)).status_code == 202                       # the maximum itself is allowed


def test_the_embedded_trainer_really_runs_and_writes_a_valid_result(tmp_path, fake):
    content = "\n".join(json.dumps(r, sort_keys=True) for r in labelled_rows())
    account = aws_trigger.resolve(aws_trigger.from_request(KEY, SECRET, None, None, "fake-bucket-one"))
    aws_trigger.launch(7, content, "b" * 64, account, "t3.medium", 30)
    res = run_trainer(fake.run_args[0]["UserData"], fake.objects[("fake-bucket-one", "datamend/train/7/snapshot.jsonl.gz")], tmp_path)
    assert res["ok"] is True and res["metrics"]["kind"] == "label_fusion" and res["metrics"]["snapshot_sha256"] == "b" * 64
    few = "\n".join(json.dumps(r, sort_keys=True) for r in labelled_rows(n_days=4))
    aws_trigger.launch(8, few, "c" * 64, account, "t3.medium", 30)
    res2 = run_trainer(fake.run_args[1]["UserData"], fake.objects[("fake-bucket-one", "datamend/train/8/snapshot.jsonl.gz")], tmp_path)
    assert res2["ok"] is False and "too few labels" in res2["error"]


def test_user_data_over_the_ec2_limit_is_refused():
    with pytest.raises(aws_trigger.AwsError):
        aws_trigger.build_user_data("a" * 64, "https://x.example/" + "a" * 17000, "https://y.example/b", 30)
    with pytest.raises(aws_trigger.AwsError):
        aws_trigger.build_user_data("a" * 64, "https://x.example/'; evil", "https://y.example/b", 30)


# ---------------------------------------------------------------------------------------------- server fallback and the listing
@pytest.mark.asyncio
async def test_server_credentials_are_the_fallback_and_the_listing_says_so(async_client: AsyncClient, fake, monkeypatch):
    sid = await add_snapshot(labelled_rows())
    jobs = (await async_client.get("/api/pipeline/train/jobs")).json()
    assert jobs["aws_supported"] is True and jobs["aws_configured"] is False
    r = await start(async_client, sid, headers={})
    assert r.status_code == 409 and "AWS_ACCESS_KEY_ID" in r.text and "your own" in r.text and fake.calls == []
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIASERVERFAKEFAKE00")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "SERVER-FAKE-SECRET-0000")
    assert (await async_client.get("/api/pipeline/train/jobs")).json()["aws_configured"] is False          # still no bucket
    assert (await start(async_client, sid, headers={})).status_code == 409
    monkeypatch.setattr(settings, "AWS_TRAIN_BUCKET", "fake-bucket-one")
    assert (await async_client.get("/api/pipeline/train/jobs")).json()["aws_configured"] is True
    r2 = await start(async_client, sid, headers={})
    assert r2.status_code == 202 and r2.json()["status"] == "running"
    assert all(a[1] is None for a in fake.accounts)                                                       # boto3's default chain: no key handed over
    mine = await start(async_client, sid)                                                                  # a visitor's own account takes precedence
    assert mine.status_code == 202 and fake.accounts[-1][1] == KEY


# ---------------------------------------------------------------------------------------------- refresh
@pytest.mark.asyncio
async def test_refresh_registers_exactly_one_challenger_and_terminates_the_instance(async_client: AsyncClient, fake, tmp_path):
    sid = await add_snapshot(labelled_rows())
    job = (await start(async_client, sid)).json()
    iid = job["slug"].split(":")[2]
    waiting = await async_client.post(f"/api/pipeline/train/jobs/{job['id']}/refresh", headers={**H, **MINE})
    assert waiting.status_code == 200 and waiting.json()["status"] == "running" and fake.terminated == []
    ud, snap = finish(fake, job)
    result = run_trainer(ud, snap, tmp_path)
    fake.objects[("fake-bucket-one", f"datamend/train/{job['id']}/result.json")] = json.dumps(result).encode()
    done = await async_client.post(f"/api/pipeline/train/jobs/{job['id']}/refresh", headers={**H, **MINE})
    assert done.status_code == 200 and done.json()["status"] == "complete" and done.json()["model_id"]
    assert fake.terminated == [iid]                                                                         # still running, so it was terminated
    assert f"datamend/train/{job['id']}/snapshot.jsonl.gz" in fake.deleted and f"datamend/train/{job['id']}/result.json" in fake.deleted
    again = await async_client.post(f"/api/pipeline/train/jobs/{job['id']}/refresh", headers={**H, **MINE})
    assert again.json()["status"] == "complete"
    models = (await async_client.get("/api/pipeline/models")).json()["models"]
    assert len(models) == 1 and models[0]["alias"] == "challenger" and models[0]["metrics"]["kind"] == "label_fusion"
    lineage = (await async_client.get("/api/pipeline/lineage")).json()
    node = next(n for n in lineage["nodes"] if n["id"] == f"train:{job['id']}")
    assert node["label"].endswith("(aws)") and node["facts"]["instance"] == job["slug"]


@pytest.mark.asyncio
async def test_two_simultaneous_refreshes_register_one_challenger(async_client: AsyncClient, fake, tmp_path):
    sid = await add_snapshot(labelled_rows())
    job = (await start(async_client, sid)).json()
    ud, snap = finish(fake, job)
    fake.objects[("fake-bucket-one", f"datamend/train/{job['id']}/result.json")] = json.dumps(run_trainer(ud, snap, tmp_path)).encode()
    fake.head_delay = 0.2
    url = f"/api/pipeline/train/jobs/{job['id']}/refresh"
    rs = await asyncio.gather(async_client.post(url, headers={**H, **MINE}), async_client.post(url, headers={**H, **MINE}))
    assert [r.status_code for r in rs] == [200, 200] and all(r.json()["status"] == "complete" for r in rs)
    assert len((await async_client.get("/api/pipeline/models")).json()["models"]) == 1


@pytest.mark.asyncio
async def test_a_refresh_for_another_region_or_account_is_refused(async_client: AsyncClient, fake):
    sid = await add_snapshot(labelled_rows())
    job = (await start(async_client, sid)).json()
    n = len(fake.calls)
    r = await async_client.post(f"/api/pipeline/train/jobs/{job['id']}/refresh", headers={**H, **MINE, "X-Aws-Region": "us-east-1"})
    assert r.status_code == 409 and "ap-southeast-2" in r.text and len(fake.calls) == n                      # refused without calling AWS
    r2 = await async_client.post(f"/api/pipeline/train/jobs/{job['id']}/refresh", headers={**H, **OTHER})
    assert r2.status_code == 409 and not any(s in r2.text for s in SECRETS)                                    # the other account cannot see the instance
    r3 = await async_client.post(f"/api/pipeline/train/jobs/{job['id']}/refresh", headers=H)                   # no credentials at all
    assert r3.status_code == 409
    assert (await async_client.get("/api/pipeline/train/jobs")).json()["jobs"][0]["status"] == "running"       # the job was left alone
    assert fake.terminated == []


@pytest.mark.asyncio
async def test_an_instance_that_ended_without_a_result_fails_the_job_after_the_grace_period(async_client: AsyncClient, fake, monkeypatch):
    sid = await add_snapshot(labelled_rows())
    job = (await start(async_client, sid)).json()
    fake.instances[job["slug"].split(":")[2]]["state"] = "terminated"
    url = f"/api/pipeline/train/jobs/{job['id']}/refresh"
    assert (await async_client.post(url, headers={**H, **MINE})).json()["status"] == "running"               # within the grace period
    monkeypatch.setattr(training, "AWS_GRACE_S", 0.0)
    r = await async_client.post(url, headers={**H, **MINE})
    j = r.json()
    assert j["status"] == "failed" and "without uploading a result" in j["error"] and j["model_id"] is None
    assert not any(s in r.text for s in SECRETS) and "https://" not in r.text
    assert (await async_client.get("/api/pipeline/models")).json()["models"] == []
    assert f"datamend/train/{job['id']}/snapshot.jsonl.gz" in fake.deleted


@pytest.mark.asyncio
async def test_a_trainer_that_reports_an_error_fails_the_job_with_its_message(async_client: AsyncClient, fake, tmp_path):
    sid = await add_snapshot(labelled_rows(n_days=4))
    job = (await start(async_client, sid)).json()
    ud, snap = finish(fake, job)
    fake.objects[("fake-bucket-one", f"datamend/train/{job['id']}/result.json")] = json.dumps(run_trainer(ud, snap, tmp_path)).encode()
    j = (await async_client.post(f"/api/pipeline/train/jobs/{job['id']}/refresh", headers={**H, **MINE})).json()
    assert j["status"] == "failed" and "too few labels" in j["error"] and j["model_id"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("op,code,words", [("run_instances", "AuthFailure", "refused the credentials"), ("put_object", "AccessDenied", "refused the credentials"),
                                            ("put_object", "NoSuchBucket", "bucket does not exist"), ("run_instances", "VcpuLimitExceeded", "quota"),
                                            ("get_parameter", "UnauthorizedOperation", "refused the credentials"), ("run_instances", "SomethingNew", "failed")])
async def test_failures_at_start_end_in_a_failed_job_with_a_safe_message(async_client: AsyncClient, fake, op, code, words):
    sid = await add_snapshot(labelled_rows())
    fake.fail[op] = code
    r = await start(async_client, sid)
    assert r.status_code == 202
    j = r.json()
    assert j["status"] == "failed" and words in j["error"] and j["slug"] is None
    assert not any(s in r.text for s in SECRETS) and "https://" not in r.text and "X-Amz" not in r.text
    assert fake.run_args == [] or fake.objects == {}                                                          # the uploaded snapshot is removed again
    async with async_session_factory() as s:
        stored = str((await s.execute(TrainingJob.__table__.select())).all())
        assert not any(x in stored for x in SECRETS)


@pytest.mark.asyncio
async def test_a_missing_bucket_on_refresh_fails_and_refused_credentials_keep_the_job_running(async_client: AsyncClient, fake):
    sid = await add_snapshot(labelled_rows())
    job = (await start(async_client, sid)).json()
    url = f"/api/pipeline/train/jobs/{job['id']}/refresh"
    fake.fail["describe_instances"] = "ExpiredToken"
    r = await async_client.post(url, headers={**H, **MINE})
    assert r.status_code == 200 and r.json()["status"] == "running" and "refused the credentials" in r.json()["error"] and not any(s in r.text for s in SECRETS)
    fake.fail.clear()
    fake.buckets.clear()
    j = (await async_client.post(url, headers={**H, **MINE})).json()
    assert j["status"] == "failed" and "bucket does not exist" in j["error"]


@pytest.mark.asyncio
async def test_a_job_past_the_longest_time_cap_is_failed_and_its_instance_terminated(async_client: AsyncClient, fake, monkeypatch):
    sid = await add_snapshot(labelled_rows())
    job = (await start(async_client, sid)).json()
    monkeypatch.setattr(training, "AWS_HARD_CAP_MIN", -1)
    j = (await async_client.post(f"/api/pipeline/train/jobs/{job['id']}/refresh", headers={**H, **MINE})).json()
    assert j["status"] == "failed" and "longest allowed time" in j["error"] and fake.terminated == [job["slug"].split(":")[2]]


# ---------------------------------------------------------------------------------------------- headers
@pytest.mark.asyncio
@pytest.mark.parametrize("headers", [
    {"X-Aws-Access-Key-Id": "short", "X-Aws-Secret-Access-Key": SECRET},
    {"X-Aws-Access-Key-Id": "AKIA FAKE FAKE FAKE!", "X-Aws-Secret-Access-Key": SECRET},
    {"X-Aws-Access-Key-Id": KEY, "X-Aws-Secret-Access-Key": "has space inside"},
    {"X-Aws-Access-Key-Id": KEY, "X-Aws-Secret-Access-Key": "s" * 201},
    {"X-Aws-Access-Key-Id": KEY},
    {"X-Aws-Secret-Access-Key": SECRET},
    {"X-Aws-Session-Token": SESSION},
    {"X-Aws-Access-Key-Id": KEY, "X-Aws-Secret-Access-Key": SECRET, "X-Aws-Region": "Mars-1"},
    {"X-Aws-Access-Key-Id": KEY, "X-Aws-Secret-Access-Key": SECRET, "X-Aws-Region": "ap-southeast-2; evil"},
    {"X-Aws-Access-Key-Id": KEY, "X-Aws-Secret-Access-Key": SECRET, "X-Aws-Bucket": "Bad_Bucket"},
    {"X-Aws-Access-Key-Id": KEY, "X-Aws-Secret-Access-Key": SECRET, "X-Aws-Bucket": "ab"},
    {"X-Aws-Access-Key-Id": KEY, "X-Aws-Secret-Access-Key": SECRET, "X-Aws-Bucket": "a..b-bucket"},
    {"X-Aws-Access-Key-Id": KEY, "X-Aws-Secret-Access-Key": SECRET, "X-Aws-Bucket": "../evil"},
])
async def test_bad_headers_give_400_without_echo_and_no_aws_call(async_client: AsyncClient, fake, headers):
    sid = await add_snapshot(labelled_rows())
    r = await start(async_client, sid, headers=headers)
    assert r.status_code == 400 and fake.calls == []
    for v in headers.values():
        if len(v) > 8:
            assert v not in r.text
    r2 = await async_client.post("/api/pipeline/train/jobs/1/refresh", headers={**H, **headers})
    assert r2.status_code == 400 and not any(v in r2.text for v in headers.values() if len(v) > 8)


def test_credentials_hide_in_repr_and_scrub_removes_them():
    req = aws_trigger.from_request(KEY, SECRET, SESSION, "ap-southeast-2", "fake-bucket-one")
    account = aws_trigger.resolve(req)
    for obj in (req, account):
        assert not any(s in repr(obj) + str(obj) for s in (SECRET, SESSION, KEY))
    dirty = f"boom {KEY} {SECRET} {SESSION} https://b.s3.example/k?X-Amz-Signature=abc&X-Amz-Credential=zzz AKIAREALLOOKINGKEY1234"
    clean = aws_trigger.scrub(dirty, account)
    assert not any(s in clean for s in (KEY, SECRET, SESSION, "X-Amz", "https://", "AKIAREAL"))
    err = aws_trigger._translate("ec2:RunInstances", FakeClientError("Weird.Code"))
    assert SECRET not in str(err) and SESSION not in str(err) and "Weird.Code" in str(err)


def test_boto3_is_imported_only_when_a_client_is_built(monkeypatch):
    monkeypatch.setitem(sys.modules, "boto3", None)                                 # an import now fails
    account = aws_trigger.resolve(aws_trigger.from_request(KEY, SECRET, None, None, "fake-bucket-one"))
    with pytest.raises(aws_trigger.AwsError) as e:
        aws_trigger.make_client("s3", account)
    assert "not installed" in str(e.value)
