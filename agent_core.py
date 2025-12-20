# agent_core.py
import os
import json
from typing import List, Dict, Any

from dotenv import load_dotenv
from openai import OpenAI

from agent_system_prompt import AGENT_SYSTEM_PROMPT
from tools.event_detail import get_event_detail_for_ai_tool
from tools.epics import ai_generate_epics_for_event_tool
from tools.tasks import ai_generate_tasks_for_epic_tool

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ====== TOOLS DEFINITION CHO OPENAI ======
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_event_detail_for_ai",
            "description": (
                "Lấy thông tin chi tiết của một sự kiện trong hệ thống myFEvent, "
                "bao gồm event, danh sách phòng ban, số lượng thành viên, EPIC và TASK hiện có. "
                "Dùng tool này trước khi sinh EPIC/TASK nếu đã biết eventId. "
                "QUAN TRỌNG: Response sẽ chứa 'currentUser' với field 'role' (HoOC, HoD, hoặc Member). "
                "BẮT BUỘC phải kiểm tra currentUser.role trước khi tạo task/epic: "
                "- Nếu role là 'Member': KHÔNG được phép tạo task/epic, trả lời rằng chỉ HoOC và HoD mới có quyền. "
                "- Nếu role là 'HoD': Chỉ được tạo task trong epic của ban mình, KHÔNG được tạo epic mới. "
                "- Nếu role là 'HoOC': Có thể tạo cả epic và task cho bất kỳ ban nào."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "eventId": {
                        "type": "string",
                        "description": "ObjectId của event trong MongoDB"
                    }
                },
                "required": ["eventId"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ai_generate_epics_for_event",
            "description": (
                "Sinh ra các EPIC (task cha, taskType='epic') cho từng phòng ban của event "
                "dựa trên mô tả sự kiện + knowledge base, sau đó lưu vào Node backend."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "eventId": {
                        "type": "string",
                        "description": "ObjectId của event trong MongoDB"
                    },
                    "eventDescription": {
                        "type": "string",
                        "description": "Mô tả chi tiết sự kiện, dùng làm query cho RAG"
                    },
                    "departments": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Danh sách phòng ban theo tên (ví dụ: 'media', 'logistic', "
                            "'ban nội dung', 'ban media design', ...). "
                            "Model có thể tự đề xuất nếu user không đưa đủ."
                        )
                    }
                },
                "required": ["eventId", "eventDescription", "departments"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ai_generate_tasks_for_epic",
            "description": (
                "Bẻ một EPIC cụ thể thành các task con (taskType='normal') và lưu vào Node backend. "
                "Mỗi task sẽ có title, description, priority, can_parallel, depends_on, "
                "offset_days_from_event,… Backend sẽ map sang TaskSchema hiện tại."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "eventId": {
                        "type": "string",
                        "description": "ObjectId của event chứa EPIC này"
                    },
                    "epicId": {
                        "type": "string",
                        "description": "TaskId của EPIC (taskType='epic') trong MongoDB"
                    },
                    "epicTitle": {
                        "type": "string",
                        "description": "Tiêu đề EPIC để LLM hiểu ngữ cảnh"
                    },
                    "department": {
                        "type": "string",
                        "description": "Tên phòng ban của EPIC (media, logistic, ...)"
                    },
                    "eventDescription": {
                        "type": "string",
                        "description": "Mô tả sự kiện (dùng cho RAG, giống khi sinh EPIC)"
                    },
                    "eventStartDate": {
                        "type": "string",
                        "description": "Ngày bắt đầu diễn ra sự kiện (D-Day - ngày đầu tiên sự kiện chính thức diễn ra), định dạng yyyy-mm-dd. Đây là mốc tham chiếu để tính toán offset_days_from_event cho các task."
                    }
                },
                "required": [
                    "eventId",
                    "epicId",
                    "epicTitle",
                    "department",
                    "eventDescription",
                    "eventStartDate"
                ]
            }
        }
    }
]


