from typing import Dict, Any, Optional

from .node_client import get


def get_event_detail_for_ai_tool(
    args: Dict[str, Any],
    user_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Tool cho LLM: Lấy thông tin chi tiết sự kiện để làm nền khi sinh EPIC/TASK.

    Input:
      - eventId: ObjectId của event trong MongoDB (string, bắt buộc)

    Trả về:
      {
        "event": {...},
        "departments": [...],
        "members": {...},
        "epics": [...],
        "summary": {...}
      }
    """
    event_id: str = args.get("eventId")

    if not event_id:
        raise ValueError("eventId là bắt buộc cho get_event_detail_for_ai_tool")

    try:
        result = get(f"/events/{event_id}/ai-detail", user_token=user_token)

        # API backend bọc data trong { data: { ... } }
        if isinstance(result, dict):
            data = result.get("data", result)
            # Đảm bảo có đủ thông tin cần thiết
            if not data.get("event"):
                raise ValueError("API không trả về thông tin event")
            return data

        return result
    except Exception as e:
        # Log chi tiết để debug
        print(f"[ERROR] get_event_detail_for_ai_tool failed: {e}")
        print(f"[ERROR] eventId: {event_id}")
        print(f"[ERROR] user_token present: {user_token is not None}")
        raise


