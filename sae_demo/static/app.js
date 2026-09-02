// M5A/M5B/M5C/M5D/M5F frontend behavior.
//
// M5A: on load, check backend health and status, show a connected/error
// indicator.
//
// M5B: list the built-in synthetic scenarios, start an in-memory,
// frozen-mode run, and advance through it one segment at a time.
//
// M5C: choose Memory OFF or Memory ON before starting a run (fixed for
// that run's lifetime -- start a new run for the other condition), and
// render each advanced segment's real assistant response as a growing
// User/Scenario + Assistant conversation.
//
// M5D: once a run completes, offer to replay the exact same scenario as
// a fresh run under the opposite memory condition; once both runs have
// completed, fetch and render the aligned Memory OFF / Memory ON
// comparison. This page never renders any system/background message,
// the memory payload, or any private artifact detail -- only the
// scenario's own segment text and each condition's reply to it, exactly
// as the API returns them -- and never rates, ranks, or labels either
// response as preferable.
//
// M5F: "Create your own" lets a user build a custom seven-segment
// scenario without writing one unassisted -- fill in plain-language
// ingredients, get back a locally generated (no AI call) copyable
// prompt, run that prompt through an AI of their own choosing, paste
// the seven-section result back, review/edit it, then freeze it. A
// frozen custom scenario runs through the exact same
// `startRunForScenario`/comparison flow as a built-in one.
//
// M5G: hardening only. A visible "Waiting for model..." state (plus a
// disabled-button guard against a duplicate in-flight request) is
// shown while `advanceSegment` is waiting on a real provider call --
// the only action in this page that actually calls a provider. The
// two comparison columns get a purely visual OFF/ON accent. No new
// endpoint or automated judgment of either response is added --
// assistant/segment text is still always set via `.textContent`, never
// rendered as HTML or Markdown.

let currentRunId = null;
let scenariosById = {};

async function loadStatus() {
  const backendText = document.getElementById("backend-status-text");
  const modelText = document.getElementById("model-status-text");

  try {
    const healthResponse = await fetch("/api/health");
    if (!healthResponse.ok) {
      throw new Error("health check failed");
    }
    await healthResponse.json();

    const statusResponse = await fetch("/api/status");
    if (!statusResponse.ok) {
      throw new Error("status check failed");
    }
    const status = await statusResponse.json();

    backendText.textContent = "Connected (" + status.stage + ")";
    backendText.classList.remove("status-error");
    backendText.classList.add("status-ok");

    const providerText = status.provider_configured
      ? "provider configured"
      : "provider not configured";
    modelText.textContent =
      "Target model: " + status.target_model + " — " + providerText + ".";
  } catch (error) {
    // Deliberately generic: no stack trace or internal detail is shown.
    backendText.textContent = "Unable to reach the backend right now.";
    backendText.classList.remove("status-ok");
    backendText.classList.add("status-error");
    modelText.textContent = "";
  }
}

// -- Scenario selection ------------------------------------------------

function showScenarioError(message) {
  const errorEl = document.getElementById("scenario-error");
  errorEl.textContent = message;
  errorEl.hidden = false;
}

function clearScenarioError() {
  const errorEl = document.getElementById("scenario-error");
  errorEl.hidden = true;
  errorEl.textContent = "";
}

// Reads a safe, human-readable message out of an error HTTP response's
// JSON body (FastAPI's {"detail": "..."} shape), falling back to a
// generic message if the body can't be parsed. Never surfaces a stack
// trace or raw exception text -- only whatever safe string the backend
// chose to send.
async function extractErrorMessage(response, fallback) {
  try {
    const body = await response.json();
    if (body && typeof body.detail === "string" && body.detail) {
      return body.detail;
    }
  } catch (error) {
    // Body wasn't JSON or didn't parse -- fall through to the default.
  }
  return fallback;
}

