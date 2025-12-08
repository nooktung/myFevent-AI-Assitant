# tools/departments.py
from typing import Dict, Any, Optional, List

from .node_client import post, get


def create_departments_for_event_tool(
    args: Dict[str, Any],
    user_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Tạo các phòng ban (Department) cho một event.

    Input (args):
      - eventId: string (Mongo ObjectId của Event)
      - departments: List[str] - tên các ban (ví dụ: ["Ban Truyền thông", "Ban Hậu cần"])

    Logic:
      1) Lấy danh sách department hiện có của event.
      2) Với mỗi tên ban:
         - nếu đã tồn tại (trùng name, không phân biệt hoa thường) => skip.
         - nếu chưa có => gọi Node POST /events/:eventId/departments để tạo.
      3) Trả về:
         - created: các ban mới tạo,
         - skipped: ban đã có sẵn,
         - department_map: map name(lower) -> {id, name} để dùng cho tool khác (EPIC).
    """
    event_id: str = args.get("eventId")
    departments_raw = args.get("departments") or []

    if not event_id:
        raise ValueError("eventId is required")
    if not isinstance(departments_raw, list) or not departments_raw:
        raise ValueError("departments must be a non-empty list of names")

    # Chuẩn hoá list tên ban
    departments: List[str] = [str(d).strip() for d in departments_raw if str(d).strip()]

    # 1) Lấy danh sách department hiện có
    try:
        existing_res = get(
            f"/events/{event_id}/departments",
            params={"page": 1, "limit": 200},
            user_token=user_token,
        )
        existing_items = existing_res.get("data") or existing_res.get("items") or []
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] Không lấy được list department hiện có: {e}")
        existing_items = []

    existing_by_name = {}
    for d in existing_items:
        name = str(d.get("name", "")).strip()
        if not name:
            continue
        existing_by_name[name.lower()] = d

    created = []
    skipped = []
    errors = []

    # 2) Tạo từng department nếu chưa tồn tại
    for raw_name in departments:
        name = raw_name.strip()
        if not name:
            continue

        key = name.lower()
        if key in existing_by_name:
            dept = existing_by_name[key]
            skipped.append(
                {
                    "name": name,
                    "departmentId": str(dept.get("_id") or dept.get("id")),
                    "reason": "already_exists",
                }
            )
            continue

        payload = {
            "name": name,
            "description": f"Phòng ban được tạo tự động bởi AI agent cho event {event_id}",
        }

        try:
            res = post(
                f"/events/{event_id}/departments",
                json=payload,
                user_token=user_token,
            )
            data = res.get("data") or res
            dept_id = str(data.get("_id") or data.get("id"))
            created.append(
                {
                    "name": name,
                    "departmentId": dept_id,
                    "raw": data,
                }
            )
            print(f"[INFO] Đã tạo department '{name}' cho event {event_id}: {dept_id}")
        except Exception as e:  # noqa: BLE001
            print(f"[ERROR] Tạo department '{name}' thất bại: {e}")
            errors.append({"name": name, "error": str(e)})

    # 3) Lấy lại danh sách department sau khi tạo
    try:
        final_res = get(
            f"/events/{event_id}/departments",
            params={"page": 1, "limit": 200},
            user_token=user_token,
        )
        final_items = final_res.get("data") or final_res.get("items") or []
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] Không load lại list department: {e}")
        final_items = existing_items

    department_map = {}
    for d in final_items:
        name = str(d.get("name", "")).strip()
        if not name:
            continue
        department_map[name.lower()] = {
            "id": str(d.get("_id") or d.get("id")),
            "name": name,
        }

    return {
        "eventId": event_id,
        "input_departments": departments,
        "created": created,
        "skipped": skipped,
        "errors": errors,
        "department_map": department_map,
    }
