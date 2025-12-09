from fastapi import FastAPI
from src.chat import get_response
from pydantic import BaseModel

app = FastAPI(
    title="Kinyarwanda Chatbot API",
    description="RAG-based chatbot for Kinyarwanda PDF content",
    version="1.0.0"
)

class ChatRequest(BaseModel):
    query: str

@app.get("/")
def read_root():
    return {
        "message": "Welcome to the Kinyarwanda Chatbot API",
        "endpoints": {
            "GET /chat": "Query with ?query=your_question",
            "POST /chat": "Send JSON body with {query: 'your_question'}",
            "GET /health": "Health check endpoint"
        }
    }

@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.get("/chat")
def chat_get(query: str):
    """
    GET endpoint for chat queries
    Example: /chat?query=Muraho
    """
    if not query or not query.strip():
        return {"error": "Query parameter is required"}
    return {"response": get_response(query)}

@app.post("/chat")
def chat_post(body: ChatRequest):
    """
    POST endpoint for chat queries
    Body: {"query": "Muraho"}
    """
    if not body.query or not body.query.strip():
        return {"error": "Query field is required"}
    return {"response": get_response(body.query)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=1000)