function updateScenarioDescription(scenarioId) {
  const descriptionEl = document.getElementById("scenario-description");
  const scenario = scenariosById[scenarioId];
  descriptionEl.textContent = scenario ? scenario.description : "";
}

async function loadScenarios() {
  const select = document.getElementById("scenario-select");
  const startBtn = document.getElementById("start-scenario-btn");

  try {
    const response = await fetch("/api/scenarios");
    if (!response.ok) {
      throw new Error("scenario list failed");
    }
    const scenarios = await response.json();

    scenariosById = {};
    select.innerHTML = "";
    scenarios.forEach((scenario) => {
      scenariosById[scenario.id] = scenario;
      const option = document.createElement("option");
      option.value = scenario.id;
      option.textContent = scenario.title + " (" + scenario.segment_count + " segments)";
      select.appendChild(option);
    });

    select.disabled = scenarios.length === 0;
    startBtn.disabled = scenarios.length === 0;

    if (scenarios.length > 0) {
      updateScenarioDescription(scenarios[0].id);
    }
  } catch (error) {
    showScenarioError("Unable to load scenarios right now. Try reloading the page.");
    select.innerHTML = "<option>Unavailable</option>";
  }

  select.addEventListener("change", () => updateScenarioDescription(select.value));
}

// -- Memory mode ----------------------------------------------------------

function selectedMemoryMode() {
  const checked = document.querySelector('input[name="memory-mode"]:checked');
  return checked ? checked.value : "off";
}

function setMemoryModeControlsEnabled(enabled) {
  document.querySelectorAll('input[name="memory-mode"]').forEach((input) => {
    input.disabled = !enabled;
  });
}

function memoryModeDisplayLabel(run) {
  const modeText = run.memory_mode === "on" ? "Memory ON" : "Memory OFF";
  // M5D: a run created as the opposite-condition replay of an already-
  // completed run is a "comparison run" for its whole lifetime -- this
  // is set from the moment it's created (see comparison_id below), not
  // only once it finishes.
  return run.comparison_id ? "Comparison run: " + modeText : "Memory: " + modeText;
}

// -- Run flow ------------------------------------------------------------

function roleLabel(segment) {
  return segment.role_label || segment.role;
}

function renderConversationTurn(turn) {
  const wrapper = document.createElement("div");
  wrapper.className = "conversation-turn";

  const roleP = document.createElement("p");
  roleP.className = "segment-role";
  roleP.textContent = roleLabel(turn);

  const userLabel = document.createElement("p");
  userLabel.className = "turn-speaker";
  userLabel.textContent = "User / Scenario";

  const userText = document.createElement("p");
  userText.className = "segment-text";
  userText.textContent = turn.user_text;

  const assistantLabel = document.createElement("p");
  assistantLabel.className = "turn-speaker";
  assistantLabel.textContent = "Assistant";

  const assistantText = document.createElement("p");
  if (turn.error) {
    assistantText.className = "assistant-text status-error";
    assistantText.textContent = turn.error;
  } else if (turn.assistant_text) {
    assistantText.className = "assistant-text";
    assistantText.textContent = turn.assistant_text;
  } else {
    assistantText.className = "assistant-text status-detail";
    assistantText.textContent = "(no response)";
  }

  wrapper.appendChild(roleP);
  wrapper.appendChild(userLabel);
  wrapper.appendChild(userText);
  wrapper.appendChild(assistantLabel);
  wrapper.appendChild(assistantText);
  return wrapper;
}

