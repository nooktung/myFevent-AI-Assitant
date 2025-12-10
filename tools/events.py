# tools/events.py
from typing import Dict, Any, Optional
from .node_client import post


def create_event_tool(args: Dict[str, Any], user_token: Optional[str] = None) -> Dict[str, Any]:
    """
    Gọi endpoint Node /api/events để tạo event mới.
    args: dict sinh từ LLM theo schema tool "create_event".
    user_token: JWT của user (để Node set req.user.id, EventMember HoOC, ...).
    """

    payload: Dict[str, Any] = {
        "name": args.get("name"),
        "description": args.get("description") or "",
        "organizerName": args.get("organizerName"),
        "eventStartDate": args.get("eventStartDate"),
        "eventEndDate": args.get("eventEndDate"),
        "location": args.get("location") or "",
        "type": args.get("type") or "private",  # 'public' | 'private'
        "images": args.get("images") or [],
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
        raise ValueError(f"Missing required fields for createEvent: {', '.join(missing)}")

    # Validate format ngày tháng (yyyy-mm-dd)
    import re
    date_pattern = r'^\d{4}-\d{2}-\d{2}$'
    if payload["eventStartDate"] and not re.match(date_pattern, payload["eventStartDate"]):
        raise ValueError(f"Invalid date format for eventStartDate: '{payload['eventStartDate']}'. Expected format: yyyy-mm-dd (e.g., 2026-03-05)")
    if payload["eventEndDate"] and not re.match(date_pattern, payload["eventEndDate"]):
        raise ValueError(f"Invalid date format for eventEndDate: '{payload['eventEndDate']}'. Expected format: yyyy-mm-dd (e.g., 2026-03-14)")

    try:
        return post("/events", json=payload, user_token=user_token)
    except ValueError as e:
        # Re-raise ValueError với message rõ ràng hơn
        raise ValueError(str(e))
    except Exception as e:
        raise ValueError(f"Error creating event: {str(e)}")
