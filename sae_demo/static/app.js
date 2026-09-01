// M5A frontend behavior: on load, check backend health and status, and
// show a clean connected/error indicator. No provider calls, no memory
// access, no scenario logic -- those are not wired to this page yet.

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

document.addEventListener("DOMContentLoaded", loadStatus);
