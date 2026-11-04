"use strict";

const $ = (selector) => document.querySelector(selector);
const state = {
  projects: [],
  sources: [],
  project: null,
  meta: null,
  editId: null,
  deleteId: null,
};
const labels = {
  success: "Başarılı",
  failure: "Başarısız",
  pending: "Sürüyor",
  unknown: "Belirsiz",
};
let toastTimer;

function node(tag, text = "", className = "") {
  const item = document.createElement(tag);
  if (text) item.textContent = text;
  if (className) item.className = className;
  return item;
}
function clear(element) {
  element.replaceChildren();
}
function toast(message, error = false) {
  clearTimeout(toastTimer);
  const box = $("#toast");
  box.textContent = message;
  box.classList.toggle("error", error);
  box.hidden = false;
  toastTimer = setTimeout(() => {
    box.hidden = true;
  }, 5500);
}
async function api(path, method = "GET", body) {
  const response = await fetch(path, {
    method,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const payload = response.status === 204 ? null : await response.json();
  if (!response.ok) {
    if (response.status === 401 && path !== "/api/login") showLogin();
    throw new Error(
      typeof payload?.detail === "string"
        ? payload.detail
        : "Bilgileri kontrol edip yeniden deneyin.",
    );
  }
  return payload;
}
function formatTime(value) {
  return new Intl.DateTimeFormat("tr-TR", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Europe/Istanbul",
  }).format(new Date(value));
}
function link(text, url) {
  const item = node("a", text);
  if (url.startsWith("https://github.com/")) {
    item.href = url;
    item.target = "_blank";
    item.rel = "noopener noreferrer";
  }
  return item;
}
function showLogin() {
  $("#workspace").hidden = true;
  if (!$("#login-dialog").open) $("#login-dialog").showModal();
}
async function loadWorkspace() {
  [state.projects, state.meta] = await Promise.all([
    api("/api/projects"),
    api("/api/meta"),
  ]);
  if ($("#login-dialog").open) $("#login-dialog").close();
  $("#workspace").hidden = false;
  $("#environment").textContent = state.meta.demo_mode
    ? "Örnek çalışma alanı"
    : "Kişisel çalışma alanı";
  $("#demo-note").hidden = !state.meta.demo_mode;
  $("#storage-label").textContent =
    state.meta.storage === "sqlite"
      ? "Yerel · SQLite"
      : "PostgreSQL · pgvector";
  $("#model-label").textContent =
    state.meta.model_backend === "ollama"
      ? "Ollama · yerel model"
      : "Kaynak alıntıları";
  renderProjects();
  const chosen =
    state.projects.find((p) => p.id === state.project?.id) ||
    state.projects.find((p) => p.name === "StockLedger") ||
    state.projects[0];
  if (chosen) await selectProject(chosen);
  else {
    $("#project-dialog").showModal();
    $("#question").disabled = true;
    $("#ask-button").disabled = true;
  }
}
function renderProjects() {
  const list = $("#project-list");
  clear(list);
  $("#project-count").textContent = state.projects.length;
  for (const project of state.projects) {
    const button = node("button", "", "project-item");
    button.type = "button";
    button.classList.toggle("selected", project.id === state.project?.id);
    if (project.id === state.project?.id)
      button.setAttribute("aria-current", "true");
    button.append(
      node("span", project.name.slice(0, 2).toUpperCase(), "project-symbol"),
    );
    const details = node("span");
    details.append(
      node("strong", project.name),
      node(
        "small",
        project.repository ? "GitHub bağlantısı" : "Kişisel notlar",
      ),
    );
    button.append(details);
    button.addEventListener("click", () =>
      selectProject(project).catch((error) => toast(error.message, true)),
    );
    list.append(button);
  }
}
async function selectProject(project) {
  state.project = project;
  state.sources = [];
  renderProjects();
  $("#breadcrumb").textContent = project.name;
  $("#repo-short").textContent =
    project.repository.split("/").pop() || "Bağlı depo yok";
  $("#include-checks").disabled = !project.repository;
  $("#include-checks").checked = false;
  $("#sync").disabled = !project.repository;
  $("#refresh-checks").disabled = !project.repository;
  $("#answer-panel").hidden = true;
  $("#evidence-panel").hidden = true;
  $("#empty-prompt").hidden = false;
  $("#question").disabled = false;
  $("#ask-button").disabled = false;
  $("#sync-result").textContent = "";
  clear($("#check-results"));
  $("#check-results").append(node("div", "◷ Henüz sorgulanmadı", "unverified"));
  renderSuggestions();
  await refreshSources(project.id);
}
async function refreshSources(projectId) {
  const sources = await api(`/api/projects/${projectId}/sources`);
  if (state.project?.id !== projectId) return;
  state.sources = sources;
  $("#source-count").textContent = sources.length;
  $("#tab-source-count").textContent = sources.length;
  renderSources();
}
function renderSuggestions() {
  clear($("#suggestions"));
  const questions =
    state.project?.name === "ProcureFlow"
      ? ["Kendi talebimi onaylayabilir miyim?", "Veriler nerede tutuluyor?"]
      : [
          "Redis neden kullanılıyor?",
          "Idempotency nasıl çalışıyor?",
          "Docker bildirimi neyi anlatıyor?",
        ];
  for (const question of questions) {
    const button = node("button", question + " ↗");
    button.type = "button";
    button.addEventListener("click", () => {
      $("#question").value = question;
      $("#question").focus();
    });
    $("#suggestions").append(button);
  }
}
function tab(name) {
  for (const key of ["ask", "sources"]) {
    const selected = key === name;
    $(`#${key}-tab`).setAttribute("aria-selected", String(selected));
    $(`#${key}-view`).hidden = !selected;
  }
}
$("#ask-tab").addEventListener("click", () => tab("ask"));
$("#sources-tab").addEventListener("click", () => tab("sources"));
$(".tabs").addEventListener("keydown", (event) => {
  if (["ArrowLeft", "ArrowRight"].includes(event.key)) {
    event.preventDefault();
    const target =
      $("#ask-tab").getAttribute("aria-selected") === "true"
        ? "sources"
        : "ask";
    tab(target);
    $(`#${target}-tab`).focus();
  }
});
function renderSources() {
  const list = $("#source-list");
  clear(list);
  if (!state.sources.length)
    list.append(
      node(
        "p",
        "Henüz kaynak yok. Bir not ekleyerek başlayabilirsin.",
        "muted",
      ),
    );
  for (const source of state.sources) {
    const card = node("article", "", "source-card");
    const head = node("div", "", "source-head");
    head.append(
      node("h3", source.title),
      node(
        "span",
        source.kind === "demo"
          ? "Kayıtlı örnek"
          : source.kind === "note"
            ? "Kişisel not"
            : "Depo belgesi",
        "badge neutral",
      ),
    );
    card.append(head);
    card.append(
      node(
        "p",
        source.body.slice(0, 340) + (source.body.length > 340 ? "…" : ""),
      ),
    );
    card.append(
      node(
        "small",
        `${source.version_count} sürüm · ${source.revision.slice(0, 12)} · ${formatTime(source.observed_at)}`,
      ),
    );
    const actions = node("div", "", "source-actions");
    if (source.url) actions.append(link("GitHub’da aç ↗", source.url));
    if (source.kind === "note") {
      const edit = node("button", "Düzenle");
      edit.addEventListener("click", () => openNote(source));
      actions.append(edit);
    }
    const remove = node("button", "Sil", "delete-source");
    remove.addEventListener("click", () => {
      state.deleteId = source.id;
      $("#delete-description").textContent =
        `“${source.title}” kaynağını silmek üzeresin.`;
      $("#delete-dialog").showModal();
    });
    actions.append(remove);
    card.append(actions);
    list.append(card);
  }
}
function renderChecks(result, target = $("#check-results")) {
  clear(target);
  const head = node(
    "div",
    `● ${labels[result.state] || "Belirsiz"}`,
    "check-heading",
  );
  target.append(head);
  for (const check of result.checks) {
    const row = node("div", "", "workflow");
    row.append(
      check.url ? link(check.name, check.url) : node("span", check.name),
      node(
        "span",
        labels[check.state] || "Belirsiz",
        `state-pill ${check.state}`,
      ),
    );
    target.append(row);
  }
  if (!result.checks.length)
    target.append(
      node("p", "Beklenen kontrol adları tanımlanmamış.", "footnote"),
    );
  target.append(
    node(
      "div",
      `${result.branch} / ${result.head_sha.slice(0, 12)}`,
      "check-sha",
    ),
  );
  target.append(
    node(
      "div",
      `Sorgulandı: ${formatTime(result.observed_at)} · Türkiye saati`,
      "check-time",
    ),
  );
  if (result.historical_failures)
    target.append(
      node(
        "p",
        `İncelenen geçmişte ${result.historical_failures} başarısız çalışma var. Yukarıdaki durum güncel commit’e ait.`,
        "footnote",
      ),
    );
}
function renderAnswer(answer, projectId) {
  const panel = $("#answer-panel");
  clear(panel);
  panel.hidden = false;
  const head = node("div", "", "answer-head");
  head.append(
    node(
      "h2",
      answer.status === "insufficient"
        ? "Yeterli kanıt bulunamadı"
        : answer.mode === "llm"
          ? "Kaynaklı yanıt"
          : "Kaynak alıntıları",
    ),
    node(
      "span",
      answer.retrieval_mode === "hybrid" ? "Hibrit arama" : "Sözcük araması",
      "badge",
    ),
  );
  panel.append(head);
  if (answer.checks) {
    const live = node("section", "", "context-card");
    live.append(node("h3", "Güncel GitHub verisi"));
    const checks = node("div");
    renderChecks(answer.checks, checks);
    live.append(checks);
    panel.append(live);
    renderChecks(answer.checks);
  }
  if (answer.check_error)
    panel.append(
      node(
        "p",
        `Güncel kontroller alınamadı: ${answer.check_error}`,
        "warning",
      ),
    );
  if (answer.status === "insufficient")
    panel.append(
      node(
        "p",
        "Bu soruyu cevaplayacak yeterli kaynak bulunamadı. İlgili belgeyi veya karar notunu ekleyebilirsin.",
        "claim",
      ),
    );
  const evidenceMap = new Map(
    answer.evidence.map((item, index) => [item.chunk.id, index + 1]),
  );
  for (const claim of answer.claims) {
    const paragraph = node("p", claim.text, "claim");
    for (const id of claim.citations) {
      const button = node(
        "button",
        `[${evidenceMap.get(id)}]`,
        "citation-button",
      );
      button.setAttribute(
        "aria-label",
        `${evidenceMap.get(id)} numaralı kaynağa git`,
      );
      button.addEventListener("click", () => {
        const source = document.getElementById(`evidence-${id}`);
        source?.scrollIntoView({ behavior: "smooth", block: "center" });
      });
      paragraph.append(button);
    }
    panel.append(paragraph);
  }
  for (const message of answer.warnings)
    panel.append(node("p", message, "warning"));
  const meta = node(
    "div",
    `${(answer.elapsed_ms / 1000).toFixed(1)} sn · ${answer.evidence.length} kaynak parçası`,
    "answer-meta",
  );
  const feedback = node("div", "", "feedback");
  feedback.append(node("span", "Faydalı mıydı?"));
  for (const [label, vote] of [
    ["Evet", 1],
    ["Hayır", -1],
  ]) {
    const button = node("button", label);
    button.addEventListener("click", async () => {
      try {
        await api(`/api/projects/${projectId}/feedback`, "POST", {
          answer_id: answer.id,
          vote,
        });
        toast("Geri bildirimin kaydedildi.");
      } catch (error) {
        toast(error.message, true);
      }
    });
    feedback.append(button);
  }
  meta.append(feedback);
  panel.append(meta);
  clear($("#evidence-list"));
  $("#evidence-panel").hidden = !answer.evidence.length;
  answer.evidence.forEach((item, index) => {
    const source = item.chunk;
    const card = node("article", "", "evidence-card");
    card.id = `evidence-${source.id}`;
    card.append(
      node("strong", `[${index + 1}] ${source.title}`),
      node("p", source.text),
      node(
        "small",
        `${source.revision.slice(0, 12)} · ${formatTime(source.observed_at)}`,
      ),
    );
    if (source.url)
      card.append(node("br"), link("Bu sürümü GitHub’da gör ↗", source.url));
    $("#evidence-list").append(card);
  });
}
$("#question-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.project) return;
  const projectId = state.project.id;
  $("#ask-button").disabled = true;
  $("#answer-panel").hidden = false;
  $("#evidence-panel").hidden = true;
  $("#empty-prompt").hidden = true;
  clear($("#answer-panel"));
  $("#answer-panel").append(node("div", "Kaynaklar inceleniyor…", "loading"));
  try {
    const answer = await api(`/api/projects/${projectId}/answer`, "POST", {
      question: $("#question").value.trim(),
      use_live_checks: $("#include-checks").checked,
    });
    if (state.project?.id === projectId) renderAnswer(answer, projectId);
  } catch (error) {
    if (state.project?.id === projectId) {
      clear($("#answer-panel"));
      $("#answer-panel").append(node("p", error.message, "warning"));
    }
  } finally {
    if (state.project?.id === projectId) $("#ask-button").disabled = false;
  }
});
$("#refresh-checks").addEventListener("click", async () => {
  if (!state.project) return;
  const projectId = state.project.id;
  $("#refresh-checks").disabled = true;
  try {
    const result = await api(`/api/projects/${projectId}/checks`, "POST");
    if (state.project?.id === projectId) renderChecks(result);
  } catch (error) {
    if (state.project?.id === projectId) {
      clear($("#check-results"));
      $("#check-results").append(node("p", error.message, "warning"));
    }
  } finally {
    if (state.project?.id === projectId) $("#refresh-checks").disabled = false;
  }
});
$("#sync").addEventListener("click", async () => {
  if (!state.project) return;
  const projectId = state.project.id;
  $("#sync").disabled = true;
  $("#sync-result").textContent = "Belgeler hazırlanıyor…";
  try {
    const result = await api(`/api/projects/${projectId}/sync`, "POST");
    if (state.project?.id === projectId) {
      $("#sync-result").textContent =
        `${result.documents} belge incelendi, ${result.changed} belge güncellendi. ${result.scope}.`;
      await refreshSources(projectId);
    }
  } catch (error) {
    if (state.project?.id === projectId)
      $("#sync-result").textContent = error.message;
  } finally {
    if (state.project?.id === projectId) $("#sync").disabled = false;
  }
});
function openNote(source) {
  state.editId = source?.id || null;
  $("#note-heading").textContent = source ? "Notu düzenle" : "Yeni not";
  $("#note-title").value = source?.title || "";
  $("#note-body").value = source?.body || "";
  $("#note-dialog").showModal();
}
$("#add-note").addEventListener("click", () => {
  if (state.project) openNote();
});
$("#new-project").addEventListener("click", () => {
  $("#project-form").reset();
  $("#project-dialog").showModal();
});
for (const button of document.querySelectorAll(".close-dialog"))
  button.addEventListener("click", () => button.closest("dialog").close());
