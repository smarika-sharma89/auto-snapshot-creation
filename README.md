# SnapCreate

Automatically generates Confluence onboarding snapshots from Gong call recordings.

Instead of manually watching hours of Gong recordings and writing up snapshots, this tool:

1. Reads the client's Confluence page to find all recorded Gong sessions
2. Fetches the call transcripts from the Gong API
3. Sends the transcripts to Claude AI to extract the key discussions
4. Creates a formatted snapshot page in the Onboarding Snapshots folder in Confluence

---

## Setup

### 1. Clone the repo and create a virtual environment

```bash
git clone <repo-url>
cd auto-snapshot-creation
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Create your `.env` file and fill in the keys

```bash
cp .env.example .env
```

## Running the UI

The easiest way to use the tool is through the Streamlit web UI:

```bash
streamlit run app.py
```

## Rate limits

On the Anthropic free/standard plan (up to $20/month), the limit is 10,000 input tokens per minute. Long Gong transcripts (1–2 hours) will hit this. The tool automatically waits 65 seconds between sessions to stay within the limit.

If you need to process many sessions faster, contact Anthropic to upgrade your rate limit tier.

---

## Project structure

```
auto-snapshot-creation/
├── app.py                      # Streamlit UI
├── main.py                     # Command-line entry point
├── requirements.txt
├── .env.example                # Template — copy to .env and fill in
├── .env                        # Your real credentials (never committed)
└── src/
    ├── confluence_client.py    # Reads client pages and creates snapshot pages
    ├── gong_client.py          # Fetches call transcripts from Gong API
    ├── snapshot_generator.py   # Sends transcripts to Claude and extracts structured data
    └── confluence_formatter.py # Converts structured data to Confluence page format
```
