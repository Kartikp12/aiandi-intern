
import html
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INPUT_FILE = BASE_DIR / "comments.json"
OUTPUT_FILE = BASE_DIR / "report.html"
CREDENTIALS_FILE = BASE_DIR / "cloud-flare.local.sh"

MODEL = "clef-flash"
VALID_LABELS = {"acceptable", "toxic", "spam"}
MAX_RETRIES = 3


def load_credentials():
    """Load credentials from the local shell file without printing secrets."""
    import re

    if not CREDENTIALS_FILE.exists():
        raise FileNotFoundError(
            "cloud-flare.local.sh is missing. Create it from cloud-flare.sh."
        )

    content = CREDENTIALS_FILE.read_text(encoding="utf-8")
    credentials = dict(
        re.findall(r'^\s*export\s+(\w+)="([^"]*)"', content, re.MULTILINE)
    )

    account = credentials.get("CLOUDFLARE_ACCOUNT_ID", "")
    token = credentials.get("CLOUDFLARE_API_TOKEN", "")

    if not account or not token:
        raise ValueError("Account ID or API token is missing from the local file.")

    if account == "0123456789abcdef0123456789abcdef":
        raise ValueError("Replace the placeholder Account ID with your real one.")

    if token == "your-cloudflare-api-token-goes-here":
        raise ValueError("Replace the placeholder API token with your real token.")

    return account, token


def classify_comment(comment, account, token):
    """Ask Clef to classify one comment and return its result."""
    url = (
        f"https://api.cloudflare.com/client/v4/accounts/{account}"
        f"/ai/run/@cf/cloudflare/{MODEL}"
    )

    payload = {
        "state": {
            "comment": comment["comment"]
        },
        "questions": {
            "moderation": {
                "type": "choice",
                "instructions": (
                    "Classify `comment`, a college course forum post, "
                    "using its actual meaning and context. Choose exactly "
                    "one category. A genuine question, disagreement, "
                    "criticism, or mention of an AI tool is not automatically "
                    "toxic or spam."
                ),
                "criteria": {
                    "acceptable": (
                        "A legitimate course-related question, discussion, "
                        "answer, opinion, or other non-abusive post. Includes "
                        "polite disagreement and constructive criticism."
                    ),
                    "toxic": (
                        "Insults, harassment, targeted abuse, hateful attacks, "
                        "or threats directed at a person or group. Do not "
                        "label a post toxic merely because it is negative."
                    ),
                    "spam": (
                        "Unsolicited advertising, repetitive promotional "
                        "content, irrelevant commercial links, scams, or "
                        "messages mainly intended to promote unrelated "
                        "products or services."
                    ),
                },
            }
        },
    }

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )

    for attempt in range(MAX_RETRIES):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data = json.load(response)

            if not data.get("success"):
                raise RuntimeError(
                    f"Cloudflare API reported an unsuccessful response: "
                    f"{data.get('errors', [])}"
                )

            answer = data["result"]["answers"]["moderation"]
            label = answer.get("choice", "").lower()

            if label not in VALID_LABELS:
                raise ValueError(f"Unexpected classification label: {label!r}")

            return {
                "label": label,
                "probabilities": answer.get("probabilities", {}),
                "confidence": answer.get("confidence"),
                "error": None,
            }

        except urllib.error.HTTPError as exc:
            if exc.code == 429 or 500 <= exc.code < 600:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)
                    continue

            # Avoid printing credentials or request headers.
            try:
                details = json.loads(exc.read().decode("utf-8"))
                message = details.get("errors", [{"message": "API request failed"}])
            except (ValueError, json.JSONDecodeError):
                message = "API request failed"

            return {
                "label": None,
                "probabilities": {},
                "confidence": None,
                "error": f"HTTP {exc.code}: {message}",
            }

        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
                continue

            return {
                "label": None,
                "probabilities": {},
                "confidence": None,
                "error": f"Request failed: {type(exc).__name__}",
            }

        except (KeyError, TypeError, ValueError, RuntimeError) as exc:
            return {
                "label": None,
                "probabilities": {},
                "confidence": None,
                "error": str(exc),
            }

    return {
        "label": None,
        "probabilities": {},
        "confidence": None,
        "error": "Retries exhausted.",
    }


