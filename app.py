# app.py
import os
import traceback
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent_core import run_agent_turn  # dùng file bạn đã có

# ====== Pydantic models ======
class Message(BaseModel):
    role: str
    content: str

class TurnRequest(BaseModel):
    history_messages: List[Message]
    eventId: Optional[str] = None  # Optional: eventId nếu đang ở trong context của một sự kiện

class TurnResponse(BaseModel):
    assistant_reply: str
    messages: List[Dict[str, Any]]
    plans: Optional[List[Dict[str, Any]]] = None  # Thêm plans vào response model
    eventId: Optional[str] = None  # Trả lại eventId để Node backend có thể lưu lịch sử


# ====== FastAPI app ======
app = FastAPI(
    title="myFEvent AI Agent Service",
    version="1.0.0"
)

# CORS cho web app / localhost
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],           # có thể siết lại về domain FE sau
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "ai-agent"}


@app.post("/agent/event-planner/turn", response_model=TurnResponse)
async def event_planner_turn(
    payload: TurnRequest,
    authorization: Optional[str] = Header(default=None),
):
    """
    Endpoint để Node / FE gọi 1 lượt agent.

    - Nhận history_messages từ FE/Node
    - Lấy JWT từ header Authorization → truyền vào run_agent_turn
    - Trả về assistant_reply + full messages (để FE render lại)
    """
    # Log request để debug
    print(f"[FastAPI] Received request: {len(payload.history_messages)} messages, eventId={payload.eventId}")
    
    if not authorization or not authorization.startswith("Bearer "):
        print("[FastAPI] ERROR: Missing or invalid Authorization header")
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header. Please provide a valid Bearer token.",
        )

    user_token = authorization.split(" ", 1)[1].strip()
    
    # Validate token không rỗng
    if not user_token:
        print("[FastAPI] ERROR: Empty token after Bearer prefix")
        raise HTTPException(
            status_code=401,
            detail="Empty authorization token",
        )
    
    print(f"[FastAPI] Token prefix: {user_token[:20]}...")

    # Chuyển Pydantic models → dict cho agent_core
    history = [m.model_dump() for m in payload.history_messages]
    
    # Log để debug lịch sử
    print(f"[FastAPI] History messages count: {len(history)}")
    if history:
        print(f"[FastAPI] First message role: {history[0].get('role')}")

    try:
        result = run_agent_turn(
            history_messages=history,
            user_token=user_token,
        )
        
        # Đảm bảo result có đúng structure
        if not isinstance(result, dict):
            raise ValueError("run_agent_turn must return a dict")
        
        if "assistant_reply" not in result:
            result["assistant_reply"] = ""
        if "messages" not in result:
            result["messages"] = []
        if "plans" not in result:
            result["plans"] = []
        
        print(f"[FastAPI] Success: assistant_reply length={len(result.get('assistant_reply', ''))}, plans count={len(result.get('plans', []))}")
        
        # Thêm eventId vào response để Node backend có thể lưu lịch sử đúng cách
        if payload.eventId:
            result["eventId"] = payload.eventId
            print(f"[FastAPI] Including eventId in response: {payload.eventId}")
            
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        # Log full traceback for debugging
        error_traceback = traceback.format_exc()
        print(f"[FastAPI] ERROR in event_planner_turn:")
        print(error_traceback)
        
        # Return more detailed error message
        error_detail = str(e)
        if len(error_traceback) > 0:
            # Include first few lines of traceback for debugging
            error_detail = f"{error_detail}\n\nTraceback:\n{error_traceback[:500]}"
        
        raise HTTPException(
            status_code=500,
            detail=f"Agent error: {error_detail}",
        )

    # result đã có đúng structure assistant_reply + messages
    return result


if __name__ == "__main__":
    # Chạy dev
    import uvicorn
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=int(os.getenv("AI_AGENT_PORT", 8000)),
        reload=True,
    )
