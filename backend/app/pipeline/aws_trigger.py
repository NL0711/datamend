"""Start a retraining run on ONE short-lived EC2 instance in the CALLER's AWS account, check on it, and fetch its result.

The instance runs the standalone trainer (pipeline/fusion.py, the same source the Kaggle notebook uses) and then powers itself off (shutdown
behaviour 'terminate'). The snapshot goes to the caller's S3 bucket (datamend/train/<job id>/snapshot.jsonl.gz); the instance has NO instance
profile and reaches S3 only through two PRESIGNED URLs (a GET for the snapshot, a PUT for result.json, one hour). Those URLs are inside the
user-data, so anyone who can read the instance's user-data (the account owner) can read them: that is inherent to the approach and expires in an
hour. A hard time cap is the first line of the user-data (shutdown -h +N), so even a hung job ends.

Credentials: per request (headers X-Aws-Access-Key-Id, X-Aws-Secret-Access-Key, optional X-Aws-Session-Token, X-Aws-Region, X-Aws-Bucket) or, when
none are sent, the server's own (boto3's default chain, AWS_REGION and AWS_TRAIN_BUCKET). They live in memory for the request; never stored, logged,
echoed, put in user-data, or placed in an error message (messages here are built from fixed text and an AWS error CODE, never the AWS message).
boto3 is imported lazily, only when a client is built, through ``make_client`` (tests replace it with a fake). UNTESTED against live AWS.
The platform enforces the time cap but cannot read AWS cost or credits.
"""
from __future__ import annotations

import base64
import gzip
import json
import os
import re
from typing import Any, Dict, Optional, Tuple

from backend.app.config import settings
from backend.app.pipeline.kaggle_trigger import FUSION_SOURCE

# GPU types are allowed, but the label-fusion trainer does not use a GPU, so they only cost more.
ALLOWED_INSTANCE_TYPES: Dict[str, bool] = {"t3.small": False, "t3.medium": False, "c6i.large": False, "g4dn.xlarge": True, "g5.xlarge": True}
DEFAULT_INSTANCE_TYPE = "t3.medium"
DEFAULT_MINUTES, MAX_MINUTES = 30, 120
GPU_NOTE = "The label-fusion trainer does not use a GPU: a GPU instance type only costs more (and AWS must have approved your quota for it)."
URL_EXPIRY_S = 3600
USER_DATA_LIMIT = 16000                  # EC2 allows 16 KB of user-data before base64
AMI_PARAMETER = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
ROOT_VOLUME_GB = 8                       # the smallest the AL2023 image allows

ACCESS_KEY_RE = re.compile(r"[A-Za-z0-9]{16,128}")
SECRET_RE = re.compile(r"[\x21-\x7e]{1,200}")
TOKEN_RE = re.compile(r"[\x21-\x7e]{1,4096}")
REGION_RE = re.compile(r"[a-z]{2}(?:-[a-z]+){1,2}-[0-9]{1,2}")
BUCKET_RE = re.compile(r"[a-z0-9][a-z0-9.\-]{1,61}[a-z0-9]")
INSTANCE_ID_RE = re.compile(r"i-[0-9a-f]{8,17}")
AMI_RE = re.compile(r"ami-[0-9a-f]{8,17}")
NO_CREDENTIALS = ("AWS is not configured: set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY (and AWS_TRAIN_BUCKET) in the server's environment, or supply your own "
                  "AWS access key, secret, region and S3 bucket (the X-Aws-* headers; the Data pipeline page has a form)")
NO_BUCKET = "no S3 bucket: send X-Aws-Bucket or set AWS_TRAIN_BUCKET on the server"


class AwsError(RuntimeError):
    """A failure with a SAFE message (fixed text and an AWS error code only). ``kind``: auth | bucket | notfound | other."""

    def __init__(self, message: str, kind: str = "other", code: str = ""):
        super().__init__(message)
        self.kind, self.code = kind, code


class Account:
    """The AWS account, region and bucket for ONE request. Held in memory only; repr and str hide every secret."""
    __slots__ = ("key_id", "secret", "token", "region", "bucket")

    def __init__(self, key_id: Optional[str], secret: Optional[str], token: Optional[str], region: str, bucket: str):
        self.key_id, self.secret, self.token, self.region, self.bucket = key_id, secret, token, region, bucket

    def __repr__(self) -> str:
        return f"Account(region={self.region!r}, bucket={self.bucket!r}, own_key={self.key_id is not None}, secret='***')"

    __str__ = __repr__


