// M5A/M5B/M5C frontend behavior.
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
// User/Scenario + Assistant conversation. This page never renders any
// system/background message, the memory payload, or any private
// artifact detail -- only the scenario's own segment text and the
// model's reply to it, exactly as the API returns them.

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
  const startAnotherBtn = document.getElementById("start-another-btn");
  const conversationEl = document.getElementById("conversation");

  runView.hidden = false;
  progressEl.textContent =
    "Segment " + run.current_segment_number + " of " + run.total_segments;
  memoryModeLabel.textContent = "Memory: " + (run.memory_mode === "on" ? "ON" : "OFF");

  conversationEl.innerHTML = "";
  run.transcript.forEach((turn) => {
    conversationEl.appendChild(renderConversationTurn(turn));
  });

  if (run.failed) {
    currentCard.hidden = true;
    completedMessage.hidden = true;
    runErrorEl.hidden = false;
    runErrorEl.textContent = run.error || "The run stopped after an error.";
    startAnotherBtn.hidden = false;
  } else if (run.completed) {
    currentCard.hidden = true;
    completedMessage.hidden = false;
    runErrorEl.hidden = true;
    startAnotherBtn.hidden = false;
  } else {
    completedMessage.hidden = true;
    runErrorEl.hidden = true;
    startAnotherBtn.hidden = true;
    currentCard.hidden = false;
    roleEl.textContent = roleLabel(run.current_segment);
    textEl.textContent = run.current_segment.text;
  }
}

async function startScenario() {
  const select = document.getElementById("scenario-select");
  const startBtn = document.getElementById("start-scenario-btn");
  clearScenarioError();
  startBtn.disabled = true;

  try {
    const response = await fetch("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        scenario_id: select.value,
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
    renderRunState(run);
  } catch (error) {
    showScenarioError("Unable to reach the backend right now. Please try again.");
  } finally {
    startBtn.disabled = false;
  }
}

async function advanceSegment() {
  const nextBtn = document.getElementById("next-segment-btn");
  clearScenarioError();
  if (!currentRunId) {
    return;
  }
  nextBtn.disabled = true;

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
  }
}

function resetRunView() {
  currentRunId = null;
  document.getElementById("run-view").hidden = true;
  document.getElementById("conversation").innerHTML = "";
  document.getElementById("completed-message").hidden = true;
  document.getElementById("current-segment-card").hidden = true;
  document.getElementById("run-error").hidden = true;
  document.getElementById("start-another-btn").hidden = true;
  setMemoryModeControlsEnabled(true);
  clearScenarioError();
}

function wireScenarioControls() {
  document.getElementById("start-scenario-btn").addEventListener("click", startScenario);
  document.getElementById("next-segment-btn").addEventListener("click", advanceSegment);
  document.getElementById("start-another-btn").addEventListener("click", resetRunView);
}

document.addEventListener("DOMContentLoaded", () => {
  loadStatus();
  loadScenarios();
  wireScenarioControls();
});
