const uncertainSave = "This action has not been confirmed as saved. Reload the latest session before retrying; the server may already have saved it.";

export async function requestInventory(baseUrl, path, method = "GET", body, csrf = "") {
  const mutation = method !== "GET";
  let response;
  try {
    response = await fetch(`${baseUrl}/api/v1${path}`, {
      method,
      credentials: "include",
      headers: { "Content-Type": "application/json", ...(csrf ? { "X-CSRF-Token": csrf } : {}) },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
  } catch {
    throw new Error(mutation
      ? `Connection unavailable. ${uncertainSave}`
      : "Connection unavailable. Reconnect and reload to retrieve the latest server state.");
  }

  if (!response.ok) {
    if (response.status === 401) {
      throw new Error("Your sign-in session has expired. Entries in this window have not been cleared. Sign in again, then reload the latest session before retrying.");
    }
    if (response.status === 409) {
      throw new Error("This session changed in another window or is no longer editable. Entries in this window have not been cleared. Reload the latest version before continuing.");
    }
    if (response.status >= 500) {
      throw new Error(mutation
        ? `Server request failed (${response.status}). ${uncertainSave}`
        : `Server request failed (${response.status}). Reload to retrieve the latest server state.`);
    }
    let detail;
    try {
      const error = await response.json();
      if (typeof error?.detail === "string") detail = error.detail;
    } catch {
      // Error responses may be HTML from a proxy rather than the API's JSON.
    }
    throw new Error(detail ?? `Request rejected (${response.status}). Entries in this window have not been cleared.`);
  }

  try {
    return await response.json();
  } catch {
    throw new Error(mutation
      ? `The server response could not be read. ${uncertainSave}`
      : "The server response could not be read. Reload to retrieve the latest server state.");
  }
}