class Request:
    """What the headers carried (all optional). Never echoed."""
    __slots__ = ("key_id", "secret", "token", "region", "bucket")

    def __init__(self, key_id=None, secret=None, token=None, region=None, bucket=None):
        self.key_id, self.secret, self.token, self.region, self.bucket = key_id, secret, token, region, bucket

    def __repr__(self) -> str:
        return "Request(***)"

    __str__ = __repr__


def from_request(key_id: Optional[str], secret: Optional[str], token: Optional[str], region: Optional[str], bucket: Optional[str]) -> Optional[Request]:
    """The caller's values from the headers. None when nothing is sent; ValueError (no value echoed) when a value is malformed or only one of
    the key id and secret is sent."""
    key_id, secret, token, region, bucket = (v.strip() if v else "" for v in (key_id, secret, token, region, bucket))
    if not any((key_id, secret, token, region, bucket)):
        return None
    if bool(key_id) != bool(secret):
        raise ValueError("send both X-Aws-Access-Key-Id and X-Aws-Secret-Access-Key, or neither")
    if token and not key_id:
        raise ValueError("X-Aws-Session-Token needs the access key id and secret")
    if key_id and not ACCESS_KEY_RE.fullmatch(key_id):
        raise ValueError("the AWS access key id is malformed (letters and digits, 16 to 128 characters)")
    if secret and not SECRET_RE.fullmatch(secret):
        raise ValueError("the AWS secret access key is malformed (printable characters without spaces, at most 200)")
    if token and not TOKEN_RE.fullmatch(token):
        raise ValueError("the AWS session token is malformed (printable characters without spaces)")
    if region and not REGION_RE.fullmatch(region):
        raise ValueError("the AWS region is malformed (like ap-southeast-2)")
    if bucket and (not BUCKET_RE.fullmatch(bucket) or ".." in bucket or re.fullmatch(r"[0-9.]+", bucket)):
        raise ValueError("the S3 bucket name is malformed (3 to 63 lowercase letters, digits, dots and hyphens)")
    return Request(key_id or None, secret or None, token or None, region or None, bucket or None)


def server_has_keys() -> bool:
    return bool(os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get("AWS_SECRET_ACCESS_KEY"))


def configured() -> bool:
    """Whether the SERVER can run AWS jobs by itself (credentials in its environment and a bucket). A caller may still bring theirs."""
    return server_has_keys() and bool(settings.AWS_TRAIN_BUCKET)


def resolve(req: Optional[Request]) -> Account:
    """The caller's credentials when given, otherwise the server's default chain. PermissionError (a fixed message) when neither exists."""
    req = req or Request()
    if req.key_id is None and not server_has_keys():
        raise PermissionError(NO_CREDENTIALS)
    region = req.region or settings.AWS_REGION
    bucket = req.bucket or settings.AWS_TRAIN_BUCKET
    if not REGION_RE.fullmatch(region or ""):
        raise PermissionError("the AWS region is not valid: send X-Aws-Region or fix AWS_REGION on the server")
    if not bucket or not BUCKET_RE.fullmatch(bucket):
        raise PermissionError(NO_BUCKET)
    return Account(req.key_id, req.secret, req.token, region, bucket)


def validate_options(instance_type: str, max_minutes: int, spot: bool) -> Tuple[str, int, bool]:
    if instance_type not in ALLOWED_INSTANCE_TYPES:
        raise ValueError(f"instance_type must be one of {sorted(ALLOWED_INSTANCE_TYPES)}")
    if isinstance(max_minutes, bool) or not isinstance(max_minutes, int) or not 1 <= max_minutes <= MAX_MINUTES:
        raise ValueError(f"max_minutes must be a whole number from 1 to {MAX_MINUTES}")
    return instance_type, max_minutes, bool(spot)


# ------------------------------------------------------------------------------------------------ slug and keys
def slug_for(region: str, instance_id: str) -> str:
    return f"aws:{region}:{instance_id}"


def parse_slug(slug: Optional[str]) -> Optional[Tuple[str, str]]:
    m = re.fullmatch(r"aws:([a-z0-9\-]+):(i-[0-9a-f]+)", slug or "")
    return (m.group(1), m.group(2)) if m else None


