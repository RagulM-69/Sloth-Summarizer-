/**
 * script.js — Sloth Summarizer frontend
 *
 * Responsibilities:
 *  - Tab switching (Text / PDF)
 *  - PDF drag-and-drop with validation
 *  - Live character counter with color states
 *  - Format + Length pill selectors
 *  - Summarize API call (JSON text & FormData PDF)
 *  - Loading message rotation
 *  - Output panel state management (placeholder / loading / error / result)
 *  - Copy, download, re-summarize actions
 */

/* ═══════════════════════════════════════════════════════════════
   DOM REFERENCES
═══════════════════════════════════════════════════════════════ */

// Tabs
const tabBtns = document.querySelectorAll('.tab-btn');
const tabPanels = document.querySelectorAll('.tab-panel');

// Text tab
const textInput = document.getElementById('text-input');
const charCounter = document.getElementById('char-counter');
const charHint = document.getElementById('char-hint');

// PDF tab
const dropZone = document.getElementById('drop-zone');
const dropZoneInner = document.getElementById('drop-zone-inner');
const dropZoneFile = document.getElementById('drop-zone-file');
const pdfInput = document.getElementById('pdf-input');
const fileName = document.getElementById('file-name');
const fileMeta = document.getElementById('file-meta');
const fileRemoveBtn = document.getElementById('file-remove-btn');
const pdfError = document.getElementById('pdf-error');

// Controls
const formatGroup = document.getElementById('format-group');
const lengthGroup = document.getElementById('length-group');
const summarizeBtn = document.getElementById('summarize-btn');

// Output states
const statePlaceholder = document.getElementById('state-placeholder');
const stateLoading = document.getElementById('state-loading');
const stateError = document.getElementById('state-error');
const stateResult = document.getElementById('state-result');

// Loading
const loadingMsg = document.getElementById('loading-msg');

// Error
const errorMsg = document.getElementById('error-msg');
const retryBtn = document.getElementById('retry-btn');

// Result
const statsText = document.getElementById('stats-text');
const statsTime = document.getElementById('stats-time');
const formatBadge = document.getElementById('format-badge');
const summaryContent = document.getElementById('summary-content');
const copyBtn = document.getElementById('copy-btn');
const resummarizeBtn = document.getElementById('resummarize-btn');
const downloadBtn = document.getElementById('download-btn');

/* ═══════════════════════════════════════════════════════════════
   STATE
═══════════════════════════════════════════════════════════════ */

let activeTab = 'text';          // 'text' | 'pdf'
let selectedFile = null;         // File object when PDF is selected
let loadingInterval = null;      // setInterval handle for loading messages
let lastSummaryText = '';        // For download + re-summarize

/* ═══════════════════════════════════════════════════════════════
   BUTTON LOADING HELPERS
═══════════════════════════════════════════════════════════════ */

function btnSetLoading() {
  summarizeBtn.disabled = true;
  summarizeBtn.setAttribute('data-original-text', summarizeBtn.textContent);
  summarizeBtn.innerHTML = '<span class="btn-spinner" aria-hidden="true"></span> Summarizing…';
  summarizeBtn.classList.add('is-loading');
}

function btnSetIdle() {
  summarizeBtn.disabled = false;
  const orig = summarizeBtn.getAttribute('data-original-text') || 'Summarize 🦥';
  summarizeBtn.textContent = orig;
  summarizeBtn.classList.remove('is-loading');
}

/* ═══════════════════════════════════════════════════════════════
   1. TAB SWITCHING
═══════════════════════════════════════════════════════════════ */

tabBtns.forEach(btn => {
  btn.addEventListener('click', () => {
    const tab = btn.dataset.tab;
    if (tab === activeTab) return;

    activeTab = tab;

    // Update buttons
    tabBtns.forEach(b => {
      b.classList.toggle('active', b.dataset.tab === tab);
      b.setAttribute('aria-selected', b.dataset.tab === tab ? 'true' : 'false');
    });

    // Update panels
    tabPanels.forEach(panel => {
      const isActive = panel.id === `tab-${tab}`;
      panel.classList.toggle('active', isActive);
      panel.hidden = !isActive;
    });
  });
});

