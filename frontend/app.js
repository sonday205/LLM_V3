const $ = (id) => document.getElementById(id);

function headers() {
  const value = sessionStorage.getItem("historical-api-key") || "";
  return { "Content-Type": "application/json", ...(value ? { "X-API-Key": value } : {}) };
}

function addMessage(role, text, meta = "") {
  const item = document.createElement("article");
  item.className = `message ${role}`;
  const content = document.createElement("div");
  content.textContent = text;
  item.appendChild(content);
  if (meta) {
    const detail = document.createElement("div");
    detail.className = "meta";
    detail.textContent = meta;
    item.appendChild(detail);
  }
  $("messages").appendChild(item);
  $("messages").scrollTop = $("messages").scrollHeight;
}

async function loadCharacters() {
  const response = await fetch("/v1/characters", { headers: headers() });
  if (!response.ok) throw new Error(`Không tải được nhân vật: HTTP ${response.status}`);
  const characters = await response.json();
  $("character").innerHTML = "";
  for (const character of characters) {
    const option = document.createElement("option");
    option.value = character.id;
    option.textContent = `${String(character.sort_order).padStart(2, "0")} · ${character.display_name}`;
    $("character").appendChild(option);
  }
}

$("save-key").addEventListener("click", async () => {
  sessionStorage.setItem("historical-api-key", $("api-key").value.trim());
  try { await loadCharacters(); } catch (error) { addMessage("assistant", error.message); }
});

$("chat-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = $("message").value.trim();
  if (!message) return;
  addMessage("user", message);
  $("message").value = "";
  $("send").disabled = true;
  try {
    const characterId = $("character").value;
    const response = await fetch(`/v1/characters/${characterId}/chat`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({
        session_id: $("session").value.trim() || "demo-session-001",
        message,
        debug: $("debug").checked,
      }),
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || `HTTP ${response.status}`);
    const meta = `${body.model || "local"} · ${body.provider_call_count} provider call · ${body.timings_ms.total} ms`;
    addMessage("assistant", body.answer, meta);
    $("debug-output").textContent = JSON.stringify(body, null, 2);
  } catch (error) {
    addMessage("assistant", `Lỗi: ${error.message}`);
  } finally {
    $("send").disabled = false;
  }
});

$("api-key").value = sessionStorage.getItem("historical-api-key") || "";
loadCharacters().catch((error) => addMessage("assistant", error.message));
