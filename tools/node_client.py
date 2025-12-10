# tools/node_client.py
import os
from typing import Optional, Dict, Any

from dotenv import load_dotenv
import requests

load_dotenv()

MYFEVENT_BASE_URL = os.getenv("MYFEVENT_BASE_URL", "http://localhost:5000/api")
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


def post(path: str, json: dict, user_token: Optional[str] = None):
    base = MYFEVENT_BASE_URL.rstrip("/")
    url = f"{base}/{path.lstrip('/')}"
    try:
        resp = requests.post(url, json=json, headers=_build_headers(user_token=user_token))
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as e:
        # Lấy thông tin chi tiết từ response body nếu có
        error_detail = str(e)
        try:
            if e.response is not None:
                error_body = e.response.json()
                if isinstance(error_body, dict):
                    error_msg = error_body.get("message") or error_body.get("error") or str(error_body)
                    error_detail = f"{error_msg} (HTTP {e.response.status_code})"
        except:
            pass
        raise ValueError(f"Backend API error: {error_detail}")
    except requests.exceptions.RequestException as e:
        raise ValueError(f"Network error when calling backend: {str(e)}")


def get(path: str, params: Optional[dict] = None, user_token: Optional[str] = None):
    base = MYFEVENT_BASE_URL.rstrip("/")
    url = f"{base}/{path.lstrip('/')}"
    resp = requests.get(url, params=params, headers=_build_headers(user_token=user_token))
    resp.raise_for_status()
    return resp.json()
