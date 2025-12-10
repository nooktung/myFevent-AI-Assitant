# tools/node_client.py
import os
import time
from typing import Optional, Dict, Any, Callable

from dotenv import load_dotenv
import requests

load_dotenv()

MYFEVENT_BASE_URL = os.getenv("MYFEVENT_BASE_URL", "http://localhost:8080/api")
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
    headers = _build_headers(user_token=user_token)
    print(f"[node_client] POST request to: {url}")
    print(f"[node_client] Base URL: {MYFEVENT_BASE_URL}")
    print(f"[node_client] Path: {path}")
    print(f"[node_client] Payload keys: {list(json.keys()) if json else 'None'}")
    print(f"[node_client] Has Authorization header: {'Authorization' in headers}")
    print(f"[node_client] Authorization prefix: {headers.get('Authorization', '')[:30]}..." if headers.get('Authorization') else "[node_client] No Authorization header")
    resp = requests.post(url, json=json, headers=headers, timeout=30)
    print(f"[node_client] Response status: {resp.status_code}")
    if resp.status_code >= 400:
        try:
            error_body = resp.json()
            print(f"[node_client] Error response body: {error_body}")
        except:
            print(f"[node_client] Error response text: {resp.text[:200]}")
    resp.raise_for_status()
    return resp.json()


