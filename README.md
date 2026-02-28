# 🦥 Sloth Summarizer

A fast, fully-featured AI summarization web application. Upload a PDF or paste text, and receive an instant, smart summary using HuggingFace's DistilBART model. 

![Sloth Summarizer](https://raw.githubusercontent.com/RagulM-69/Sloth-Summarizer-/main/static/favicon.png)

## 🌐 Live Demo

You can try out the live version of the application here once it is deployed:

👉 **[Paste Your Render URL Here]** 👈

---

## ✨ Features

- **Blazing Fast**: Uses `sshleifer/distilbart-cnn-12-6` to summarize large texts in under 5 seconds.
- **Smart Chunking**: Automatically splits large 50+ page PDFs into context-aware chunks, processes them in parallel, and stitches them back together seamlessly.
- **Multiple Formats**: Output as a Paragraph, Bullet Points, Numbered List, or a quick TL;DR.
- **Adjustable Length**: Choose between Short, Medium, or Long summaries.
- **Instant Re-Summarization**: Utilizes in-memory caching to instantly return results for recently summarized documents.
- **Universal Input**: Support for both raw text pasting and `.pdf` file uploads (via `pdfplumber`).

## 🛠️ Built With

* **Backend**: Python 3, Flask, Gunicorn
* **Frontend**: HTML5, CSS3, Vanilla JavaScript (Fetch API)
* **AI / ML Model**: [HuggingFace Inference API](https://huggingface.co/inference-api) (DistilBART)
* **Text Extraction**: `pdfplumber`

## 🚀 Local Development

1. **Clone the repository:**
   ```bash
   git clone https://github.com/RagulM-69/Sloth-Summarizer-.git
   cd Sloth-Summarizer-
   ```

2. **Set up a virtual environment (optional but recommended):**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Add your API Key:**
   Create a `.env` file in the root directory and add your HuggingFace API key:
   ```env
   HF_API_KEY=hf_your_api_key_here
   ```

5. **Run the local server:**
   ```bash
   python app.py
   ```
   *The app will be available at `http://localhost:5000`*

## 📦 Deployment (Render)

This project is configured out-of-the-box for [Render.com](https://render.com).
1. Connect this repository to a new Render "Web Service".
2. Render will automatically detect the settings in the included `render.yaml`.
3. Add the `HF_API_KEY` as an Environment Variable in your Render dashboard.
4. Deploy!