/* ═══════════════════════════════════════════════════════════════
   2. CHARACTER COUNTER
═══════════════════════════════════════════════════════════════ */

textInput.addEventListener('input', updateCharCounter);

function updateCharCounter() {
  const len = textInput.value.length;
  charCounter.textContent = `${len.toLocaleString()} chars`;

  // Remove all state classes
  charCounter.classList.remove('warn', 'ok', 'chunked');

  if (len === 0) {
    charHint.textContent = 'At least 100 characters needed';
    charHint.style.color = '';
  } else if (len < 100) {
    charCounter.classList.add('warn');
    charHint.textContent = `⚠ Need ${100 - len} more characters`;
    charHint.style.color = 'var(--text-error)';
  } else if (len >= 5000) {
    charCounter.classList.add('chunked');
    charHint.textContent = '📦 Long text — will be chunked automatically';
    charHint.style.color = 'var(--amber)';
  } else {
    charCounter.classList.add('ok');
    charHint.textContent = '✓ Ready to summarize';
    charHint.style.color = 'var(--olive)';
  }
}

/* ═══════════════════════════════════════════════════════════════
   3. PDF DRAG-AND-DROP
═══════════════════════════════════════════════════════════════ */

const MAX_PDF_BYTES = 5 * 1024 * 1024; // 5 MB

// Click to browse
dropZone.addEventListener('click', (e) => {
  if (e.target === fileRemoveBtn) return; // handled separately
  pdfInput.click();
});

// Keyboard accessibility for drop zone
dropZone.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault();
    pdfInput.click();
  }
});

pdfInput.addEventListener('change', () => {
  if (pdfInput.files.length > 0) {
    handleFile(pdfInput.files[0]);
  }
});

// Drag events
dropZone.addEventListener('dragover', (e) => {
  e.preventDefault();
  dropZone.classList.add('drag-over');
});

dropZone.addEventListener('dragleave', (e) => {
  // Only remove class when leaving the drop zone itself (not a child)
  if (!dropZone.contains(e.relatedTarget)) {
    dropZone.classList.remove('drag-over');
  }
});

dropZone.addEventListener('drop', (e) => {
  e.preventDefault();
  dropZone.classList.remove('drag-over');
  const file = e.dataTransfer.files[0];
  if (file) handleFile(file);
});

/**
 * Validate and accept a dropped/selected PDF file.
 */
function handleFile(file) {
  hidePdfError();

  if (!file.name.toLowerCase().endsWith('.pdf') || file.type !== 'application/pdf') {
    showPdfError('🦥 Only PDF files are accepted. Please choose a .pdf file.');
    return;
  }

  if (file.size > MAX_PDF_BYTES) {
    showPdfError(`🦥 That file is ${(file.size / 1024 / 1024).toFixed(1)} MB — too big! Max is 5 MB.`);
    return;
  }

  selectedFile = file;

  // Estimate: ~250 words/page, ~3 MB/page for typical PDF density is unreliable,
  // so we estimate from file size as a rough proxy (~2 KB per page on average for text PDFs)
  const estimatedPages = Math.max(1, Math.round(file.size / 2048));
  const estimatedReadMin = Math.max(1, Math.round(estimatedPages * 0.5));

  fileName.textContent = file.name;
  fileMeta.textContent = `~${estimatedPages} page${estimatedPages !== 1 ? 's' : ''} · approx ${estimatedReadMin} min read`;

  // Switch drop zone to "file selected" view
  dropZoneInner.hidden = true;
  dropZoneFile.hidden = false;
}

// Remove file
fileRemoveBtn.addEventListener('click', (e) => {
  e.stopPropagation();
  clearFile();
});

function clearFile() {
  selectedFile = null;
  pdfInput.value = '';
  dropZoneInner.hidden = false;
  dropZoneFile.hidden = true;
  hidePdfError();
}

function showPdfError(msg) {
  pdfError.textContent = msg;
  pdfError.hidden = false;
}

function hidePdfError() {
  pdfError.textContent = '';
  pdfError.hidden = true;
}

