"""
Converts the structured snapshot dict produced by SnapshotGenerator into
Confluence storage format (XHTML):

  • Onboarding Journey Audit table
  • Journey Stages & Stuck Points
      – one collapsible "Major Discussions" expand-macro per session
      – bullet lists and pink-highlighted problems (background #ffebe6)
"""

from html import escape


def format_snapshot(snapshot: dict, client_name: str, onboarding_start: str) -> str:
    """Return Confluence storage-format XML for the full snapshot."""
    parts = []

    # ── 1. Onboarding Journey Audit table ─────────────────────────────────
    audit = snapshot.get("audit_info") or {}
    use_cases = audit.get("primary_use_cases") or []
    use_cases_html = "".join(f"<li>{escape(uc)}</li>" for uc in use_cases)

    parts.append(
        f"""<h2>Onboarding Journey Audit</h2>
<table>
  <tbody>
    <tr><th>Item</th><th>Detail</th></tr>
    <tr>
      <td>Customer</td>
      <td><code>{escape(audit.get("customer_name") or client_name)}</code></td>
    </tr>
    <tr>
      <td>Segment / Tier</td>
      <td>{escape(audit.get("segment_tier") or "")}</td>
    </tr>
    <tr>
      <td>Primary use case</td>
      <td><ul>{use_cases_html}</ul></td>
    </tr>
    <tr>
      <td>CS owner / Technical Assistant</td>
      <td>{escape(audit.get("cs_owner") or "")}</td>
    </tr>
    <tr>
      <td>Onboarding start</td>
      <td>Kick-off: {escape(onboarding_start)}</td>
    </tr>
    <tr>
      <td>Data sources</td>
      <td>Activities recorded in Gong</td>
    </tr>
    <tr>
      <td>Accounting Software</td>
      <td>{escape(audit.get("accounting_software") or "")}</td>
    </tr>
  </tbody>
</table>"""
    )

    # ── 2. Journey Stages & Stuck Points ──────────────────────────────────
    parts.append("<h2>Journey Stages &amp; Stuck Points</h2>")

    for session in snapshot.get("sessions") or []:
        session_name = session.get("session_name", "")
        date = session.get("date", "")
        discussions = session.get("major_discussions") or []

        # Section header (bold, matches PDF style)
        parts.append(
            f"<p><strong>{escape(session_name)}:&nbsp; {escape(date)}</strong></p>"
        )

        # Collapsible expand macro
        inner = _render_discussions(discussions)
        parts.append(
            f"""<ac:structured-macro ac:name="expand" ac:schema-version="1">
  <ac:parameter ac:name="title">Major Discussions</ac:parameter>
  <ac:rich-text-body>
{inner}
  </ac:rich-text-body>
</ac:structured-macro>"""
        )

    return "\n".join(parts)


def format_session_block(session: dict) -> str:
    """
    Return the Confluence storage XML for a single session block only
    (bold header + expand macro). Used when appending to an existing page.
    """
    session_name = session.get("session_name", "")
    date = session.get("date", "")
    discussions = session.get("major_discussions") or []
    inner = _render_discussions(discussions)
    return (
        f"<p><strong>{escape(session_name)}:&nbsp; {escape(date)}</strong></p>\n"
        f'<ac:structured-macro ac:name="expand" ac:schema-version="1">\n'
        f'  <ac:parameter ac:name="title">Major Discussions</ac:parameter>\n'
        f"  <ac:rich-text-body>\n{inner}\n  </ac:rich-text-body>\n"
        f"</ac:structured-macro>"
    )


# ── helpers ────────────────────────────────────────────────────────────────

def _render_discussions(discussions: list[dict]) -> str:
    """Convert a list of discussion items into Confluence storage HTML."""
    parts = []
    i = 0

    while i < len(discussions):
        item = discussions[i]
        kind = item.get("type", "bullet")
        text = escape(item.get("text", ""))

        if kind == "problem":
            parts.append(
                f'<p><span style="background-color: #ffebe6;">'
                f"<strong>{text}</strong></span></p>"
            )
            i += 1

        else:
            # bullet — group consecutive ones into a single <ul>
            bullets = [text]
            j = i + 1
            while j < len(discussions) and discussions[j].get("type") == "bullet":
                bullets.append(escape(discussions[j].get("text", "")))
                j += 1
            lis = "".join(f"<li>{b}</li>" for b in bullets)
            parts.append(f"<ul>{lis}</ul>")
            i = j

    return "\n".join(parts)
