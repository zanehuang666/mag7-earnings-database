"""Small, redacted connectivity check for the repository's Paratera secrets."""
import json
import os
import urllib.error
import urllib.request


def main() -> None:
    names = ("PARATERA_API_KEY", "PARATERA_BASE_URL", "PARATERA_MODEL")
    missing = [name for name in names if not os.getenv(name, "").strip()]
    if missing:
        raise SystemExit("Missing Actions secrets: " + ", ".join(missing))
    base = os.environ["PARATERA_BASE_URL"].strip().rstrip("/")
    endpoint = base + ("/chat/completions" if base.endswith("/v1") else "/v1/chat/completions")
    body = json.dumps({"model": os.environ["PARATERA_MODEL"].strip(),
                       "messages": [{"role": "user", "content": "Reply with OK."}],
                       "max_tokens": 8}).encode()
    request = urllib.request.Request(
        endpoint, data=body,
        headers={"Authorization": "Bearer " + os.environ["PARATERA_API_KEY"].strip(),
                 "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"Paratera returned HTTP {exc.code}; check URL, model and key") from None
    if not result.get("choices"):
        raise SystemExit("Paratera responded without choices")
    print("Paratera model call succeeded")


if __name__ == "__main__":
    main()
