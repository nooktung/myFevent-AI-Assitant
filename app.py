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

class TurnResponse(BaseModel):
    assistant_reply: str
    messages: List[Dict[str, Any]]
    plans: Optional[List[Dict[str, Any]]] = None  # Thêm plans vào response model


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
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header",
        )

    user_token = authorization.split(" ", 1)[1].strip()

    # Chuyển Pydantic models → dict cho agent_core
    history = [m.model_dump() for m in payload.history_messages]

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
            
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        # Log full traceback for debugging
        error_traceback = traceback.format_exc()
        print(f"[FastAPI] Error in event_planner_turn:")
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
