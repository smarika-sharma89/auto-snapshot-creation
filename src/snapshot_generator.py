import os
import json
import time
import anthropic


_SYSTEM_PROMPT = """\
You are an expert at analysing customer onboarding call transcripts for Varicon, \
a construction management software. Your job is to extract structured information \
and produce a well-organised onboarding snapshot that matches the company's format."""


_KICKOFF_PROMPT = """\
Analyse this Kickoff call transcript and return a JSON object with this exact shape:

{{
  "primary_use_cases": ["...", "..."],
  "accounting_software": "...",
  "success_canvas_on_screen": true or false,
  "major_discussions": [
    {{"type": "bullet", "text": "..."}}
  ]
}}

Field rules:
- "primary_use_cases": 3–5 short labels for what the client will mainly use Varicon for \
  (e.g. "Payroll Automation", "Project Cost Tracking", "Accounts Payable").
- "accounting_software": The accounting/finance system the client uses \
  (e.g. "Xero", "QuickBooks", "MYOB"). Write "N/A" if none mentioned.
- "success_canvas_on_screen": true if the Success Canvas was screen-shared or visually \
  presented during the call; false if it was only mentioned or not referenced at all.

Rules for major_discussions — these must follow this EXACT STRUCTURE for kickoff calls:

1. Always include this bullet first (verbatim):
   {{"type": "bullet", "text": "The team introduction and clarity on available support and resources were provided to the client"}}

2. If an accounting software was mentioned or set up, include ONE bullet like:
   {{"type": "bullet", "text": "[AccountingSoftware] integration and its technical limitations were explained"}}
   Replace [AccountingSoftware] with the actual software name.

3. Always include this bullet:
   {{"type": "bullet", "text": "The six onboarding phases were reviewed"}}

4. For the Success Canvas:
   - If success_canvas_on_screen is true:
     {{"type": "bullet", "text": "Success Canvas was presented on screen — see the recording for details"}}
   - If success_canvas_on_screen is false but it was discussed:
     {{"type": "bullet", "text": "Discussion on Success Canvas covering: Key Challenges, Milestones & Training schedule, Success Criteria"}}

5. After the above fixed bullets, add up to 4 additional bullets for anything else important \
   that was specifically decided or agreed (e.g. a phased rollout plan, a pilot date, a specific \
   integration setup completed during the call). Skip generic conversation. \
   Write as a plain clear sentence. No dashes, no labels, no "X – Y" format.

6. At the end, list any client concerns or issues as type "problem". \
   Write each as a plain clear sentence. No dashes, no label prefixes. \
   Example: {{"type": "problem", "text": "Client raised concern about duplicate data entry across timesheets and site diary"}}

Transcript:
{transcript}

Return ONLY valid JSON — no markdown, no explanation."""


_SESSION_PROMPT = """\
Analyse this onboarding call transcript and return a JSON object with this exact shape:

{{
  "major_discussions": [
    {{"type": "bullet", "text": "..."}}
  ]
}}

Session: {session_name}
Date: {date}

Rules for major_discussions — write plain, clear sentences. No dashes, no "Label – description" format.

Good example output:
  {{"type": "bullet", "text": "Resource management within Varicon was reviewed including how resources are set up and linked to suppliers"}}
  {{"type": "bullet", "text": "Default accounting code and purchase order settings were configured"}}
  {{"type": "problem", "text": "Unclear resource list was causing issues when creating a purchase order"}}
  {{"type": "problem", "text": "Some bills were syncing to Xero without attachments"}}

Rules:
- type "bullet"  → a key topic or feature covered. Write as a plain sentence describing what was done or decided.
- type "problem" → a bug, confusion, or issue raised. Write as a plain sentence describing the problem.
- Pick only the MOST IMPORTANT 5–10 points. Skip greetings, scheduling chat, and minor asides.
- No dashes, no label prefixes, no "X – Y" style. Just clear sentences a non-technical person can read.
- Do NOT write long paragraphs. Each entry should be one concise sentence.
- List all problems/issues together at the end as type "problem".

Transcript:
{transcript}

Return ONLY valid JSON — no markdown, no explanation."""


class SnapshotGenerator:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    def generate(self, sessions: list[dict], client_name: str = "", sleep_between: int = 0) -> dict:
        snapshot = {"audit_info": None, "sessions": []}

        for i, session in enumerate(sessions):
            name = session["session_name"]
            is_kickoff = i == 0 or "kickoff" in name.lower() or name.upper().startswith("KO")

            if i > 0 and sleep_between > 0:
                time.sleep(sleep_between)

            if is_kickoff and snapshot["audit_info"] is None:
                result = self._process_kickoff(session["transcript"])
                snapshot["audit_info"] = {
                    "customer_name": client_name or result.get("customer_name", ""),
                    "segment_tier": "Civil Construction Company",
                    "primary_use_cases": result.get("primary_use_cases", []),
                    "cs_owner": "",
                    "accounting_software": result.get("accounting_software", "N/A"),
                }
                snapshot["sessions"].append({
                    "session_name": name,
                    "date": session["date"],
                    "major_discussions": result.get("major_discussions", []),
                })
            else:
                result = self._process_session(session["transcript"], name, session["date"])
                snapshot["sessions"].append({
                    "session_name": name,
                    "date": session["date"],
                    "major_discussions": result.get("major_discussions", []),
                })

        return snapshot

    def _process_kickoff(self, transcript: str) -> dict:
        return self._call_claude(_KICKOFF_PROMPT.format(transcript=self._trim(transcript)))

    def _process_session(self, transcript: str, session_name: str, date: str) -> dict:
        return self._call_claude(_SESSION_PROMPT.format(
            session_name=session_name,
            date=date,
            transcript=self._trim(transcript),
        ))

    def _call_claude(self, prompt: str) -> dict:
        message = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())

    @staticmethod
    def _trim(text: str, max_chars: int = 180_000) -> str:
        return text[:max_chars]
