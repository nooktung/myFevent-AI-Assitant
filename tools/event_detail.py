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
        print(f"[INFO] get_event_detail_for_ai_tool: calling /events/{event_id}/ai-detail")
        result = get(f"/events/{event_id}/ai-detail", user_token=user_token)
        print(f"[INFO] get_event_detail_for_ai_tool: received response, type={type(result)}")

        # API backend bọc data trong { data: { ... } }
        if isinstance(result, dict):
            data = result.get("data", result)
            # Đảm bảo có đủ thông tin cần thiết
            if not data.get("event"):
                error_msg = f"API không trả về thông tin event. Response keys: {list(data.keys()) if isinstance(data, dict) else 'N/A'}"
                print(f"[ERROR] {error_msg}")
                raise ValueError(error_msg)
            print(f"[INFO] get_event_detail_for_ai_tool: success, event name={data.get('event', {}).get('name', 'N/A')}")
            return data

        print(f"[WARN] get_event_detail_for_ai_tool: unexpected result type: {type(result)}")
        return result
    except Exception as e:
        # Log chi tiết để debug
        import traceback
        error_traceback = traceback.format_exc()
        print(f"[ERROR] get_event_detail_for_ai_tool failed: {e}")
        print(f"[ERROR] eventId: {event_id}")
        print(f"[ERROR] user_token present: {user_token is not None}")
        print(f"[ERROR] Traceback:\n{error_traceback}")
        # Trả về error message rõ ràng hơn cho LLM
        raise ValueError(f"Không thể lấy thông tin sự kiện với eventId={event_id}. Lỗi: {str(e)}. Vui lòng kiểm tra lại eventId hoặc quyền truy cập.")


