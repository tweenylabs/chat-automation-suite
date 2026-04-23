import os
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
from backend.auth import router as auth_router
from backend.agent import TravelAgent
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Notion Travel Agent Pro API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)

class Message(BaseModel):
    role: str
    content: str

class QueryRequest(BaseModel):
    query: str
    history: List[Message] = []
    clarification_count: int = 0
    mode: str = "Hybrid" # Default to Hybrid
    is_confirmed: bool = False # Skip clarification/consent if true
    travel_date: Optional[str] = None

@app.get("/")
async def root():
    return {"message": "Notion Travel Agent Pro API is running"}

@app.post("/query/stream")
async def handle_query_stream(request: QueryRequest, authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization")
    token = authorization.split(" ")[1]
    
    agent = TravelAgent(notion_token=token)
    history_dicts = [{"role": m.role, "content": m.content} for m in request.history]
    
    return StreamingResponse(
        agent.run_query_stream(
            request.query, 
            history_dicts, 
            request.mode,
            request.is_confirmed,
            request.travel_date
        ),
        media_type="text/event-stream"
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
