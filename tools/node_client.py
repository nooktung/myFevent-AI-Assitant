# tools/node_client.py
import os
import time
from typing import Optional, Dict, Any, Callable

from dotenv import load_dotenv
import requests

load_dotenv()

MYFEVENT_BASE_URL = os.getenv("MYFEVENT_BASE_URL", "http://localhost:5000/api")
SERVICE_API_KEY = os.getenv("MYFEVENT_API_KEY", "")

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY_BASE = 1  # seconds (exponential backoff: 1s, 2s, 4s)

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


def _should_retry_error(error: Exception) -> bool:
    """
    Kiểm tra xem lỗi có nên retry không.
    Chỉ retry các lỗi tạm thời: timeout, connection error, server error (500, 502, 503, 504)
    """
    if isinstance(error, (requests.exceptions.Timeout, requests.exceptions.ConnectionError)):
        return True
    
    if isinstance(error, requests.exceptions.HTTPError):
        if error.response is not None:
            status_code = error.response.status_code
            # Retry cho server errors (5xx) và một số client errors có thể tạm thời
            if status_code in [500, 502, 503, 504]:
                return True
    
    return False


def _retry_request(
    request_func: Callable,
    *args,
    max_retries: int = MAX_RETRIES,
    **kwargs
) -> Any:
    """
    Wrapper function để retry request với exponential backoff.
    Chỉ retry các lỗi tạm thời (timeout, connection error, server error).
    """
    last_error = None
    
    for attempt in range(max_retries):
        try:
            return request_func(*args, **kwargs)
        except Exception as e:
            last_error = e
            
            # Nếu không phải lỗi nên retry, raise ngay
            if not _should_retry_error(e):
                raise
            
            # Nếu đã hết số lần retry, raise lỗi cuối cùng
            if attempt == max_retries - 1:
                break
            
            # Tính delay với exponential backoff
            delay = RETRY_DELAY_BASE * (2 ** attempt)
            print(f"[node_client] Retry attempt {attempt + 1}/{max_retries} after {delay}s delay. Error: {type(e).__name__}: {str(e)[:100]}")
            time.sleep(delay)
    
    # Nếu đến đây, đã hết retry, raise lỗi cuối cùng
    raise last_error


def _post_internal(path: str, json: dict, user_token: Optional[str] = None):
    """Internal function để thực hiện POST request (không có retry)."""
    base = MYFEVENT_BASE_URL.rstrip("/")
    url = f"{base}/{path.lstrip('/')}"
    resp = requests.post(url, json=json, headers=_build_headers(user_token=user_token), timeout=30)
    resp.raise_for_status()
    return resp.json()


def post(path: str, json: dict, user_token: Optional[str] = None):
    """POST request với retry logic cho các lỗi tạm thời."""
    base = MYFEVENT_BASE_URL.rstrip("/")
    url = f"{base}/{path.lstrip('/')}"
    
    try:
        return _retry_request(_post_internal, path, json, user_token=user_token)
    except requests.exceptions.Timeout as e:
        raise ValueError(f"Kết nối đến backend quá thời gian chờ (timeout). URL: {url}. Vui lòng kiểm tra kết nối mạng hoặc thử lại sau.")
    except requests.exceptions.ConnectionError as e:
        raise ValueError(f"Không thể kết nối đến backend tại {base}. Vui lòng kiểm tra xem backend có đang chạy không. Chi tiết: {str(e)}")
    except requests.exceptions.HTTPError as e:
        # Lấy thông tin chi tiết từ response body nếu có
        error_detail = str(e)
        error_type = "HTTP_ERROR"
        suggestion = "Vui lòng kiểm tra lại thông tin yêu cầu hoặc thử lại sau."
        
        try:
            if e.response is not None:
                error_body = e.response.json() if e.response.content else {}
                if isinstance(error_body, dict):
                    error_msg = error_body.get("message") or error_body.get("error") or str(error_body)
                    error_detail = f"{error_msg} (HTTP {e.response.status_code})"
                    
                    # Phân loại lỗi và đưa ra gợi ý cụ thể
                    status_code = e.response.status_code
                    if status_code == 401:
                        error_type = "AUTHENTICATION_ERROR"
                        suggestion = "Token xác thực không hợp lệ hoặc đã hết hạn. Vui lòng đăng nhập lại."
                    elif status_code == 403:
                        error_type = "PERMISSION_ERROR"
                        suggestion = "Bạn không có quyền truy cập tài nguyên này. Vui lòng kiểm tra quyền của bạn."
                    elif status_code == 404:
                        error_type = "NOT_FOUND_ERROR"
                        suggestion = f"Không tìm thấy tài nguyên tại {path}. Vui lòng kiểm tra lại ID hoặc đường dẫn."
                    elif status_code == 500:
                        error_type = "SERVER_ERROR"
                        suggestion = "Lỗi từ phía server. Vui lòng thử lại sau hoặc liên hệ hỗ trợ."
        except:
            pass
        
        raise ValueError(f"Backend API error ({error_type}): {error_detail}. {suggestion}")
    except requests.exceptions.RequestException as e:
        raise ValueError(f"Lỗi kết nối khi gọi backend: {str(e)}. URL: {url}. Vui lòng kiểm tra kết nối mạng.")


