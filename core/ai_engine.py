"""Shared Gemini engine for ACUMEN.

Uses Gemini's HTTP API directly so ACUMEN receives the real API error instead of a
large abstraction stack turning everything into a mysterious 503. Humanity has
suffered enough from error messages that say nothing.
"""
import json
import os
import urllib.error
import urllib.request
import time

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

DEFAULT_FALLBACK_MODELS = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-flash-latest"]
TRANSIENT_RETRIES = 2
RETRY_DELAYS = (0.8, 1.8)

class GeminiAPIError(RuntimeError):
    def __init__(self, status, message, code="api"):
        super().__init__(message)
        self.status = status
        self.code = code


def resolve_api_key(api_key=""):
    return (api_key or os.getenv("GEMINI_API_KEY", "")).strip()


def build_fallback_chain(primary):
    out = []
    for model in [primary, *DEFAULT_FALLBACK_MODELS]:
        if model and model not in out:
            out.append(model)
    return out


def classify_error(e):
    text = str(e).lower()
    status = getattr(e, "status", None)

    if status in (400, 401, 403) or any(x in text for x in (
        "api key", "api_key", "unauthenticated", "unauthorized", "permission denied", "invalid argument"
    )):
        if "invalid argument" in text and "key" not in text:
            return "request", "Gemini rejected the request. Check the selected model and try again."
        return "auth", "Gemini rejected the API key. Check Settings and make sure the key is valid."

    if status == 429 or any(x in text for x in ("quota", "resource_exhausted", "rate limit", "too many requests")):
        return "quota", "Gemini's quota or rate limit was reached. Try again in a moment."

    if status == 404 or ("model" in text and ("not found" in text or "unsupported" in text)):
        return "model", "The selected Gemini model is unavailable. Choose another model in Settings."

    if status in (408, 504) or "timed out" in text or "timeout" in text:
        return "timeout", "Gemini took too long to respond. Try again."

    if status in (500, 502, 503) or "overloaded" in text or "temporarily unavailable" in text:
        return "service", "Gemini is temporarily unavailable. ACUMEN is fine; try the request again shortly."

    return "unknown", f"Gemini request failed: {str(e)[:220]}"


def _extract_text(payload):
    candidates = payload.get("candidates") or []
    if not candidates:
        block = payload.get("promptFeedback") or payload.get("error")
        raise GeminiAPIError(502, f"Gemini returned no candidate content: {block}", "empty")
    parts = ((candidates[0].get("content") or {}).get("parts") or [])
    text = "".join(str(part.get("text", "")) for part in parts if isinstance(part, dict))
    if not text.strip():
        finish = candidates[0].get("finishReason", "unknown")
        raise GeminiAPIError(502, f"Gemini returned no text (finish reason: {finish})", "empty")
    return text


def _request(model, api_key, system_prompt, contents, temperature, timeout, json_mode=False):
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": contents,
    }
    generation = {}
    # Gemini 3.6+ deprecates temperature. Keep it for the 2.5 family only.
    if model.startswith("gemini-2.5") or model.startswith("gemini-flash"):
        generation["temperature"] = temperature
    if json_mode:
        generation["responseMimeType"] = "application/json"
    if generation:
        body["generationConfig"] = generation

    request = urllib.request.Request(
        endpoint,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return _extract_text(payload)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
            message = ((payload.get("error") or {}).get("message") or raw).strip()
        except Exception:
            message = raw.strip() or str(e)
        raise GeminiAPIError(e.code, message[:700], "http") from e
    except urllib.error.URLError as e:
        raise GeminiAPIError(503, f"Network error while contacting Gemini: {e.reason}", "network") from e
    except TimeoutError as e:
        raise GeminiAPIError(504, "Gemini request timed out", "timeout") from e


def invoke_llm_with_fallback(system_prompt, history, api_key, model="gemini-2.5-flash", temperature=.55, timeout=60, json_mode=False):
    api_key = resolve_api_key(api_key)
    if not api_key:
        raise GeminiAPIError(401, "Missing Gemini API key", "auth")

    contents = []
    for item in history or []:
        role = item.get("role", "user")
        role = "model" if role == "assistant" else "user"
        content = str(item.get("content", ""))
        if content.strip():
            contents.append({"role": role, "parts": [{"text": content}]})

    if not contents:
        contents = [{"role": "user", "parts": [{"text": "Please respond."}]}]

    last = None
    for candidate in build_fallback_chain(model):
        for attempt in range(TRANSIENT_RETRIES + 1):
            try:
                return _request(candidate, api_key, system_prompt, contents, temperature, timeout, json_mode)
            except GeminiAPIError as error:
                last = error
                # FIX: Never retry authentication, quota, or malformed-request errors.
                if error.status in (400, 401, 403, 429):
                    break
                # UPGRADE: Transient failures get a short backoff before ACUMEN
                # tries the next model. This makes intermittent 5xx/network failures
                # much less visible to the student.
                transient = error.status in (408, 500, 502, 503, 504) or error.code in ("network", "timeout")
                if transient and attempt < TRANSIENT_RETRIES:
                    time.sleep(RETRY_DELAYS[attempt])
                    continue
                # A missing model is worth trying against the fallback chain.
                break

    raise last or GeminiAPIError(503, "All Gemini model attempts failed", "service")


def generate_text(system_prompt, user_prompt, api_key, model="gemini-2.5-flash", temperature=.55, timeout=60, json_mode=False):
    return invoke_llm_with_fallback(
        system_prompt,
        [{"role": "user", "content": user_prompt}],
        api_key,
        model,
        temperature,
        timeout,
        json_mode,
    )
