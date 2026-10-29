'use strict';

const $ = selector => document.querySelector(selector);
const drafts = new Map();
let selectedId = new URLSearchParams(location.search).get('id') || '';
let currentPerson = null;
let period = 'today';
let busy = false;
let requestSequence = 0;
let serverTime = Date.now() / 1000;
let syncedAt = performance.now();

function node(tag, text, className) {
  const result = document.createElement(tag);
  if (text !== undefined) result.textContent = text;
  if (className) result.className = className;
  return result;
}

function duration(seconds) {
  const total = Math.max(0, Math.floor(seconds));
  return [Math.floor(total / 3600), Math.floor(total / 60) % 60, total % 60]
    .map(value => String(value).padStart(2, '0')).join(':');
}

function now() {
  return serverTime + (performance.now() - syncedAt) / 1000;
}

function message(text, error = false) {
  $('#message').textContent = text;
  $('#message').className = error ? 'error' : '';
}

async function api(path, body) {
  let response;
  try {
    response = await fetch(path, body === undefined ? {} : {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    });
  } catch {
    throw new Error('Нет связи с сервером. Проверьте, запущено ли приложение.');
  }
  let data;
  try { data = await response.json(); }
  catch { throw new Error('Сервер вернул неожиданный ответ. Обновите страницу.'); }
  if (!response.ok) throw new Error(data.error || 'Не удалось выполнить запрос.');
  return data;
}

function rememberDraft() {
  if (currentPerson && !currentPerson.timer_id) {
    drafts.set(String(currentPerson.id), $('#task-description').value);
  }
}

function renderTimer() {
  const active = currentPerson.timer_id !== null;
  $('#person-name').textContent = currentPerson.name;
  $('#timer-status').textContent = active ? '● Таймер запущен' : 'Готов к работе';
  $('#personal-timer').textContent = active ? duration(now() - currentPerson.started_at) : '00:00:00';
  const input = $('#task-description');
  const value = active ? currentPerson.description : drafts.get(String(currentPerson.id)) || '';
  // Preserve caret and draft during background refresh when the value is unchanged.
  if (input.value !== value) input.value = value;
  input.readOnly = active;
  input.required = !active;
  const button = $('#timer-action');
  button.textContent = active ? '■ Завершить задачу' : '▷ Начать задачу';
  button.classList.toggle('is-running', active);
  $('#focus-hint').textContent = active
    ? 'Можно закрыть вкладку: запущенная задача сохранится в общем обзоре.'
    : 'Опишите задачу. Её время появится и в вашей истории, и в отчёте команды.';
}

function reportDates() {
  const end = new Date(now() * 1000);
  const start = new Date(end);
  if (period === 'week') start.setUTCDate(start.getUTCDate() - (start.getUTCDay() + 6) % 7);
  if (period === 'month') start.setUTCDate(1);
  return [start.toISOString().slice(0, 10), end.toISOString().slice(0, 10)];
}

function renderHistory(report) {
  const entries = report.entries.filter(entry => String(entry.employee_id) === selectedId);
  const total = report.employees.find(person => String(person.id) === selectedId)?.seconds || 0;
  $('#personal-total').textContent = duration(total);
  $('#personal-entry-count').textContent = `Записей: ${entries.length}`;
  $('#personal-report-note').textContent = `С учётом активных задач · ${new Date(report.as_of * 1000).toISOString().slice(11, 19)} UTC`;
  const table = $('#personal-entries');
  table.replaceChildren();
  if (!entries.length) {
    const row = node('tr');
    const cell = node('td', 'Задач за этот период пока нет. Самое время начать первую.', 'empty');
    cell.colSpan = 4;
    row.append(cell);
    table.append(row);
  }
  entries.forEach(entry => {
    const row = node('tr');
    const status = node('td');
    status.append(node('span', entry.ended_at === null ? 'В работе' : 'Завершено',
      entry.ended_at === null ? 'status-pill active' : 'status-pill'));
    row.append(node('td', entry.description), node('td',
      new Date(entry.started_at * 1000).toISOString().slice(0, 19).replace('T', ' '), 'date-cell'),
    status, node('td', duration(entry.seconds), 'duration'));
    table.append(row);
  });
}

