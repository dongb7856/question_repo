"""腾讯云 GeneralAccurateOCR（与 autoyt2 / SE_VXLFT 同源）。"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

from tencentcloud.common import credential
from tencentcloud.common.exception.tencent_cloud_sdk_exception import (
    TencentCloudSDKException,
)
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.ocr.v20181119 import models, ocr_client


class OcrNotConfiguredError(RuntimeError):
    pass


class OcrApiError(RuntimeError):
    pass


def _credentials() -> tuple[str, str, str]:
    secret_id = os.environ.get("TENCENT_OCR_SECRET_ID", "").strip()
    secret_key = os.environ.get("TENCENT_OCR_SECRET_KEY", "").strip()
    region = os.environ.get("TENCENT_OCR_REGION", "ap-shanghai").strip()
    if not secret_id or not secret_key:
        raise OcrNotConfiguredError(
            "请在 .env 中配置 TENCENT_OCR_SECRET_ID / TENCENT_OCR_SECRET_KEY"
        )
    return secret_id, secret_key, region


def image_to_base64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def general_accurate_ocr(path: Path, *, min_confidence: int = 80) -> list[str]:
    secret_id, secret_key, region = _credentials()
    client = ocr_client.OcrClient(
        credential.Credential(secret_id, secret_key),
        region,
        ClientProfile(),
    )
    req = models.GeneralAccurateOCRRequest()
    req.from_json_string(
        json.dumps({"ImageBase64": image_to_base64(path), "IsPdf": False})
    )
    try:
        resp = client.GeneralAccurateOCR(req)
        payload = json.loads(resp.to_json_string())
    except TencentCloudSDKException as exc:
        raise OcrApiError(exc.message) from exc

    lines: list[str] = []
    for item in payload.get("TextDetections", []):
        if item.get("Confidence", 0) >= min_confidence:
            text = (item.get("DetectedText") or "").strip()
            if text:
                lines.append(text)
    return lines