/* ═══════════════════════════════════════════════════════════════
   4. PILL SELECTORS (format + length)
═══════════════════════════════════════════════════════════════ */

function makePillGroup(group) {
  group.addEventListener('click', (e) => {
    const pill = e.target.closest('.pill');
    if (!pill) return;

    group.querySelectorAll('.pill').forEach(p => {
      p.classList.remove('active');
      p.setAttribute('aria-pressed', 'false');
    });

    pill.classList.add('active');
    pill.setAttribute('aria-pressed', 'true');
  });
}

makePillGroup(formatGroup);
makePillGroup(lengthGroup);

function getSelectedPill(group) {
  const active = group.querySelector('.pill.active');
  return active ? active.dataset.value : null;
}

/* ═══════════════════════════════════════════════════════════════
   5. OUTPUT STATE MANAGEMENT
═══════════════════════════════════════════════════════════════ */

function showState(name) {
  // name: 'placeholder' | 'loading' | 'error' | 'result'
  [statePlaceholder, stateLoading, stateError, stateResult].forEach(el => {
    el.hidden = true;
  });
  const el = document.getElementById(`state-${name}`);
  if (el) el.hidden = false;

  // Toggle amber pulsing border + progress bar on the output panel
  const outputPanel = document.querySelector('.panel-output');
  if (name === 'loading') {
    outputPanel.classList.add('is-loading');
  } else {
    outputPanel.classList.remove('is-loading');
  }

  // Show/hide the status-strip below the Summarize button
  const statusStrip = document.getElementById('status-strip');
  const statusText = document.getElementById('status-text');
  if (name === 'loading') {
    statusText.textContent = '🦥 Sending to AI — this may take 5–30 seconds…';
    statusStrip.hidden = false;
  } else {
    statusStrip.hidden = true;
  }
}

/* ═══════════════════════════════════════════════════════════════
   6. LOADING MESSAGE ROTATION
═══════════════════════════════════════════════════════════════ */

const LOADING_MESSAGES = [
  '🦥 Reading very slowly...',
  '🦥 Chewing through your content...',
  '🦥 Almost there, sloths don\'t rush...',
  '🦥 Digesting the important bits...',
  '🦥 Finding the essence, one claw at a time...',
  '🦥 Carefully weighing every sentence...',
];

function startLoadingMessages() {
  let index = 0;
  loadingMsg.textContent = LOADING_MESSAGES[0];

  loadingInterval = setInterval(() => {
    index = (index + 1) % LOADING_MESSAGES.length;
    loadingMsg.textContent = LOADING_MESSAGES[index];
  }, 3000);
}

function stopLoadingMessages() {
  if (loadingInterval !== null) {
    clearInterval(loadingInterval);
    loadingInterval = null;
  }
}

/* ═══════════════════════════════════════════════════════════════
   7. SUMMARIZE — API CALL + ORCHESTRATION
═══════════════════════════════════════════════════════════════ */

summarizeBtn.addEventListener('click', runSummarize);
retryBtn.addEventListener('click', runSummarize);

async function runSummarize() {
  const format = getSelectedPill(formatGroup) || 'paragraph';
  const length = getSelectedPill(lengthGroup) || 'medium';

  // ── Validate input before hitting the API ──────────────────────────────────
  if (activeTab === 'text') {
    const text = textInput.value.trim();
    if (text.length < 100) {
      showError('🦥 Please paste at least 100 characters for the sloth to summarize!');
      return;
    }
  } else {
    if (!selectedFile) {
      showError('🦥 Please select a PDF file first!');
      return;
    }
  }

  // ── Enter loading state ────────────────────────────────────────────────────
  btnSetLoading();
  showState('loading');
  startLoadingMessages();

  try {
    let result;

    if (activeTab === 'text') {
      // JSON text request
      result = await summarizeText(
        textInput.value.trim(),
        format,
        length
      );
    } else {
      // Multipart form PDF request
      result = await summarizePdf(selectedFile, format, length);
    }

    stopLoadingMessages();
    displayResult(result, format);

  } catch (err) {
    stopLoadingMessages();
    showError(err.message || '🦥 Something went wrong. Please try again!');
  } finally {
    btnSetIdle();
  }
}