def _get_internal(path: str, params: Optional[dict] = None, user_token: Optional[str] = None):
    """Internal function để thực hiện GET request (không có retry)."""
    base = MYFEVENT_BASE_URL.rstrip("/")
    url = f"{base}/{path.lstrip('/')}"
    resp = requests.get(url, params=params, headers=_build_headers(user_token=user_token), timeout=30)
    resp.raise_for_status()
    return resp.json()


def get(path: str, params: Optional[dict] = None, user_token: Optional[str] = None):
    """GET request với retry logic cho các lỗi tạm thời."""
    base = MYFEVENT_BASE_URL.rstrip("/")
    url = f"{base}/{path.lstrip('/')}"
    
    try:
        return _retry_request(_get_internal, path, params=params, user_token=user_token)
    except requests.exceptions.Timeout as e:
        raise ValueError(f"Kết nối đến backend quá thời gian chờ (timeout). URL: {url}. Vui lòng kiểm tra kết nối mạng hoặc thử lại sau.")
    except requests.exceptions.ConnectionError as e:
        raise ValueError(f"Không thể kết nối đến backend tại {base}. Vui lòng kiểm tra xem backend có đang chạy không. Chi tiết: {str(e)}")
    except requests.exceptions.HTTPError as e:
        # Lấy thông tin chi tiết từ response body nếu có
        error_detail = str(e)
        error_type = "HTTP_ERROR"
        suggestion = "Vui lòng kiểm tra lại thông tin yêu cầu hoặc thử lại sau."
        
        try:
            if e.response is not None:
                error_body = e.response.json() if e.response.content else {}
                if isinstance(error_body, dict):
                    error_msg = error_body.get("message") or error_body.get("error") or str(error_body)
                    error_detail = f"{error_msg} (HTTP {e.response.status_code})"
                    
                    # Phân loại lỗi và đưa ra gợi ý cụ thể
                    status_code = e.response.status_code
                    if status_code == 401:
                        error_type = "AUTHENTICATION_ERROR"
                        suggestion = "Token xác thực không hợp lệ hoặc đã hết hạn. Vui lòng đăng nhập lại."
                    elif status_code == 403:
                        error_type = "PERMISSION_ERROR"
                        suggestion = "Bạn không có quyền truy cập tài nguyên này. Vui lòng kiểm tra quyền của bạn."
                    elif status_code == 404:
                        error_type = "NOT_FOUND_ERROR"
                        suggestion = f"Không tìm thấy tài nguyên tại {path}. Vui lòng kiểm tra lại ID hoặc đường dẫn."
                    elif status_code == 500:
                        error_type = "SERVER_ERROR"
                        suggestion = "Lỗi từ phía server. Vui lòng thử lại sau hoặc liên hệ hỗ trợ."
        except:
            pass
        
        raise ValueError(f"Backend API error ({error_type}): {error_detail}. {suggestion}")
    except requests.exceptions.RequestException as e:
        raise ValueError(f"Lỗi kết nối khi gọi backend: {str(e)}. URL: {url}. Vui lòng kiểm tra kết nối mạng.")