async function refresh() {
  const sequence = ++requestSequence;
  const data = await api('/api/state');
  if (sequence !== requestSequence) return;
  rememberDraft();
  serverTime = data.server_time;
  syncedAt = performance.now();
  const select = $('#person-select');
  select.replaceChildren(new Option('Выберите сотрудника', ''));
  data.employees.forEach(person => select.add(new Option(person.name, String(person.id))));
  select.disabled = busy || !data.employees.length;
  currentPerson = data.employees.find(person => String(person.id) === selectedId) || null;
  select.value = currentPerson ? selectedId : '';
  $('#personal-workspace').hidden = !currentPerson;
  $('#choose-person').hidden = Boolean(currentPerson);
  if (!data.employees.length) {
    $('#choose-person').replaceChildren(node('p', 'В команде пока никого нет. Добавьте сотрудника в общем обзоре.', 'empty'));
    return;
  }
  if (!currentPerson) {
    const text = selectedId ? 'Сотрудник не найден. Выберите другого сотрудника в списке.' : 'Выберите сотрудника, чтобы открыть его таймер и историю.';
    $('#choose-person').replaceChildren(node('p', text, 'empty'));
    return;
  }
  renderTimer();
  const [from, to] = reportDates();
  const report = await api(`/api/report?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`);
  if (sequence === requestSequence) renderHistory(report);
}

$('#person-select').addEventListener('change', () => {
  rememberDraft();
  selectedId = $('#person-select').value;
  currentPerson = null;
  const url = new URL(location.href);
  if (selectedId) url.searchParams.set('id', selectedId);
  else url.searchParams.delete('id');
  history.replaceState(null, '', url);
  message('');
  // Hide the previous employee immediately while the new state loads.
  $('#personal-workspace').hidden = true;
  refresh().catch(error => message(error.message, true));
});

$('#timer-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (busy || !currentPerson) return;
  busy = true;
  const person = currentPerson;
  const active = person.timer_id !== null;
  $('#timer-action').disabled = true;
  $('#person-select').disabled = true;
  try {
    await api(active ? '/api/stop' : '/api/start', {
      employee_id: person.id, description: $('#task-description').value,
    });
    drafts.delete(String(person.id));
    // Do not preserve the completed/submitted task as a draft during refresh.
    currentPerson = null;
    $('#task-description').value = '';
    message(active ? 'Задача завершена. Время сохранено в общем отчёте.' : 'Задача запущена. Таймер виден в обзоре команды.');
  } catch (error) {
    message(error.message, true);
  }
  try { await refresh(); }
  catch { message('Не удалось обновить состояние. Обновите страницу перед следующим действием.', true); }
  finally {
    busy = false;
    $('#timer-action').disabled = false;
    $('#person-select').disabled = false;
  }
});

async function refreshWithButton(button) {
  button.disabled = true;
  try { await refresh(); }
  catch (error) { message(error.message, true); }
  finally { button.disabled = false; }
}
$('#personal-refresh').addEventListener('click', event => refreshWithButton(event.currentTarget));
document.querySelectorAll('[data-range]').forEach(button => {
  button.addEventListener('click', () => {
    period = button.dataset.range;
    document.querySelectorAll('[data-range]').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
    refreshWithButton(button);
  });
});
setInterval(() => {
  if (currentPerson?.timer_id) $('#personal-timer').textContent = duration(now() - currentPerson.started_at);
}, 1000);
window.addEventListener('focus', () => {
  if (!busy) refresh().catch(error => message(error.message, true));
});
refresh().catch(error => message(error.message, true));