def snapshot_key(job_id: int) -> str:
    return f"datamend/train/{job_id}/snapshot.jsonl.gz"


def result_key(job_id: int) -> str:
    return f"datamend/train/{job_id}/result.json"


# ------------------------------------------------------------------------------------------------ client and safe errors
def make_client(service: str, account: Account) -> Any:
    """A boto3 client for ``service`` using the caller's keys, or boto3's default chain when none were sent. Tests replace this function."""
    try:
        import boto3                                    # lazy: the app and the tests start without it
        from botocore.config import Config
    except ImportError:
        raise AwsError("boto3 is not installed on the server (pip install boto3)") from None
    kw: Dict[str, Any] = {}
    if account.key_id is not None:
        kw.update(aws_access_key_id=account.key_id, aws_secret_access_key=account.secret)
        if account.token:
            kw["aws_session_token"] = account.token
    cfg = Config(region_name=account.region, retries={"max_attempts": 3, "mode": "standard"}, connect_timeout=10, read_timeout=30,
                 **({"signature_version": "s3v4"} if service == "s3" else {}))
    return boto3.client(service, config=cfg, **kw)


_AUTH = {"AuthFailure", "UnauthorizedOperation", "UnauthorizedAccess", "InvalidClientTokenId", "SignatureDoesNotMatch", "ExpiredToken", "ExpiredTokenException",
         "AccessDenied", "InvalidAccessKeyId", "AccessDeniedException", "403", "OptInRequired", "UnrecognizedClientException"}
_GONE = {"InvalidInstanceID.NotFound", "InvalidInstanceID.Malformed"}
_MISSING_KEY = {"404", "NoSuchKey", "NotFound"}


def _code_of(e: BaseException) -> str:
    resp = getattr(e, "response", None)
    code = ""
    if isinstance(resp, dict) and isinstance(resp.get("Error"), dict):
        code = str(resp["Error"].get("Code") or "")
    return code if re.fullmatch(r"[A-Za-z0-9._\-]{1,64}", code) else ""


def _translate(op: str, e: BaseException) -> AwsError:
    """A safe AwsError from any exception: fixed wording, the AWS error code, the exception class. Never the exception's own text."""
    code = _code_of(e)
    if code in _AUTH:
        return AwsError(f"AWS refused the credentials or they lack a permission for {op} ({code})", "auth", code)
    if code == "NoSuchBucket":
        return AwsError("the S3 bucket does not exist in this account or region", "bucket", code)
    if code in _GONE:
        return AwsError("this instance is not visible to the credentials supplied (a different AWS account or region, or it was removed)", "notfound", code)
    if code in ("InstanceLimitExceeded", "VcpuLimitExceeded", "MaxSpotInstanceCountExceeded"):
        return AwsError(f"AWS refused to start the instance: a quota is exhausted ({code}); a GPU type needs a quota approved by AWS first", "other", code)
    if code in ("InsufficientInstanceCapacity", "SpotMaxPriceTooLow", "Unsupported"):
        return AwsError(f"AWS has no capacity for that instance type here right now ({code})", "other", code)
    name = type(e).__name__ if re.fullmatch(r"[A-Za-z0-9_]{1,60}", type(e).__name__) else "error"
    return AwsError(f"the AWS call {op} failed ({code or name})", "other", code)


def _call(op: str, fn, **kw):
    try:
        return fn(**kw)
    except AwsError:
        raise
    except Exception as e:                                              # noqa: BLE001: translated to a safe message, the original is dropped
        raise _translate(op, e) from None


def scrub(text: str, account: Optional[Account] = None) -> str:
    """Remove anything credential-like from a text: the account's own values, any URL, and key-id or signature shapes."""
    t = text or ""
    if account is not None:
        for v in (account.secret, account.token, account.key_id):
            if v:
                t = t.replace(v, "***")
    t = re.sub(r"https?://\S+", "[url]", t)
    t = re.sub(r"\b(?:AKIA|ASIA)[A-Z0-9]{12,}\b", "***", t)
    t = re.sub(r"(?i)X-Amz-[A-Za-z\-]+=[^&\s]*", "***", t)
    return t


