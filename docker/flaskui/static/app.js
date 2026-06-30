(() => {
  const tabs = Array.from(document.querySelectorAll('.tab'));
  const panels = Array.from(document.querySelectorAll('.tab-panel'));

  function activateTab(name) {
    tabs.forEach((tab) => tab.classList.toggle('is-active', tab.dataset.tab === name));
    panels.forEach((panel) => panel.classList.toggle('is-active', panel.dataset.panel === name));
  }

  tabs.forEach((tab) => {
    tab.addEventListener('click', () => activateTab(tab.dataset.tab));
  });

  const chatForm = document.getElementById('chat-form');
  const chatLog = document.getElementById('chat-log');
  const modelSelect = document.getElementById('chat-model-select');
  const customModelInput = document.getElementById('chat-custom-model');
  const messageInput = document.getElementById('chat-message');
  const sendBtn = document.getElementById('chat-send-btn');
  const settingsModel = document.getElementById('settings-model');

  if (!chatForm || !chatLog || !messageInput) {
    return;
  }

  function appendBubble(role, text, streaming = false) {
    const article = document.createElement('article');
    article.className = `msg msg-${role}`;
    const p = document.createElement('p');
    p.textContent = text;
    article.appendChild(p);
    if (streaming) {
      article.dataset.streaming = '1';
    }
    chatLog.appendChild(article);
    chatLog.scrollTop = chatLog.scrollHeight;
    return p;
  }

  async function persistChat(characterId, userText, assistantText) {
    await fetch(`/api/chat/store/${encodeURIComponent(characterId)}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ user: userText, assistant: assistantText })
    });
  }

  chatForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const characterId = chatLog.dataset.characterId;
    if (!characterId) {
      return;
    }

    const message = messageInput.value.trim();
    if (!message) {
      return;
    }

    const chosenModel = (customModelInput.value || modelSelect.value || '').trim();
    if (settingsModel) {
      settingsModel.textContent = chosenModel || 'n/a';
    }

    appendBubble('user', message);
    const assistantP = appendBubble('assistant', '', true);

    sendBtn.disabled = true;
    messageInput.value = '';

    let fullText = '';

    try {
      const response = await fetch(`/api/chat/stream/${encodeURIComponent(characterId)}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          message,
          model: chosenModel
        })
      });

      if (!response.ok || !response.body) {
        const text = await response.text();
        assistantP.textContent = `Fel: ${text || response.statusText}`;
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          break;
        }
        const chunk = decoder.decode(value, { stream: true });
        fullText += chunk;
        assistantP.textContent = fullText;
        chatLog.scrollTop = chatLog.scrollHeight;
      }

      if (fullText.startsWith('[ERROR]')) {
        assistantP.textContent = fullText;
      } else {
        try {
          await persistChat(characterId, message, fullText.trim());
        } catch (err) {
          console.error('Could not persist chat history', err);
        }
      }
    } catch (err) {
      assistantP.textContent = `Fel: ${err}`;
    } finally {
      sendBtn.disabled = false;
      messageInput.focus();
    }
  });
})();
