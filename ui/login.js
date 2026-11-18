'use strict';
const form = document.querySelector('#login-form');
const input = document.querySelector('#password');
const button = document.querySelector('#login-button');
const error = document.querySelector('#error');
const toggle = document.querySelector('#visibility');
const note = document.querySelector('#connection-note');

note.hidden = location.protocol === 'https:' || location.hostname === 'localhost' || location.hostname === '127.0.0.1';

toggle.addEventListener('click', () => {
  const show = input.type === 'password';
  input.type = show ? 'text' : 'password';
  toggle.textContent = show ? 'Verbergen' : 'Anzeigen';
  toggle.setAttribute('aria-pressed', String(show));
  input.focus();
});

form.addEventListener('submit', async event => {
  event.preventDefault();
  const password = input.value;
  if (!password) return;
  button.disabled = true;
  error.textContent = '';
  try {
    const response = await fetch('/api/login', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      credentials: 'same-origin',
      body: JSON.stringify({password})
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Anmeldung fehlgeschlagen.');
    input.value = '';
    location.replace('/');
  } catch (e) {
    error.textContent = e.message || 'Verbindung fehlgeschlagen.';
    input.select();
  } finally {
    button.disabled = false;
  }
});
