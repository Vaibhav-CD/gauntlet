/**
 * System Kernel Multi-Model IDE Client
 * Interacts with Kernel REST API to execute coding instructions,
 * synchronize the Single Source of Truth snapshot, and visualize failovers.
 */

class KernelIDE {
  constructor() {
    this.currentSnapshot = null;
    this.primaryModel = null;
    this.models = [];
    this.activeFile = null;
    this.isSimulating429 = false;

    this.initDOMElements();
    this.bindEvents();
    this.bootstrap();
  }

  initDOMElements() {
    this.primaryModelSelect = document.getElementById("primaryModelSelect");
    this.fallbackPills = document.getElementById("fallbackPills");
    this.toggleSim429Btn = document.getElementById("toggleSim429Btn");
    this.simStatus = document.getElementById("simStatus");
    this.undoBtn = document.getElementById("undoBtn");

    this.fileList = document.getElementById("fileList");
    this.bufferList = document.getElementById("bufferList");
    this.bufferCount = document.getElementById("bufferCount");
    this.newFileBtn = document.getElementById("newFileBtn");

    this.activeFileTitle = document.getElementById("activeFileTitle");
    this.saveStatus = document.getElementById("saveStatus");
    this.saveFileBtn = document.getElementById("saveFileBtn");
    this.codeEditor = document.getElementById("codeEditor");

    this.chatFeed = document.getElementById("chatFeed");
    this.taskPromptInput = document.getElementById("taskPromptInput");
    this.executeTaskBtn = document.getElementById("executeTaskBtn");
    this.execSpinner = document.getElementById("execSpinner");
    this.autoVerifyCheck = document.getElementById("autoVerifyCheck");
    this.runTestsBtn = document.getElementById("runTestsBtn");

    this.snapshotViewer = document.getElementById("snapshotViewer");
    this.refreshSnapshotBtn = document.getElementById("refreshSnapshotBtn");
    this.modelsMatrix = document.getElementById("modelsMatrix");

    this.navTabs = document.querySelectorAll(".nav-tab");
    this.tabPanes = document.querySelectorAll(".tab-pane");
    this.toastContainer = document.getElementById("toastContainer");
  }

