"""Read-only File Search helper for the AI Studio agent environment.

In Playground, the network proxy supplies the linked Gemini API key.
For a local diagnostic, GEMINI_API_KEY may instead be supplied as an environment variable.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request

STORE = "fileSearchStores/helpcenter8bee671fe5df46f19-eygp8bxkqfhi"
MODEL = "gemini-3.8-flash"
SYSTEM = (
    "You are OptiBot, the customer-support bot for OptiSigns.com.\n"
    "\u2022 Tone: helpful, factual, concise.\n"
    "\u2022 Only answer using the uploaded docs.\n"
    "\u2022 Max 5 bullet points; else link to the doc.\n"
    '\u2022 Cite up to 3 "Article URL:" lines per reply.'
)

def main():
    question = " ".join(sys.argv[1:]).strip()
    if not question or len(question) > 12000:
        print(json.dumps({"error": "Provide a question of 1 to 12000 characters."}))
        return 1
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": question}]}],
        "tools": [{"fileSearch": {"fileSearchStoreNames": [STORE]}}],
    }
    headers = {"Content-Type": "application/json"}
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if key:
        headers["x-goog-api-key"] = key
    request = urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + MODEL + ":generateContent",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        # Do not print request headers, response bodies, or credentials.
        print(json.dumps({"error": "Gemini HTTP " + str(exc.code),
                          "hint": "Check linked key, network authentication, store access and quota. A 503 may be temporary."}))
        return 1
    except Exception:
        print(json.dumps({"error": "Gemini request failed; check the environment network settings."}))
        return 1

    candidates = result.get("candidates") or []
    candidate = candidates[0] if candidates else {}
    answer = "\n".join(
        part["text"] for part in candidate.get("content", {}).get("parts", [])
        if part.get("text") and not part.get("thought")
    )
    grounding = candidate.get("groundingMetadata") or {}
    chunks = grounding.get("groundingChunks") or []
    sources = []
    for chunk in chunks:
        context = chunk.get("retrievedContext") or {}
        if not context:
            continue
        actual_store = context.get("fileSearchStore")
        if actual_store and actual_store != STORE:
            continue
        urls = set()
        for item in context.get("customMetadata") or []:
            if item.get("key") == "article_url" and item.get("stringValue"):
                urls.add(item["stringValue"])
        urls.update(re.findall(r'Article URL:\s*(https://[^\s<>"]+)', context.get("text", "")))
        for url in sorted(urls):
            if url.startswith("https://support.optisigns.com/hc/"):
                source = {"title": context.get("title", ""), "url": url}
                if source not in sources:
                    sources.append(source)

    verified = bool(answer and chunks and sources and grounding.get("groundingSupports"))
    output = {
        "store_name": STORE,
        "model": MODEL,
        "question": question,
        "grounded": verified,
        "answer": answer if verified else None,
        "sources": sources,
        "retrieved_chunk_count": len(chunks),
    }
    if not verified:
        output["error"] = "No verifiable grounded answer. Do not answer from memory or fabricate citations."
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if verified else 2

if __name__ == "__main__":
    raise SystemExit(main())
