# tools/node_client.py
import os
from typing import Optional, Dict, Any

from dotenv import load_dotenv
import requests

load_dotenv()

MYFEVENT_BASE_URL = os.getenv("MYFEVENT_BASE_URL", "http://localhost:5000/api")
# Đảm bảo base URL luôn trỏ tới prefix `/api` của backend Node, tránh lỗi thiếu `/api`
if not MYFEVENT_BASE_URL.rstrip("/").endswith("/api"):
    MYFEVENT_BASE_URL = MYFEVENT_BASE_URL.rstrip("/") + "/api"
SERVICE_API_KEY = os.getenv("MYFEVENT_API_KEY", "")

...



def _build_headers(
    user_token: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    headers: Dict[str, str] = {
        "Content-Type": "application/json",
    }

    # Ưu tiên JWT của user
    if user_token:
        headers["Authorization"] = f"Bearer {user_token}"
    elif SERVICE_API_KEY:
        headers["Authorization"] = f"Bearer {SERVICE_API_KEY}"

    if extra:
        headers.update(extra)

    return headers


def post(path: str, json: dict, user_token: Optional[str] = None, timeout: int = 30):
    base = MYFEVENT_BASE_URL.rstrip("/")
    url = f"{base}/{path.lstrip('/')}"
    resp = requests.post(url, json=json, headers=_build_headers(user_token=user_token), timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def get(path: str, params: Optional[dict] = None, user_token: Optional[str] = None, timeout: int = 30):
    base = MYFEVENT_BASE_URL.rstrip("/")
    url = f"{base}/{path.lstrip('/')}"
    resp = requests.get(url, params=params, headers=_build_headers(user_token=user_token), timeout=timeout)
    resp.raise_for_status()
    return resp.json()