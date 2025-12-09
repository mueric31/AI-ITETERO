# Quick Start Guide 🚀

Get your Kinyarwanda chatbot running in 5 minutes!

## Step 1: Install Dependencies

```bash
pip install -r requirements.txt
```

## Step 2: Configure Environment

Create `.env` file from the example:

```bash
cp .env.example .env
```

Edit `.env` and add your OpenAI API key:

```env
OPENAI_API_KEY=sk-your-actual-key-here
```

## Step 3: Verify PDF is in Place

Your PDF should already be at `data/imirire.pdf`. If not:

```bash
cp /path/to/your/pdf data/imirire.pdf
```

## Step 4: Build the Index

This processes your PDF and creates the searchable index:

```bash
python build_index.py
```

You should see:
```
Reading PDF from: data/imirire.pdf
Embedding X chunks with model text-embedding-3-small ...
100%|████████████████████| ...
Saved index to data/index.faiss and meta to data/meta.jsonl
```

## Step 5: Test the Chatbot

### CLI Mode

```bash
python src/chat.py
```

Try these queries:
```
>> Muraho
>> Ni iki kintu cyiza cyo kurya?
>> Saa ngapi ubu?
>> Urakoze
```

### API Server Mode

```bash
python main.py
```

Visit http://127.0.0.1:1000/docs for interactive API testing.

Or use curl:
```bash
curl "http://127.0.0.1:1000/chat?query=Muraho"
```

## What to Expect

✅ **Greetings**: Instant response (no API call)
```
User: Muraho!
Bot: Muraho, Nshuti! Nitwa Umufasha w'Itetero.
```

✅ **PDF Questions**: Answer from document
```
User: Ni iki kintu cyiza cyo kurya?
Bot: [Answer based on PDF content]
```

✅ **Unrelated Questions**: Fallback response
```
User: What's the weather?
Bot: ntamakuru ndagira kuri iyi ngingo
```

## Common Issues

### "FAISS index not found"
→ Run `python build_index.py` first

### "No API key provided"
→ Check your `.env` file has `OPENAI_API_KEY=sk-...`

### "Module not found"
→ Run `pip install -r requirements.txt`

## Next Steps

- Read [README.md](README.md) for full documentation
- Customize `data/synonyms.json` for better search
- Adjust `SCORE_THRESHOLD` in `.env` if needed
- Deploy to production server

---

**That's it! Your chatbot is ready.** 🎉
