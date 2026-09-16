// 0.0.0.0 chỉ dùng để bind server; browser không coi đây là origin an toàn cho microphone.
if (location.protocol === "http:" && location.hostname === "0.0.0.0") {
  const safeUrl = new URL(location.href);
  safeUrl.hostname = "127.0.0.1";
  location.replace(safeUrl);
}

const $ = (id) => document.getElementById(id);
let voiceSocket = null;
let audioContext = null;
let mediaStream = null;
let audioProcessor = null;
let recording = false;
let transcriptDraft = "";

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

function showVoiceStatus(message, isError = false) {
  const status = $("voice-status");
  status.textContent = message;
  status.style.color = isError ? "#fca5a5" : "#aebed2";
}

function floatToPcm16(input, inputRate) {
  const ratio = inputRate / 24000;
  const length = Math.round(input.length / ratio);
  const output = new Int16Array(length);
  for (let index = 0; index < length; index += 1) {
    const sourceIndex = Math.min(input.length - 1, Math.round(index * ratio));
    const value = Math.max(-1, Math.min(1, input[sourceIndex]));
    output[index] = value < 0 ? value * 0x8000 : value * 0x7fff;
  }
  return output.buffer;
}

function handleVoiceEvent(data) {
  if (data.type === "session.ready") {
    showVoiceStatus("Đang nghe… nhả nút để tạo transcript.");
  } else if (data.type === "transcript.delta") {
    transcriptDraft += data.delta || "";
    $("voice-transcript").textContent = transcriptDraft;
    $("voice-transcript").classList.remove("hidden");
  } else if (data.type === "transcript.final") {
    transcriptDraft = data.transcript || "";
    $("voice-transcript").textContent = transcriptDraft || "Không nghe rõ.";
    $("voice-transcript").classList.remove("hidden");
    $("message").value = transcriptDraft;
    $("message").focus();
    showVoiceStatus(
      data.stt_latency_ms == null
        ? "Đã có transcript; hãy kiểm tra rồi bấm gửi."
        : `Đã có transcript sau ${data.stt_latency_ms} ms; hãy kiểm tra rồi bấm gửi.`,
    );
    if (voiceSocket?.readyState === WebSocket.OPEN) {
      voiceSocket.send(JSON.stringify({ type: "session.close" }));
    }
  } else if (data.type === "error") {
    showVoiceStatus(data.message || "STT gặp lỗi.", true);
  }
}

async function startVoice() {
  if (recording) return;
  if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
    throw new Error("Microphone chỉ hoạt động trên localhost, 127.0.0.1 hoặc HTTPS.");
  }

  transcriptDraft = "";
  $("voice-transcript").textContent = "";
  $("voice-transcript").classList.add("hidden");
  mediaStream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
  });

  const scheme = location.protocol === "https:" ? "wss" : "ws";
  voiceSocket = new WebSocket(
    `${scheme}://${location.host}/v1/characters/${$("character").value}/voice`,
  );
  voiceSocket.binaryType = "arraybuffer";
  voiceSocket.onopen = () => {
    voiceSocket.send(JSON.stringify({
      type: "session.start",
      session_id: $("session").value.trim() || "demo-session-001",
      api_key: sessionStorage.getItem("historical-api-key") || null,
    }));
  };
  voiceSocket.onmessage = (event) => handleVoiceEvent(JSON.parse(event.data));
  voiceSocket.onerror = () => showVoiceStatus("Không kết nối được WebSocket STT.", true);
  voiceSocket.onclose = () => {
    if (recording) stopVoice(false);
  };

  audioContext = new AudioContext({ sampleRate: 24000 });
  const source = audioContext.createMediaStreamSource(mediaStream);
  audioProcessor = audioContext.createScriptProcessor(4096, 1, 1);
  audioProcessor.onaudioprocess = (event) => {
    if (voiceSocket?.readyState === WebSocket.OPEN) {
      voiceSocket.send(
        floatToPcm16(event.inputBuffer.getChannelData(0), audioContext.sampleRate),
      );
    }
  };
  source.connect(audioProcessor);
  audioProcessor.connect(audioContext.destination);

  recording = true;
  $("mic").classList.add("recording");
  $("mic").setAttribute("aria-pressed", "true");
  $("mic").textContent = "● Đang ghi âm";
  showVoiceStatus("Đang kết nối STT…");
}

async function stopVoice(commit = true) {
  if (!recording && !mediaStream) return;
  recording = false;
  audioProcessor?.disconnect();
  audioProcessor = null;
  if (audioContext) await audioContext.close();
  audioContext = null;
  mediaStream?.getTracks().forEach((track) => track.stop());
  mediaStream = null;

  const commitAudio = () => {
    if (voiceSocket?.readyState === WebSocket.OPEN) {
      voiceSocket.send(JSON.stringify({ type: "input_audio.commit" }));
    }
  };
  if (commit) {
    if (voiceSocket?.readyState === WebSocket.CONNECTING) {
      voiceSocket.addEventListener("open", commitAudio, { once: true });
    } else {
      commitAudio();
    }
    showVoiceStatus("Đang xử lý transcript…");
  }

  $("mic").classList.remove("recording");
  $("mic").setAttribute("aria-pressed", "false");
  $("mic").textContent = "🎙 Giữ để nói";
}

$("save-key").addEventListener("click", async () => {
  sessionStorage.setItem("historical-api-key", $("api-key").value.trim());
  try { await loadCharacters(); } catch (error) { addMessage("assistant", error.message); }
});

$("mic").addEventListener("pointerdown", async (event) => {
  event.preventDefault();
  try {
    await startVoice();
  } catch (error) {
    showVoiceStatus(error.message || String(error), true);
    await stopVoice(false);
  }
});
$("mic").addEventListener("pointerup", (event) => {
  event.preventDefault();
  stopVoice();
});
$("mic").addEventListener("pointerleave", () => {
  if (recording) stopVoice();
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
fetch("/health")
  .then((response) => response.json())
  .then((body) => showVoiceStatus(
    body.stt_configured
      ? "STT đã cấu hình; giữ nút micro để nói."
      : "STT chưa có OPENAI_API_KEY trong .env.",
    !body.stt_configured,
  ))
  .catch(() => showVoiceStatus("Không kiểm tra được trạng thái STT.", true));
