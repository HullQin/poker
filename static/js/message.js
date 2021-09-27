(() => {
  const messageDiv = document.createElement('div');
  messageDiv.id = 'message';
  document.body.appendChild(messageDiv);
  window.Message = (content) => {
    const div = document.createElement('div');
    div.innerHTML = `<div>${content}</div>`;
    messageDiv.appendChild(div);
    setTimeout(() => {
      div.style.marginTop = '-58px';
      setTimeout(() => {
        messageDiv.removeChild(div)
      }, 500);
    }, 3000);
  };
})();
