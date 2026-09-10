const MAX_AUDIO_BYTES = 20 * 1024 * 1024;

const state = { audio: null, json: null, result: null };
const $ = (id) => document.getElementById(id);

const refs = {
  audioInput: $("audioInput"), jsonInput: $("jsonInput"),
  audioDropzone: $("audioDropzone"), jsonDropzone: $("jsonDropzone"),
  audioSelected: $("audioSelected"), jsonSelected: $("jsonSelected"),
  audioFileName: $("audioFileName"), audioFileSize: $("audioFileSize"),
  jsonFileName: $("jsonFileName"), jsonFileInfo: $("jsonFileInfo"),
  removeAudio: $("removeAudio"), removeJson: $("removeJson"),
  analyzeButton: $("analyzeButton"), readyDot: $("readyDot"),
  readyTitle: $("readyTitle"), readySubtitle: $("readySubtitle"),
  uploadSection: $("uploadSection"), heroSection: $("heroSection"),
  processingSection: $("processingSection"), processingMessage: $("processingMessage"),
  progressBar: $("progressBar"), resultsSection: $("resultsSection"),
  errorPanel: $("errorPanel"), errorMessage: $("errorMessage"), dismissError: $("dismissError"),
  newComparisonButton: $("newComparisonButton")
};

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function showError(message) {
  refs.errorMessage.textContent = message;
  refs.errorPanel.classList.remove("hidden");
}

function hideError() { refs.errorPanel.classList.add("hidden"); }
refs.dismissError.addEventListener("click", hideError);

async function validateJson(file) {
  try {
    const content = await file.text();
    const parsed = JSON.parse(content);
    let count = 0;
    if (Array.isArray(parsed)) count = parsed.length;
    else if (Array.isArray(parsed.segments)) count = parsed.segments.length;
    else if (Array.isArray(parsed.entries)) count = parsed.entries.length;
    else if (parsed.diarized_transcript?.entries) count = parsed.diarized_transcript.entries.length;
    else if (typeof parsed.transcript === "string") count = 1;
    return { valid: true, count };
  } catch {
    return { valid: false, count: 0 };
  }
}

async function setAudio(file) {
  hideError();
  if (!file) return;
  const ext = `.${file.name.split(".").pop()?.toLowerCase()}`;
  if (![".wav", ".mp3"].includes(ext)) return showError("Please choose a WAV or MP3 audio file.");
  if (file.size > MAX_AUDIO_BYTES) return showError("The audio file is larger than 20 MB.");
  if (file.size === 0) return showError("The audio file is empty.");
  state.audio = file;
  refs.audioFileName.textContent = file.name;
  refs.audioFileSize.textContent = formatBytes(file.size);
  refs.audioSelected.classList.remove("hidden");
  updateReadyState();
}

async function setJson(file) {
  hideError();
  if (!file) return;
  if (!file.name.toLowerCase().endsWith(".json")) return showError("Please choose a JSON transcript file.");
  const validation = await validateJson(file);
  if (!validation.valid) return showError("That file is not valid JSON.");
  state.json = file;
  refs.jsonFileName.textContent = file.name;
  refs.jsonFileInfo.textContent = validation.count ? `${validation.count} transcript segment${validation.count === 1 ? "" : "s"}` : "JSON ready";
  refs.jsonSelected.classList.remove("hidden");
  updateReadyState();
}

function updateReadyState() {
  const ready = Boolean(state.audio && state.json);
  refs.analyzeButton.disabled = !ready;
  refs.readyDot.classList.toggle("active", ready);
  refs.readyTitle.textContent = ready ? "Ready to compare" : "Add both files to continue";
  refs.readySubtitle.textContent = ready ? "Both files look good. Start the analysis when ready." : "Nothing is sent until you click Analyze match.";
}

function connectDropzone(dropzone, input, setter) {
  dropzone.addEventListener("click", (event) => {
    if (event.target.closest(".remove-file")) return;
    input.click();
  });
  dropzone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") input.click();
  });
  input.addEventListener("change", () => setter(input.files?.[0]));
  ["dragenter", "dragover"].forEach((name) => dropzone.addEventListener(name, (event) => {
    event.preventDefault(); dropzone.classList.add("dragging");
  }));
  ["dragleave", "drop"].forEach((name) => dropzone.addEventListener(name, (event) => {
    event.preventDefault(); dropzone.classList.remove("dragging");
  }));
  dropzone.addEventListener("drop", (event) => setter(event.dataTransfer.files?.[0]));
}

connectDropzone(refs.audioDropzone, refs.audioInput, setAudio);
connectDropzone(refs.jsonDropzone, refs.jsonInput, setJson);

refs.removeAudio.addEventListener("click", (event) => {
  event.stopPropagation(); state.audio = null; refs.audioInput.value = ""; refs.audioSelected.classList.add("hidden"); updateReadyState();
});
refs.removeJson.addEventListener("click", (event) => {
  event.stopPropagation(); state.json = null; refs.jsonInput.value = ""; refs.jsonSelected.classList.add("hidden"); updateReadyState();
});

let progressTimer;
function startProgress() {
  let progress = 7;
  const messages = [
    [13, "Uploading and preparing the recording…"],
    [30, "Transcribing the audio…"],
    [60, "Still transcribing — longer audio needs more time…"],
    [82, "Comparing words and transcript segments…"],
    [94, "Building your match report…"]
  ];
  refs.progressBar.style.width = `${progress}%`;
  progressTimer = setInterval(() => {
    progress = Math.min(94, progress + Math.max(1, Math.round((96 - progress) / 12)));
    refs.progressBar.style.width = `${progress}%`;
    const current = [...messages].reverse().find(([threshold]) => progress >= threshold);
    if (current) refs.processingMessage.textContent = current[1];
  }, 1300);
}