# ====== KIỂM TRA CÂU HỎI CÓ LIÊN QUAN ĐẾN SỰ KIỆN KHÔNG ======
def is_event_related(message: str) -> bool:
    """
    Kiểm tra xem câu hỏi có liên quan đến tổ chức/quản lý sự kiện không.
    Trả về True nếu liên quan, False nếu không liên quan.
    """
    if not message or not message.strip():
        return False
    
    message_lower = message.lower().strip()
    
    # Từ khóa liên quan đến sự kiện
    event_keywords = [
        'sự kiện', 'su kien', 'event', 'tổ chức', 'to chuc',
        'tạo sự kiện', 'tao su kien', 'create event',
        'công việc', 'cong viec', 'task', 'epic', 'công việc lớn',
        'ban', 'phòng ban', 'phong ban', 'department',
        'thành viên', 'thanh vien', 'member',
        'trưởng ban', 'truong ban', 'hod', 'hooc',
        'lịch', 'lich', 'calendar', 'schedule',
        'rủi ro', 'rui ro', 'risk',
        'ngân sách', 'ngan sach', 'budget', 'chi phí', 'chi phi', 'expense',
        'cột mốc', 'cot moc', 'milestone',
        'địa điểm', 'dia diem', 'venue', 'location',
        'ngày', 'ngay', 'date', 'thời gian', 'thoi gian',
        'tổ chức sự kiện', 'to chuc su kien', 'organize event',
        'quản lý sự kiện', 'quan ly su kien', 'manage event',
        'myfevent', 'myf event'
    ]
    
    # Từ khóa KHÔNG liên quan đến sự kiện (các câu hỏi chung chung)
    non_event_keywords = [
        '1+1', '2+2', 'tính toán', 'tinh toan', 'calculate', 'math',
        'hdpe', 'nhựa', 'plastic', 'polyethylene',
        'vui không', 'vui khong', 'khỏe không', 'khoe khong',
        'kể chuyện', 'ke chuyen', 'tell story',
        'lịch sử', 'lich su', 'history',
        'địa lý', 'dia ly', 'geography',
        'việt nam', 'viet nam', 'vietnam',
        'học', 'hoc', 'learn', 'study',
        'tin tức', 'tin tuc', 'news',
        'thời tiết', 'thoi tiet', 'weather',
        'ai là gì', 'ai la gi', 'what is ai',
        'blockchain', 'crypto', 'bitcoin'
    ]
    
    # Kiểm tra các từ khóa không liên quan trước (ưu tiên)
    for keyword in non_event_keywords:
        if keyword in message_lower:
            # Nếu có từ khóa không liên quan, kiểm tra xem có từ khóa sự kiện không
            # Nếu không có từ khóa sự kiện nào, thì không liên quan
            has_event_keyword = any(ek in message_lower for ek in event_keywords)
            if not has_event_keyword:
                return False
    
    # Kiểm tra các từ khóa liên quan đến sự kiện
    for keyword in event_keywords:
        if keyword in message_lower:
            return True
    
    # Nếu không có từ khóa nào, dùng LLM để phân loại (fallback)
    try:
        classification_prompt = f"""Bạn là một hệ thống phân loại câu hỏi. Nhiệm vụ của bạn là xác định xem câu hỏi sau có liên quan đến TỔ CHỨC VÀ QUẢN LÝ SỰ KIỆN không.

Câu hỏi: "{message}"

Các câu hỏi LIÊN QUAN đến sự kiện bao gồm:
- Tạo sự kiện mới
- Tạo công việc (task) và Công việc lớn (epic) cho sự kiện
- Tra cứu thông tin về sự kiện (thành viên, ban, lịch, rủi ro, cột mốc)
- Quản lý và tổ chức sự kiện
- Các câu hỏi khác liên quan TRỰC TIẾP đến chức năng của hệ thống quản lý sự kiện

Các câu hỏi KHÔNG LIÊN QUAN bao gồm:
- Toán học, tính toán
- Kiến thức chung (HDPE là gì, lịch sử, địa lý)
- Khoa học, công nghệ không liên quan
- Giáo dục, học thuật
- Tin tức, thời sự
- Cảm xúc, trò chuyện chung

Trả lời CHỈ bằng một từ: "YES" nếu liên quan đến sự kiện, "NO" nếu không liên quan."""
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Bạn là một hệ thống phân loại câu hỏi. Trả lời chỉ bằng YES hoặc NO."},
                {"role": "user", "content": classification_prompt}
            ],
            temperature=0,
            max_tokens=10,
            timeout=10.0,
        )
        
        result = response.choices[0].message.content.strip().upper()
        return result == "YES"
    except Exception as e:
        print(f"[AGENT] Error in is_event_related classification: {e}")
        # Nếu lỗi, mặc định cho phép (để tránh chặn nhầm)
        return True


