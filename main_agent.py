# main_agent.py
import os
import sys
import json
from typing import List, Dict, Any

from dotenv import load_dotenv
from openai import OpenAI

# Load .env
load_dotenv()

# Thêm project root vào sys.path để import tools/*
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.append(CURRENT_DIR)

from tools.events import create_event_tool
from tools.epics import ai_generate_epics_for_event_tool
from tools.tasks import ai_generate_tasks_for_epic_tool
from agent_system_prompt import AGENT_SYSTEM_PROMPT

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# =========================
# 1) KHAI BÁO TOOLS
# =========================
TOOLS = [
    # ---- Tool tạo event ----
    {
        "type": "function",
        "function": {
            "name": "create_event",
            "description": "Tạo một event mới trên hệ thống myFEvent (Node backend).",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Tên sự kiện."
                    },
                    "description": {
                        "type": "string",
                        "description": (
                            "Mô tả chi tiết sự kiện (2–5 câu): mục tiêu, đối tượng tham gia, quy mô, "
                            "có livestream không, phần chính của chương trình,... "
                            "Thông tin này sẽ dùng cho RAG để sinh EPIC/TASK."
                        )
                    },
                    "organizerName": {
                        "type": "string",
                        "description": "Tên CLB/đơn vị tổ chức."
                    },
                    "eventStartDate": {
                        "type": "string",
                        "description": "Ngày bắt đầu diễn ra sự kiện (D-Day - ngày đầu tiên sự kiện chính thức diễn ra), định dạng yyyy-mm-dd."
                    },
                    "eventEndDate": {
                        "type": "string",
                        "description": "Ngày kết thúc diễn ra sự kiện (ngày cuối cùng sự kiện chính thức diễn ra), định dạng yyyy-mm-dd."
                    },
                    "location": {
                        "type": "string",
                        "description": "Địa điểm tổ chức (phòng, toà nhà, cơ sở, ...)."
                    },
                    "type": {
                        "type": "string",
                        "enum": ["public", "private"],
                        "description": "Loại sự kiện."
                    },
                    "images": {
                        "type": "array",
                        "description": "Danh sách URL ảnh sự kiện (có thể để [] ban đầu).",
                        "items": {"type": "string"}
                    }
                },
                "required": [
                    "name",
                    "description",      # ⚠ bắt buộc để RAG có đủ ngữ cảnh
                    "organizerName",
                    "eventStartDate",
                    "eventEndDate",
                    "location",
                    "type"
                ]
            }
        },
    },

    # ---- Tool sinh EPIC bằng RAG ----
    {
        "type": "function",
        "function": {
            "name": "ai_generate_epics_for_event",
            "description": (
                "Dùng RAG + LLM để sinh danh sách EPIC cho một event. "
                "Phải truyền eventId. Có thể truyền thêm eventDescription và danh sách departments."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "eventId": {
                        "type": "string",
                        "description": "ID sự kiện trong myFEvent."
                    },
                    "eventDescription": {
                        "type": "string",
                        "description": (
                            "Mô tả chi tiết sự kiện. Nếu để trống, tool sẽ tự lấy thông tin "
                            "từ backend (GET /events/detail/:id) để build mô tả cho RAG."
                        )
                    },
                    "departments": {
                        "type": "array",
                        "description": (
                            "Danh sách tên phòng ban tham gia (ví dụ: ['media', 'program', 'logistic']). "
                            "Dùng để gợi ý EPIC theo từng ban."
                        ),
                        "items": {"type": "string"}
                    }
                },
                "required": ["eventId"]
            }
        },
    },

    # ---- Tool sinh TASK chi tiết cho 1 EPIC ----
    {
        "type": "function",
        "function": {
            "name": "ai_generate_tasks_for_epic",
            "description": (
                "Dùng RAG + LLM để bẻ một EPIC thành các task nhỏ và gọi backend để tạo hàng loạt. "
                "Cần eventId + epicId + epicTitle + department."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "eventId": {
                        "type": "string",
                        "description": "ID sự kiện trong myFEvent."
                    },
                    "epicId": {
                        "type": "string",
                        "description": "ID EPIC (task parent) trong DB. Dùng để gắn task con."
                    },
                    "epicTitle": {
                        "type": "string",
                        "description": "Tiêu đề EPIC."
                    },
                    "department": {
                        "type": "string",
                        "description": "Tên phòng ban thực hiện EPIC."
                    },
                    "eventDescription": {
                        "type": "string",
                        "description": "Mô tả sự kiện dùng làm context cho RAG."
                    },
                    "eventStartDate": {
                        "type": "string",
                        "description": "Ngày bắt đầu diễn ra sự kiện (D-Day - ngày đầu tiên sự kiện chính thức diễn ra), định dạng yyyy-mm-dd. Đây là mốc tham chiếu để tính toán offset_days_from_event cho các task."
                    }
                },
                "required": ["eventId", "epicId", "epicTitle", "department"]
            }
        },
    },
]


