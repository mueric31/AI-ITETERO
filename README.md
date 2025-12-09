# Kinyarwanda PDF Chatbot 🤖

A RAG (Retrieval Augmented Generation) chatbot that answers questions in Kinyarwanda based on PDF content. Uses OpenAI embeddings and GPT for accurate, context-aware responses.

## Features ✨

- **PDF-Based Answers**: Only responds with information from the PDF
- **Kinyarwanda Support**: Full support for Kinyarwanda language queries
- **Smart Greetings**: Handles social interactions (greetings, thanks, time, etc.)
- **Fallback Mechanism**: Returns "ntamakuru ndagira kuri iyi ngingo" for unrelated questions
- **Synonym Expansion**: Improves retrieval with synonyms
- **Session Memory**: Optional name persistence
- **FastAPI Server**: RESTful API for easy integration

## Project Structure 📁

```
kinyarwanda-chatbot/
├── .env.example          # Environment variables template
├── requirements.txt      # Python dependencies
├── config.py            # Configuration settings
├── utils.py             # PDF processing utilities
├── build_index.py       # Index builder script
├── main.py              # FastAPI server
├── src/
│   ├── __init__.py
│   ├── chat.py          # Main chat logic
│   └── greetings.py     # Small talk handler
└── data/
    ├── imirire.pdf      # Your PDF file (add this)
    ├── synonyms.json    # Query expansion synonyms
    ├── index.faiss      # Generated FAISS index
    └── meta.jsonl       # Generated metadata
```

## Installation 🚀

### 1. Clone or Download

Download this project and navigate to the directory:

```bash
cd kinyarwanda-chatbot
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Set Up Environment

Copy the example environment file:

```bash
cp .env.example .env
```

Edit `.env` and add your OpenAI API key:

```env
OPENAI_API_KEY=sk-your-api-key-here
```

### 4. Add Your PDF

Place your PDF file in the `data/` folder:

```bash
cp /path/to/your/imirire.pdf data/imirire.pdf
```

### 5. Build the Index

Process your PDF and create the FAISS index:

```bash
python build_index.py
```

This will:
- Extract text from the PDF
- Create embeddings using OpenAI
- Build a searchable FAISS index
- Save metadata for retrieval

## Usage 💬

### Command Line Interface

**Interactive mode:**
```bash
python src/chat.py
```

**Single query:**
```bash
python src/chat.py "Ni iki kintu cyiza cyo kurya?"
```

### API Server

**Start the server:**
```bash
python main.py
```

**Test endpoints:**

- Root: http://127.0.0.1:1000
- Health: http://127.0.0.1:1000/health
- API Docs: http://127.0.0.1:1000/docs

**GET request:**
```bash
curl "http://127.0.0.1:1000/chat?query=Muraho"
```

**POST request:**
```bash
curl -X POST "http://127.0.0.1:1000/chat" \
  -H "Content-Type: application/json" \
  -d '{"query": "Ni iki kintu cyiza cyo kurya?"}'
```

## Example Queries 📝

### Greetings (No API call)
```
User: Muraho!
Bot: Muraho, Nshuti! Nitwa Umufasha w'Itetero.

User: Saa ngapi ubu?
Bot: Ubu ni saa 14:30, Nshuti. ⏰

User: Urakoze
Bot: Urakoze cyane, Nshuti! 🙏
```

### PDF Questions (Uses OpenAI)
```
User: Ni iki kintu cyiza cyo kurya?
Bot: [Searches PDF and generates answer based on content]

User: Inkingo ni izi?
Bot: [Returns information about vaccines from PDF]
```

### Unrelated Questions
```
User: Ni nde Perezida wa Amerika?
Bot: ntamakuru ndagira kuri iyi ngingo
```

### Name Memory
```
User: Nitwa Jean
Bot: Nishimiye kukumenya, Jean! 🎉

User: Urakibuka izina ryanjye?
Bot: Yego, ndaribuka. Witwa Jean.
```

## Configuration ⚙️

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | (required) | Your OpenAI API key |
| `EMBED_MODEL` | text-embedding-3-small | Embedding model |
| `CHAT_MODEL` | gpt-4o-mini | Chat completion model |
| `CHUNK_SIZE` | 900 | Token chunk size |
| `OVERLAP` | 200 | Token overlap between chunks |
| `TOP_K` | 5 | Number of chunks to retrieve |
| `SCORE_THRESHOLD` | 0.15 | Minimum similarity score |
| `BOT_NAME` | Umufasha w'Itetero | Bot display name |
| `GREETINGS_PERSIST` | 0 | Persist name across sessions |

### Customize Synonyms

Edit `data/synonyms.json` to add domain-specific terms:

```json
{
  "umwana": ["abana", "uruhinja", "ingene"],
  "ibiryo": ["indyo", "kurya", "ibyo kurya"]
}
```

## How It Works 🔍

1. **Indexing Phase** (`build_index.py`):
   - Extracts text from PDF
   - Splits into overlapping chunks
   - Creates embeddings using OpenAI
   - Stores in FAISS vector database

2. **Query Phase** (`src/chat.py`):
   - Checks for small talk (greetings, etc.)
   - If content query:
     - Cleans and expands query with synonyms
     - Retrieves top-K similar chunks from FAISS
     - Uses GPT to generate answer based ONLY on chunks
   - Returns fallback if no relevant content

3. **API Layer** (`main.py`):
   - Exposes REST endpoints
   - Handles GET/POST requests
   - Returns JSON responses

## Commands 🎮

- `/help` - Show available commands
- `/reset` - Clear saved name
- `Nitwa [name]` - Introduce yourself
- `urakibuka izina ryanjye?` - Ask if bot remembers your name

## Troubleshooting 🔧

### "FAISS index not found"
**Solution:** Run `python build_index.py` first

### "No API key provided"
**Solution:** Check `.env` file has valid `OPENAI_API_KEY`

### Bot returns fallback too often
**Solution:** Lower the threshold:
```env
SCORE_THRESHOLD=0.10
```

### Need more context per answer
**Solution:** Increase these values:
```env
TOP_K=8
CHUNK_SIZE=1200
```

## Cost Estimation 💰

- **Embedding**: ~$0.0001 per 1000 tokens
- **Chat**: ~$0.15 per 1M tokens (gpt-4o-mini)
- **Typical usage**: 100-page PDF + 1000 queries ≈ $2-5

## Development 👨‍💻

### Run Tests
```bash
# Test greetings
python src/chat.py "Muraho"

# Test PDF query
python src/chat.py "Ni iki kintu cyiza cyo kurya?"

# Test unrelated query
python src/chat.py "Ni nde Perezida wa Amerika?"
```

### Debug Mode
Set verbose logging in `.env`:
```env
LOG_LEVEL=DEBUG
```

## API Integration Example 🔌

### Python
```python
import requests

response = requests.post(
    "http://127.0.0.1:1000/chat",
    json={"query": "Ni iki kintu cyiza cyo kurya?"}
)
print(response.json()["response"])
```

### JavaScript
```javascript
fetch('http://127.0.0.1:1000/chat', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({query: 'Muraho'})
})
.then(r => r.json())
.then(data => console.log(data.response));
```

## License 📄

MIT License - feel free to use and modify!

## Support 💬

For issues or questions, please check:
- OpenAI API docs: https://platform.openai.com/docs
- FAISS documentation: https://github.com/facebookresearch/faiss

---

**Made with ❤️ for the Kinyarwanda community**
