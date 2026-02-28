"""
summarizer.py — Core summarization logic for Sloth Summarizer.

Handles:
  - PDF text extraction via pdfplumber
  - Sentence-aware text chunking with overlap
  - HuggingFace Inference API calls with wait_for_model + retry logic
  - Parallel chunk summarization via ThreadPoolExecutor
  - Summary formatting (paragraph, bullets, numbered, tldr)
  - Full orchestration pipeline with lru_cache for instant repeats
"""

import re
import time
import requests # type: ignore
import functools
from concurrent.futures import ThreadPoolExecutor, as_completed

# ─── Language / locale config ─────────────────────────────────────────────────
LANGUAGE = "en"

# ─── HuggingFace model chain ──────────────────────────────────────────────────
HF_API_BASE = "https://router.huggingface.co/hf-inference/models"

# We use distilbart permanently. It's ~2x faster than facebook/bart-large-cnn
# and usually returns results in < 4 seconds.
PRIMARY_MODEL = "sshleifer/distilbart-cnn-12-6"

# ─── Length parameter maps ────────────────────────────────────────────────────
LENGTH_PARAMS = {
    "short":  {"min_length": 30,  "max_length": 80},
    "medium": {"min_length": 60,  "max_length": 150},
    "long":   {"min_length": 80,  "max_length": 250},
}

# ─── Request config ───────────────────────────────────────────────────────────
REQUEST_TIMEOUT = 55          # seconds per API call (HF cold-start can take ~20s)
MAX_RETRIES     = 2           # per model
RETRY_DELAY     = 1.5         # seconds between retries (short — we use wait_for_model)
MAX_WORKERS     = 4           # parallel threads for multi-chunk summarization


# ─── 1. PDF text extraction ───────────────────────────────────────────────────