# ------------------------------------------------------------------------------------------------ the instance's script
def build_trainer(snapshot_sha: str) -> str:
    """train.py: the trainer plus a runner that reads snapshot.jsonl.gz from the working folder and writes result.json beside it."""
    runner = (
        "\n\n# ---- runner (generated by the platform) ----\n"
        "import gzip as _gz, json as _json\n"
        f"_SHA = {snapshot_sha!r}\n"
        "_text = _gz.open('snapshot.jsonl.gz', 'rt', encoding='utf-8').read()\n"
        "try:\n"
        "    _res = {'ok': True, 'metrics': train(parse_snapshot(_text), snapshot_sha256=_SHA)}\n"
        "except NotEnoughLabels as _e:\n"
        "    _res = {'ok': False, 'error': str(_e)}\n"
        "open('result.json', 'w').write(_json.dumps(_res))\n"
        "print(_json.dumps(_res)[:2000])\n")
    source = FUSION_SOURCE.read_text(encoding="utf-8").split('\nif __name__ == "__main__":')[0]
    return source + runner


def build_user_data(snapshot_sha: str, get_url: str, put_url: str, max_minutes: int) -> str:
    """The shell script EC2 runs at first boot. The time cap is its first command. It holds the trainer (gzip and base64) and two presigned URLs,
    and no credential. Must stay under 16 KB (before base64)."""
    for u in (get_url, put_url):
        if not u.startswith("https://") or "'" in u or "\n" in u:
            raise AwsError("an unexpected presigned URL was produced")
    script = base64.b64encode(gzip.compress(build_trainer(snapshot_sha).encode("utf-8"))).decode("ascii")
    fail = json.dumps({"ok": False, "error": "the trainer did not finish on the instance (see /var/log/datamend-train.log there)"})
    ud = (
        "#!/bin/bash\n"
        f"shutdown -h +{int(max_minutes)}\n"                                   # the hard time cap, before anything else
        "exec >/var/log/datamend-train.log 2>&1\n"
        "mkdir -p /opt/datamend && cd /opt/datamend\n"
        f"echo '{script}' | base64 -d | gunzip > train.py\n"
        f"curl -sS --fail --retry 5 --retry-delay 3 -o snapshot.jsonl.gz '{get_url}'\n"
        "dnf install -y python3-pip\n"
        "python3 -m pip install 'numpy<2' 'scipy<2'\n"
        "python3 train.py\n"
        f"[ -s result.json ] || echo '{fail}' > result.json\n"
        f"curl -sS --fail --retry 5 --retry-delay 3 -X PUT --upload-file result.json '{put_url}'\n"
        "shutdown -h now\n")
    if len(ud.encode("utf-8")) > USER_DATA_LIMIT:
        raise AwsError("the generated instance script is larger than EC2 allows (16 KB)")
    return ud


# ------------------------------------------------------------------------------------------------ operations
def launch(job_id: int, snapshot_content: str, snapshot_sha: str, account: Account, instance_type: str, max_minutes: int, spot: bool = False) -> str:
    """Upload the snapshot, presign, and run ONE instance. Returns the instance id. On a failure after the upload the snapshot is deleted again."""
    instance_type, max_minutes, spot = validate_options(instance_type, max_minutes, spot)
    s3, ec2, ssm = make_client("s3", account), make_client("ec2", account), make_client("ssm", account)
    body = gzip.compress(snapshot_content.encode("utf-8"))
    _call("s3:PutObject", s3.put_object, Bucket=account.bucket, Key=snapshot_key(job_id), Body=body, ServerSideEncryption="AES256")
    try:
        get_url = _call("s3:GetObject", s3.generate_presigned_url, ClientMethod="get_object",
                        Params={"Bucket": account.bucket, "Key": snapshot_key(job_id)}, ExpiresIn=URL_EXPIRY_S)
        put_url = _call("s3:PutObject", s3.generate_presigned_url, ClientMethod="put_object",
                        Params={"Bucket": account.bucket, "Key": result_key(job_id)}, ExpiresIn=URL_EXPIRY_S)
        user_data = build_user_data(snapshot_sha, get_url, put_url, max_minutes)
        ami = str(_call("ssm:GetParameter", ssm.get_parameter, Name=AMI_PARAMETER)["Parameter"]["Value"])
        if not AMI_RE.fullmatch(ami):
            raise AwsError("the AMI parameter returned an unexpected value")
        tags = [{"Key": "datamend-job", "Value": str(job_id)}, {"Key": "datamend-managed", "Value": "true"}]
        args: Dict[str, Any] = dict(
            ImageId=ami, InstanceType=instance_type, MinCount=1, MaxCount=1, UserData=user_data,
            InstanceInitiatedShutdownBehavior="terminate", MetadataOptions={"HttpTokens": "required", "HttpEndpoint": "enabled"},
            BlockDeviceMappings=[{"DeviceName": "/dev/xvda", "Ebs": {"VolumeSize": ROOT_VOLUME_GB, "VolumeType": "gp3", "DeleteOnTermination": True}}],
            TagSpecifications=[{"ResourceType": "instance", "Tags": tags}, {"ResourceType": "volume", "Tags": tags}])
        if spot:
            args["InstanceMarketOptions"] = {"MarketType": "spot", "SpotOptions": {"SpotInstanceType": "one-time", "InstanceInterruptionBehavior": "terminate"}}
        out = _call("ec2:RunInstances", ec2.run_instances, **args)
        iid = str(out["Instances"][0]["InstanceId"])
        if not INSTANCE_ID_RE.fullmatch(iid):
            raise AwsError("AWS returned an unexpected instance id")
        return iid
    except Exception:
        delete_objects(job_id, account)
        raise


