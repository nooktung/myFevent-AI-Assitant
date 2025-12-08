# tools/tasks.py
import json
from typing import Dict, Any, Optional, List

from openai import OpenAI

from rag import retrieve_chunks
from .node_client import post, get

from dotenv import load_dotenv
import os

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ======================================================================
#  TASK PLANNER PROMPT – ĐÃ ĐIỀU CHỈNH THEO TASK MODEL MỚI
# ======================================================================
TASK_PLANNER_SYSTEM_PROMPT = """
Bạn là trợ lý HoD để bẻ một EPIC thành các task nhỏ trong hệ thống quản lý sự kiện.

Ngữ cảnh hệ thống (rất quan trọng):
- Mỗi task trong DB có các field chính: title, description, status, progressPct, estimate, estimateUnit,
  suggestedTeamSize, startDate, dueDate, eventId, departmentId, milestoneId, parentId, dependencies, taskType.
- Task sinh ra từ AI sẽ:
  - Được gán taskType = "normal" (task con của EPIC).
  - Có status ban đầu = "suggested" (gợi ý, chưa được confirm).
  - Được gắn parentId = EPIC tương ứng (do backend map).
  - Department sẽ lấy theo EPIC, không cần output trong JSON.

Nhiệm vụ của bạn:
- Dựa trên:
  - Mô tả sự kiện,
  - Thông tin EPIC (title, department),
  - TASK_TEMPLATE và các snapshot task của những sự kiện tương tự (từ RAG),
  hãy sinh ra danh sách task con hợp lý cho EPIC này.

Yêu cầu:
- Các task phải đủ rõ ràng để có thể giao cho thành viên hoặc ban thực hiện.
- Không tạo quá nhiều task vặt vãnh; ưu tiên những bước chính, có thể gom các việc nhỏ vào một task lớn.
- Sắp xếp task theo logic thời gian và phụ thuộc (depends_on).
- Dùng offset_days_from_event để thể hiện mốc thời gian tương đối:
  - offset_days_from_event < 0  → công việc trước ngày bắt đầu sự kiện,
  - offset_days_from_event = 0  → công việc diễn ra trong ngày bắt đầu sự kiện,
  - offset_days_from_event > 0  → công việc sau ngày bắt đầu sự kiện.

Schema output BẮT BUỘC (JSON duy nhất):

{
  "tasks": [
    {
      "title": "string",
      "description": "string",
      "priority": "low | medium | high",
      "can_parallel": true,
      "depends_on": ["title task A", "title task B"],
      "offset_days_from_event": -10
    }
  ]
}

Giải thích các field:
- title: tên task ngắn gọn, hành động cụ thể (vd: "Thiết kế poster chính", "Chốt bracket thi đấu").
- description: mô tả chi tiết hơn về công việc, đủ để người khác hiểu phải làm gì.
- priority:
  - "high": rất quan trọng, nên làm sớm, có thể map sang estimate lớn hơn.
  - "medium": quan trọng vừa.
  - "low": việc phụ, có thể làm sau.
- can_parallel: true nếu task có thể làm song song với các task khác, false nếu cần làm theo thứ tự.
- depends_on: danh sách title của các task cần hoàn thành trước (cùng EPIC này). Nếu không có phụ thuộc thì để [].
- offset_days_from_event: số ngày tương đối so với ngày bắt đầu sự kiện:
  - Ví dụ: -14 (2 tuần trước), -7 (1 tuần trước), 0 (ngày diễn ra sự kiện), 1 (ngày sau sự kiện để tổng kết).

Chỉ trả về JSON đúng schema trên, KHÔNG thêm giải thích, không thêm text ngoài JSON.
"""


def _chunk_to_text(chunk: Any) -> str:
    """
    Lấy phần text chính trong 1 chunk RAG mà không phụ thuộc cứng vào key 'content'.
    Hỗ trợ nhiều kiểu backend khác nhau (page_content, document, metadata.context,...).
    """
    # Nếu chunk đã là string thì trả về luôn
    if isinstance(chunk, str):
        return chunk

    # Nếu không phải dict thì stringify
    if not isinstance(chunk, dict):
        return str(chunk)

    # Ưu tiên các key text phổ biến
    for key in ("content", "text", "document", "page_content"):
        v = chunk.get(key)
        if isinstance(v, str) and v.strip():
            return v

    # Có thể text nằm trong metadata["context"]
    meta = chunk.get("metadata") or {}
    ctx = meta.get("context")
    if isinstance(ctx, str) and ctx.strip():
        return ctx

    # Fallback: dump cả chunk (ít dùng, nhưng an toàn)
    return json.dumps(chunk, ensure_ascii=False)