# =========================
# 2) MAP TÊN TOOL -> HÀM PYTHON
# =========================
def call_tool(name: str, arguments: Dict[str, Any], user_token: str) -> Dict[str, Any]:
    if name == "create_event":
        return create_event_tool(arguments, user_token=user_token)
    elif name == "ai_generate_epics_for_event":
        return ai_generate_epics_for_event_tool(arguments, user_token=user_token)
    elif name == "ai_generate_tasks_for_epic":
        return ai_generate_tasks_for_epic_tool(arguments, user_token=user_token)
    else:
        raise ValueError(f"Unknown tool name: {name}")


# =========================
# 3) VÒNG LẶP CLI
# =========================
def run_agent_cli(user_token: str):
    """
    Demo CLI:
      - User nhập prompt.
      - Agent hỏi thêm info nếu thiếu.
      - Khi đủ, gọi create_event -> sau đó có thể gọi EPIC/TASK tùy cuộc hội thoại.
    """
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
    ]

    print("=== myFEvent AI Event Planner – full flow (Event + EPIC + TASK) ===")
    print("Gõ mô tả sự kiện bằng tiếng Việt. Gõ 'exit' để thoát.\n")

    while True:
        user_input = input("👤 Bạn: ").strip()
        if user_input.lower() in ("exit", "quit"):
            print("👋 Kết thúc phiên.")
            break

        messages.append({"role": "user", "content": user_input})

        # Gọi OpenAI với tools
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )

        msg = response.choices[0].message

        # ===== Nếu model muốn gọi tool =====
        if msg.tool_calls:
            for tool_call in msg.tool_calls:
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments or "{}")

                print(f"\n⚙️ Agent gọi tool: {tool_name} với args:")
                print(json.dumps(tool_args, ensure_ascii=False, indent=2))

                try:
                    tool_result = call_tool(tool_name, tool_args, user_token=user_token)
                except Exception as e:
                    tool_result = {"error": str(e)}
                    print(f"❌ Lỗi khi gọi tool {tool_name}: {e}")

                # Ghi lại vào history để model nhìn thấy kết quả tool
                messages.append(
                    {
                        "role": "assistant",
                        "tool_calls": [tool_call],
                    }
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_name,
                        "content": json.dumps(tool_result, ensure_ascii=False),
                    }
                )

            # Gọi lại model để nó trả lời user dựa trên kết quả tool
            followup = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
            )
            final_msg = followup.choices[0].message
            assistant_reply = final_msg.content
            messages.append({"role": "assistant", "content": assistant_reply})
            print(f"\n🤖 Agent: {assistant_reply}\n")

        # ===== Nếu không dùng tool (chỉ chat / hỏi thêm info) =====
        else:
            assistant_reply = msg.content
            messages.append({"role": "assistant", "content": assistant_reply})
            print(f"\n🤖 Agent: {assistant_reply}\n")


if __name__ == "__main__":
    jwt = os.getenv("MYFEVENT_TEST_JWT")
    if not jwt:
        print("❌ Thiếu MYFEVENT_TEST_JWT trong .env")
        sys.exit(1)

    print(f"JWT prefix = {jwt[:20]}...")
    run_agent_cli(user_token=jwt)
