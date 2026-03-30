import time

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from src.confluence_client import ConfluenceClient
from src.gong_client import GongClient
from src.snapshot_generator import SnapshotGenerator
from src.confluence_formatter import format_snapshot, format_session_block


st.set_page_config(page_title="SnapCreate", layout="centered")

st.title("SnapCreate")
st.caption("Automatically generates Confluence snapshots from Gong recordings.")
st.divider()

st.subheader("Step 1 — Select client")
client_name = st.text_input(
    "Type the company name exactly as it appears in Confluence",
    placeholder="e.g. Riley Earthmoving",
)

if client_name:
    if st.button("Load sessions", type="secondary"):
        with st.spinner("Fetching sessions from Confluence..."):
            try:
                confluence = ConfluenceClient()
                page = confluence.get_client_page(client_name)
                sessions = confluence.parse_gong_sessions(page)
                st.session_state["sessions"] = sessions
                st.session_state["page_title"] = page["title"]
                st.session_state["client_name"] = client_name
                st.success(f"Found **{page['title']}** with {len(sessions)} session(s).")
            except Exception as e:
                st.error(f"Could not load sessions: {e}")

if "sessions" in st.session_state and st.session_state["sessions"]:
    st.divider()
    st.subheader("Step 2 — Choose session")

    sessions = st.session_state["sessions"]
    session_labels = [f"{s['session_name']}  ({s['date']})" for s in sessions]

    selected_label = st.selectbox(
        "Select the session to generate a snapshot for",
        options=session_labels,
        index=0,
    )

    selected_index = session_labels.index(selected_label)
    selected_session = sessions[selected_index]

    st.info(
        "The **Kickoff** session will always be included alongside your selected session "
        "to populate the Onboarding Journey Audit table."
        if selected_index != 0
        else "The Kickoff session was selected — this will generate the full audit table."
    )

    st.divider()
    st.subheader("Step 3 — Generate")

    if st.button("Generate Snapshot", type="primary"):
        client = st.session_state["client_name"]

        kickoff = sessions[0]
        sessions_to_process = [selected_session] if selected_index == 0 else [kickoff, selected_session]

        progress = st.empty()
        log = st.empty()

        def update(msg: str, paragraph: bool = False):
            content = msg if paragraph else f"```\n{msg}\n```"
            log.markdown(content)

        try:
            gong = GongClient()
            generator = SnapshotGenerator()
            confluence = ConfluenceClient()

            progress.progress(0.2, "Fetching Gong transcripts...")
            for session in sessions_to_process:
                update(f"Fetching transcript: {session['session_name']} ({session['date']})...")
                session["transcript"] = gong.get_transcript_for_session(
                    session["gong_url"], session["date"], client, session["session_name"]
                )
                word_count = len(session["transcript"].split())
                session["word_count"] = word_count
                update(f"Transcript fetched: {session['session_name']} ({word_count:,} words)")

            progress.progress(0.5, "Generating snapshot with Claude AI...")
            snapshot = {"audit_info": None, "sessions": []}

            for i, session in enumerate(sessions_to_process):
                if i > 0:
                    prev = sessions_to_process[i - 1]
                    prev_words = prev.get("word_count", 0)
                    update(
                        f"**Waiting 65 seconds before processing the next session.**\n\n"
                        f"The current Claude plan allows only 10,000 tokens (roughly words) per minute. "
                        f"The previous recording — *{prev['session_name']}* — had **{prev_words:,} words**, "
                        f"which used up the minute's quota. "
                        f"Waiting resets the limit so the next session can be processed.",
                        paragraph=True,
                    )
                    time.sleep(65)

                update(f"Claude processing: {session['session_name']}...")
                partial = generator.generate([session], client_name=client, sleep_between=0)
                if partial.get("audit_info") and not snapshot["audit_info"]:
                    snapshot["audit_info"] = partial["audit_info"]
                snapshot["sessions"].extend(partial.get("sessions", []))

            progress.progress(0.85, "Posting to Confluence...")
            title = f"{client} [Snapshot]"
            existing_page = confluence.find_snapshot_page(client)

            if existing_page:
                page_id = existing_page["id"]
                version = existing_page["version"]["number"]
                session_block = format_session_block(snapshot["sessions"][-1])
                confluence.append_session_to_snapshot(page_id, title, version, session_block)
            else:
                onboarding_start = sessions_to_process[0]["date"]
                storage_content = format_snapshot(snapshot, client, onboarding_start)
                confluence.create_snapshot_page(title, storage_content)

            progress.progress(1.0, "Done!")
            log.empty()
            st.success("Snapshot created successfully!")

        except Exception as e:
            progress.empty()
            st.error(f"Error: {e}")