function renderRunState(run) {
  currentRunId = run.run_id;

  const runView = document.getElementById("run-view");
  const progressEl = document.getElementById("run-progress");
  const memoryModeLabel = document.getElementById("run-memory-mode-label");
  const currentCard = document.getElementById("current-segment-card");
  const roleEl = document.getElementById("current-segment-role");
  const textEl = document.getElementById("current-segment-text");
  const completedMessage = document.getElementById("completed-message");
  const runErrorEl = document.getElementById("run-error");
  const compareBtn = document.getElementById("compare-alternate-btn");
  const startAnotherBtn = document.getElementById("start-another-btn");
  const conversationEl = document.getElementById("conversation");

  runView.hidden = false;
  progressEl.textContent =
    "Segment " + run.current_segment_number + " of " + run.total_segments;
  memoryModeLabel.textContent = memoryModeDisplayLabel(run);

  conversationEl.innerHTML = "";
  run.transcript.forEach((turn) => {
    conversationEl.appendChild(renderConversationTurn(turn));
  });

  if (run.failed) {
    currentCard.hidden = true;
    completedMessage.hidden = true;
    runErrorEl.hidden = false;
    runErrorEl.textContent = run.error || "The run stopped after an error.";
    compareBtn.hidden = true;
    startAnotherBtn.hidden = false;
    if (run.comparison_id) {
      // The alternate condition failed -- the pair can never become a
      // complete comparison. Say so plainly rather than showing a
      // partial or misleading side-by-side view.
      showComparisonStatusNote(
        "This comparison could not be completed because one of the two runs failed."
      );
    } else {
      hideComparisonPanel();
    }
  } else if (run.completed) {
    currentCard.hidden = true;
    completedMessage.hidden = false;
    runErrorEl.hidden = true;
    startAnotherBtn.hidden = false;
    if (run.comparison_id) {
      // This run is one half of a pair -- fetch and (once the other
      // half is also done) reveal the comparison. Offering a second
      // "Compare with ..." action here would attempt to pair a third
      // run, which the backend rejects.
      compareBtn.hidden = true;
      loadComparison(run.comparison_id);
    } else {
      showCompareButton(run.memory_mode);
      hideComparisonPanel();
    }
  } else {
    completedMessage.hidden = true;
    runErrorEl.hidden = true;
    compareBtn.hidden = true;
    startAnotherBtn.hidden = true;
    currentCard.hidden = false;
    roleEl.textContent = roleLabel(run.current_segment);
    textEl.textContent = run.current_segment.text;
  }
}

// Shared by the built-in scenario path (M5B/M5C) and the M5F "Create
// your own" wizard's Step 6: once a scenario id is resolvable by the
// backend (a BUILTIN_SCENARIOS key, or a frozen custom scenario's
// runnable id), starting a run works identically either way -- this
// is the one function that calls `POST /api/runs`, so there is no
// separate custom-scenario run path to keep in sync with this one.
async function startRunForScenario(scenarioId, triggerBtn) {
  clearScenarioError();
  if (triggerBtn) {
    if (triggerBtn.disabled) {
      return;
    }
    triggerBtn.disabled = true;
  }

  try {
    const response = await fetch("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        scenario_id: scenarioId,
        memory_mode: selectedMemoryMode(),
      }),
    });
    if (!response.ok) {
      const message = await extractErrorMessage(
        response,
        "Unable to start that scenario right now. Please try again."
      );
      showScenarioError(message);
      return;
    }
    const run = await response.json();
    setMemoryModeControlsEnabled(false);
    hideComparisonPanel();
    renderRunState(run);
  } catch (error) {
    showScenarioError("Unable to reach the backend right now. Please try again.");
  } finally {
    if (triggerBtn) {
      triggerBtn.disabled = false;
    }
  }
}

function startBuiltinScenario() {
  const select = document.getElementById("scenario-select");
  const startBtn = document.getElementById("start-scenario-btn");
  return startRunForScenario(select.value, startBtn);
}

function startWizardScenario() {
  const startBtn = document.getElementById("wizard-start-run-btn");
  if (!wizardRunnableScenarioId) {
    showScenarioError("Freeze the custom scenario before starting a comparison run.");
    return;
  }
  return startRunForScenario(wizardRunnableScenarioId, startBtn);
}

