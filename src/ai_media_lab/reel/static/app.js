const health = document.querySelector("#health");
const form = document.querySelector("#uploadForm");
const fileInput = document.querySelector("#file");
const fileLabel = document.querySelector("#fileLabel");
const fileMeta = document.querySelector("#fileMeta");
const dropZone = document.querySelector("#dropZone");
const submitBtn = document.querySelector("#submitBtn");
const timeline = document.querySelector("#timeline");
const analysisStatus = document.querySelector("#analysisStatus");
const formError = document.querySelector("#formError");
const resultPanel = document.querySelector("#result");
const prefersReducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const unitIndex = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** unitIndex;
  return `${value.toFixed(unitIndex === 0 || value >= 10 ? 0 : 1)} ${units[unitIndex]}`;
}

function drawTimeline(seed = 2) {
  timeline.innerHTML = "";
  const bars = 72;
  for (let index = 0; index < bars; index += 1) {
    const bar = document.createElement("span");
    const height = 16 + Math.abs(Math.sin((index + seed) * 0.41)) * 62 + Math.abs(Math.cos(index * 0.17)) * 12;
    bar.style.left = `${(index / bars) * 100}%`;
    bar.style.height = `${height}px`;
    timeline.appendChild(bar);
  }
}

function setLoading(isLoading) {
  submitBtn.disabled = isLoading;
  submitBtn.classList.toggle("is-loading", isLoading);
  submitBtn.textContent = isLoading ? "Finding highlights…" : "Find Highlights";
  if (isLoading) {
    analysisStatus.textContent =
      "Analyzing the source and building your edit pack. This can take a moment for long media.";
  }
}

function showError(message = "") {
  formError.textContent = message;
  formError.classList.toggle("hidden", !message);
}

function describeFile(file) {
  if (!file) {
    fileLabel.textContent = "Choose long-form footage";
    fileMeta.textContent = "No file selected";
    return;
  }
  fileLabel.textContent = file.name;
  const kind = file.type || "Transcript";
  fileMeta.textContent = `${formatBytes(file.size)} · ${kind}`;
  analysisStatus.textContent = "Source ready. Choose your clip settings, then find highlights.";
  showError();
  drawTimeline(file.size % 37);
}

function acceptDroppedFile(file) {
  if (!file) return;
  const transfer = new DataTransfer();
  transfer.items.add(file);
  fileInput.files = transfer.files;
  describeFile(file);
}

function renderWarnings(warnings) {
  const root = document.querySelector("#warnings");
  root.innerHTML = "";
  if (!warnings.length) {
    root.classList.add("hidden");
    return;
  }
  warnings.forEach((warning) => {
    const div = document.createElement("div");
    div.textContent = warning;
    root.appendChild(div);
  });
  root.classList.remove("hidden");
}

function renderClips(clips) {
  const root = document.querySelector("#clips");
  root.innerHTML = "";
  clips.forEach((clip) => {
    const card = document.createElement("article");
    card.className = "clip";
    const video = clip.video_url ? `<a class="button" href="${clip.video_url}">MP4</a>` : "";
    const srt = clip.srt_url ? `<a class="button secondary" href="${clip.srt_url}">SRT</a>` : "";
    card.innerHTML = `
      <h3></h3>
      <div class="meta">
        <span>${clip.start.toFixed(2)}s to ${clip.end.toFixed(2)}s</span>
        <span>${clip.duration.toFixed(2)}s</span>
        <span>score ${clip.score.toFixed(2)}</span>
      </div>
      <p class="caption"></p>
      <p class="tags"></p>
      <div class="clip-actions">${video}${srt}</div>
    `;
    card.querySelector("h3").textContent = clip.title;
    card.querySelector(".caption").textContent = clip.caption;
    card.querySelector(".tags").textContent = clip.hashtags.join(" ");
    root.appendChild(card);
  });
}

async function checkHealth() {
  try {
    const response = await fetch("/api/health");
    const data = await response.json();
    health.textContent = data.status === "ok" ? "Ready" : "Offline";
  } catch {
    health.textContent = "Offline";
  }
}

fileInput.addEventListener("change", () => describeFile(fileInput.files[0]));

["dragenter", "dragover"].forEach((eventName) => {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.add("is-dragging");
    if (event.dataTransfer) event.dataTransfer.dropEffect = "copy";
  });
});

["dragleave", "drop"].forEach((eventName) => {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.remove("is-dragging");
  });
});

dropZone.addEventListener("drop", (event) => {
  acceptDroppedFile(event.dataTransfer?.files?.[0]);
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!fileInput.files.length) {
    showError("Choose a video, audio file, or transcript before finding highlights.");
    fileInput.focus();
    return;
  }
  showError();
  setLoading(true);
  const formData = new FormData();
  formData.append("file", fileInput.files[0]);
  formData.append("clip_count", document.querySelector("#clipCount").value);
  formData.append("platform", document.querySelector("#platform").value);
  formData.append("captions", document.querySelector("#captions").checked ? "true" : "false");
  formData.append("demo_mode", document.querySelector("#demoMode").checked ? "true" : "false");

  try {
    const response = await fetch("/api/highlights", { method: "POST", body: formData });
    if (!response.ok) throw new Error(await response.text());
    const result = await response.json();
    document.querySelector("#status").textContent = result.status === "rendered" ? "Rendered Clips" : "Planned Clips";
    document.querySelector("#edlLink").href = result.edit_decision_list_url;
    renderWarnings(result.warnings || []);
    renderClips(result.clips || []);
    resultPanel.classList.remove("hidden");
    resultPanel.focus({ preventScroll: true });
    resultPanel.scrollIntoView({
      behavior: prefersReducedMotion ? "auto" : "smooth",
      block: "start",
    });
    analysisStatus.textContent = `${result.clips?.length || 0} highlights are ready in the edit pack below.`;
  } catch (error) {
    showError(`Unable to make highlights: ${error.message}`);
    analysisStatus.textContent = "The edit pack was not created. Review the message and try again.";
  } finally {
    setLoading(false);
  }
});

drawTimeline();
checkHealth();

