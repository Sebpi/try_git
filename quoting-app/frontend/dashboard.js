// Vanilla JS admin dashboard -- no build step, matches the rest of this repo's philosophy.
let currentThreadId = null;
let pollTimer = null;

function getToken() {
  return localStorage.getItem('quoting_admin_token') || '';
}

function saveToken() {
  const v = document.getElementById('adminToken').value.trim();
  if (v) localStorage.setItem('quoting_admin_token', v);
  refreshCurrentView();
}

function toast(msg, isError) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.style.borderColor = isError ? 'var(--red)' : 'var(--border)';
  el.style.display = 'block';
  clearTimeout(el._t);
  el._t = setTimeout(() => { el.style.display = 'none'; }, 3500);
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      'X-Admin-Token': getToken(),
      ...(opts.headers || {}),
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `${res.status} ${res.statusText}`);
  }
  return res.status === 204 ? null : res.json();
}

const apiGet = (path) => api(path);
const apiPost = (path, data) => api(path, { method: 'POST', body: JSON.stringify(data) });

window.addEventListener('DOMContentLoaded', () => {
  document.getElementById('adminToken').value = getToken();
  showView('overview');
  setInterval(refreshCurrentView, 20000); // light polling so the dashboard stays live
});

function showView(name) {
  document.querySelectorAll('.view').forEach((v) => v.classList.remove('active'));
  document.getElementById(`view-${name}`).classList.add('active');
  document.querySelectorAll('nav button').forEach((b) => b.classList.toggle('active', b.dataset.view === name));
  refreshCurrentView(name);
}

function refreshCurrentView(name) {
  const active = name || document.querySelector('.view.active')?.id.replace('view-', '');
  if (!getToken()) return;
  if (active === 'overview') loadOverview();
  else if (active === 'threads') loadThreads();
  else if (active === 'approvals') loadApprovals();
  else if (active === 'thread-detail' && currentThreadId) loadThreadDetail(currentThreadId);
}

// ------------------------------------------------------------------ overview --
async function loadOverview() {
  try {
    const [metrics, decisions, notifications] = await Promise.all([
      apiGet('/v1/metrics'), apiGet('/v1/decisions?limit=40'), apiGet('/v1/notifications'),
    ]);

    const tiles = [
      { n: metrics.total_threads, l: 'Total threads' },
      { n: metrics.pending_approvals, l: 'Pending approvals' },
      ...Object.entries(metrics.by_status).map(([status, n]) => ({ n, l: status })),
    ];
    document.getElementById('metricTiles').innerHTML = tiles
      .map((t) => `<div class="tile"><div class="n">${t.n}</div><div class="l">${t.l}</div></div>`).join('');

    document.getElementById('recentDecisions').innerHTML = decisions.length ? decisions.map((d) => `
      <div class="timeline-item">
        <b>${d.agent_name}</b> &middot; <span class="muted">${fmtTime(d.created_at)}</span> &middot;
        <a class="back" onclick="openThread('${d.thread_id}')">${d.thread_id}</a><br>
        ${escapeHtml(d.summary || '')}
      </div>`).join('') : '<span class="muted">No agent activity yet -- try Simulate.</span>';

    document.getElementById('amNotifications').innerHTML = notifications.length ? notifications.map((n) => `
      <div class="timeline-item">
        <b>${n.kind}</b> &middot; <span class="muted">${fmtTime(n.created_at)}</span> &middot;
        <a class="back" onclick="openThread('${n.thread_id}')">${n.thread_id}</a><br>
        ${escapeHtml(n.message || '')}
      </div>`).join('') : '<span class="muted">No notifications yet.</span>';
  } catch (e) { toast(e.message, true); }
}

// ------------------------------------------------------------------- threads --
async function loadThreads() {
  try {
    const threads = await apiGet('/v1/threads');
    const tbody = document.querySelector('#threadsTable tbody');
    tbody.innerHTML = threads.map((t) => `
      <tr class="clickable" onclick="openThread('${t.id}')">
        <td><code>${t.id}</code></td>
        <td>${escapeHtml(t.customer_name || '')}<br><span class="muted">${escapeHtml(t.customer_email)}</span></td>
        <td>${escapeHtml(t.subject || '')}</td>
        <td>${statusPill(t.status)}</td>
        <td>${t.complexity ? `<span class="pill">${t.complexity}</span>` : ''}</td>
        <td class="muted">${fmtTime(t.updated_at)}</td>
      </tr>`).join('') || '<tr><td colspan="6" class="muted">No threads yet.</td></tr>';
  } catch (e) { toast(e.message, true); }
}