// M5G: `next-segment-btn` is disabled for the whole request (blocking
// both a rapid double-click and a keyboard-triggered repeat while a
// real provider call is in flight) and re-enabled only in `finally`,
// so it comes back whether the call succeeds, fails, or throws --
// never left stuck disabled, and never re-enabled early while a
// request is still outstanding. The visible "Waiting for model..."
// text is the same disabled window made visible, so a real (slow)
// provider call reads as "in progress," not as a stuck or broken page.
async function advanceSegment() {
  const nextBtn = document.getElementById("next-segment-btn");
  const waitingText = document.getElementById("run-waiting-text");
  clearScenarioError();
  if (!currentRunId || nextBtn.disabled) {
    return;
  }
  nextBtn.disabled = true;
  waitingText.hidden = false;

  try {
    const response = await fetch("/api/runs/" + currentRunId + "/advance", {
      method: "POST",
    });
    if (!response.ok) {
      const message = await extractErrorMessage(
        response,
        "Unable to advance the scenario right now. Please try again."
      );
      showScenarioError(message);
      return;
    }
    const run = await response.json();
    renderRunState(run);
  } catch (error) {
    showScenarioError("Unable to reach the backend right now. Please try again.");
  } finally {
    nextBtn.disabled = false;
    waitingText.hidden = true;
  }
}

// -- M5D: controlled comparison -------------------------------------------

function showCompareButton(currentMode) {
  const btn = document.getElementById("compare-alternate-btn");
  const alternateMode = currentMode === "on" ? "off" : "on";
  btn.textContent = "Compare with Memory " + (alternateMode === "on" ? "ON" : "OFF");
  btn.hidden = false;
}

async function compareAlternate() {
  const btn = document.getElementById("compare-alternate-btn");
  clearScenarioError();
  if (!currentRunId || btn.disabled) {
    return;
  }
  btn.disabled = true;

  try {
    const response = await fetch("/api/runs/" + currentRunId + "/alternate", {
      method: "POST",
    });
    if (!response.ok) {
      const message = await extractErrorMessage(
        response,
        "Unable to start the comparison run right now. Please try again."
      );
      showScenarioError(message);
      return;
    }
    const run = await response.json();
    hideComparisonPanel();
    renderRunState(run);
  } catch (error) {
    showScenarioError("Unable to reach the backend right now. Please try again.");
  } finally {
    btn.disabled = false;
  }
}

function hideComparisonPanel() {
  document.getElementById("comparison-panel").hidden = true;
  document.getElementById("comparison-status-note").hidden = true;
}

function showComparisonStatusNote(message) {
  document.getElementById("comparison-segments").innerHTML = "";
  document.getElementById("comparison-summary").textContent = "";
  const noteEl = document.getElementById("comparison-status-note");
  noteEl.textContent = message;
  noteEl.hidden = false;
  document.getElementById("comparison-panel").hidden = false;
}

// M5G: `modifierClass` gives the OFF and ON columns a distinct, purely
// visual accent (see `.comparison-column-off` / `.comparison-column-on`
// in styles.css) so the two conditions are easier to tell apart at a
// glance -- it carries no meaning about which response is preferable.
function renderComparisonColumn(label, text, modifierClass) {
  const column = document.createElement("div");
  column.className = "comparison-column " + modifierClass;

  const labelP = document.createElement("p");
  labelP.className = "turn-speaker";
  labelP.textContent = label;

  const textP = document.createElement("p");
  textP.className = "assistant-text";
  textP.textContent = text || "(no response)";

  column.appendChild(labelP);
  column.appendChild(textP);
  return column;
}

function renderComparisonSegment(segment) {
  const wrapper = document.createElement("div");
  wrapper.className = "comparison-segment";

  const roleP = document.createElement("p");
  roleP.className = "segment-role";
  roleP.textContent = segment.role_label;

  const textP = document.createElement("p");
  textP.className = "segment-text";
  textP.textContent = segment.text;

  const columns = document.createElement("div");
  columns.className = "comparison-columns";
  columns.appendChild(
    renderComparisonColumn("Memory OFF", segment.off_assistant_text, "comparison-column-off")
  );
  columns.appendChild(
    renderComparisonColumn("Memory ON", segment.on_assistant_text, "comparison-column-on")
  );

  wrapper.appendChild(roleP);
  wrapper.appendChild(textP);
  wrapper.appendChild(columns);
  return wrapper;
}

