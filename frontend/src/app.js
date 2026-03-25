const API_BASE = (window.APP_CONFIG && window.APP_CONFIG.API_BASE) || "http://127.0.0.1:8000";

const sendBtn = document.getElementById("send-btn");
const userInput = document.getElementById("user-input");
const messagesContainer = document.getElementById("messages");
const chatListEl = document.getElementById("chat-list");
const btnNewChat = document.querySelector(".btn-new-chat");
const chatTitleEl = document.getElementById("chat-title");

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

function formatTime() {
    const now = new Date();
    return now.getHours().toString().padStart(2, "0") + ":" + now.getMinutes().toString().padStart(2, "0");
}

async function loadChats() {
    try {
        const res = await fetch(apiUrl("/api/chats"));
        const chats = await res.json();
        chatListEl.innerHTML = chats
            .map(
                (c) =>
                    `<div class="chat-item-wrapper" style="position:relative;display:flex;align-items:center;">
                        <button type="button" class="chat-item" data-chat-id="${c.id}" title="${escapeAttr(c.title)}" style="flex:1;">${escapeHtml(c.title)}</button>
                        <button type="button" class="chat-item-delete" data-chat-id="${c.id}" title="Жою">
                            <span class="material-symbols-outlined" style="font-size:16px;">delete</span>
                        </button>
                    </div>`
            )
            .join("");

        chatListEl.querySelectorAll(".chat-item").forEach((btn) => {
            btn.addEventListener("click", () => selectChat(btn.dataset.chatId));
        });

        chatListEl.querySelectorAll(".chat-item-delete").forEach((btn) => {
            btn.addEventListener("click", (e) => {
                e.stopPropagation();
                deleteChat(btn.dataset.chatId);
            });
        });

        if (currentChatId) {
            chatListEl.querySelector(`[data-chat-id="${currentChatId}"]`)?.classList.add("active");
        }
    } catch (_) {
        chatListEl.innerHTML = '<span class="text-sm text-slate-400 px-3 py-2">Тізім жүктелмеді</span>';
    }
}

async function deleteChat(chatId) {
    try {
        await fetch(apiUrl(`/api/chats/${chatId}`), { method: "DELETE" });
        if (currentChatId === chatId) {
            newChat();
        }
        loadChats();
    } catch (_) {}
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
        if (data.title) {
            chatTitleEl.textContent = data.title;
        }
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
    chatTitleEl.textContent = "Жаңа сөйлесім";
    userInput.value = "";
    userInput.focus();
}

function appendMessage(role, text, scroll = true) {
    messagesContainer.classList.remove("empty");
    const row = document.createElement("div");
    row.className = `message-row ${role}`;

    const inner = document.createElement("div");
    inner.className = "message-inner";

    const isLoading = role === "bot" && text === "Ойлануда...";

    if (role === "bot") {
        const msg = document.createElement("div");
        msg.className = "message" + (isLoading ? " loading" : "");

        // Header
        const header = document.createElement("div");
        header.className = "bot-message-header";
        header.innerHTML = `
            <div class="icon-box">
                <span class="material-symbols-outlined" style="font-variation-settings: 'FILL' 1;">gavel</span>
            </div>
            <span class="title">Lex AI Кеңесі</span>
        `;
        msg.appendChild(header);

        // Content
        const content = document.createElement("div");
        content.className = "bot-content";
        content.textContent = text;
        msg.appendChild(content);

        // Copy button (not for loading)
        if (!isLoading) {
            const actions = document.createElement("div");
            actions.className = "bot-actions";
            const copyBtn = document.createElement("button");
            copyBtn.innerHTML = '<span class="material-symbols-outlined">content_copy</span> Көшіру';
            copyBtn.addEventListener("click", () => {
                navigator.clipboard.writeText(text);
                copyBtn.innerHTML = '<span class="material-symbols-outlined">check</span> Көшірілді';
                setTimeout(() => {
                    copyBtn.innerHTML = '<span class="material-symbols-outlined">content_copy</span> Көшіру';
                }, 2000);
            });
            actions.appendChild(copyBtn);
            msg.appendChild(actions);
        }

        inner.appendChild(msg);
    } else {
        const msg = document.createElement("div");
        msg.className = "message";
        msg.textContent = text;
        inner.appendChild(msg);
    }

    // Timestamp
    const ts = document.createElement("div");
    ts.className = "msg-timestamp";
    ts.textContent = formatTime();
    inner.appendChild(ts);

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

        // Replace loading message with actual response
        const msg = loadingRow.querySelector(".message");
        msg.classList.remove("loading");

        // Update content
        const content = msg.querySelector(".bot-content");
        content.textContent = data.answer;

        // Add copy button
        const actions = document.createElement("div");
        actions.className = "bot-actions";
        const copyBtn = document.createElement("button");
        copyBtn.innerHTML = '<span class="material-symbols-outlined">content_copy</span> Көшіру';
        copyBtn.addEventListener("click", () => {
            navigator.clipboard.writeText(data.answer);
            copyBtn.innerHTML = '<span class="material-symbols-outlined">check</span> Көшірілді';
            setTimeout(() => {
                copyBtn.innerHTML = '<span class="material-symbols-outlined">content_copy</span> Көшіру';
            }, 2000);
        });
        actions.appendChild(copyBtn);
        msg.appendChild(actions);

        currentChatId = data.chat_id;
        chatTitleEl.textContent = query.length > 50 ? query.slice(0, 50) + "…" : query;
        loadChats();
    } catch (_) {
        const content = loadingRow.querySelector(".bot-content");
        content.textContent = "Қате: Сервермен байланыс жоқ.";
        const msg = loadingRow.querySelector(".message");
        msg.classList.remove("loading");
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