function statusPill(status) {
  const map = {
    ACCEPTED: 'green', CLOSED_LOST: 'red', CLOSED_NO_RESPONSE: 'red',
    ROUTED_TO_HUMAN: 'amber', NEEDS_HUMAN_REVIEW: 'amber', PENDING_APPROVAL: 'blue',
    AWAITING_RESPONSE: 'blue', REJECTED: 'red', FOLLOW_UP_SENT: 'amber',
  };
  return `<span class="pill ${map[status] || ''}">${status}</span>`;
}

async function openThread(id) {
  currentThreadId = id;
  document.getElementById('detailNavBtn').style.display = 'inline-block';
  showView('thread-detail');
}

async function loadThreadDetail(id) {
  try {
    const data = await apiGet(`/v1/threads/${id}`);
    const t = data.thread;
    const el = document.getElementById('threadDetail');
    el.innerHTML = `
      <div class="card">
        <h3>${escapeHtml(t.subject || t.id)} ${statusPill(t.status)}</h3>
        <div class="row">
          <div class="col">
            <div class="muted">Customer</div>
            <div>${escapeHtml(t.customer_name || '')} &lt;${escapeHtml(t.customer_email)}&gt;</div>
          </div>
          <div class="col">
            <div class="muted">Complexity</div>
            <div>${t.complexity || '--'} <span class="muted">${escapeHtml(t.complexity_reason || '')}</span></div>
          </div>
          <div class="col">
            <div class="muted">Closed reason</div>
            <div>${escapeHtml(t.closed_reason || '--')}</div>
          </div>
        </div>
        ${data.routing_ticket ? `<div class="muted" style="margin-top:8px">Routed to AM <b>${data.routing_ticket.assigned_am}</b> + engineer <b>${data.routing_ticket.assigned_engineer}</b>: ${escapeHtml(data.routing_ticket.reason)}</div>` : ''}
        ${data.reminder ? `<div class="muted" style="margin-top:8px">Reminder stage: <b>${data.reminder.stage}</b>, next fire: ${fmtTime(data.reminder.next_fire_at)}
          <button class="btn btn-ghost" onclick="fastForward('${t.id}')">Fast-forward 3 days (test)</button></div>` : ''}
      </div>

      <div class="row">
        <div class="col">
          <div class="card">
            <h3>Line items</h3>
            ${renderLineItems(data.line_items)}
          </div>
          <div class="card">
            <h3>Drafts</h3>
            ${data.drafts.map(renderDraft).join('') || '<span class="muted">No drafts yet.</span>'}
          </div>
          <div class="card">
            <h3>Reply as customer (test)</h3>
            <p class="muted">Simulates the customer replying on this thread -- routes through Ingestion + Response Classifier exactly like a real reply.</p>
            <div class="example-btns">
              <button class="btn btn-ghost" onclick="replyAs('${t.id}', 'accept')">Accept</button>
              <button class="btn btn-ghost" onclick="replyAs('${t.id}', 'reject')">Reject</button>
              <button class="btn btn-ghost" onclick="replyAs('${t.id}', 'query')">Ask a question</button>
            </div>
          </div>
        </div>
        <div class="col">
          <div class="card">
            <h3>Agent decision timeline</h3>
            ${data.decisions.map((d) => `
              <div class="timeline-item">
                <b>${d.agent_name}</b> &middot; <span class="muted">${fmtTime(d.created_at)}</span>
                ${d.confidence != null ? `&middot; conf ${Number(d.confidence).toFixed(2)}` : ''}<br>
                ${escapeHtml(d.summary || '')}
              </div>`).join('') || '<span class="muted">No decisions logged.</span>'}
          </div>
        </div>
      </div>`;
  } catch (e) { toast(e.message, true); }
}