def build_html(results):
    """Create a searchable HTML report of the model's classifications."""
    counts = {label: 0 for label in VALID_LABELS}
    errors = 0

    for item in results:
        if item["label"] in counts:
            counts[item["label"]] += 1
        else:
            errors += 1

    rows = []

    for item in results:
        comment = item["comment"]
        label = item["label"] or "error"
        confidence = item["confidence"]

        confidence_text = (
            f"{confidence:.1%}" if isinstance(confidence, (int, float))
            else "N/A"
        )

        probabilities = item["probabilities"]
        probability_text = ", ".join(
            f"{name}: {value:.1%}"
            for name, value in probabilities.items()
            if isinstance(value, (int, float))
        )

        error_text = (
            f'<p class="error">{html.escape(item["error"])}</p>'
            if item["error"] else ""
        )

        rows.append(f"""
        <tr data-label="{html.escape(label)}">
          <td>{html.escape(str(comment.get("id", "")))}</td>
          <td>{html.escape(str(comment.get("author", "")))}<br>
              <small>{html.escape(str(comment.get("thread", "")))}</small></td>
          <td class="comment">{html.escape(str(comment.get("comment", "")))}{error_text}</td>
          <td><span class="badge {html.escape(label)}">{html.escape(label.upper())}</span></td>
          <td title="{html.escape(probability_text)}">{confidence_text}<br>
              <small>{html.escape(probability_text)}</small></td>
        </tr>
        """)

    generated_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")

    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Comment Moderator — Evaluation Report</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif;
         margin: 0; padding: 28px; color: #202124; background: #f5f7fa; }}
  h1 {{ margin-bottom: 6px; }}
  .muted {{ color: #626b78; }}
  .summary {{ display: flex; gap: 12px; flex-wrap: wrap; margin: 22px 0; }}
  .card {{ background: white; border: 1px solid #e1e5eb; border-radius: 10px;
           padding: 16px 20px; min-width: 125px; }}
  .number {{ font-size: 25px; font-weight: 700; margin-top: 5px; }}
  .toolbar {{ display: flex; gap: 10px; flex-wrap: wrap; margin: 20px 0; }}
  input, select {{ padding: 10px; border: 1px solid #ccd2dc;
                   border-radius: 7px; background: white; font-size: 14px; }}
  input {{ flex: 1; min-width: 200px; }}
  .table-wrap {{ overflow-x: auto; background: white; border-radius: 10px;
                 border: 1px solid #e1e5eb; }}
  table {{ border-collapse: collapse; width: 100%; min-width: 850px; }}
  th, td {{ padding: 13px; border-bottom: 1px solid #e8ebf0;
            text-align: left; vertical-align: top; }}
  th {{ background: #f9fafb; position: sticky; top: 0; }}
  .comment {{ max-width: 560px; white-space: pre-wrap; overflow-wrap: anywhere; }}
  .badge {{ display: inline-block; padding: 5px 8px; border-radius: 6px;
            font-size: 11px; font-weight: 700; }}
  .acceptable {{ background: #dcfce7; color: #166534; }}
  .toxic {{ background: #fee2e2; color: #991b1b; }}
  .spam {{ background: #fef3c7; color: #92400e; }}
  .error {{ color: #b91c1c; overflow-wrap: anywhere; }}
  small {{ color: #626b78; }}
  @media (max-width: 600px) {{ body {{ padding: 14px; }} }}
</style>
</head>
<body>
<h1>AI Comment Moderator</h1>
<p class="muted">Model: {html.escape(MODEL)} · Generated: {html.escape(generated_at)}</p>
<p class="muted">AI classifications are predictions, not ground truth. Review every comment manually.</p>

<div class="summary">
  <div class="card">Total comments<div class="number">{len(results)}</div></div>
  <div class="card">Acceptable<div class="number">{counts["acceptable"]}</div></div>
  <div class="card">Toxic<div class="number">{counts["toxic"]}</div></div>
  <div class="card">Spam<div class="number">{counts["spam"]}</div></div>
  <div class="card">Errors<div class="number">{errors}</div></div>
</div>

<div class="toolbar">
  <input id="search" type="search" placeholder="Search comments, authors or IDs...">
  <select id="filter">
    <option value="all">All classifications</option>
    <option value="acceptable">Acceptable</option>
    <option value="toxic">Toxic</option>
    <option value="spam">Spam</option>
    <option value="error">Errors</option>
  </select>
</div>

<div class="table-wrap">
<table>
<thead><tr>
<th>ID</th><th>Author / Thread</th><th>Comment</th>
<th>Clef label</th><th>Confidence / Probabilities</th>
</tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>
</div>
<script>
const search = document.getElementById('search');
const filter = document.getElementById('filter');
function updateRows() {{
  const query = search.value.toLowerCase();
  const label = filter.value;
  document.querySelectorAll('tbody tr').forEach(row => {{
    const matchesText = row.innerText.toLowerCase().includes(query);
    const matchesLabel = label === 'all' || row.dataset.label === label;
    row.hidden = !(matchesText && matchesLabel);
  }});
}}
search.addEventListener('input', updateRows);
filter.addEventListener('change', updateRows);
</script>
</body>
</html>
"""
    OUTPUT_FILE.write_text(document, encoding="utf-8")


def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError("comments.json was not found in the project folder.")

    data = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
    comments = data.get("comments")

    if not isinstance(comments, list):
        raise ValueError("Expected a list of comments under the 'comments' key.")

    account, token = load_credentials()
    results = []

    print(f"Model: {MODEL}")
    print(f"Comments to classify: {len(comments)}")

    for index, comment in enumerate(comments, start=1):
        if not isinstance(comment, dict) or "comment" not in comment:
            print(f"[{index}/{len(comments)}] Invalid comment record; recording error.")
            results.append({
                "comment": comment if isinstance(comment, dict) else {},
                "label": None,
                "probabilities": {},
                "confidence": None,
                "error": "Invalid comment record or missing comment text.",
            })
            continue

        result = classify_comment(comment, account, token)
        results.append({"comment": comment, **result})

        label = result["label"] or "ERROR"
        print(f"[{index}/{len(comments)}] ID {comment.get('id', '?')}: {label}")

        # Brief pause to avoid sending requests too rapidly.
        if index < len(comments):
            time.sleep(0.15)

    build_html(results)
    print(f"\nReport saved to: {OUTPUT_FILE}")
    print("Classification run complete.")
    print("Next: open report.html and manually review every comment.")
    print("Do not treat Clef's labels as ground truth.")


if __name__ == "__main__":
    main()