$("#note-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.project) return;
  const button = event.submitter;
  button.disabled = true;
  const projectId = state.project.id;
  try {
    await api(
      `/api/projects/${projectId}/notes${state.editId ? "/" + state.editId : ""}`,
      state.editId ? "PUT" : "POST",
      {
        title: $("#note-title").value.trim(),
        body: $("#note-body").value.trim(),
      },
    );
    $("#note-dialog").close();
    await refreshSources(projectId);
    toast("Notun kaydedildi.");
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
  }
});
$("#project-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.submitter;
  button.disabled = true;
  try {
    const project = await api("/api/projects", "POST", {
      name: $("#project-name").value.trim(),
      repository: $("#project-repo").value.trim(),
      workflows: $("#project-workflows")
        .value.split(",")
        .map((x) => x.trim())
        .filter(Boolean),
    });
    state.projects = await api("/api/projects");
    $("#project-dialog").close();
    await selectProject(project);
    toast("Yeni projen hazır.");
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
  }
});
$("#delete-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.submitter;
  button.disabled = true;
  const projectId = state.project.id;
  try {
    await api(`/api/projects/${projectId}/sources/${state.deleteId}`, "DELETE");
    $("#delete-dialog").close();
    await refreshSources(projectId);
    $("#answer-panel").hidden = true;
    $("#evidence-panel").hidden = true;
    $("#empty-prompt").hidden = false;
    toast("Kaynak ve kayıtlı sürümleri silindi.");
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
  }
});
$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.submitter;
  button.disabled = true;
  $("#login-error").textContent = "";
  try {
    await api("/api/login", "POST", { password: $("#password").value });
    $("#password").value = "";
    await loadWorkspace();
  } catch (error) {
    $("#login-error").textContent = error.message;
  } finally {
    button.disabled = false;
  }
});
$("#login-dialog").addEventListener("cancel", (event) =>
  event.preventDefault(),
);
async function logout() {
  try {
    await api("/api/logout", "POST");
    state.project = null;
    state.sources = [];
    showLogin();
  } catch (error) {
    toast(error.message, true);
  }
}
$("#logout").addEventListener("click", logout);
$("#mobile-logout").addEventListener("click", logout);
loadWorkspace().catch((error) => {
  showLogin();
  if (!error.message.includes("Oturum"))
    $("#login-error").textContent = error.message;
});