function renderComparison(comparison) {
  if (comparison.status !== "ready") {
    // Not both sides are done yet (or the pairing hasn't produced a
    // usable state for some other reason) -- an incomplete comparison
    // is never shown as though it were complete.
    hideComparisonPanel();
    return;
  }

  const panel = document.getElementById("comparison-panel");
  const summaryEl = document.getElementById("comparison-summary");
  const noteEl = document.getElementById("comparison-status-note");
  const segmentsEl = document.getElementById("comparison-segments");

  summaryEl.textContent =
    comparison.scenario_title +
    " — " +
    comparison.target_model +
    " — Memory OFF vs Memory ON — " +
    comparison.total_segments +
    " segments, completed — controlled comparison (same scenario, fresh runs)";
  noteEl.hidden = true;
  noteEl.textContent = "";

  segmentsEl.innerHTML = "";
  comparison.segments.forEach((segment) => {
    segmentsEl.appendChild(renderComparisonSegment(segment));
  });

  panel.hidden = false;
}

async function loadComparison(comparisonId) {
  try {
    const response = await fetch("/api/comparisons/" + comparisonId);
    if (!response.ok) {
      return;
    }
    const comparison = await response.json();
    renderComparison(comparison);
  } catch (error) {
    // The per-run conversation view above is still available even if
    // this fetch fails -- fail quietly rather than blocking the page.
  }
}

function resetRunView() {
  currentRunId = null;
  document.getElementById("run-view").hidden = true;
  document.getElementById("conversation").innerHTML = "";
  document.getElementById("completed-message").hidden = true;
  document.getElementById("current-segment-card").hidden = true;
  document.getElementById("run-waiting-text").hidden = true;
  document.getElementById("run-error").hidden = true;
  document.getElementById("compare-alternate-btn").hidden = true;
  document.getElementById("start-another-btn").hidden = true;
  hideComparisonPanel();
  setMemoryModeControlsEnabled(true);
  clearScenarioError();
}

function wireScenarioControls() {
  document.getElementById("start-scenario-btn").addEventListener("click", startBuiltinScenario);
  document.getElementById("next-segment-btn").addEventListener("click", advanceSegment);
  document.getElementById("compare-alternate-btn").addEventListener("click", compareAlternate);
  document.getElementById("start-another-btn").addEventListener("click", resetRunView);
}

// -- M5F: Scenario Wizard / Bring Your Own Story --------------------------
//
// Generate (local, no AI call) -> paste -> review/edit -> freeze ->
// compare. `wizardCustomScenarioId` is the process-local draft id from
// `POST /api/custom-scenarios`; `wizardRunnableScenarioId` is set only
// once that draft is frozen, and is exactly the `scenario_id` passed to
// `POST /api/runs` by `startWizardScenario` above -- a frozen custom
// scenario runs through the *same* `startRunForScenario` (and so the
// same controlled-comparison flow) as any built-in scenario.

let wizardCustomScenarioId = null;
let wizardRunnableScenarioId = null;

function scenarioSource() {
  const checked = document.querySelector('input[name="scenario-source"]:checked');
  return checked ? checked.value : "builtin";
}

function showWizardStep(stepNumber) {
  document.getElementById("wizard-step-" + stepNumber).hidden = false;
}

function wireScenarioSourceControls() {
  document.querySelectorAll('input[name="scenario-source"]').forEach((input) => {
    input.addEventListener("change", () => {
      const source = scenarioSource();
      document.getElementById("builtin-scenario-controls").hidden = source !== "builtin";
      document.getElementById("wizard-panel").hidden = source !== "custom";
      resetRunView();
    });
  });
}

