const API_BASE = (window.APP_CONFIG && window.APP_CONFIG.API_BASE) || "http://127.0.0.1:8000";

const sendBtn = document.getElementById("send-btn");
const userInput = document.getElementById("user-input");
const messagesContainer = document.getElementById("messages");
const chatListEl = document.getElementById("chat-list");
const btnNewChat = document.querySelector(".btn-new-chat");

const TEXTAREA_MAX_HEIGHT = 200;

let currentChatId = null;

function resizeTextarea() {
    userInput.style.height = "auto";
    const h = Math.min(userInput.scrollHeight, TEXTAREA_MAX_HEIGHT);
    userInput.style.height = h + "px";
    userInput.style.overflowY = h >= TEXTAREA_MAX_HEIGHT ? "auto" : "hidden";
}

function apiUrl(path) {
    return `${API_BASE}${path}`;
}

function escapeHtml(s) {
    const div = document.createElement("div");
    div.textContent = s;
    return div.innerHTML;
}

function escapeAttr(s) {
    return escapeHtml(s).replace(/"/g, "&quot;");
}

async function loadChats() {
    try {
        const res = await fetch(apiUrl("/api/chats"));
        const chats = await res.json();
        chatListEl.innerHTML = chats
            .map(
                (c) =>
                    `<button type="button" class="chat-item" data-chat-id="${c.id}" title="${escapeAttr(c.title)}">${escapeHtml(c.title)}</button>`
            )
            .join("");

        chatListEl.querySelectorAll(".chat-item").forEach((btn) => {
            btn.addEventListener("click", () => selectChat(btn.dataset.chatId));
        });

        if (currentChatId) {
            chatListEl.querySelector(`[data-chat-id="${currentChatId}"]`)?.classList.add("active");
        }
    } catch (_) {
        chatListEl.innerHTML = '<span class="text-muted">Тізім жүктелмеді</span>';
    }
}

async function selectChat(chatId) {
    currentChatId = chatId;
    chatListEl.querySelectorAll(".chat-item").forEach((el) => el.classList.remove("active"));
    chatListEl.querySelector(`[data-chat-id="${chatId}"]`)?.classList.add("active");

    try {
        const res = await fetch(apiUrl(`/api/chats/${chatId}`));
        if (!res.ok) return;
        const data = await res.json();
        messagesContainer.innerHTML = "";
        messagesContainer.classList.remove("empty");
        data.messages.forEach((m) => appendMessage(m.role === "user" ? "user" : "bot", m.content, false));
        scrollToBottom();
    } catch (_) {
        appendMessage("bot", "Қате: сөйлесім жүктелмеді.");
    }
}

function newChat() {
    currentChatId = null;
    chatListEl.querySelectorAll(".chat-item").forEach((el) => el.classList.remove("active"));
    messagesContainer.innerHTML = "";
    messagesContainer.classList.add("empty");
    userInput.value = "";
    userInput.focus();
}

function appendMessage(role, text, scroll = true) {
    messagesContainer.classList.remove("empty");
    const row = document.createElement("div");
    row.className = `message-row ${role}`;
    const inner = document.createElement("div");
    inner.className = "message-inner";
    const msg = document.createElement("div");
    msg.className = "message" + (role === "bot" && text === "Ойлануда..." ? " loading" : "");
    msg.textContent = text;
    inner.appendChild(msg);
    row.appendChild(inner);
    messagesContainer.appendChild(row);
    if (scroll) scrollToBottom();
}

function scrollToBottom() {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

async function handleSend() {
    const query = userInput.value.trim();
    if (!query) return;

    appendMessage("user", query);
    userInput.value = "";
    resizeTextarea();

    appendMessage("bot", "Ойлануда...", true);
    const loadingRow = messagesContainer.querySelector(".message-row.bot:last-child");
    sendBtn.disabled = true;

    try {
        const response = await fetch(apiUrl("/api/chat"), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query, chat_id: currentChatId }),
        });

        const data = await response.json();
        const msgEl = loadingRow.querySelector(".message");
        msgEl.classList.remove("loading");
        msgEl.textContent = data.answer;
        currentChatId = data.chat_id;
        loadChats();
    } catch (_) {
        const msgEl = loadingRow.querySelector(".message");
        msgEl.textContent = "Қате: Сервермен байланыс жоқ.";
        msgEl.classList.remove("loading");
    } finally {
        sendBtn.disabled = false;
        scrollToBottom();
    }
}

sendBtn.addEventListener("click", handleSend);

userInput.addEventListener("input", resizeTextarea);
userInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
    }
});
setTimeout(resizeTextarea, 0);

btnNewChat.addEventListener("click", newChat);

messagesContainer.classList.add("empty");
loadChats();
