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
        "currentUser": {
          "role": "HoOC" | "HoD" | "Member" | null,  # QUAN TRỌNG: Role của người dùng hiện tại
          "departmentId": "...",
          "departmentName": "...",
          "eventName": "..."
        },
        "departments": [...],
        "members": {...},
        "epics": [...],
        "summary": {...}
      }
      
    QUAN TRỌNG: Luôn kiểm tra currentUser.role trước khi tạo task/epic:
    - Nếu currentUser.role === "Member": KHÔNG được phép tạo task/epic
    - Nếu currentUser.role === "HoD": Chỉ được tạo task trong epic của ban mình, KHÔNG được tạo epic mới
    - Nếu currentUser.role === "HoOC": Có thể tạo cả epic và task cho bất kỳ ban nào
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
            
            # Format lại response để AI dễ đọc currentUser.role
            # Thêm message rõ ràng về role ở đầu response
            if data.get("currentUser"):
                current_user = data["currentUser"]
                role = current_user.get("role")
                if role:
                    # Thêm thông báo rõ ràng về role vào response
                    data["_user_role_info"] = {
                        "role": role,
                        "can_create_epic": role == "HoOC",
                        "can_create_task": role in ["HoOC", "HoD"],
                        "message": f"Người dùng hiện tại có vai trò: {role}. " + (
                            "Có thể tạo cả công việc lớn (epic) và công việc (task)." if role == "HoOC" else
                            "Chỉ có thể tạo công việc (task) trong epic của ban mình, KHÔNG được tạo epic mới." if role == "HoD" else
                            "KHÔNG được phép tạo công việc lớn (epic) hoặc công việc (task)."
                        )
                    }
            
            return data

        return result
    except ValueError as e:
        # ValueError từ node_client đã có thông tin chi tiết, chỉ cần re-raise
        raise
    except Exception as e:
        # Log chi tiết để debug
        error_type = type(e).__name__
        error_message = str(e)
        
        print(f"[ERROR] get_event_detail_for_ai_tool failed:")
        print(f"  - Error type: {error_type}")
        print(f"  - Error message: {error_message}")
        print(f"  - eventId: {event_id}")
        print(f"  - user_token present: {user_token is not None}")
        
        # Tạo error message tự nhiên, không hiển thị mã lỗi kỹ thuật
        if "timeout" in error_message.lower() or "connection" in error_message.lower() or "kết nối" in error_message.lower():
            raise ValueError(
                "Không thể kết nối đến hệ thống để lấy thông tin sự kiện. "
                "Nguyên nhân có thể do mạng không ổn định hoặc hệ thống đang quá tải. "
                "Vui lòng kiểm tra kết nối và thử lại sau."
            )
        elif "authentication" in error_message.lower() or "xác thực" in error_message.lower() or "hết hạn" in error_message.lower():
            raise ValueError(
                "Phiên đăng nhập của bạn đã hết hạn hoặc không hợp lệ. "
                "Vui lòng đăng nhập lại để tiếp tục."
            )
        elif "not found" in error_message.lower() or "không tìm thấy" in error_message.lower():
            raise ValueError(
                f"Không tìm thấy sự kiện với ID đã cung cấp. "
                "Vui lòng kiểm tra lại ID sự kiện hoặc đảm bảo bạn có quyền truy cập sự kiện này."
            )
        else:
            raise ValueError(
                "Không thể lấy thông tin sự kiện. "
                "Vui lòng thử lại sau hoặc liên hệ hỗ trợ nếu vấn đề vẫn tiếp tục."
            )