function stopProgress() {
  clearInterval(progressTimer);
  refs.progressBar.style.width = "100%";
}

refs.analyzeButton.addEventListener("click", async () => {
  if (!state.audio || !state.json) return;
  hideError();
  refs.heroSection.classList.add("hidden");
  refs.uploadSection.classList.add("hidden");
  refs.resultsSection.classList.add("hidden");
  refs.processingSection.classList.remove("hidden");
  startProgress();

  const formData = new FormData();
  formData.append("audio", state.audio);
  formData.append("transcript", state.json);

  try {
    const response = await fetch("/api/compare", { method: "POST", body: formData });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || "The comparison request failed.");
    state.result = data;
    stopProgress();
    await new Promise((resolve) => setTimeout(resolve, 300));
    refs.processingSection.classList.add("hidden");
    renderResult(data);
    refs.resultsSection.classList.remove("hidden");
    window.scrollTo({ top: 0, behavior: "smooth" });
  } catch (error) {
    stopProgress();
    refs.processingSection.classList.add("hidden");
    refs.heroSection.classList.remove("hidden");
    refs.uploadSection.classList.remove("hidden");
    showError(error.message || "Something went wrong.");
  }
});

function qualityFor(score) {
  if (score >= 90) return { label: "Excellent", cls: "good", title: "Very strong match", text: "The generated transcript is highly consistent with the reference text." };
  if (score >= 75) return { label: "Good", cls: "good", title: "Good match", text: "Most of the wording matches, with a few differences worth reviewing." };
  if (score >= 55) return { label: "Fair", cls: "medium", title: "Partial match", text: "There are noticeable differences between the audio transcription and the reference." };
  return { label: "Low", cls: "low", title: "Low match", text: "The two transcripts differ significantly. Check the audio, reference JSON, or language/script style." };
}

function badgeClass(score) {
  if (score >= 75) return "good";
  if (score >= 50) return "medium";
  return "low";
}

function safeText(value) { return value == null || value === "" ? "—" : String(value); }
function timeLabel(start, end) {
  if (start == null && end == null) return "Segment";
  const format = (value) => value == null ? "?" : `${Number(value).toFixed(1)}s`;
  return `${format(start)} – ${format(end)}`;
}

function renderResult(data) {
  const m = data.metrics;
  const quality = qualityFor(m.matchScore);
  $("matchScore").textContent = `${Math.round(m.matchScore)}%`;
  $("scoreRing").style.setProperty("--score", `${Math.max(0, Math.min(100, m.matchScore)) * 3.6}deg`);
  $("qualityPill").className = `quality-pill ${quality.cls}`;
  $("qualityPill").textContent = quality.label;
  $("qualityTitle").textContent = quality.title;
  $("qualityDescription").textContent = quality.text;
  $("wordAccuracy").textContent = `${m.wordAccuracy.toFixed(1)}%`;
  $("charSimilarity").textContent = `${m.characterSimilarity.toFixed(1)}%`;
  $("wer").textContent = `${m.wer.toFixed(1)}%`;
  $("referenceWords").textContent = m.referenceWords.toLocaleString();
  $("modelWords").textContent = `${m.modelWords.toLocaleString()} model words`;
  $("referenceCount").textContent = `${m.referenceWords} words`;
  $("generatedCount").textContent = `${m.modelWords} words`;
  $("referenceTranscript").textContent = data.referenceTranscript;
  $("modelTranscript").textContent = data.modelTranscript;
  $("resultFileLine").textContent = `${data.files.audio}  ·  ${formatBytes(data.files.audioSizeBytes)}`;
  $("languageBadge").textContent = `Language: ${safeText(data.languageCode || "auto detected")}`;

  const list = $("segmentsList");
  list.replaceChildren();
  if (!data.segments?.length) {
    const empty = document.createElement("div");
    empty.className = "empty-segments";
    empty.textContent = "No segment-level rows were available, but the overall transcript comparison is complete.";
    list.appendChild(empty);
    return;
  }

  data.segments.forEach((segment) => {
    const row = document.createElement("div");
    row.className = "segment-row";

    const meta = document.createElement("div");
    meta.className = "segment-meta";
    const speaker = document.createElement("strong");
    speaker.textContent = segment.speaker || `#${segment.index}`;
    const timing = document.createElement("span");
    timing.textContent = timeLabel(segment.start, segment.end);
    meta.append(speaker, timing);

    const copy = document.createElement("div");
    copy.className = "segment-copy";
    copy.append(makeSegmentLine("Reference", segment.reference), makeSegmentLine("Generated", segment.model || "No overlapping text found"));

    const score = document.createElement("div");
    score.className = `segment-score ${badgeClass(segment.score)}`;
    score.textContent = `${Math.round(segment.score)}%`;

    row.append(meta, copy, score);
    list.appendChild(row);
  });
}

function makeSegmentLine(label, text) {
  const line = document.createElement("div");
  line.className = "segment-line";
  const labelEl = document.createElement("span");
  labelEl.textContent = label;
  const textEl = document.createElement("p");
  textEl.textContent = text;
  line.append(labelEl, textEl);
  return line;
}

refs.newComparisonButton.addEventListener("click", () => {
  state.result = null;
  refs.resultsSection.classList.add("hidden");
  refs.heroSection.classList.remove("hidden");
  refs.uploadSection.classList.remove("hidden");
  refs.progressBar.style.width = "7%";
  window.scrollTo({ top: 0, behavior: "smooth" });
});
