const chatLog = document.getElementById("chatLog");
const chatForm = document.getElementById("chatForm");
const messageInput = document.getElementById("messageInput");
const statusEl = document.getElementById("status");
const loginBtn = document.getElementById("loginBtn");
const logoutBtn = document.getElementById("logoutBtn");
const userLabel = document.getElementById("userLabel");
const errorBanner = document.getElementById("errorBanner");
const tokenClaims = document.getElementById("tokenClaims");
const claimsBtn = document.getElementById("claimsBtn");

let msalApp;
let authScopes = [];

const setStatus = (text) => {
  statusEl.textContent = text;
};

const setError = (text) => {
  if (!text) {
    errorBanner.hidden = true;
    errorBanner.textContent = "";
    return;
  }
  errorBanner.hidden = false;
  errorBanner.textContent = text;
};

const setClaims = (text) => {
  if (!text) {
    tokenClaims.hidden = true;
    tokenClaims.textContent = "";
    return;
  }
  tokenClaims.hidden = false;
  tokenClaims.textContent = text;
};

const appendMessage = (role, text) => {
  const wrapper = document.createElement("div");
  wrapper.className = `message ${role}`;

  const bubble = document.createElement("div");
  bubble.className = "bubble";

  const para = document.createElement("p");
  para.textContent = text;

  bubble.appendChild(para);
  wrapper.appendChild(bubble);
  chatLog.appendChild(wrapper);
  chatLog.scrollTop = chatLog.scrollHeight;
  return para;
};

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = messageInput.value.trim();
  if (!message) {
    return;
  }

  appendMessage("user", message);
  messageInput.value = "";
  setStatus("Streaming response...");
  setError("");

  try {
    const token = await getAccessToken();
    const headers = {
      "Content-Type": "application/json",
    };

    headers.Authorization = `Bearer ${token}`;

    const response = await fetch("/chat/stream", {
      method: "POST",
      headers,
      body: JSON.stringify({ message }),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || "Request failed");
    }

    const botPara = appendMessage("bot", "");
    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error("Streaming is not supported in this browser.");
    }

    const decoder = new TextDecoder();
    let fullText = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) {
        break;
      }

      const chunk = decoder.decode(value, { stream: true });
      fullText += chunk;
      botPara.textContent = fullText;
      chatLog.scrollTop = chatLog.scrollHeight;
    }

    const count = response.headers.get("X-Resource-Count") || "0";
    setStatus(`Done. Resources analyzed: ${count}.`);
  } catch (error) {
    appendMessage("bot", `Error: ${error.message}`);
    setStatus("Error. Check token and backend logs.");
    setError(error.message);
  }
});

const setAuthState = (account) => {
  if (account) {
    userLabel.textContent = account.username || "Signed in";
    loginBtn.disabled = true;
    logoutBtn.disabled = false;
  } else {
    userLabel.textContent = "Not signed in";
    loginBtn.disabled = false;
    logoutBtn.disabled = true;
    setClaims("");
  }
};

const initAuth = async () => {
  if (typeof window.msal === "undefined") {
    setStatus("Auth init failed: MSAL script not loaded.");
    setError(
      "MSAL failed to load. Check network access to https://alcdn.msauth.net or allowlist it."
    );
    return;
  }

  const response = await fetch("/auth/config");
  const config = await response.json();

  if (config.auth_mode !== "azure_ad") {
    setStatus("Auth disabled in backend.");
    return;
  }

  if (!config.client_id || !config.tenant_id) {
    setStatus("Azure AD not configured. Set AZURE_AD_CLIENT_ID and AZURE_AD_TENANT_ID.");
    setError("Azure AD config is missing. Check server environment variables.");
    return;
  }

  authScopes = config.scopes && config.scopes.length ? config.scopes : [];
  msalApp = new msal.PublicClientApplication({
    auth: {
      clientId: config.client_id,
      authority: `https://login.microsoftonline.com/${config.tenant_id}`,
      redirectUri: "http://localhost:8000",
    },
    cache: {
      cacheLocation: "localStorage",
    },
  });

  await msalApp.initialize();
  try {
    const redirectResult = await msalApp.handleRedirectPromise();
    if (redirectResult?.account) {
      setAuthState(redirectResult.account);
      return;
    }
  } catch (error) {
    setError(`Sign-in failed: ${error.message}`);
  }

  const accounts = msalApp.getAllAccounts();
  setAuthState(accounts[0]);
};

const getAccessToken = async () => {
  if (!msalApp) {
    throw new Error("Auth is not initialized.");
  }

  const account = msalApp.getAllAccounts()[0];
  if (!account) {
    throw new Error("Please sign in first.");
  }

  try {
    const result = await msalApp.acquireTokenSilent({
      account,
      scopes: authScopes,
    });
    return result.accessToken;
  } catch (error) {
    await msalApp.acquireTokenRedirect({ scopes: authScopes });
    throw new Error("Redirecting to sign in...");
  }
};

const decodeJwtClaims = (token) => {
  const parts = token.split(".");
  if (parts.length < 2) {
    throw new Error("Invalid token format.");
  }
  const base64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
  const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), "=");
  const json = atob(padded);
  return JSON.parse(json);
};

loginBtn.addEventListener("click", async () => {
  if (!msalApp) {
    return;
  }
  try {
    await msalApp.loginRedirect({ scopes: authScopes });
  } catch (error) {
    setStatus(`Sign-in failed: ${error.message}`);
    setError(`Sign-in failed: ${error.message}`);
  }
});

logoutBtn.addEventListener("click", async () => {
  if (!msalApp) {
    return;
  }
  const account = msalApp.getAllAccounts()[0];
  if (!account) {
    return;
  }
  await msalApp.logoutRedirect({ account });
});

claimsBtn.addEventListener("click", async () => {
  setError("");
  try {
    const token = await getAccessToken();
    const claims = decodeJwtClaims(token);
    setClaims(`aud: ${claims.aud} | iss: ${claims.iss}`);
  } catch (error) {
    setError(`Token claims failed: ${error.message}`);
  }
});

initAuth().catch((error) => {
  setStatus(`Auth init failed: ${error.message}`);
  setError(`Auth init failed: ${error.message}`);
});
