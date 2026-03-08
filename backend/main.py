import uuid
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import PORT
from engine import get_legal_answer

app = FastAPI(title="Legal RAG Chatbot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

chats: dict[str, dict] = {}


class ChatRequest(BaseModel):
    query: str
    chat_id: str | None = None


class ChatResponse(BaseModel):
    answer: str
    chat_id: str


class Message(BaseModel):
    role: str
    content: str


class ChatInfo(BaseModel):
    id: str
    title: str
    updated: str
    message_count: int


def _make_title(query: str) -> str:
    return (query[:50] + "…") if len(query) > 50 else query


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    chat_id = request.chat_id
    if not chat_id or chat_id not in chats:
        chat_id = str(uuid.uuid4())
        chats[chat_id] = {
            "title": _make_title(request.query),
            "messages": [],
            "updated": datetime.utcnow().isoformat() + "Z",
        }

    history = [
        {"role": m["role"], "content": m["content"]}
        for m in chats[chat_id]["messages"]
    ]
    answer = get_legal_answer(request.query, history=history if history else None)

    chats[chat_id]["messages"].append({"role": "user", "content": request.query})
    chats[chat_id]["messages"].append({"role": "assistant", "content": answer})
    chats[chat_id]["updated"] = datetime.utcnow().isoformat() + "Z"
    if len(chats[chat_id]["messages"]) == 2:
        chats[chat_id]["title"] = _make_title(request.query)

    return ChatResponse(answer=answer, chat_id=chat_id)


@app.get("/api/chats", response_model=list[ChatInfo])
async def list_chats():
    items = [
        ChatInfo(
            id=cid,
            title=data["title"],
            updated=data["updated"],
            message_count=len(data["messages"]),
        )
        for cid, data in sorted(
            chats.items(), key=lambda x: x[1]["updated"], reverse=True
        )
    ]
    return items


@app.get("/api/chats/{chat_id}")
async def get_chat(chat_id: str):
    if chat_id not in chats:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chats[chat_id]


@app.delete("/api/chats/{chat_id}")
async def delete_chat(chat_id: str):
    if chat_id not in chats:
        raise HTTPException(status_code=404, detail="Chat not found")
    del chats[chat_id]
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