function wizardIngredientsPayload() {
  const form = document.getElementById("wizard-ingredients-form");
  const data = new FormData(form);
  const payload = {};
  data.forEach((value, key) => {
    payload[key] = value;
  });
  return payload;
}

async function submitWizardIngredients(event) {
  event.preventDefault();
  const errorEl = document.getElementById("wizard-ingredients-error");
  const generateBtn = document.getElementById("wizard-generate-prompt-btn");
  errorEl.hidden = true;
  errorEl.textContent = "";
  generateBtn.disabled = true;

  try {
    const response = await fetch("/api/scenario-wizard/prompt", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(wizardIngredientsPayload()),
    });
    if (!response.ok) {
      const message = await extractErrorMessage(
        response,
        "Unable to generate a prompt from those ingredients. Every field above is required."
      );
      errorEl.textContent = message;
      errorEl.hidden = false;
      return;
    }
    const body = await response.json();
    document.getElementById("wizard-prompt-output").value = body.prompt;
    document.getElementById("wizard-copy-status").hidden = true;
    showWizardStep(2);
  } catch (error) {
    errorEl.textContent = "Unable to reach the backend right now. Please try again.";
    errorEl.hidden = false;
  } finally {
    generateBtn.disabled = false;
  }
}

// Browser clipboard API, with a graceful fallback for browsers/contexts
// where it isn't available (e.g. no `navigator.clipboard`, or a
// non-secure context): falls back to selecting the text so the user can
// copy it manually (Ctrl/Cmd+C), rather than failing silently.
async function copyWizardPrompt() {
  const textarea = document.getElementById("wizard-prompt-output");
  const statusEl = document.getElementById("wizard-copy-status");

  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(textarea.value);
      statusEl.textContent = "Copied to clipboard.";
    } else {
      throw new Error("Clipboard API unavailable");
    }
  } catch (error) {
    textarea.focus();
    textarea.select();
    statusEl.textContent = "Prompt text selected -- copy it with Ctrl/Cmd+C.";
  }
  statusEl.hidden = false;
}

function renderWizardValidationReport(issues) {
  const container = document.getElementById("wizard-validation-report");
  container.innerHTML = "";
  if (!issues || issues.length === 0) {
    container.hidden = true;
    return;
  }

  const list = document.createElement("ul");
  list.className = "validation-issue-list";
  issues.forEach((issue) => {
    const item = document.createElement("li");
    item.textContent = issue.message;
    list.appendChild(item);
  });
  container.appendChild(list);
  container.hidden = false;
}

function renderWizardSegmentEditors(segments) {
  const container = document.getElementById("wizard-segment-editors");
  container.innerHTML = "";
  segments.forEach((segment) => {
    const wrapper = document.createElement("div");
    wrapper.className = "wizard-segment-editor";

    const label = document.createElement("label");
    label.setAttribute("for", "wizard-segment-" + segment.role);
    label.textContent = segment.role_label;

    const textarea = document.createElement("textarea");
    textarea.id = "wizard-segment-" + segment.role;
    textarea.dataset.role = segment.role;
    textarea.value = segment.text;

    wrapper.appendChild(label);
    wrapper.appendChild(textarea);
    container.appendChild(wrapper);
  });
}

async function parseWizardPaste() {
  const pasteInput = document.getElementById("wizard-paste-input");
  const titleInput = document.getElementById("wizard-draft-title");
  const parseBtn = document.getElementById("wizard-parse-btn");
  parseBtn.disabled = true;

  try {
    const response = await fetch("/api/custom-scenarios", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        pasted_text: pasteInput.value,
        title: titleInput.value,
      }),
    });
    const body = await response.json();
    if (!response.ok) {
      const issues = (body && body.detail && body.detail.issues) || [];
      renderWizardValidationReport(issues);
      return;
    }

    renderWizardValidationReport([]);
    wizardCustomScenarioId = body.custom_scenario_id;
    document.getElementById("wizard-review-status").textContent =
      "Parsed successfully -- all seven segments found.";
    renderWizardSegmentEditors(body.segments);
    showWizardStep(4);
  } catch (error) {
    renderWizardValidationReport([
      { code: "network_error", message: "Unable to reach the backend right now. Please try again." },
    ]);
  } finally {
    parseBtn.disabled = false;
  }
}

