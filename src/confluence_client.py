from __future__ import annotations

import os
import requests
from base64 import b64encode
from bs4 import BeautifulSoup


class ConfluenceClient:
    def __init__(self):
        self.base_url = os.environ["CONFLUENCE_BASE_URL"]
        self.space_key = os.environ["CONFLUENCE_SPACE_KEY"]
        self.onboarding_parent_id = os.environ["CONFLUENCE_ONBOARDING_PARENT_PAGE_ID"]
        self.snapshots_parent_id = os.environ["CONFLUENCE_SNAPSHOTS_PARENT_PAGE_ID"]

        email = os.environ["CONFLUENCE_EMAIL"]
        token = os.environ["CONFLUENCE_API_TOKEN"]
        credentials = b64encode(f"{email}:{token}".encode()).decode()
        self.headers = {
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def get_client_page(self, client_name: str) -> dict:
        url = f"{self.base_url}/rest/api/content/search"
        params = {
            "cql": (
                f'space="{self.space_key}" '
                f'AND title~"{client_name}" '
                f'AND ancestor="{self.onboarding_parent_id}"'
            ),
            "expand": "body.storage",
        }
        resp = requests.get(url, headers=self.headers, params=params)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            raise ValueError(f"No Confluence page found for client: {client_name}")
        for page in results:
            if client_name.lower() in page["title"].lower():
                return page
        return results[0]

    def get_page_by_id(self, page_id: str) -> dict:
        url = f"{self.base_url}/rest/api/content/{page_id}"
        resp = requests.get(url, headers=self.headers, params={"expand": "body.storage"})
        resp.raise_for_status()
        return resp.json()

    def parse_gong_sessions(self, page: dict) -> list[dict]:
        html = page["body"]["storage"]["value"]
        soup = BeautifulSoup(html, "lxml")
        sessions = []
        for table in soup.find_all("table"):
            headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
            if "session" in headers and "recording" in headers:
                for row in table.find_all("tr")[1:]:
                    cells = row.find_all("td")
                    if len(cells) < 2:
                        continue
                    session_name = cells[0].get_text(strip=True)
                    link = cells[1].find("a")
                    gong_url = link["href"] if link else cells[1].get_text(strip=True)
                    date_text = ""
                    if len(cells) > 2:
                        time_tag = cells[2].find("time")
                        date_text = (
                            time_tag["datetime"]
                            if time_tag and time_tag.get("datetime")
                            else cells[2].get_text(strip=True)
                        )
                    if session_name and gong_url:
                        sessions.append({
                            "session_name": session_name,
                            "gong_url": gong_url,
                            "date": date_text,
                        })
        return sessions

    def find_snapshot_page(self, client_name: str) -> dict | None:
        url = f"{self.base_url}/rest/api/content/search"
        params = {
            "cql": (
                f'space="{self.space_key}" '
                f'AND title="{client_name} [Snapshot]" '
                f'AND ancestor="{self.snapshots_parent_id}"'
            ),
            "expand": "body.storage,version",
        }
        resp = requests.get(url, headers=self.headers, params=params)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return results[0] if results else None

    def _get_space_id(self) -> str:
        if hasattr(self, "_space_id"):
            return self._space_id
        url = f"{self.base_url}/api/v2/spaces"
        resp = requests.get(url, headers=self.headers, params={"keys": self.space_key})
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            raise ValueError(f"Confluence space not found for key: {self.space_key}")
        self._space_id = str(results[0]["id"])
        return self._space_id

    def create_snapshot_page(self, title: str, storage_content: str) -> dict:
        space_id = self._get_space_id()
        url = f"{self.base_url}/api/v2/pages"
        payload = {
            "spaceId": space_id,
            "parentId": str(self.snapshots_parent_id),
            "status": "current",
            "title": title,
            "body": {"representation": "storage", "value": storage_content},
        }
        resp = requests.post(url, headers=self.headers, json=payload)
        if not resp.ok:
            raise ValueError(f"Confluence API error {resp.status_code}: {resp.text}")
        return resp.json()

    def append_session_to_snapshot(
        self, page_id: str, title: str, version: int, new_session_storage: str
    ) -> dict:
        existing = self.get_page_by_id(page_id)
        updated_body = existing["body"]["storage"]["value"] + "\n" + new_session_storage
        url = f"{self.base_url}/api/v2/pages/{page_id}"
        payload = {
            "id": page_id,
            "status": "current",
            "title": title,
            "version": {"number": version + 1},
            "body": {"representation": "storage", "value": updated_body},
        }
        resp = requests.put(url, headers=self.headers, json=payload)
        if not resp.ok:
            raise ValueError(f"Confluence API error {resp.status_code}: {resp.text}")
        return resp.json()