  bindEvents() {
    // Primary model change
    this.primaryModelSelect.addEventListener("change", (e) => this.setPrimaryModel(e.target.value));

    // Simulate 429 Toggle
    this.toggleSim429Btn.addEventListener("click", () => this.toggleSimulate429());

    // Rollback / Undo
    this.undoBtn.addEventListener("click", () => this.rollback());

    // Save File
    this.saveFileBtn.addEventListener("click", () => this.saveActiveFile());

    // New File
    this.newFileBtn.addEventListener("click", () => this.promptNewFile());

    // Execute Task
    this.executeTaskBtn.addEventListener("click", () => this.executeTask());
    this.taskPromptInput.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        this.executeTask();
      }
    });

    // Run Tests
    if (this.runTestsBtn) {
      this.runTestsBtn.addEventListener("click", () => this.runTests());
    }

    // Refresh Snapshot
    this.refreshSnapshotBtn.addEventListener("click", () => this.loadSnapshot());

    // Editor typing triggers unsaved marker
    this.codeEditor.addEventListener("input", () => {
      this.saveStatus.textContent = "Unsaved changes";
      this.saveStatus.style.color = "#f59e0b";
    });

    // Nav tabs
    this.navTabs.forEach(tab => {
      tab.addEventListener("click", () => {
        this.navTabs.forEach(t => t.classList.remove("active"));
        this.tabPanes.forEach(p => p.classList.remove("active"));
        tab.classList.add("active");
        document.getElementById(tab.dataset.tab).classList.add("active");

        if (tab.dataset.tab === "snapshotTab") {
          this.loadSnapshot();
        } else if (tab.dataset.tab === "modelsTab") {
          this.renderModelsMatrix();
        }
      });
    });
  }

  async bootstrap() {
    await this.loadModels();
    await this.loadFiles();
    await this.loadSnapshot();
  }

  showToast(msg, type = "success") {
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.textContent = msg;
    this.toastContainer.appendChild(toast);
    setTimeout(() => {
      toast.remove();
    }, 3500);
  }

  async loadModels() {
    try {
      const res = await fetch("/api/models");
      const data = await res.json();
      this.primaryModel = data.primary_model;
      this.models = data.models;

      // Populate select
      this.primaryModelSelect.innerHTML = "";
      this.models.forEach(m => {
        const opt = document.createElement("option");
        opt.value = m.name;
        opt.textContent = `${m.name} (${m.provider})`;
        if (m.name === this.primaryModel) opt.selected = true;
        this.primaryModelSelect.appendChild(opt);
      });

      // Update fallback pills
      this.fallbackPills.innerHTML = "";
      const fallbacks = this.models.filter(m => m.is_fallback);
      fallbacks.forEach(fb => {
        const p = document.createElement("span");
        p.className = "pill fallback";
        p.textContent = `↳ ${fb.name}`;
        this.fallbackPills.appendChild(p);
      });

      // Check if primary is simulating 429
      const primaryCfg = this.models.find(m => m.name === this.primaryModel);
      if (primaryCfg) {
        this.isSimulating429 = primaryCfg.simulate_429;
        this.updateSimButtonState();
      }
    } catch (err) {
      console.error("Error loading models:", err);
    }
  }

  updateSimButtonState() {
    this.simStatus.textContent = this.isSimulating429 ? "ON (FAILOVER ACTIVE)" : "OFF";
    if (this.isSimulating429) {
      this.toggleSim429Btn.style.backgroundColor = "rgba(239, 68, 68, 0.25)";
      this.toggleSim429Btn.style.borderColor = "var(--accent-red)";
      this.toggleSim429Btn.style.color = "var(--accent-red)";
    } else {
      this.toggleSim429Btn.style.backgroundColor = "rgba(245, 158, 11, 0.15)";
      this.toggleSim429Btn.style.borderColor = "var(--accent-amber)";
      this.toggleSim429Btn.style.color = "var(--accent-amber)";
    }
  }

  async setPrimaryModel(modelName) {
    try {
      const res = await fetch("/api/models/set-primary", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model_name: modelName })
      });
      if (res.ok) {
        this.primaryModel = modelName;
        this.showToast(`Switched primary model to ${modelName}`);
        await this.loadModels();
      }
    } catch (err) {
      this.showToast(`Failed to switch model: ${err}`, "error");
    }
  }

  async toggleSimulate429() {
    const newState = !this.isSimulating429;
    try {
      const res = await fetch("/api/models/simulate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model_name: this.primaryModel,
          simulate_429: newState
        })
      });
      if (res.ok) {
        this.isSimulating429 = newState;
        this.updateSimButtonState();
        const msg = newState
          ? `HTTP 429 simulation enabled on '${this.primaryModel}'. Next run will trigger transparent failover!`
          : `HTTP 429 simulation disabled on '${this.primaryModel}'.`;
        this.showToast(msg, newState ? "warn" : "success");
      }
    } catch (err) {
      this.showToast(`Error toggling simulation: ${err}`, "error");
    }
  }

  async loadFiles() {
    try {
      const res = await fetch("/api/files");
      const data = await res.json();

      // Render workspace files
      this.fileList.innerHTML = "";
      data.disk_files.forEach(f => {
        const item = document.createElement("div");
        item.className = `file-item ${f === data.active_file ? "active" : ""}`;
        item.innerHTML = `<span>📄</span> <span>${f}</span>`;
        item.onclick = () => this.openFile(f);
        this.fileList.appendChild(item);
      });

      // Render open buffers
      this.bufferList.innerHTML = "";
      this.bufferCount.textContent = data.open_files.length;
      data.open_files.forEach(f => {
        const item = document.createElement("div");
        item.className = `file-item ${f === data.active_file ? "active" : ""}`;
        item.innerHTML = `<span>⚡</span> <span>${f}</span>`;
        item.onclick = () => this.openFile(f);
        this.bufferList.appendChild(item);
      });

      // If active file set, load its content into editor
      if (data.active_file) {
        this.activeFile = data.active_file;
        this.activeFileTitle.textContent = data.active_file;
      }
    } catch (err) {
      console.error("Error loading files:", err);
    }
  }

  async openFile(filePath) {
    try {
      const res = await fetch("/api/files/open", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ file_path: filePath })
      });
      const data = await res.json();
      if (data.status === "success") {
        this.activeFile = filePath;
        this.activeFileTitle.textContent = filePath;
        this.codeEditor.value = data.content;
        this.saveStatus.textContent = "Saved";
        this.saveStatus.style.color = "var(--text-muted)";
        await this.loadFiles();
        await this.loadSnapshot();
      }
    } catch (err) {
      this.showToast(`Failed to open file: ${err}`, "error");
    }
  }

  async saveActiveFile() {
    if (!this.activeFile) return;
    try {
      const res = await fetch("/api/files/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          file_path: this.activeFile,
          content: this.codeEditor.value
        })
      });
      if (res.ok) {
        this.saveStatus.textContent = "Saved";
        this.saveStatus.style.color = "var(--accent-green)";
        this.showToast(`Saved ${this.activeFile}`);
        await this.loadSnapshot();
      }
    } catch (err) {
      this.showToast(`Error saving file: ${err}`, "error");
    }
  }

  async promptNewFile() {
    const filename = prompt("Enter file path (e.g. src/utils.py):");
    if (!filename) return;
    try {
      const res = await fetch("/api/files/create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ file_path: filename, content: "" })
      });
      if (res.ok) {
        this.showToast(`Created ${filename}`);
        await this.openFile(filename);
      }
    } catch (err) {
      this.showToast(`Error creating file: ${err}`, "error");
    }
  }

  async loadSnapshot() {
    try {
      const res = await fetch("/api/snapshot");
      const snap = await res.json();
      this.currentSnapshot = snap;
      this.snapshotViewer.textContent = JSON.stringify(snap, null, 2);

      // If active file is open, ensure editor matches buffer
      if (snap.active_file && snap.open_files[snap.active_file] !== undefined) {
        this.activeFile = snap.active_file;
        this.activeFileTitle.textContent = snap.active_file;
        this.codeEditor.value = snap.open_files[snap.active_file];
        this.saveStatus.textContent = "In Sync";
        this.saveStatus.style.color = "var(--accent-green)";
      }
    } catch (err) {
      console.error("Error loading snapshot:", err);
    }
  }

  async rollback() {
    try {
      const res = await fetch("/api/rollback", { method: "POST" });
      const data = await res.json();
      if (data.status === "success") {
        this.showToast("Rolled back to previous workspace snapshot state!");
        await this.loadSnapshot();
        await this.loadFiles();
      } else {
        this.showToast("Undo stack is empty", "warn");
      }
    } catch (err) {
      this.showToast(`Rollback error: ${err}`, "error");
    }
  }

  async executeTask() {
    const promptText = this.taskPromptInput.value.trim();
    if (!promptText) return;

    // Append user message to chat feed
    this.appendChatMessage("User", promptText, "user-msg");
    this.taskPromptInput.value = "";
    this.execSpinner.classList.remove("hidden");
    this.executeTaskBtn.disabled = true;

    try {
      const autoVerify = this.autoVerifyCheck ? this.autoVerifyCheck.checked : false;
      const res = await fetch("/api/execute", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          task_prompt: promptText,
          primary_model: this.primaryModel,
          workspace_snapshot: this.currentSnapshot,
          auto_verify: autoVerify
        })
      });

      const result = await res.json();

      // Check if failover occurred
      if (result.handoff_notes && result.handoff_notes.length > 0) {
        result.handoff_notes.forEach(note => {
          this.appendChatMessage("Transparent Failover", note, "handoff-alert");
        });
      }

      // Append assistant response
      let mutationInfo = "";
      if (result.mutations_applied && result.mutations_applied.length > 0) {
        const mutItems = result.mutations_applied.map(m => {
          const syntaxTag = m.syntax_valid !== false ? '<span style="color:#10b981"> [Syntax Valid]</span>' : '<span style="color:#ef4444"> [Syntax Error]</span>';
          return `<div>✓ [${m.action.toUpperCase()}] <strong>${m.file_path}</strong>${syntaxTag}</div>`;
        }).join("");
        mutationInfo = `<div class="mutation-badge">${mutItems}</div>`;
      }

      // Verification info if auto_verify was enabled
      let verifyBadge = "";
      if (result.verification_passed !== null && result.verification_passed !== undefined) {
        const passClass = result.verification_passed ? "color:#10b981;" : "color:#ef4444;";
        const passIcon = result.verification_passed ? "✓" : "✗";
        verifyBadge = `<div style="margin-top:6px; font-size:0.75rem; ${passClass}"><strong>${passIcon} Test Verification:</strong> ${result.verification_output.split("\n")[0]}</div>`;
      }

      const metaHeader = `Model: ${result.model_used} | Latency: ${result.latency_seconds}s | Status: ${result.status}`;
      this.appendChatMessage(metaHeader, result.response_text + mutationInfo + verifyBadge, "assistant-msg");

      // Auto update active editor and snapshot
      await this.loadSnapshot();
      await this.loadFiles();
      await this.loadModels();

      if (result.status === "failover_success") {
        this.showToast(`Task completed via failover model '${result.model_used}'!`, "warn");
      } else {
        this.showToast(`Task completed successfully by '${result.model_used}'.`);
      }

    } catch (err) {
      this.appendChatMessage("System Error", `Execution failed: ${err}`, "error");
      this.showToast(`Execution failed: ${err}`, "error");
    } finally {
      this.execSpinner.classList.add("hidden");
      this.executeTaskBtn.disabled = false;
    }
  }

  async runTests() {
    this.appendChatMessage("Test Runner", "Running project unit tests...", "system-msg");
    try {
      const res = await fetch("/api/verify", { method: "POST" });
      const data = await res.json();
      const statusClass = data.passed ? "assistant-msg" : "handoff-alert";
      const header = data.passed ? "✓ All Unit Tests Passed" : "✗ Unit Tests Failed";
      this.appendChatMessage(header, `<pre style="font-size:0.75rem; font-family:var(--font-mono);">${data.output}</pre>`, statusClass);
      this.showToast(data.passed ? "Tests passed successfully!" : "Tests failed", data.passed ? "success" : "error");
    } catch (err) {
      this.showToast(`Error running tests: ${err}`, "error");
    }
  }

  appendChatMessage(sender, content, extraClass = "") {
    const msg = document.createElement("div");
    msg.className = `message ${extraClass}`;
    msg.innerHTML = `
      <div class="msg-header">${sender}</div>
      <div class="msg-content">${content.replace(/\n/g, "<br>")}</div>
    `;
    this.chatFeed.appendChild(msg);
    this.chatFeed.scrollTop = this.chatFeed.scrollHeight;
  }

  renderModelsMatrix() {
    this.modelsMatrix.innerHTML = "";
    this.models.forEach(m => {
      const card = document.createElement("div");
      card.className = `model-card ${m.name === this.primaryModel ? "is-primary" : ""}`;

      const isPrimary = m.name === this.primaryModel;
      const primaryBadge = isPrimary
        ? '<span class="pill active">ACTIVE PRIMARY</span>'
        : (m.is_fallback ? '<span class="pill fallback">FALLBACK</span>' : '');

      let cbBadge = '<span class="pill" style="border-color:#10b981; color:#10b981;">CIRCUIT: HEALTHY</span>';
      if (m.circuit_state === "OPEN") {
        cbBadge = '<span class="pill" style="border-color:#ef4444; color:#ef4444;">CIRCUIT: OPEN (COOLDOWN)</span>';
      } else if (m.circuit_state === "HALF_OPEN") {
        cbBadge = '<span class="pill" style="border-color:#f59e0b; color:#f59e0b;">CIRCUIT: HALF-OPEN</span>';
      }

      card.innerHTML = `
        <div class="card-top">
          <span class="model-name">${m.name}</span>
          <div style="display:flex; gap:4px; align-items:center;">
            ${cbBadge}
            ${primaryBadge}
          </div>
        </div>
        <div class="card-body">
          <span>Provider: <strong>${m.provider}</strong></span>
          <span>Model ID: <strong>${m.model_id}</strong></span>
          <span>Failures: <strong>${m.failure_count || 0}</strong></span>
        </div>
        <div class="card-actions">
          <div style="display:flex; gap:10px; align-items:center;">
            <label style="font-size: 0.75rem; color: var(--text-muted); cursor: pointer;">
              <input type="checkbox" ${m.simulate_429 ? "checked" : ""} class="sim-check" data-model="${m.name}">
              Simulate 429
            </label>
            ${m.circuit_state === "OPEN" ? `<button class="btn btn-sm btn-warning reset-circuit-btn" data-model="${m.name}">Reset Circuit</button>` : ''}
          </div>
          ${!isPrimary ? `<button class="btn btn-sm btn-outline make-primary-btn" data-model="${m.name}">Set as Primary</button>` : ''}
        </div>
      `;

      // Checkbox event
      const check = card.querySelector(".sim-check");
      check.addEventListener("change", async (e) => {
        await fetch("/api/models/simulate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            model_name: m.name,
            simulate_429: e.target.checked
          })
        });
        await this.loadModels();
        this.renderModelsMatrix();
      });

      // Reset Circuit button
      const resetBtn = card.querySelector(".reset-circuit-btn");
      if (resetBtn) {
        resetBtn.addEventListener("click", async () => {
          await fetch("/api/models/reset-circuit", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ model_name: m.name })
          });
          this.showToast(`Reset circuit breaker for ${m.name}`);
          await this.loadModels();
          this.renderModelsMatrix();
        });
      }

      // Set primary button
      const setBtn = card.querySelector(".make-primary-btn");
      if (setBtn) {
        setBtn.addEventListener("click", () => this.setPrimaryModel(m.name));
      }

      this.modelsMatrix.appendChild(card);
    });
  }
}

// Instantiate on load
document.addEventListener("DOMContentLoaded", () => {
  window.kernelIDE = new KernelIDE();
});