function collectWizardSegmentEdits() {
  const segments = {};
  document.querySelectorAll("#wizard-segment-editors textarea").forEach((textarea) => {
    segments[textarea.dataset.role] = textarea.value;
  });
  return segments;
}

async function saveWizardEdits() {
  if (!wizardCustomScenarioId) {
    return;
  }
  const saveBtn = document.getElementById("wizard-save-edits-btn");
  const statusEl = document.getElementById("wizard-review-status");
  saveBtn.disabled = true;

  try {
    const response = await fetch("/api/custom-scenarios/" + wizardCustomScenarioId, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ segments: collectWizardSegmentEdits() }),
    });
    const body = await response.json();
    if (!response.ok) {
      statusEl.textContent = "Unable to save edits right now. Please try again.";
      return;
    }
    statusEl.textContent = body.valid
      ? "Edits saved -- all seven segments look complete."
      : "Edits saved, but some segments still need text before this can be frozen.";
    renderWizardValidationReport(body.issues);
    showWizardStep(5);
  } catch (error) {
    statusEl.textContent = "Unable to reach the backend right now. Please try again.";
  } finally {
    saveBtn.disabled = false;
  }
}

async function freezeWizardScenario() {
  if (!wizardCustomScenarioId) {
    return;
  }
  const freezeBtn = document.getElementById("wizard-freeze-btn");
  const statusEl = document.getElementById("wizard-freeze-status");
  freezeBtn.disabled = true;

  try {
    const response = await fetch(
      "/api/custom-scenarios/" + wizardCustomScenarioId + "/freeze",
      { method: "POST" }
    );
    const body = await response.json();
    if (!response.ok) {
      statusEl.className = "status-text status-error";
      statusEl.textContent =
        "This scenario is not ready to freeze yet -- see the issues listed in Step 4.";
      statusEl.hidden = false;
      const issues = (body && body.detail && body.detail.issues) || [];
      renderWizardValidationReport(issues);
      return;
    }

    wizardRunnableScenarioId = body.runnable_scenario_id;
    document.querySelectorAll("#wizard-segment-editors textarea").forEach((textarea) => {
      textarea.disabled = true;
    });
    document.getElementById("wizard-save-edits-btn").disabled = true;
    statusEl.className = "status-text status-ok";
    statusEl.textContent = "Frozen. This scenario's text is now fixed and ready to run.";
    statusEl.hidden = false;
    showWizardStep(6);
  } catch (error) {
    statusEl.className = "status-text status-error";
    statusEl.textContent = "Unable to reach the backend right now. Please try again.";
    statusEl.hidden = false;
  } finally {
    freezeBtn.disabled = false;
  }
}

function wireWizardControls() {
  document
    .getElementById("wizard-ingredients-form")
    .addEventListener("submit", submitWizardIngredients);
  document.getElementById("wizard-copy-prompt-btn").addEventListener("click", copyWizardPrompt);
  document.getElementById("wizard-parse-btn").addEventListener("click", parseWizardPaste);
  document.getElementById("wizard-save-edits-btn").addEventListener("click", saveWizardEdits);
  document.getElementById("wizard-freeze-btn").addEventListener("click", freezeWizardScenario);
  document.getElementById("wizard-start-run-btn").addEventListener("click", startWizardScenario);
}

document.addEventListener("DOMContentLoaded", () => {
  loadStatus();
  loadScenarios();
  wireScenarioControls();
  wireScenarioSourceControls();
  wireWizardControls();
});
