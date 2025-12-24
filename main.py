import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from src.chat import get_response
from pydantic import BaseModel

app = FastAPI(
    title="Kinyarwanda Chatbot API",
    description="RAG-based chatbot for Kinyarwanda PDF content",
    version="1.0.0"
)

# ⭐⭐⭐ THIS IS THE FIX - CORS Middleware ⭐⭐⭐
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins (for development)
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods (GET, POST, etc.)
    allow_headers=["*"],  # Allows all headers
)

class ChatRequest(BaseModel):
    query: str

@app.get("/")
def read_root():
    return {
        "message": "Welcome to the Kinyarwanda Chatbot API",
        "status": "online",
        "endpoints": {
            "GET /chat": "Query with ?query=your_question",
            "POST /chat": "Send JSON body with {query: 'your_question'}",
            "GET /health": "Health check endpoint"
        }
    }

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "Kinyarwanda Chatbot",
        "version": "1.0.0"
    }

@app.get("/chat")
def chat_get(query: str):
    """
    GET endpoint for chat queries
    Example: /chat?query=Muraho
    """
    if not query or not query.strip():
        raise HTTPException(status_code=400, detail="Query parameter is required")
    
    try:
        response = get_response(query)
        return {"response": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing query: {str(e)}")

@app.post("/chat")
def chat_post(body: ChatRequest):
    """
    POST endpoint for chat queries
    Body: {"query": "Muraho"}
    """
    if not body.query or not body.query.strip():
        raise HTTPException(status_code=400, detail="Query field is required")
    
    try:
        response = get_response(body.query)
        return {"response": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing query: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)