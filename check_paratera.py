"""Small, redacted connectivity check for the repository's Paratera secrets."""
import json
import os
import time
import urllib.error
import urllib.request


def main() -> None:
    names = ("PARATERA_API_KEY", "PARATERA_BASE_URL", "PARATERA_MODEL")
    missing = [name for name in names if not os.getenv(name, "").strip()]
    if missing:
        raise SystemExit("Missing Actions secrets: " + ", ".join(missing))
    base = os.environ["PARATERA_BASE_URL"].strip().rstrip("/")
    endpoint = base + ("/chat/completions" if base.endswith("/v1") else "/v1/chat/completions")
    models_endpoint = base + ("/models" if base.endswith("/v1") else "/v1/models")
    models_request = urllib.request.Request(
        models_endpoint, headers={"Authorization": "Bearer " + os.environ["PARATERA_API_KEY"].strip()})
    try:
        with urllib.request.urlopen(models_request, timeout=15) as response:
            models = json.load(response)
        ids = {item.get("id") for item in models.get("data", []) if isinstance(item, dict)}
        print(f"Model list HTTP 200; selected model listed: {os.environ['PARATERA_MODEL'].strip() in ids}")
        if os.getenv("LIST_MODELS_ONLY") == "1":
            print("Available DeepSeek models: " + ", ".join(sorted(str(x) for x in ids if x and "deepseek" in str(x).lower())))
            return
    except urllib.error.HTTPError as exc:
        print(f"Model list HTTP {exc.code}")
    except urllib.error.URLError as exc:
        print(f"Model list connection error: {type(exc.reason).__name__}")
    body = json.dumps({"model": os.environ["PARATERA_MODEL"].strip(),
                       "messages": [{"role": "user", "content": "Reply with OK."}],
                       "max_tokens": 8}).encode()
    request = urllib.request.Request(
        endpoint, data=body,
        headers={"Authorization": "Bearer " + os.environ["PARATERA_API_KEY"].strip(),
                 "Content-Type": "application/json"}, method="POST")
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                result = json.load(response)
            break
        except urllib.error.HTTPError as exc:
            try:
                payload = json.load(exc)
                error = payload.get("error", payload)
                error_code = error.get("code", "unknown") if isinstance(error, dict) else "unknown"
                error_message = error.get("message", error.get("detail", "")) if isinstance(error, dict) else ""
                if not error_message and isinstance(payload, dict):
                    error_message = payload.get("message", payload.get("detail", ""))
            except (ValueError, UnicodeDecodeError):
                error_code = "unknown"
                error_message = ""
            print(f"Paratera HTTP {exc.code}; provider error code: {error_code}; "
                  f"retry-after: {exc.headers.get('Retry-After', 'none')}; "
                  f"message: {str(error_message)[:240]}")
            if exc.code == 429 and attempt == 0:
                time.sleep(15)
                continue
            raise SystemExit("Paratera model call failed") from None
        except urllib.error.URLError as exc:
            raise SystemExit(f"Paratera connection error: {type(exc.reason).__name__}") from None
    if not result.get("choices"):
        raise SystemExit("Paratera responded without choices")
    print("Paratera model call succeeded")


if __name__ == "__main__":
    main()
