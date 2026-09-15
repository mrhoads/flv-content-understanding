let currentCaseId = null;
let selectedEmployeeCase = null;

const byId = (id) => document.getElementById(id);
const escapeHtml = (value) => {
  const node = document.createElement("div");
  node.textContent = value;
  return node.innerHTML;
};

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab, .panel").forEach((item) => item.classList.remove("active"));
    tab.classList.add("active");
    byId(tab.dataset.target).classList.add("active");
  });
});

function addMessage(role, text) {
  const message = document.createElement("div");
  message.className = `message ${role}`;
  message.textContent = text;
  byId("customer-chat").appendChild(message);
  message.scrollIntoView({ behavior: "smooth" });
}

function appendInlineFormatting(element, text) {
  text.split(/(\*\*[^*]+\*\*)/).forEach((part) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      const strong = document.createElement("strong");
      strong.textContent = part.slice(2, -2);
      element.appendChild(strong);
    } else {
      element.appendChild(document.createTextNode(part));
    }
  });
}

function renderAgentAnswer(text) {
  const body = document.createElement("div");
  body.className = "agent-answer-body";
  let list = null;
  let listType = null;

  text.replace(/\r\n/g, "\n").split("\n").forEach((rawLine) => {
    const line = rawLine.trim();
    if (!line) {
      list = null;
      listType = null;
      return;
    }

    const bullet = line.match(/^[-*]\s+(.+)$/);
    const numbered = line.match(/^\d+[.)]\s+(.+)$/);
    if (bullet || numbered) {
      const nextListType = bullet ? "ul" : "ol";
      if (!list || listType !== nextListType) {
        list = document.createElement(nextListType);
        listType = nextListType;
        body.appendChild(list);
      }
      const item = document.createElement("li");
      appendInlineFormatting(item, (bullet || numbered)[1]);
      list.appendChild(item);
      return;
    }

    list = null;
    listType = null;
    const markdownHeading = line.match(/^#{1,4}\s+(.+)$/);
    const labelHeading = line.endsWith(":") && line.length <= 80;
    if (markdownHeading || labelHeading) {
      const heading = document.createElement("h4");
      appendInlineFormatting(
        heading,
        markdownHeading ? markdownHeading[1] : line.slice(0, -1),
      );
      body.appendChild(heading);
      return;
    }

    const paragraph = document.createElement("p");
    appendInlineFormatting(paragraph, line);
    body.appendChild(paragraph);
  });

  return body;
}

async function api(url, options = {}) {
  const response = await fetch(url, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || "The request could not be completed.");
  return body;
}

byId("start-case").addEventListener("click", async () => {
  const button = byId("start-case");
  button.disabled = true;
  button.textContent = "Starting…";
  try {
    const result = await api("/api/cases", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ customer_name: byId("customer-name").value || null }),
    });
    currentCaseId = result.case.id;
    addMessage("assistant", result.message);
    byId("start-area").classList.add("hidden");
    byId("upload-area").classList.remove("hidden");
    byId("step-upload").classList.add("done");
  } catch (error) {
    addMessage("assistant", error.message);
    button.disabled = false;
    button.textContent = "Start verification";
  }
});

byId("evidence-file").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (!file || !currentCaseId) return;
  addMessage("user", `Uploading ${file.name}`);
  const form = new FormData();
  form.append("file", file);
  try {
    const result = await api(`/api/cases/${currentCaseId}/uploads`, {
      method: "POST",
      body: form,
    });
    addMessage("assistant", result.message);
    byId("step-review").classList.add("done");
    byId("upload-area").classList.add("hidden");
    byId("customer-message-form").classList.remove("hidden");
  } catch (error) {
    addMessage("assistant", error.message);
  }
});

byId("customer-message-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = byId("customer-message");
  const text = input.value.trim();
  if (!text || !currentCaseId) return;
  addMessage("user", text);
  input.value = "";
  try {
    const result = await api(`/api/cases/${currentCaseId}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
    });
    addMessage("assistant", result.message);
  } catch (error) {
    addMessage("assistant", error.message);
  }
});

byId("load-cases").addEventListener("click", async () => {
  const key = byId("employee-key").value.trim();
  const list = byId("case-list");
  if (!key) {
    list.innerHTML = '<p class="muted">Enter the employee access key from Azure Key Vault.</p>';
    return;
  }
  list.innerHTML = '<p class="muted">Loading…</p>';
  try {
    const result = await api("/api/employee/cases", {
      headers: { "X-Employee-Key": key },
    });
    list.innerHTML = result.cases.length
      ? result.cases.map((item) => `
          <article class="case-item" data-case="${escapeHtml(item.id)}">
            <strong>${escapeHtml(item.customerName)}</strong>
            <small>${item.uploadCount} upload(s) · ${escapeHtml(item.status)}</small>
          </article>`).join("")
      : '<p class="muted">No cases have been submitted.</p>';
    document.querySelectorAll(".case-item").forEach((item) => {
      item.addEventListener("click", () => {
        document.querySelectorAll(".case-item").forEach((caseItem) => caseItem.classList.remove("active"));
        item.classList.add("active");
        selectedEmployeeCase = item.dataset.case;
        byId("selected-case").textContent = `Case ${selectedEmployeeCase.slice(0, 8)}`;
        byId("analysis-preview").innerHTML = '<div class="empty-state"><span>✓</span><h3>Case selected</h3><p>Ask a question and the internal agent will answer only from submitted evidence.</p></div>';
      });
    });
  } catch (error) {
    list.innerHTML = `<p class="muted">${escapeHtml(error.message)}</p>`;
  }
});

byId("employee-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const question = byId("employee-question").value.trim();
  const key = byId("employee-key").value.trim();
  if (!selectedEmployeeCase || !question) return;
  if (!key) {
    byId("analysis-preview").innerHTML = '<div class="empty-state"><p>Enter the employee access key from Azure Key Vault.</p></div>';
    return;
  }
  byId("analysis-preview").innerHTML = '<div class="empty-state"><p>Reviewing grounded evidence…</p></div>';
  try {
    const result = await api("/api/employee/query", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Employee-Key": key,
      },
      body: JSON.stringify({ case_id: selectedEmployeeCase, question }),
    });
    const answer = document.createElement("div");
    answer.className = "answer";
    const eyebrow = document.createElement("p");
    eyebrow.className = "eyebrow";
    eyebrow.textContent = "EVIDENCE AGENT";
    const heading = document.createElement("h3");
    heading.textContent = question;
    answer.append(eyebrow, heading, renderAgentAnswer(result.answer));
    byId("analysis-preview").replaceChildren(answer);
  } catch (error) {
    byId("analysis-preview").innerHTML = `<div class="empty-state"><p>${escapeHtml(error.message)}</p></div>`;
  }
});
