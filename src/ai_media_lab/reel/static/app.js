const health = document.querySelector("#health");
const form = document.querySelector("#uploadForm");
const fileInput = document.querySelector("#file");
const fileLabel = document.querySelector("#fileLabel");
const submitBtn = document.querySelector("#submitBtn");
const timeline = document.querySelector("#timeline");

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
  submitBtn.textContent = isLoading ? "Finding" : "Find Highlights";
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

fileInput.addEventListener("change", () => {
  const file = fileInput.files[0];
  fileLabel.textContent = file ? file.name : "Choose long-form footage";
  drawTimeline(file ? file.size % 37 : 2);
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!fileInput.files.length) return;
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
    document.querySelector("#result").classList.remove("hidden");
  } catch (error) {
    alert(`Unable to make highlights: ${error.message}`);
  } finally {
    setLoading(false);
  }
});

drawTimeline();
checkHealth();

