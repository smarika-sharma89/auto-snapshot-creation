import os
import re
import requests
from base64 import b64encode
from datetime import datetime, timedelta


class GongClient:
    def __init__(self):
        access_key = os.environ["GONG_ACCESS_KEY"]
        access_key_secret = os.environ["GONG_ACCESS_KEY_SECRET"]
        credentials = b64encode(f"{access_key}:{access_key_secret}".encode()).decode()
        self.headers = {
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/json",
        }
        self.base_url = os.environ.get("GONG_BASE_URL", "https://api.gong.io")

    def get_transcript_for_session(
        self, gong_url: str, session_date: str, client_name: str = "", session_name: str = ""
    ) -> str:
        """
        Fetch the full transcript for a Gong session.

        Resolution order:
        1. Extract call ID directly from the Gong share URL (most reliable — always works
           regardless of what the call is titled in Gong).
        2. Fall back to searching by date + client/session name in the title.
        """
        # Primary: resolve the share URL to a call ID
        call_id = self._call_id_from_share_url(gong_url)
        parties: list = []

        if call_id:
            parties = self._get_parties(call_id)
        else:
            call_id, parties = self._find_call_by_date(session_date, client_name, session_name)

        if not call_id:
            raise ValueError(
                f"Could not find the Gong call for '{session_name}' on {session_date}. "
                f"Check the terminal for the list of calls found on that date."
            )
        return self._get_transcript(call_id, parties)

    # ── Share URL resolution ───────────────────────────────────────────────

    def _call_id_from_share_url(self, share_url: str) -> str | None:
        """
        Resolve a Gong share URL to a call ID by following the redirect.
        Gong share URLs redirect to the full call page whose URL contains the call ID.
        e.g. https://...app.gong.io/call?id=1234567890
        """
        if not share_url or "gong.io" not in share_url:
            return None
        try:
            resp = requests.get(share_url, allow_redirects=True, timeout=15)
            # Check final URL after redirect
            final_url = resp.url
            match = re.search(r"[?&]id=(\d+)", final_url)
            if match:
                return match.group(1)
            # Also scan HTML body for callId patterns (some Gong pages embed it)
            match = re.search(r'"callId"\s*:\s*"?(\d+)"?', resp.text)
            if match:
                return match.group(1)
        except Exception as exc:
            print(f"        Could not resolve share URL: {exc}")
        return None

    def _get_parties(self, call_id: str) -> list:
        """Fetch party/participant info for a call to get company affiliations."""
        try:
            resp = requests.get(
                f"{self.base_url}/v2/calls",
                headers=self.headers,
                params={"callIds": call_id},
            )
            resp.raise_for_status()
            calls = resp.json().get("calls", [])
            if calls:
                return calls[0].get("parties", [])
        except Exception:
            pass
        return []

    # ── Date + title fallback ──────────────────────────────────────────────

    def _find_call_by_date(
        self, session_date: str, client_name: str, session_name: str = ""
    ) -> tuple[str | None, list]:
        """
        Search Gong calls on the session date and return the best title match.
        Scoring:
          4 — full client name in title
          3 — all client name words in title
          2 — at least 2 client name words in title
          1 — any session name word in title
          0 — last resort: only one call exists on that date
        """
        date = self._parse_date(session_date)
        if not date:
            raise ValueError(
                f"Could not parse session date: {session_date!r}. "
                "Expected format: 2025-06-04 or Jun 4, 2025"
            )

        params = {
            "fromDateTime": date.strftime("%Y-%m-%dT00:00:00+00:00"),
            "toDateTime":   date.strftime("%Y-%m-%dT23:59:59+00:00"),
        }

        client_lower = client_name.lower()
        client_words = [w for w in client_lower.split() if len(w) > 1]
        session_words = [w for w in session_name.lower().split() if len(w) > 3]

        cursor = None
        all_calls: list[dict] = []

        while True:
            if cursor:
                params["cursor"] = cursor
            resp = requests.get(
                f"{self.base_url}/v2/calls",
                headers=self.headers,
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()
            all_calls.extend(data.get("calls", []))
            cursor = data.get("records", {}).get("cursor")
            if not cursor:
                break

        def _score(call: dict) -> int:
            title = call.get("title", "").lower()
            if client_lower and client_lower in title:
                return 4
            if client_words and all(w in title for w in client_words):
                return 3
            matched = [w for w in client_words if w in title]
            if len(matched) >= 2:
                return 2
            if session_words and any(w in title for w in session_words):
                return 1
            return 0

        scored = [(call, _score(call)) for call in all_calls]
        best_score = max((s for _, s in scored), default=0)

        if best_score > 0:
            best = next(c for c, s in scored if s == best_score)
            return best["id"], best.get("parties", [])

        if len(all_calls) == 1:
            call = all_calls[0]
            return call["id"], call.get("parties", [])

        return None, []

    # ── Transcript fetching ────────────────────────────────────────────────

    def _get_transcript(self, call_id: str, parties: list) -> str:
        """
        Fetch and format the transcript for a call ID.
        Each speaker line is tagged with their company affiliation, e.g.:
          "Prashant [Varicon]: ..." or "Paul [Riley Earthmoving]: ..."
        This lets Claude reliably identify who is from Varicon.
        """
        resp = requests.post(
            f"{self.base_url}/v2/calls/transcript",
            headers=self.headers,
            json={"filter": {"callIds": [call_id]}},
        )
        resp.raise_for_status()

        data = resp.json()
        call_transcripts = data.get("callTranscripts", [])
        if not call_transcripts:
            return ""

        # Build speaker-id → "Name [Company]" lookup from parties
        speaker_label: dict[str, str] = {}
        for party in parties:
            name = party.get("name", "")
            company = party.get("company", "")
            affiliation = party.get("affiliation", "")  # "Internal" = Varicon
            tag = "Varicon" if affiliation == "Internal" else (company or affiliation)
            label = f"{name} [{tag}]" if tag else name
            for si in party.get("speakersInfo", []):
                speaker_label[si.get("id", "")] = label

        lines = []
        for segment in call_transcripts[0].get("transcript", []):
            speaker_id = segment.get("speakerId", "")
            speaker = speaker_label.get(speaker_id) or segment.get("speakerName", "Unknown")
            for sentence in segment.get("sentences", []):
                text = sentence.get("text", "").strip()
                if text:
                    lines.append(f"{speaker}: {text}")

        return "\n".join(lines)

    @staticmethod
    def _parse_date(date_str: str) -> datetime | None:
        """Parse ISO dates (from Confluence time tags) and common human formats."""
        for fmt in ["%Y-%m-%d", "%b %d, %Y", "%B %d, %Y", "%d %b %Y"]:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue
        return None