function renderLineItems(items) {
  if (!items.length) return '<span class="muted">None resolved yet.</span>';
  return `<table><thead><tr><th>Query text</th><th>SKU</th><th>Price</th><th>Qty</th><th>Confidence</th></tr></thead><tbody>
    ${items.map((li) => `<tr>
      <td>${escapeHtml(li.product_query_text || '')}</td>
      <td>${li.resolved_sku || '<span class="muted">unresolved</span>'}</td>
      <td>${li.resolved_price != null ? li.resolved_price.toFixed(2) + ' ' + (li.currency || '') : '--'}</td>
      <td>${li.quantity}</td>
      <td>${li.confidence != null ? li.confidence.toFixed(2) : '--'}</td>
    </tr>`).join('')}</tbody></table>`;
}

function renderDraft(d) {
  const statusColor = { approved: 'green', rejected: 'red', pending: 'amber', superseded: '' }[d.approval_status] || '';
  return `<div class="draft-box" id="draft-${d.id}">
    <div class="subject">v${d.version} &middot; ${d.kind} <span class="pill ${statusColor}">${d.approval_status}</span></div>
    <div class="subject muted" style="font-weight:400">${escapeHtml(d.subject || '')}</div>
    <pre>${escapeHtml(d.body || '')}</pre>
    ${d.approval_status === 'pending' ? `
      <textarea id="edit-${d.id}" style="display:none">${escapeHtml(d.body || '')}</textarea>
      <div class="btn-row">
        <button class="btn btn-green" onclick="approveDraft(${d.id})">Approve &amp; send</button>
        <button class="btn btn-red" onclick="rejectDraft(${d.id})">Reject</button>
        <button class="btn btn-ghost" onclick="toggleEdit(${d.id})">Edit</button>
        <button class="btn btn-primary" style="display:none" id="save-${d.id}" onclick="saveEdit(${d.id}, '${escapeAttr(d.subject)}')">Save edits &amp; approve</button>
      </div>` : d.reject_reason ? `<div class="muted">Rejected: ${escapeHtml(d.reject_reason)}</div>` : ''}
  </div>`;
}

function toggleEdit(id) {
  const ta = document.getElementById(`edit-${id}`);
  const btn = document.getElementById(`save-${id}`);
  const show = ta.style.display === 'none';
  ta.style.display = show ? 'block' : 'none';
  btn.style.display = show ? 'inline-block' : 'none';
}

async function approveDraft(id) {
  try {
    await apiPost(`/v1/drafts/${id}/approve`, { approver: promptApprover() });
    toast('Approved and sent.');
    loadThreadDetail(currentThreadId);
  } catch (e) { toast(e.message, true); }
}

async function rejectDraft(id) {
  const reason = prompt('Reason for rejecting this draft?');
  if (reason === null) return;
  try {
    await apiPost(`/v1/drafts/${id}/reject`, { approver: promptApprover(), reason });
    toast('Draft rejected.');
    loadThreadDetail(currentThreadId);
  } catch (e) { toast(e.message, true); }
}

async function saveEdit(id, subject) {
  const body = document.getElementById(`edit-${id}`).value;
  try {
    await apiPost(`/v1/drafts/${id}/edit`, { approver: promptApprover(), subject, body });
    toast('Edited draft approved and sent.');
    loadThreadDetail(currentThreadId);
  } catch (e) { toast(e.message, true); }
}

function promptApprover() {
  let name = localStorage.getItem('quoting_am_name');
  if (!name) {
    name = prompt('Your name (account manager)?', 'Account Manager') || 'Account Manager';
    localStorage.setItem('quoting_am_name', name);
  }
  return name;
}

async function fastForward(threadId) {
  try {
    await apiPost(`/dev/fast-forward/${threadId}`, { hours: 72 });
    await apiPost('/v1/reminders/run-sweep', {});
    toast('Fast-forwarded 3 days and ran the reminder sweep.');
    loadThreadDetail(currentThreadId);
  } catch (e) { toast(e.message, true); }
}

