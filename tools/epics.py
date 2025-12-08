# tools/epics.py
import json
from typing import Dict, Any, Optional, List

from openai import OpenAI

from rag import retrieve_chunks
from .node_client import post, get  # ⬅️ nhớ import get


from dotenv import load_dotenv
import os
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


EPIC_PLANNER_SYSTEM_PROMPT = """
Bạn là trợ lý HoOC để lập kế hoạch EPIC cho từng phòng ban trong một sự kiện.

Nhiệm vụ:
- Dựa trên mô tả sự kiện, danh sách phòng ban, và EPIC_TEMPLATE + EVENT_CASE bên dưới,
  hãy đề xuất các epic hợp lý cho từng phòng ban (department).
- Mỗi epic gồm: title, description, phase (pre_event|event_day|post_event), department.
- Tối ưu để không quá nhiều epic thừa; ưu tiên rõ ràng, dễ giao việc.
- Output duy nhất: JSON với structure:
{
  "epics": [
    {
      "title": "string",
      "description": "string",
      "department": "string",
      "phase": "pre_event | event_day | post_event"
    }
  ]
}
"""


def _chunk_to_text(chunk: Any) -> str:
    """Lấy phần text chính trong 1 chunk RAG mà không phụ thuộc vào key 'content'."""
    if isinstance(chunk, str):
        return chunk

    if not isinstance(chunk, dict):
        return str(chunk)

    # Ưu tiên các key phổ biến
    for key in ("content", "text", "document", "page_content"):
        value = chunk.get(key)
        if isinstance(value, str) and value.strip():
            return value

    # Có thể text nằm trong metadata["context"]
    meta = chunk.get("metadata") or {}
    ctx = meta.get("context")
    if isinstance(ctx, str) and ctx.strip():
        return ctx

    # Fallback: dump cả chunk
    return json.dumps(chunk, ensure_ascii=False)


def ai_generate_epics_for_event_tool(
    args: Dict[str, Any],
    user_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Tool cho LLM:
      - Input: eventId, eventDescription, departments (list string),
      - Nội bộ:
        + Gọi RAG: lấy epic_template + event_case giống event này,
        + Gọi LLM con: sinh plan EPIC.

    LƯU Ý:
      - Hàm NÀY KHÔNG còn tự gọi Node để tạo EPIC thật nữa.
      - Nó chỉ trả về kế hoạch EPIC (epics_plan) để layer phía trên
        (Node / frontend) hiển thị preview và quyết định khi nào áp dụng.
    """
    event_id: str = args.get("eventId")
    event_description: str = args.get("eventDescription", "")
    departments: List[str] = args.get("departments") or []

    if not event_id:
        raise ValueError("eventId is required")

    # BẮT BUỘC nên có eventDescription để RAG hiểu ngữ cảnh
    if not event_description:
        raise ValueError("eventDescription is required")

    # 1) RAG: lấy epic_template + case tương tự
    query = f"{event_description} departments: {', '.join(departments)} epic_template"
    kb_chunks = retrieve_chunks(query, top_k=12) or []
    print(f"[DEBUG] RAG – retrieved {len(kb_chunks)} KB chunks for EPIC planning.")

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
        else "Không tìm thấy template nào."
    )

    # 2) Gọi LLM con để sinh JSON epics
    messages = [
        {"role": "system", "content": EPIC_PLANNER_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "Mô tả sự kiện:\n"
                f"{event_description}\n\n"
                f"Danh sách phòng ban (department) tham gia: {departments}\n\n"
                "EPIC_TEMPLATE & EVENT_CASE từ KB:\n"
                f"{kb_text}"
            ),
        },
    ]

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        response_format={"type": "json_object"},
    )

    # 3) Parse JSON từ assistant
    content = resp.choices[0].message.content
    # Phòng trường hợp content = None
    if not content:
        raise ValueError("LLM không trả về nội dung cho kế hoạch EPIC.")

    epics_plan = json.loads(content)
    epics = epics_plan.get("epics", [])
    if not isinstance(epics, list) or not epics:
        raise ValueError("Không sinh được epic nào từ AI.")

    # 4) Không ghi vào DB tại đây — chỉ trả về kế hoạch để preview/apply sau.
    return {
        "type": "epics_plan",
        "eventId": event_id,
        "departments": departments,
        "eventDescription": event_description,
        "plan": epics_plan,
    }