def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract plain text from PDF bytes using pdfplumber."""
    import io
    import pdfplumber # type: ignore

    if not file_bytes:
        raise ValueError("🦥 Oops! That file appears to be empty. Try another one?")

    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            if len(pdf.pages) == 0:
                raise ValueError("🦥 That PDF has no pages. Are you sure it's a real PDF?")

            pages_text = []
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    pages_text.append(page_text)

            if not pages_text:
                raise ValueError(
                    "🦥 Oops! That PDF seems to be empty or image-only. "
                    "The sloth can only read text-based PDFs, not scanned images."
                )

            raw = "\n".join(pages_text)
    except ValueError:
        raise  # re-raise our own ValueErrors
    except Exception as exc:
        raise ValueError(f"🦥 Couldn't read that PDF — it may be corrupted or password-protected. ({exc})")

    # Normalize whitespace
    text = re.sub(r"[ \t]+", " ", raw)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" +\n", "\n", text)
    return text.strip()


# ─── 2. Sentence-aware chunking ───────────────────────────────────────────────

def _split_sentences(text: str) -> list[str]:
    """Split text into sentences using a simple regex approach."""
    raw_sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z\"'])", text)
    sentences = []
    for sentence in raw_sentences:
        if len(sentence) > 800:
            sub = [s.strip() for s in sentence.split("\n") if s.strip()]
            sentences.extend(sub)
        else:
            stripped = sentence.strip()
            if stripped:
                sentences.append(stripped)
    return sentences


def chunk_text(text: str, max_tokens: int = 950) -> list[str]:
    """
    Split text into chunks that fit within the model's token limit.

    Tokens maxed to 950 so that almost all documents fit in ONE chunk,
    meaning ONE network request and NO secondary merge pass. Speeds up
    the pipeline massively vs splitting early at 600.
    """
    max_chars = max_tokens * 4  # ~4 chars per token

    sentences = _split_sentences(text)
    if not sentences:
        return [text]

    chunks: list[str] = []
    current_sentences: list[str] = []
    current_len = 0

    for sentence in sentences:
        sentence_len = len(sentence) + 1

        if current_len + sentence_len > max_chars and current_sentences:
            chunks.append(" ".join(current_sentences))
            overlap_sentence = current_sentences[-1]
            current_sentences = [overlap_sentence, sentence]
            current_len = len(overlap_sentence) + sentence_len
        else:
            current_sentences.append(sentence) # type: ignore
            current_len += sentence_len

    if current_sentences:
        chunks.append(" ".join(current_sentences))

    return chunks


# ─── 3. Single-chunk summarization via HuggingFace REST API ──────────────────

def _call_hf_api(chunk: str, length_params: dict, api_key: str, model: str) -> str:
    url = f"{HF_API_BASE}/{model}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "inputs": chunk,
        "parameters": {
            "min_length": length_params["min_length"],
            "max_length": length_params["max_length"],
            "do_sample":  False,
            "truncation": True,
        },
        "options": {
            "wait_for_model": True,   # Queue request serverside instead of returning 503
            "use_cache":       True,
        },
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)

    if resp.status_code == 200:
        data = resp.json()
        if isinstance(data, list) and data and "summary_text" in data[0]:
            return data[0]["summary_text"].strip()
        raise ValueError(f"Unexpected API response format: {data}")

    if resp.status_code == 401:
        raise ValueError("🦥 Invalid HuggingFace API key. Check your .env setup.")
    if resp.status_code == 429:
        raise ValueError("🦥 Moving too fast! HuggingFace rate limit reached.")
    if resp.status_code == 400:
        raise ValueError("🦥 The text is too short or unsupported. Add more content!")

    resp.raise_for_status()
    raise ValueError(f"Unexpected HTTP {resp.status_code} from HuggingFace.")


def summarize_chunk(chunk: str, length: str, hf_api_key: str) -> str:
    """Strategy: try PRIMARY_MODEL twice."""
    length_params = LENGTH_PARAMS.get(length, LENGTH_PARAMS["medium"])
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return _call_hf_api(chunk, length_params, hf_api_key, PRIMARY_MODEL)

        except ValueError as exc:
            last_error = exc
            msg = str(exc)
            if any(kw in msg for kw in ["rate limit", "API key", "too short"]):
                raise
            if attempt == MAX_RETRIES:
                break
            time.sleep(RETRY_DELAY)

        except requests.exceptions.Timeout as exc:
            last_error = exc
            if attempt == MAX_RETRIES:
                break
            time.sleep(RETRY_DELAY)

        except requests.exceptions.HTTPError as exc:
            last_error = exc
            status = exc.response.status_code if exc.response is not None else 0
            if status in (401, 429, 400):
                raise ValueError(str(exc))
            if attempt == MAX_RETRIES:
                break
            time.sleep(RETRY_DELAY)

        except Exception as exc:
            last_error = exc
            if attempt == MAX_RETRIES:
                break
            time.sleep(RETRY_DELAY)

    raise ValueError(
        f"🦥 Hmm, the summarization service seems to be having a nap. "
        f"Please try again in a minute! (Status: {last_error})"
    )


# ─── 4. Summary formatting ────────────────────────────────────────────────────

def format_summary(raw_summary: str, format_type: str) -> str:
    text = re.sub(r"\s+", " ", raw_summary).strip()

    if format_type == "paragraph":
        return text

    elif format_type in ("bullets", "numbered"):
        sentences = _split_sentences(text)
        if len(sentences) < 3:
            extra = re.split(r"[;,]", text)
            extra = [s.strip() for s in extra if len(s.strip()) > 20]
            if len(extra) >= len(sentences):
                sentences = extra

        seen = set()
        unique_sentences = []
        for s in sentences:
            key = s.lower().strip()
            if key not in seen:
                seen.add(key)
                unique_sentences.append(s)
        sentences = unique_sentences

        if format_type == "bullets":
            lines = [f"• {s.rstrip('.')}." if not s.endswith(".") else f"• {s}" for s in sentences]
            return "\n".join(lines)
        else:
            lines = [
                f"{i}. {s.rstrip('.')}." if not s.endswith(".") else f"{i}. {s}"
                for i, s in enumerate(sentences, start=1)
            ]
            return "\n".join(lines)

    elif format_type == "tldr":
        sentences = _split_sentences(text)
        short_text = " ".join(sentences[0:2]) # type: ignore
        return f"TL;DR — {short_text}"

    else:
        return text


# ─── 5. Main orchestration pipeline ──────────────────────────────────────────

# Cache up to 32 recent summaries in memory.
# Hash based on text + format + length. hf_api_key is ignored in the hash since
# it doesn't change the output, but it must be passed positionally.
@functools.lru_cache(maxsize=32)
def _summarize_cached(text: str, format_type: str, length: str, hf_api_key: str) -> str:
    """Internal cached logic that returns just the raw summary text string."""
    chunks = chunk_text(text)
    partial_summaries: list[str] = [""] * len(chunks)

    if len(chunks) == 1:
        partial_summaries[0] = summarize_chunk(chunks[0], length, hf_api_key)
    else:
        with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(chunks))) as executor:
            import typing
            from concurrent.futures import Future
            future_to_idx: typing.Dict[Future[str], int] = {
                executor.submit(summarize_chunk, chunk, length, hf_api_key): idx # type: ignore
                for idx, chunk in enumerate(chunks)
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                partial_summaries[idx] = future.result()

    if len(partial_summaries) > 1:
        merged = " ".join(partial_summaries)
        final_length = length if length == "long" else "medium"
        raw_summary = summarize_chunk(merged, final_length, hf_api_key)
    else:
        raw_summary = partial_summaries[0]
        
    return raw_summary


def summarize(text: str, format_type: str, length: str, hf_api_key: str) -> dict:
    """
    Wrapper around the cached logic that computes dynamic timings and stats.
    """
    start_time = time.time()
    original_word_count = len(text.split())

    # Get the raw string (instantly if cached, otherwise does the network work)
    raw_summary = _summarize_cached(text, format_type, length, hf_api_key)

    # Format
    formatted = format_summary(raw_summary, format_type)

    elapsed = float(round(time.time() - start_time, 2)) # type: ignore

    return {
        "summary":              formatted,
        "word_count":           len(formatted.split()),
        "char_count":           len(formatted),
        "original_word_count":  original_word_count,
        "time_taken":           elapsed,
    }