def post(path: str, json: dict, user_token: Optional[str] = None):
    """POST request với retry logic cho các lỗi tạm thời."""
    base = MYFEVENT_BASE_URL.rstrip("/")
    url = f"{base}/{path.lstrip('/')}"
    
    try:
        return _retry_request(_post_internal, path, json, user_token=user_token)
    except requests.exceptions.Timeout as e:
        raise ValueError("Kết nối đến hệ thống quá thời gian chờ. Vui lòng kiểm tra kết nối mạng hoặc thử lại sau.")
    except requests.exceptions.ConnectionError as e:
        raise ValueError("Không thể kết nối đến hệ thống. Vui lòng kiểm tra xem hệ thống có đang hoạt động không hoặc thử lại sau.")
    except requests.exceptions.HTTPError as e:
        # Lấy thông tin chi tiết từ response body nếu có
        error_message = ""
        suggestion = "Vui lòng kiểm tra lại thông tin yêu cầu hoặc thử lại sau."
        
        try:
            if e.response is not None:
                error_body = e.response.json() if e.response.content else {}
                if isinstance(error_body, dict):
                    backend_msg = error_body.get("message") or error_body.get("error") or ""
                    
                    # Phân loại lỗi và đưa ra thông báo tự nhiên
                    status_code = e.response.status_code
                    if status_code == 400:
                        # Lỗi validation - hiển thị message từ backend một cách tự nhiên
                        if backend_msg:
                            if "Ảnh sự kiện là bắt buộc" in backend_msg or "image" in backend_msg.lower():
                                error_message = "Vui lòng cung cấp ảnh sự kiện hoặc để hệ thống tự động sử dụng ảnh mặc định."
                            elif "ngày" in backend_msg.lower() or "date" in backend_msg.lower():
                                if "Ngày kết thúc" in backend_msg:
                                    error_message = "Ngày kết thúc phải sau ngày bắt đầu. Vui lòng kiểm tra lại ngày tháng."
                                elif "phải là ngày hôm nay" in backend_msg:
                                    error_message = "Ngày bắt đầu và ngày kết thúc phải là ngày hôm nay hoặc trong tương lai. Vui lòng chọn lại ngày phù hợp."
                                else:
                                    error_message = "Ngày tháng không hợp lệ. Vui lòng kiểm tra lại định dạng ngày tháng (ví dụ: 2025-05-06)."
                            elif "missing" in backend_msg.lower() or "required" in backend_msg.lower() or "thiếu" in backend_msg.lower():
                                error_message = "Thiếu thông tin bắt buộc. Vui lòng cung cấp đầy đủ thông tin."
                            else:
                                error_message = backend_msg if backend_msg else "Thông tin không hợp lệ. Vui lòng kiểm tra lại các trường đã nhập."
                        else:
                            error_message = "Thông tin không hợp lệ. Vui lòng kiểm tra lại các trường đã nhập."
                    elif status_code == 401:
                        error_message = "Phiên đăng nhập của bạn đã hết hạn hoặc không hợp lệ. Vui lòng đăng nhập lại."
                    elif status_code == 403:
                        error_message = "Bạn không có quyền thực hiện thao tác này. Vui lòng kiểm tra quyền của bạn hoặc liên hệ quản trị viên."
                    elif status_code == 404:
                        error_message = "Không tìm thấy tài nguyên yêu cầu. Có thể đường dẫn không đúng hoặc tài nguyên đã bị xóa."
                    elif status_code == 500:
                        error_message = "Hệ thống đang gặp sự cố. Vui lòng thử lại sau hoặc liên hệ hỗ trợ nếu vấn đề vẫn tiếp tục."
                    else:
                        error_message = backend_msg if backend_msg else "Đã xảy ra lỗi khi xử lý yêu cầu. Vui lòng thử lại sau."
        except:
            error_message = "Đã xảy ra lỗi khi kết nối đến hệ thống. Vui lòng thử lại sau."
        
        if not error_message:
            error_message = "Đã xảy ra lỗi khi xử lý yêu cầu. Vui lòng thử lại sau."
        
        raise ValueError(error_message)
    except requests.exceptions.RequestException as e:
        raise ValueError("Không thể kết nối đến hệ thống. Vui lòng kiểm tra kết nối mạng và thử lại sau.")


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
        raise ValueError("Kết nối đến hệ thống quá thời gian chờ. Vui lòng kiểm tra kết nối mạng hoặc thử lại sau.")
    except requests.exceptions.ConnectionError as e:
        raise ValueError("Không thể kết nối đến hệ thống. Vui lòng kiểm tra xem hệ thống có đang hoạt động không hoặc thử lại sau.")
    except requests.exceptions.HTTPError as e:
        # Lấy thông tin chi tiết từ response body nếu có
        error_message = ""
        suggestion = "Vui lòng kiểm tra lại thông tin yêu cầu hoặc thử lại sau."
        
        try:
            if e.response is not None:
                error_body = e.response.json() if e.response.content else {}
                if isinstance(error_body, dict):
                    backend_msg = error_body.get("message") or error_body.get("error") or ""
                    
                    # Phân loại lỗi và đưa ra thông báo tự nhiên
                    status_code = e.response.status_code
                    if status_code == 400:
                        # Lỗi validation - hiển thị message từ backend một cách tự nhiên
                        if backend_msg:
                            if "Ảnh sự kiện là bắt buộc" in backend_msg or "image" in backend_msg.lower():
                                error_message = "Vui lòng cung cấp ảnh sự kiện hoặc để hệ thống tự động sử dụng ảnh mặc định."
                            elif "ngày" in backend_msg.lower() or "date" in backend_msg.lower():
                                if "Ngày kết thúc" in backend_msg:
                                    error_message = "Ngày kết thúc phải sau ngày bắt đầu. Vui lòng kiểm tra lại ngày tháng."
                                elif "phải là ngày hôm nay" in backend_msg:
                                    error_message = "Ngày bắt đầu và ngày kết thúc phải là ngày hôm nay hoặc trong tương lai. Vui lòng chọn lại ngày phù hợp."
                                else:
                                    error_message = "Ngày tháng không hợp lệ. Vui lòng kiểm tra lại định dạng ngày tháng (ví dụ: 2025-05-06)."
                            elif "missing" in backend_msg.lower() or "required" in backend_msg.lower() or "thiếu" in backend_msg.lower():
                                error_message = "Thiếu thông tin bắt buộc. Vui lòng cung cấp đầy đủ thông tin."
                            else:
                                error_message = backend_msg if backend_msg else "Thông tin không hợp lệ. Vui lòng kiểm tra lại các trường đã nhập."
                        else:
                            error_message = "Thông tin không hợp lệ. Vui lòng kiểm tra lại các trường đã nhập."
                    elif status_code == 401:
                        error_message = "Phiên đăng nhập của bạn đã hết hạn hoặc không hợp lệ. Vui lòng đăng nhập lại."
                    elif status_code == 403:
                        error_message = "Bạn không có quyền thực hiện thao tác này. Vui lòng kiểm tra quyền của bạn hoặc liên hệ quản trị viên."
                    elif status_code == 404:
                        error_message = "Không tìm thấy tài nguyên yêu cầu. Có thể đường dẫn không đúng hoặc tài nguyên đã bị xóa."
                    elif status_code == 500:
                        error_message = "Hệ thống đang gặp sự cố. Vui lòng thử lại sau hoặc liên hệ hỗ trợ nếu vấn đề vẫn tiếp tục."
                    else:
                        error_message = backend_msg if backend_msg else "Đã xảy ra lỗi khi xử lý yêu cầu. Vui lòng thử lại sau."
        except:
            error_message = "Đã xảy ra lỗi khi kết nối đến hệ thống. Vui lòng thử lại sau."
        
        if not error_message:
            error_message = "Đã xảy ra lỗi khi xử lý yêu cầu. Vui lòng thử lại sau."
        
        raise ValueError(error_message)
    except requests.exceptions.RequestException as e:
        raise ValueError("Không thể kết nối đến hệ thống. Vui lòng kiểm tra kết nối mạng và thử lại sau.")
