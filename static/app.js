'use strict';

const $ = selector => document.querySelector(selector);
const state = {
  employees: [],
  report: null,
  reportRequest: 0,
  teamRequest: 0,
  mutations: 0,
  serverTime: Date.now() / 1000,
  syncedAt: performance.now(),
};

function element(tag, text, className) {
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

function serverNow() {
  return state.serverTime + (performance.now() - state.syncedAt) / 1000;
}

function avatar(name, index = 0) {
  const initials = name.trim().split(/\s+/).slice(0, 2).map(word => [...word][0]).join('');
  const result = element('span', initials.toUpperCase(), `avatar avatar-tone-${index % 4}`);
  result.setAttribute('aria-hidden', 'true');
  return result;
}

function showMessage(text, isError = false) {
  const box = $('#message');
  box.textContent = text;
  box.className = isError ? 'error' : '';
}

async function api(path, body) {
  let response;
  try {
    response = await fetch(path, body === undefined ? {} : {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  } catch {
    throw new Error('Нет связи с сервером. Проверьте, запущено ли приложение, и повторите действие.');
  }
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error('Сервер вернул неожиданный ответ. Обновите страницу.');
  }
  if (!response.ok) throw new Error(data.error || 'Не удалось выполнить запрос.');
  return data;
}

async function withButton(button, task) {
  if (button.disabled) return;
  button.disabled = true;
  button.setAttribute('aria-busy', 'true');
  try {
    await task();
  } catch (error) {
    showMessage(error.message, true);
  } finally {
    button.disabled = false;
    button.removeAttribute('aria-busy');
  }
}

async function mutate(button, path, payload, successMessage) {
  await withButton(button, async () => {
    state.mutations += 1;
    try {
      await api(path, payload);
      showMessage(successMessage);
      // A failed refresh must not imply that an already successful write failed.
      try {
        await refresh();
      } catch {
        showMessage(`${successMessage} Не удалось обновить экран; обновите страницу.`, true);
      }
    } finally {
      state.mutations -= 1;
    }
  });
}

async function loadTeam() {
  const requestId = ++state.teamRequest;
  const data = await api('/api/state');
  if (requestId !== state.teamRequest) return;
  state.serverTime = data.server_time;
  state.syncedAt = performance.now();
  state.employees = data.employees;

  // Capture drafts and focus immediately before replacing the DOM, not before fetch.
  const drafts = new Map([...document.querySelectorAll('[data-employee]')]
    .map(input => [input.dataset.employee, input.value]));
  const focused = document.activeElement;
  const focusedId = focused?.dataset.employee;
  const selection = focusedId ? [focused.selectionStart, focused.selectionEnd] : null;
  renderTeam(drafts);
  if (focusedId) {
    const restored = document.querySelector(`[data-employee="${focusedId}"]`);
    if (restored) {
      restored.focus({ preventScroll: true });
      restored.setSelectionRange(...selection);
    }
  }
  renderEmployeeFilter();
}

function renderTeam(drafts) {
  const box = $('#employees');
  box.replaceChildren();
  box.setAttribute('aria-busy', 'false');
  $('#team-count').textContent = state.employees.length;
  $('#active-count').textContent = state.employees.filter(person => person.timer_id !== null).length;

  if (!state.employees.length) {
    const empty = element('div', undefined, 'empty');
    empty.append(element('strong', 'Здесь начинается рабочий день'),
      element('span', 'Добавьте первого сотрудника и запустите его задачу.'));
    box.append(empty);
  }

  state.employees.forEach((person, index) => {
    const row = element('div', undefined, 'employee');
    const identity = element('div', undefined, 'person');
    identity.append(element('strong', person.name), element('small',
      person.timer_id ? person.description : 'Готов к новой задаче',
      person.timer_id ? 'running-label' : ''));
    const trackerLink = element('a', 'Открыть трекер ↗', 'tracker-link');
    trackerLink.href = `/employee?id=${person.id}`;
    trackerLink.setAttribute('aria-label', `Открыть трекер: ${person.name}`);
    identity.append(trackerLink);
    row.append(avatar(person.name, index), identity);

    if (person.timer_id) {
      const timer = element('span', duration(serverNow() - person.started_at), 'timer');
      timer.dataset.start = person.started_at;
      timer.setAttribute('aria-label', `Время задачи: ${person.name}`);
      const stop = element('button', undefined, 'stop');
      stop.type = 'button';
      stop.setAttribute('aria-label', `Остановить таймер: ${person.name}`);
      stop.append(element('span', '', 'stop-symbol'), element('span', 'Остановить'));
      stop.addEventListener('click', () => mutate(stop, '/api/stop',
        { employee_id: person.id }, `Таймер остановлен: ${person.name}`));
      row.append(timer, stop);
    } else {
      const form = element('form', undefined, 'task-form');
      const input = element('input');
      input.placeholder = 'Над чем работаете?';
      input.maxLength = 500;
      input.required = true;
      input.dataset.employee = String(person.id);
      input.value = drafts.get(String(person.id)) || '';
      input.setAttribute('aria-label', `Описание задачи: ${person.name}`);
      const start = element('button', '▷ Начать');
      start.type = 'submit';
      start.setAttribute('aria-label', `Запустить таймер: ${person.name}`);
      form.append(input, start);
      form.addEventListener('submit', event => {
        event.preventDefault();
        mutate(start, '/api/start', { employee_id: person.id, description: input.value },
          `Таймер запущен: ${person.name}`);
      });
      row.append(form);
    }
    box.append(row);
  });
}

function renderEmployeeFilter() {
  const select = $('#employee-filter');
  const selected = select.value;
  select.replaceChildren(new Option('Вся команда', ''));
  state.employees.forEach(person => select.add(new Option(person.name, String(person.id))));
  if (state.employees.some(person => String(person.id) === selected)) select.value = selected;
}

async function loadReport() {
  const from = $('#date-from').value;
  const to = $('#date-to').value;
  if (!from || !to || from > to) throw new Error('Выберите даты: начало периода должно быть не позже конца.');
  const requestId = ++state.reportRequest;
  $('#entries').setAttribute('aria-busy', 'true');
  try {
    const report = await api(`/api/report?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`);
    // Ignore an older response if the user has already requested another period.
    if (requestId !== state.reportRequest) return;
    state.report = { ...report, from, to };
    renderReport();
  } finally {
    if (requestId === state.reportRequest) $('#entries').setAttribute('aria-busy', 'false');
  }
}

function renderReport() {
  const report = state.report;
  if (!report) return;
  const selected = Number($('#employee-filter').value);
  const employees = report.employees.filter(person => !selected || person.id === selected);
  const entries = report.entries.filter(entry => !selected || entry.employee_id === selected);
  $('#total').textContent = duration(employees.reduce((sum, person) => sum + person.seconds, 0));
  $('#metric-period').textContent = `${report.from} — ${report.to} · UTC`;
  $('#entry-count').textContent = `Записей: ${entries.length}`;
  $('#report-note').textContent = `С учётом активных задач · ${new Date(report.as_of * 1000).toISOString().slice(11, 19)} UTC`;

  const totals = $('#totals');
  totals.replaceChildren();
  employees.forEach(person => {
    const chip = element('div', person.name, 'total-chip');
    chip.append(element('strong', duration(person.seconds)));
    totals.append(chip);
  });

  const table = $('#entries');
  table.replaceChildren();
  if (!entries.length) {
    const row = element('tr');
    const cell = element('td', undefined, 'empty');
    cell.colSpan = 4;
    cell.append(element('strong', 'За этот период пока нет записей'),
      element('span', 'Выберите другие даты или запустите новую задачу.'));
    row.append(cell);
    table.append(row);
  }

  entries.forEach(entry => {
    const row = element('tr');
    const cell = element('td');
    const person = element('div', undefined, 'table-person');
    const identity = element('div');
    identity.append(element('strong', entry.name), element('small', entry.description));
    const index = state.employees.findIndex(employee => employee.id === entry.employee_id);
    person.append(avatar(entry.name, Math.max(0, index)), identity);
    cell.append(person);
    const statusCell = element('td');
    statusCell.append(element('span', entry.ended_at === null ? 'В работе' : 'Завершено',
      entry.ended_at === null ? 'status-pill active' : 'status-pill'));
    row.append(cell, element('td',
      new Date(entry.started_at * 1000).toISOString().slice(0, 19).replace('T', ' '), 'date-cell'),
    statusCell, element('td', duration(entry.seconds), 'duration'));
    table.append(row);
  });
}

function setPeriod(period) {
  const end = new Date(serverNow() * 1000);
  const start = new Date(end);
  if (period === 'week') start.setUTCDate(start.getUTCDate() - (start.getUTCDay() + 6) % 7);
  if (period === 'month') start.setUTCDate(1);
  $('#date-from').value = start.toISOString().slice(0, 10);
  $('#date-to').value = end.toISOString().slice(0, 10);
  document.querySelectorAll('[data-period]').forEach(button => {
    button.setAttribute('aria-pressed', String(button.dataset.period === period));
  });
}

async function refresh() {
  await loadTeam();
  await loadReport();
}

$('#employee-form').addEventListener('submit', event => {
  event.preventDefault();
  const button = event.submitter;
  withButton(button, async () => {
    state.mutations += 1;
    try {
      await api('/api/employees', { name: $('#employee-name').value });
      $('#employee-name').value = '';
      showMessage('Сотрудник добавлен. Можно запускать первую задачу.');
      try { await refresh(); }
      catch { showMessage('Сотрудник добавлен. Не удалось обновить экран; обновите страницу.', true); }
    } finally {
      state.mutations -= 1;
    }
  });
});
$('#report-form').addEventListener('submit', event => {
  event.preventDefault();
  document.querySelectorAll('[data-period]').forEach(button => button.setAttribute('aria-pressed', 'false'));
  withButton(event.submitter, loadReport);
});
$('#employee-filter').addEventListener('change', renderReport);
$('#refresh-report').addEventListener('click', event => withButton(event.currentTarget, refresh));
document.querySelectorAll('[data-period]').forEach(button => {
  button.addEventListener('click', () => withButton(button, async () => {
    setPeriod(button.dataset.period);
    await loadReport();
  }));
});
setInterval(() => {
  document.querySelectorAll('[data-start]').forEach(timer => {
    timer.textContent = duration(serverNow() - Number(timer.dataset.start));
  });
}, 1000);
window.addEventListener('focus', () => {
  if (!state.mutations) refresh().catch(error => showMessage(error.message, true));
});
(async () => {
  try {
    await loadTeam();
    setPeriod('week');
    await loadReport();
  } catch (error) {
    $('#employees').setAttribute('aria-busy', 'false');
    showMessage(error.message, true);
  }
})();