/**
 * POST text as JSON to /summarize.
 */
async function summarizeText(text, format, length) {
  const response = await fetch('/summarize', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, format, length }),
  });

  return parseApiResponse(response);
}

/**
 * POST PDF as FormData to /summarize.
 */
async function summarizePdf(file, format, length) {
  const formData = new FormData();
  formData.append('pdf', file);
  formData.append('format', format);
  formData.append('length', length);

  const response = await fetch('/summarize', {
    method: 'POST',
    body: formData,
  });

  return parseApiResponse(response);
}

/**
 * Parse the API response, throwing a descriptive error on failure.
 */
async function parseApiResponse(response) {
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error('🦥 The server returned an unexpected response. Please try again.');
  }

  if (!response.ok) {
    // Use the server's error message if available
    throw new Error(data.error || `🦥 Server error (${response.status}). Try again!`);
  }

  return data;
}

/* ═══════════════════════════════════════════════════════════════
   8. DISPLAY RESULT
═══════════════════════════════════════════════════════════════ */

function displayResult(data, format) {
  const { summary, word_count, char_count, original_word_count, time_taken } = data;

  // Cache for download + re-summarize
  lastSummaryText = summary;

  // Stats bar
  const reduction =
    original_word_count > 0
      ? Math.round((1 - word_count / original_word_count) * 100)
      : 0;

  statsText.textContent =
    `Original: ${original_word_count.toLocaleString()} words → Summary: ${word_count.toLocaleString()} words (${reduction}% shorter)`;
  statsTime.textContent = `Summarized in ${time_taken}s`;

  // Format badge
  formatBadge.textContent = format;

  // Summary content — set text and re-trigger animation
  summaryContent.textContent = summary;
  summaryContent.style.animation = 'none';
  // Force reflow to restart animation
  void summaryContent.offsetWidth;
  summaryContent.style.animation = '';

  showState('result');
}

function showError(msg) {
  errorMsg.textContent = msg;
  showState('error');
}

/* ═══════════════════════════════════════════════════════════════
   9. COPY BUTTON
═══════════════════════════════════════════════════════════════ */

copyBtn.addEventListener('click', async () => {
  if (!lastSummaryText) return;

  try {
    await navigator.clipboard.writeText(lastSummaryText);
    copyBtn.textContent = '✅ Copied!';
    copyBtn.classList.add('success');

    setTimeout(() => {
      copyBtn.textContent = '📋 Copy Summary';
      copyBtn.classList.remove('success');
    }, 2000);
  } catch {
    // Fallback for browsers without clipboard API
    const el = document.createElement('textarea');
    el.value = lastSummaryText;
    el.style.position = 'fixed';
    el.style.opacity = '0';
    document.body.appendChild(el);
    el.select();
    document.execCommand('copy');
    document.body.removeChild(el);

    copyBtn.textContent = '✅ Copied!';
    copyBtn.classList.add('success');
    setTimeout(() => {
      copyBtn.textContent = '📋 Copy Summary';
      copyBtn.classList.remove('success');
    }, 2000);
  }
});

/* ═══════════════════════════════════════════════════════════════
   10. DOWNLOAD BUTTON
═══════════════════════════════════════════════════════════════ */

downloadBtn.addEventListener('click', () => {
  if (!lastSummaryText) return;

  const blob = new Blob([lastSummaryText], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'sloth-summary.txt';
  link.style.display = 'none';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);

  // Clean up the object URL after a short delay
  setTimeout(() => URL.revokeObjectURL(url), 5000);
});

/* ═══════════════════════════════════════════════════════════════
   11. RE-SUMMARIZE
═══════════════════════════════════════════════════════════════ */

resummarizeBtn.addEventListener('click', () => {
  // Go back to placeholder then immediately trigger a new summarize
  showState('placeholder');
  lastSummaryText = '';
  // Small delay so the user sees the transition before loading starts
  setTimeout(runSummarize, 120);
});

/* ═══════════════════════════════════════════════════════════════
   INIT
═══════════════════════════════════════════════════════════════ */

// Show placeholder on startup
showState('placeholder');

// Initialise character counter display
updateCharCounter();
