# tools/events.py
from typing import Dict, Any, Optional
from .node_client import post


def create_event_tool(args: Dict[str, Any], user_token: Optional[str] = None) -> Dict[str, Any]:
    """
    Gọi endpoint Node /api/events để tạo event mới.
    args: dict sinh từ LLM theo schema tool "create_event".
    user_token: JWT của user (để Node set req.user.id, EventMember HoOC, ...).
    """

    # Xử lý images: nếu không có thì dùng default image
    images = args.get("images") or []
    if not images or (isinstance(images, list) and len(images) == 0):
        # Default image URL cho sự kiện (có thể thay bằng URL ảnh mặc định của hệ thống)
        images = ["https://images.unsplash.com/photo-1540575467063-178a50c2df87?w=800"]
    
    payload: Dict[str, Any] = {
        "name": args.get("name"),
        "description": args.get("description") or "",
        "organizerName": args.get("organizerName"),
        "eventStartDate": args.get("eventStartDate"),
        "eventEndDate": args.get("eventEndDate"),
        "location": args.get("location") or "",
        "type": args.get("type") or "private",  # 'public' | 'private'
        "images": images,
    }

    # Validate tối thiểu
    missing = []
    if not payload["name"]:
        missing.append("name")
    if not payload["organizerName"]:
        missing.append("organizerName")
    if not payload["eventStartDate"]:
        missing.append("eventStartDate")
    if not payload["eventEndDate"]:
        missing.append("eventEndDate")
    if not payload["location"]:
        missing.append("location")

    if missing:
        # Chuyển đổi tên field sang tiếng Việt
        field_names = {
            "name": "tên sự kiện",
            "organizerName": "đơn vị tổ chức",
            "eventStartDate": "ngày bắt đầu",
            "eventEndDate": "ngày kết thúc",
            "location": "địa điểm"
        }
        missing_vn = [field_names.get(f, f) for f in missing]
        raise ValueError(f"Thiếu thông tin bắt buộc: {', '.join(missing_vn)}. Vui lòng cung cấp đầy đủ thông tin.")

    # Validate format ngày tháng (yyyy-mm-dd)
    import re
    date_pattern = r'^\d{4}-\d{2}-\d{2}$'
    if payload["eventStartDate"] and not re.match(date_pattern, payload["eventStartDate"]):
        raise ValueError(f"Định dạng ngày bắt đầu không hợp lệ: '{payload['eventStartDate']}'. Vui lòng sử dụng định dạng yyyy-mm-dd (ví dụ: 2025-05-06).")
    if payload["eventEndDate"] and not re.match(date_pattern, payload["eventEndDate"]):
        raise ValueError(f"Định dạng ngày kết thúc không hợp lệ: '{payload['eventEndDate']}'. Vui lòng sử dụng định dạng yyyy-mm-dd (ví dụ: 2025-05-11).")

    # Log để debug
    print(f"[create_event_tool] Creating event with payload:")
    print(f"  - name: {payload.get('name')}")
    print(f"  - organizerName: {payload.get('organizerName')}")
    print(f"  - eventStartDate: {payload.get('eventStartDate')}")
    print(f"  - eventEndDate: {payload.get('eventEndDate')}")
    print(f"  - location: {payload.get('location')}")
    print(f"  - type: {payload.get('type')}")
    print(f"  - images: {payload.get('images')}")
    print(f"  - has_token: {bool(user_token)}")
    print(f"  - token_prefix: {user_token[:20] + '...' if user_token else 'None'}")
    
    try:
        return post("/events", json=payload, user_token=user_token)
    except ValueError as e:
        # Re-raise ValueError với message rõ ràng hơn
        print(f"[create_event_tool] ValueError: {str(e)}")
        raise ValueError(str(e))
    except Exception as e:
        print(f"[create_event_tool] Exception: {str(e)}")
        # Nếu đã là ValueError thì giữ nguyên message, nếu không thì wrap lại
        if isinstance(e, ValueError):
            raise
        raise ValueError(f"Không thể tạo sự kiện. {str(e)}")
