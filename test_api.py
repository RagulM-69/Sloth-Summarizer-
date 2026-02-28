import requests, os, sys # type: ignore
from dotenv import load_dotenv # type: ignore

load_dotenv()
key = os.environ.get("HF_API_KEY", "").strip()
print(f"Key: {key[:15]}... length={len(key)}") # type: ignore

url = "https://api-inference.huggingface.co/models/facebook/bart-large-cnn"
headers = {"Authorization": f"Bearer {key}"}
payload = {
    "inputs": (
        "Artificial intelligence is transforming every industry. "
        "Machine learning powers recommendation systems, diagnostics, and fraud detection. "
        "Large language models generate text and code. Despite advances, AI faces challenges "
        "including bias, opacity, and high compute needs. Researchers are working on making "
        "AI more transparent and equitable for all users worldwide."
    ),
    "parameters": {"min_length": 30, "max_length": 80},
    "options": {"wait_for_model": True},
}

print("Calling HuggingFace API...")
try:
    resp = requests.post(url, headers=headers, json=payload, timeout=90)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text[:600]}")
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