def ai_generate_tasks_for_epic_tool(
    args: Dict[str, Any],
    user_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Tool cho LLM cha (agent):

    Input (args):
      - eventId: ID sự kiện trong hệ thống myFEvent (string, bắt buộc)
      - epicId: ID task cha (EPIC) trong DB (string, bắt buộc)
      - epicTitle: tên EPIC (string, bắt buộc)
      - department: tên ban phụ trách EPIC (string, optional – chỉ để context cho LLM)
      - eventDescription: mô tả sự kiện (string, bắt buộc để RAG hiểu context)
      - eventStartDate: "yyyy-mm-dd" (string, optional nhưng nên có để tính offset)

    Pipeline:
      1) Gọi RAG: lấy task_template + task_snapshot phù hợp với eventDescription + epicTitle + department.
      2) Gọi LLM con với TASK_PLANNER_SYSTEM_PROMPT để sinh JSON tasks:
         - tasks[].title, description, priority, can_parallel, depends_on, offset_days_from_event.
      3) Trả JSON tasks này (tasks_plan) cho layer phía trên để HIỂN THỊ & PREVIEW.
         Backend / frontend sẽ quyết định khi nào gọi API apply để tạo task thật.
    """
    event_id: str = args.get("eventId")
    epic_id: str = args.get("epicId")
    epic_title: str = args.get("epicTitle", "")
    department: str = args.get("department", "")
    event_description: str = args.get("eventDescription", "")
    event_start_date: str = args.get("eventStartDate", "")  # "yyyy-mm-dd"

    # ===== Validate input tối thiểu =====
    if not event_id or not epic_id:
        raise ValueError("eventId và epicId là bắt buộc")

    if not epic_title:
        raise ValueError("epicTitle là bắt buộc")

    if not event_description:
        raise ValueError("eventDescription là bắt buộc để RAG hiểu ngữ cảnh")

    # 1) RAG – lấy task_template + snapshot cho EPIC này
    query = f"{event_description} EPIC: {epic_title} department: {department} task_template task_snapshot"
    kb_chunks = retrieve_chunks(query, top_k=12) or []
    print(f"[DEBUG] RAG – retrieved {len(kb_chunks)} KB chunks for TASK planning.")

    kb_text_parts: List[str] = []
    for idx, c in enumerate(kb_chunks):
        meta = c.get("metadata", {}) if isinstance(c, dict) else {}
        kb_type = meta.get("type") or meta.get("kb_group") or "unknown"
        kb_text_parts.append(
            f"[KB#{idx+1}] ({kb_type}): {_chunk_to_text(c)}"
        )

    kb_text = (
        "\n\n".join(kb_text_parts)
        if kb_text_parts
        else "Không tìm thấy task template nào trong KB."
    )

    # 2) Gọi LLM con – sinh JSON tasks
    messages = [
        {"role": "system", "content": TASK_PLANNER_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Mô tả sự kiện:\n{event_description}\n\n"
                f"Ngày bắt đầu sự kiện (eventStartDate): {event_start_date}\n"
                f"Phòng ban (department): {department}\n"
                f"EPIC:\n  - Title: {epic_title}\n  - EpicId: {epic_id}\n\n"
                "TASK_TEMPLATE & SNAPSHOT từ KB:\n"
                f"{kb_text}"
            ),
        },
    ]

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        response_format={"type": "json_object"},
    )

    content = resp.choices[0].message.content
    if not content:
        raise ValueError("LLM không trả về nội dung cho kế hoạch TASK (content rỗng).")

    try:
        tasks_plan = json.loads(content)
    except json.JSONDecodeError as e:
        # Log thêm để debug nếu LLM trả về JSON lỗi
        print("[ERROR] JSON decode error from TASK planner:", e)
        print("[RAW CONTENT]", content)
        raise

    tasks = tasks_plan.get("tasks", [])
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("Không sinh được task nào từ AI cho EPIC này (tasks rỗng).")

    # 3) Không gửi sang Node ở đây nữa – chỉ trả plan để preview/apply sau.
    return {
        "type": "tasks_plan",
        "eventId": event_id,
        "epicId": epic_id,
        "epicTitle": epic_title,
        "department": department,
        "eventStartDate": event_start_date,
        "plan": tasks_plan,   # raw plan từ LLM (title/priority/offset/depends_on)
    }
