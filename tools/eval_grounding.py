"""Grounding eval: hit the live server and measure citation coverage.
API-gated (real /ask calls) — run manually, not in CI. Usage:
    ENABLE_RERANK=1 GROUNDING_MODE=enforce python tools/eval_grounding.py
"""
import json, os, sys, urllib.request

PORT = os.environ.get("GURUDEV_BACKEND_PORT", "8765")
QUESTIONS = [
    ("What are Gurudev's views on Bhakti?", "mr"),
    ("गुरुदेव भक्तीविषयी काय सांगतात?", "mr"),
    ("What are the stages of sadhana in Gurudev's teaching?", "en"),
    ("आत्मज्ञानाविषयी गुरुदेव रानडे यांचे विचार काय आहेत?", "mr"),
]

def ask(q, lang):
    body = json.dumps({"mode": "qa", "question": q, "lang": lang}).encode()
    req = urllib.request.Request(f"http://localhost:{PORT}/ask", data=body,
                                 headers={"Content-Type": "application/json",
                                          "Accept": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=120))

def main():
    grounded = 0
    for q, lang in QUESTIONS:
        r = ask(q, lang)
        n = len(r.get("citations") or [])
        grounded += 1 if n >= 1 else 0
        print(f"[{'OK ' if n else 'BARE'}] cites={n:2d}  {q[:50]}")
    print(f"\nGrounded: {grounded}/{len(QUESTIONS)} doctrinal answers have >=1 citation")

if __name__ == "__main__":
    main()