async function replyAs(threadId, kind) {
  const detail = await apiGet(`/v1/threads/${threadId}`);
  const t = detail.thread;
  const bodies = {
    accept: 'Thanks for the quote -- this looks good, please go ahead and confirm the order.',
    reject: "Thanks, but we've decided to go with another supplier -- the price was a bit too high for us right now.",
    query: 'Quick question -- does this price include delivery, and what is the lead time?',
  };
  try {
    const res = await apiPost('/dev/simulate-inbound-email', {
      from_email: t.customer_email,
      from_name: t.customer_name,
      subject: `Re: ${t.subject} [Ref: ${t.id}]`,
      body: bodies[kind],
    });
    toast(`Simulated ${kind} reply -- thread status is now ${res.status}.`);
    loadThreadDetail(currentThreadId);
  } catch (e) { toast(e.message, true); }
}

// ---------------------------------------------------------------- approvals --
async function loadApprovals() {
  try {
    const drafts = await apiGet('/v1/approvals/pending');
    const el = document.getElementById('approvalsList');
    el.innerHTML = drafts.length ? drafts.map((d) => `
      <div class="draft-box">
        <div class="subject">${escapeHtml(d.customer_name || '')} &lt;${escapeHtml(d.customer_email)}&gt;
          &middot; <a class="back" onclick="openThread('${d.thread_id}')">${d.thread_id}</a>
          &middot; ${d.kind} v${d.version}</div>
        <div class="subject muted" style="font-weight:400">${escapeHtml(d.subject || '')}</div>
        <pre>${escapeHtml(d.body || '')}</pre>
        <div class="btn-row">
          <button class="btn btn-green" onclick="approveFromList(${d.id})">Approve &amp; send</button>
          <button class="btn btn-red" onclick="rejectFromList(${d.id})">Reject</button>
        </div>
      </div>`).join('') : '<span class="muted">Nothing pending approval.</span>';
  } catch (e) { toast(e.message, true); }
}

async function approveFromList(id) {
  try { await apiPost(`/v1/drafts/${id}/approve`, { approver: promptApprover() }); toast('Approved and sent.'); loadApprovals(); }
  catch (e) { toast(e.message, true); }
}
async function rejectFromList(id) {
  const reason = prompt('Reason for rejecting this draft?');
  if (reason === null) return;
  try { await apiPost(`/v1/drafts/${id}/reject`, { approver: promptApprover(), reason }); toast('Rejected.'); loadApprovals(); }
  catch (e) { toast(e.message, true); }
}

// ---------------------------------------------------------------- simulate --
const EXAMPLES = {
  simple: {
    from: 'jordan.lee@northwind.example', name: 'Jordan Lee', subject: 'Quote request',
    body: 'Hi, could you send a quote for 5 ergonomic office chairs and 2 standing desks? Thanks, Jordan',
  },
  complex: {
    from: 'sam.osei@globex.example', name: 'Sam Osei', subject: 'Custom office fit-out',
    body: "Hi, we're planning a full office fit-out for 200 people and would like custom pricing and to schedule a call to discuss integration with our existing furniture. Can someone reach out?",
  },
  unknown: {
    from: 'nobody@unknown-company.example', name: 'A. Stranger', subject: 'Quote please',
    body: 'Hello, please send a quote for 3 wireless keyboards.',
  },
};

function fillExample(key) {
  const ex = EXAMPLES[key];
  document.getElementById('simFrom').value = ex.from;
  document.getElementById('simName').value = ex.name;
  document.getElementById('simSubject').value = ex.subject;
  document.getElementById('simBody').value = ex.body;
}

async function submitSimulate() {
  const payload = {
    from_email: document.getElementById('simFrom').value,
    from_name: document.getElementById('simName').value,
    subject: document.getElementById('simSubject').value,
    body: document.getElementById('simBody').value,
  };
  try {
    const res = await apiPost('/dev/simulate-inbound-email', payload);
    document.getElementById('simResult').innerHTML =
      `<div class="pill blue">thread ${res.thread_id} -&gt; ${res.status}</div> ` +
      `<a class="back" onclick="openThread('${res.thread_id}')">view thread</a>`;
    toast('Inbound email processed.');
  } catch (e) { toast(e.message, true); }
}

// ------------------------------------------------------------------- utils --
function fmtTime(iso) {
  if (!iso) return '--';
  const d = new Date(iso);
  return d.toLocaleString();
}
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
function escapeAttr(s) {
  return escapeHtml(s).replace(/'/g, "\\'");
}
