(() => {
  const messageDiv = document.createElement('div');
  messageDiv.id = 'message';
  document.body.appendChild(messageDiv);
  let lastMessageDisappearTime = 0;
  window.Message = (content) => {
    const div = document.createElement('div');
    div.innerHTML = `<div>${content}</div>`;
    messageDiv.appendChild(div);
    const now = new Date().getTime();
    const timeout = Math.max(3000, lastMessageDisappearTime - now);
    lastMessageDisappearTime = now + timeout + 600;
    setTimeout(() => {
      div.style.marginTop = '-58px';
      setTimeout(() => {
        messageDiv.removeChild(div)
      }, 500);
    }, timeout);
  };
})();