# ====== MAP TÊN TOOL → HÀM PYTHON THẬT ======
def call_tool(name: str, arguments: Dict[str, Any], user_token: str) -> Dict[str, Any]:
    """
    Map tên tool trong OpenAI function-calling → hàm Python tương ứng.

    - user_token: JWT (myFEvent) để Node client (tools/*.py) gọi backend Node.
    """
    if name == "get_event_detail_for_ai":
        return get_event_detail_for_ai_tool(arguments, user_token=user_token)
    if name == "ai_generate_epics_for_event":
        return ai_generate_epics_for_event_tool(arguments, user_token=user_token)
    if name == "ai_generate_tasks_for_epic":
        return ai_generate_tasks_for_epic_tool(arguments, user_token=user_token)
    raise ValueError(f"Unknown tool name: {name}")


# ====== CORE LOOP CHO MỖI LƯỢT AGENT (WEB) ======
def run_agent_turn(
    history_messages: List[Dict[str, Any]],
    user_token: str,
) -> Dict[str, Any]:
    """
    Chạy 1 lượt agent cho web/app:

    - history_messages:
        Danh sách message mà frontend/Node gửi sang, KHÔNG cần system prompt.
        Ví dụ:
        [
          {"role": "user", "content": "Tạo giúp tôi một giải đấu cầu lông..."},
          {"role": "assistant", "content": "..."},
          ...
        ]

    - user_token:
        JWT của user (myFEvent) để các tool Python gọi Node backend (create event, tạo EPIC/TASK,...)

    Trả về cho Node:
    {
      "assistant_reply": "string",            # câu trả lời cuối cùng gửi lại cho web
      "messages": [...full_conversation...]   # bao gồm system + user + assistant + tool messages
    }

    Node sẽ:
      - Lưu lại lịch sử cần thiết vào Mongo (ConversationHistory),
      - Gửi assistant_reply lại cho frontend.
    """
    # 0) KIỂM TRA CÂU HỎI CÓ LIÊN QUAN ĐẾN SỰ KIỆN KHÔNG (BẮT BUỘC)
    # Lấy tin nhắn user cuối cùng từ history
    last_user_message = None
    if history_messages:
        for msg in reversed(history_messages):
            if msg.get("role") == "user":
                last_user_message = msg.get("content", "")
                break
    
    # Nếu có tin nhắn user, kiểm tra xem có liên quan đến sự kiện không
    if last_user_message:
        if not is_event_related(last_user_message):
            # Câu hỏi không liên quan → trả về ngay lập tức với câu từ chối
            rejection_message = "Xin lỗi, tôi không thể giải đáp câu hỏi này. Tôi chỉ có thể hỗ trợ các câu hỏi liên quan đến việc tổ chức và quản lý sự kiện mà thôi."
            suggestion = "Bạn có muốn tôi giúp bạn tạo sự kiện mới hoặc quản lý sự kiện hiện có không?"
            
            # Build messages để lưu vào history
            messages: List[Dict[str, Any]] = [
                {"role": "system", "content": AGENT_SYSTEM_PROMPT},
            ]
            messages.extend(history_messages or [])
            messages.append({
                "role": "assistant",
                "content": f"{rejection_message} {suggestion}"
            })
            
            print(f"[AGENT] Rejected non-event question: {last_user_message[:50]}...")
            return {
                "assistant_reply": f"{rejection_message} {suggestion}",
                "messages": messages,
                "plans": [],
            }
    
    # 1) Build messages cho OpenAI: prepend system prompt
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
    ]
    messages.extend(history_messages or [])

    # Thu thập các "plan" mà tool trả về (epics_plan, tasks_plan, ...)
    collected_plans: List[Dict[str, Any]] = []

    # 2) Loop: model ↔ tools cho đến khi model trả về final answer (không còn tool_calls)
    # Giới hạn số lần lặp để tránh timeout (max 10 tool calls)
    max_iterations = 10
    iteration = 0
    
    while iteration < max_iterations:
        iteration += 1
        print(f"[AGENT] Iteration {iteration}/{max_iterations}")
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            timeout=60.0,  # Timeout 60s cho mỗi LLM call
        )

        msg = response.choices[0].message

        # Không gọi tool nữa → final answer cho user
        if not msg.tool_calls:
            assistant_reply = msg.content or ""
            messages.append({"role": "assistant", "content": assistant_reply})
            print(f"[AGENT] Final answer after {iteration} iterations, collected {len(collected_plans)} plans")
            return {
                "assistant_reply": assistant_reply,
                "messages": messages,
                # Trả thêm danh sách kế hoạch để FE/Node có thể cho user preview & apply
                "plans": collected_plans,
            }
        
        # Nếu đạt max iterations mà vẫn còn tool_calls, trả về với warning
        if iteration >= max_iterations:
            print(f"[AGENT] WARNING: Reached max iterations ({max_iterations}), stopping")
            assistant_reply = "Tôi đã xử lý yêu cầu của bạn nhưng có thể chưa hoàn tất do giới hạn số lần xử lý. Vui lòng thử lại với yêu cầu cụ thể hơn."
            messages.append({"role": "assistant", "content": assistant_reply})
            return {
                "assistant_reply": assistant_reply,
                "messages": messages,
                "plans": collected_plans,
            }

        # Có tool_calls → thêm message assistant chứa tool_calls vào history
        messages.append({
            "role": "assistant",
            "tool_calls": msg.tool_calls,
        })

        # Thực thi tuần tự từng tool
        for tool_call in msg.tool_calls:
            tool_name = tool_call.function.name
            raw_args = tool_call.function.arguments or "{}"
            try:
                tool_args = json.loads(raw_args)
            except Exception:
                tool_args = {}

            print(f"[AGENT] calling tool {tool_name} with args={tool_args}")

            try:
                tool_result = call_tool(tool_name, tool_args, user_token=user_token)
                print(f"[AGENT] tool {tool_name} success: {json.dumps(tool_result, ensure_ascii=False)[:200]}...")
                # Nếu tool trả về một "plan" (epics_plan / tasks_plan / ...), lưu lại để trả cho FE.
                if isinstance(tool_result, dict) and tool_result.get("type") in {"epics_plan", "tasks_plan"}:
                    collected_plans.append(
                        {
                            "tool": tool_name,
                            **tool_result,
                        }
                    )
            except ValueError as e:
                # ValueError từ tools thường chứa thông tin lỗi chi tiết
                error_message = str(e)
                error_type = "VALUE_ERROR"
                
                # Phân tích error message để xác định loại lỗi cụ thể
                if "timeout" in error_message.lower() or "quá thời gian chờ" in error_message.lower():
                    error_type = "TIMEOUT_ERROR"
                    suggestion = "Kết nối đến backend quá thời gian chờ. Vui lòng thử lại sau hoặc kiểm tra kết nối mạng."
                elif "connection" in error_message.lower() or "kết nối" in error_message.lower():
                    error_type = "CONNECTION_ERROR"
                    suggestion = "Không thể kết nối đến backend. Vui lòng kiểm tra xem backend có đang chạy không hoặc thử lại sau."
                elif "authentication" in error_message.lower() or "401" in error_message or "xác thực" in error_message.lower():
                    error_type = "AUTHENTICATION_ERROR"
                    suggestion = "Token xác thực không hợp lệ hoặc đã hết hạn. Vui lòng đăng nhập lại."
                elif "permission" in error_message.lower() or "403" in error_message or "quyền" in error_message.lower():
                    error_type = "PERMISSION_ERROR"
                    suggestion = "Bạn không có quyền thực hiện thao tác này. Vui lòng kiểm tra quyền của bạn."
                elif "not found" in error_message.lower() or "404" in error_message or "không tìm thấy" in error_message.lower():
                    error_type = "NOT_FOUND_ERROR"
                    suggestion = "Không tìm thấy tài nguyên yêu cầu. Vui lòng kiểm tra lại ID hoặc thông tin đã cung cấp."
                elif "missing" in error_message.lower() or "thiếu" in error_message.lower():
                    error_type = "MISSING_FIELD_ERROR"
                    suggestion = "Thiếu thông tin bắt buộc. Vui lòng kiểm tra lại các trường cần thiết."
                elif "invalid" in error_message.lower() or "không hợp lệ" in error_message.lower():
                    error_type = "VALIDATION_ERROR"
                    suggestion = "Thông tin không hợp lệ. Vui lòng kiểm tra lại format hoặc giá trị đã nhập."
                else:
                    # Tạo suggestion dựa trên tool name
                    if tool_name == "create_event":
                        suggestion = "Vui lòng kiểm tra lại: tên sự kiện, đơn vị tổ chức, ngày bắt đầu/kết thúc (format yyyy-mm-dd), địa điểm, và loại sự kiện (public/private)."
                    elif tool_name == "get_event_detail_for_ai":
                        suggestion = "Vui lòng kiểm tra lại eventId hoặc thử lại sau. Nếu vấn đề vẫn tiếp tục, có thể backend đang gặp sự cố."
                    elif tool_name == "ai_generate_tasks_for_epic":
                        suggestion = "Vui lòng kiểm tra lại các tham số đầu vào (eventId, epicId, department, eventDescription, eventStartDate) và thử lại."
                    elif tool_name == "ai_generate_epics_for_event":
                        suggestion = "Vui lòng kiểm tra lại các tham số đầu vào (eventId, eventDescription, departments) và thử lại."
                    else:
                        suggestion = "Vui lòng kiểm tra lại các tham số đầu vào và thử lại."
                
                print(f"[AGENT] tool {tool_name} error ({error_type}): {error_message}")
                
                # Trả về error message chi tiết để LLM có thể xử lý
                # Format này giúp AI dễ đọc và hiển thị lỗi cho người dùng
                tool_result = {
                    "error": True,
                    "error_type": error_type,
                    "error_message": error_message,
                    "suggestion": suggestion,
                    "tool_name": tool_name,
                    "tool_args": tool_args if 'tool_args' in locals() else {},
                    "message": f"Lỗi khi thực hiện {tool_name}: {error_message}. {suggestion}"
                }
            except Exception as e:
                import traceback
                error_detail = traceback.format_exc()
                error_message = str(e)
                error_type = type(e).__name__
                
                print(f"[AGENT] tool {tool_name} error ({error_type}):")
                print(error_detail)
                
                # Tạo suggestion dựa trên tool name và error type
                if tool_name == "create_event":
                    suggestion = "Vui lòng kiểm tra lại: tên sự kiện, đơn vị tổ chức, ngày bắt đầu/kết thúc (format yyyy-mm-dd), địa điểm, và loại sự kiện (public/private)."
                elif tool_name == "get_event_detail_for_ai":
                    suggestion = "Vui lòng kiểm tra lại eventId hoặc thử lại sau. Nếu vấn đề vẫn tiếp tục, có thể backend đang gặp sự cố."
                elif tool_name == "ai_generate_tasks_for_epic":
                    suggestion = "Vui lòng kiểm tra lại các tham số đầu vào (eventId, epicId, department, eventDescription, eventStartDate) và thử lại."
                elif tool_name == "ai_generate_epics_for_event":
                    suggestion = "Vui lòng kiểm tra lại các tham số đầu vào (eventId, eventDescription, departments) và thử lại."
                else:
                    suggestion = "Vui lòng kiểm tra lại các tham số đầu vào và thử lại."
                
                # Trả về error message chi tiết để LLM có thể xử lý
                tool_result = {
                    "error": True,
                    "error_type": error_type,
                    "error_message": error_message,
                    "suggestion": suggestion,
                    "tool_name": tool_name,
                    "tool_args": tool_args if 'tool_args' in locals() else {},
                    "message": f"Lỗi không mong đợi khi thực hiện {tool_name}: {error_message}. {suggestion}"
                }

            # Tool result để model “nhìn thấy” ở vòng lặp kế tiếp
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": tool_name,
                "content": json.dumps(tool_result, ensure_ascii=False),
            })
        # quay lại while: model sẽ đọc kết quả tool và quyết định bước tiếp