def inspect(job_id: int, instance_id: str, account: Account) -> Dict[str, Any]:
    """{'state': pending|running|shutting-down|terminated|..., 'result': bool}. Raises AwsError(kind='notfound') when the instance is not visible to
    these credentials or is not tagged for this job (so a job is never confused with another account's or another job's instance)."""
    ec2, s3 = make_client("ec2", account), make_client("s3", account)
    out = _call("ec2:DescribeInstances", ec2.describe_instances, InstanceIds=[instance_id])
    try:
        inst = out["Reservations"][0]["Instances"][0]
        state = str(inst["State"]["Name"])
        tags = {t["Key"]: t["Value"] for t in inst.get("Tags", [])}
    except (KeyError, IndexError, TypeError):
        raise AwsError("this instance is not visible to the credentials supplied", "notfound") from None
    if tags.get("datamend-job") != str(job_id) or tags.get("datamend-managed") != "true":
        raise AwsError("this instance is not a DataMend instance for this job", "notfound")
    return {"state": state, "result": _result_exists(job_id, account, s3)}


def _result_exists(job_id: int, account: Account, s3: Any = None) -> bool:
    s3 = s3 or make_client("s3", account)
    try:
        s3.head_object(Bucket=account.bucket, Key=result_key(job_id))
        return True
    except Exception as e:                                              # noqa: BLE001
        if _code_of(e) in _MISSING_KEY:
            return False
        raise _translate("s3:HeadObject", e) from None


def fetch_result(job_id: int, account: Account) -> Dict[str, Any]:
    s3 = make_client("s3", account)
    obj = _call("s3:GetObject", s3.get_object, Bucket=account.bucket, Key=result_key(job_id))
    try:
        data = json.loads(obj["Body"].read(2_000_000).decode("utf-8"))
    except Exception:                                                   # noqa: BLE001
        raise AwsError("the result file on S3 is not valid JSON") from None
    if not isinstance(data, dict):
        raise AwsError("the result file on S3 is not a JSON object")
    return data


def terminate(instance_id: str, account: Account) -> None:
    _call("ec2:TerminateInstances", make_client("ec2", account).terminate_instances, InstanceIds=[instance_id])


def delete_objects(job_id: int, account: Account) -> None:
    """Best effort: remove the snapshot and the result from the bucket. Never raises."""
    try:
        s3 = make_client("s3", account)
        for key in (snapshot_key(job_id), result_key(job_id)):
            try:
                s3.delete_object(Bucket=account.bucket, Key=key)
            except Exception:                                           # noqa: BLE001
                pass
    except Exception:                                                   # noqa: BLE001
        pass


def cleanup(job_id: int, instance_id: Optional[str], account: Account, terminate_instance: bool = True) -> None:
    """Cancel and clean up when a job ends: terminate the instance (if asked and still there) and delete the snapshot and result objects. Never raises."""
    if terminate_instance and instance_id:
        try:
            terminate(instance_id, account)
        except Exception:                                               # noqa: BLE001
            pass
    delete_objects(job_id, account)
