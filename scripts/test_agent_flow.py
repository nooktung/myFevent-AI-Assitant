# scripts/test_agent_flow.py
import os
import sys
import json
from dotenv import load_dotenv

# Load .env trước
load_dotenv()

# Thêm project root vào sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from tools.events import create_event_tool
from tools.epics import ai_generate_epics_for_event_tool
from tools.tasks import ai_generate_tasks_for_epic_tool


def pretty(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main():
    # ====== 1) Đọc env ======
    base_url = os.getenv("MYFEVENT_BASE_URL", "http://localhost:8080/api")
    openai_key = os.getenv("OPENAI_API_KEY")
    user_jwt = os.getenv("MYFEVENT_TEST_JWT")

    print(f"BASE_URL   = {base_url}")
    print(f"JWT prefix = {user_jwt[:20] + '...'}" if user_jwt else "JWT prefix = <EMPTY>")

    if not openai_key:
        print("❌ Thiếu OPENAI_API_KEY trong .env")
        return
    if not user_jwt:
        print("❌ Thiếu MYFEVENT_TEST_JWT trong .env")
        return

    # ====== 2) Tạo event mới bằng agent (create_event_tool) ======
    print("\n=== [STEP 1] Tạo event mới ===")

    event_args = {
        "name": "Workshop AI Agent Demo",
        "description": (
            "Workshop demo hệ thống AI agent myFEvent: giới thiệu cách sinh EPIC/TASK tự động, "
            "quy mô 120-150 sinh viên, tổ chức tại hội trường lớn, có livestream."
        ),
        "organizerName": "CLB Sự kiện FPTU",
        "eventStartDate": "2025-12-20",
        "eventEndDate": "2025-12-20",
        "location": "Hội trường Innovation",
        "type": "private",
        "images": [],
    }

    try:
        create_res = create_event_tool(event_args, user_token=user_jwt)
        print("✅ Kết quả create_event_tool:")
        pretty(create_res)
    except Exception as e:
        print("❌ Lỗi khi gọi create_event_tool:")
        print(repr(e))
        return

    # Lấy eventId từ response Node
    try:
        event_id = create_res["data"]["id"]
    except Exception:
        print("❌ Không lấy được eventId từ response, format có thể khác:")
        pretty(create_res)
        return

    print(f"\n[INFO] eventId mới tạo: {event_id}")

    # ====== 3) Gọi AI sinh EPIC cho event (ai_generate_epics_for_event_tool) ======
    print("\n=== [STEP 2] Sinh EPIC cho event bằng AI ===")

    departments = ["media", "program", "logistic", "sponsor"]

    epic_args = {
        "eventId": event_id,
        "eventDescription": event_args["description"],
        "departments": departments,
    }

    try:
        epics_result = ai_generate_epics_for_event_tool(epic_args, user_token=user_jwt)
        print("✅ Kết quả ai_generate_epics_for_event_tool (rút gọn):")
        pretty(epics_result.get("epics_plan", {}))
    except Exception as e:
        print("❌ Lỗi khi gọi ai_generate_epics_for_event_tool:")
        print(repr(e))
        return

    epics_plan = epics_result.get("epics_plan", {})
    epics = epics_plan.get("epics", [])

    if not epics:
        print("❌ epics_plan trống, không có EPIC nào để test TASK.")
        return

    first_epic = epics[0]
    print("\n[INFO] EPIC đầu tiên để test TASK:")
    pretty(first_epic)

    epic_id = input("\nNhập epicId thật trong DB (hoặc ấn Enter để bỏ qua test TASK): ").strip()
    if not epic_id:
        print("⏭ Bỏ qua bước sinh TASK vì chưa có epicId.")
        return

    # ====== 4) Gọi AI sinh TASK cho EPIC vừa chọn ======
    print("\n=== [STEP 3] Sinh TASK cho EPIC bằng AI ===")

    task_args = {
        "eventId": event_id,
        "epicId": epic_id,
        "epicTitle": first_epic.get("title", ""),
        "department": first_epic.get("department", ""),
        "eventDescription": event_args["description"],
        "eventStartDate": event_args["eventStartDate"],
    }

    try:
        tasks_result = ai_generate_tasks_for_epic_tool(task_args, user_token=user_jwt)
        print("✅ Kết quả ai_generate_tasks_for_epic_tool (plan):")
        pretty(tasks_result.get("tasks_plan", {}))
    except Exception as e:
        print("❌ Lỗi khi gọi ai_generate_tasks_for_epic_tool:")
        print(repr(e))
        return

    print("\n🎉 Flow agent demo hoàn tất.")


if __name__ == "__main__":
    main()
