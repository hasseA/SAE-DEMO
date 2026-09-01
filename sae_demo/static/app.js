// M5A/M5B frontend behavior.
//
// M5A: on load, check backend health and status, show a connected/error
// indicator.
//
// M5B: list the built-in synthetic scenarios, start an in-memory,
// Memory-OFF, frozen-mode run, and advance through it one segment at a
// time. No provider call and no memory access happen anywhere on this
// page -- every segment's response area is labeled as coming in a
// later stage rather than showing any real or simulated model output.

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

// -- Run flow ------------------------------------------------------------

function roleLabel(segment) {
  return segment.role_label || segment.role;
}

function renderRunState(run) {
  currentRunId = run.run_id;

  const runView = document.getElementById("run-view");
  const progressEl = document.getElementById("run-progress");
  const currentCard = document.getElementById("current-segment-card");
  const roleEl = document.getElementById("current-segment-role");
  const textEl = document.getElementById("current-segment-text");
  const completedMessage = document.getElementById("completed-message");
  const transcriptEl = document.getElementById("transcript");

  runView.hidden = false;
  progressEl.textContent =
    "Segment " + run.current_segment_number + " of " + run.total_segments;

  transcriptEl.innerHTML = "";
  run.transcript.forEach((segment) => {
    const card = document.createElement("div");
    card.className = "segment-card";

    const roleP = document.createElement("p");
    roleP.className = "segment-role";
    roleP.textContent = roleLabel(segment);

    const textP = document.createElement("p");
    textP.className = "segment-text";
    textP.textContent = segment.text;

    const noteP = document.createElement("p");
    noteP.className = "model-response-note";
    noteP.textContent = "Model response will appear in M5C";

    card.appendChild(roleP);
    card.appendChild(textP);
    card.appendChild(noteP);
    transcriptEl.appendChild(card);
  });

  if (run.completed) {
    currentCard.hidden = true;
    completedMessage.hidden = false;
  } else {
    completedMessage.hidden = true;
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
      body: JSON.stringify({ scenario_id: select.value }),
    });
    if (!response.ok) {
      throw new Error("start run failed");
    }
    const run = await response.json();
    renderRunState(run);
  } catch (error) {
    showScenarioError("Unable to start that scenario right now. Please try again.");
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
      throw new Error("advance failed");
    }
    const run = await response.json();
    renderRunState(run);
  } catch (error) {
    showScenarioError("Unable to advance the scenario right now. Please try again.");
  } finally {
    nextBtn.disabled = false;
  }
}

function resetRunView() {
  currentRunId = null;
  document.getElementById("run-view").hidden = true;
  document.getElementById("transcript").innerHTML = "";
  document.getElementById("completed-message").hidden = true;
  document.getElementById("current-segment-card").hidden = true;
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
