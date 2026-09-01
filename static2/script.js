const state = { view: 'dashboard', pollers: new Map() };
const $ = (selector) => document.querySelector(selector);
const api = async (path, options = {}) => {
	const response = await fetch(`/api${path}`, { headers: { 'Content-Type': 'application/json' }, ...options });
	if (!response.ok) { const error = await response.json().catch(() => ({})); throw new Error(error.detail || `Request failed (${response.status})`); }
	return response.status === 204 ? null : response.json();
};
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#039;' }[char]));
const date = (value) => value ? new Date(value).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : '—';
const toast = (message) => { const node = document.createElement('div'); node.className = 'toast'; node.textContent = message; $('#toast-region').append(node); setTimeout(() => node.remove(), 3500); };
const openModal = (id) => { const modal = $(`#${id}`); modal.classList.add('open'); modal.setAttribute('aria-hidden', 'false'); modal.querySelector('input')?.focus(); };
const closeModal = (id) => { const modal = $(`#${id}`); modal.classList.remove('open'); modal.setAttribute('aria-hidden', 'true'); };

function setView(view) {
	state.view = view;
	document.querySelectorAll('.nav-item').forEach((item) => item.classList.toggle('active', item.dataset.view === view));
	document.querySelectorAll('.view').forEach((item) => item.classList.toggle('active-view', item.id === `view-${view}`));
	const titles = { dashboard: ['FIELD NOTES / 01', 'Investigation overview'], investigations: ['CASE MANAGEMENT / 02', 'Investigations'], searches: ['COLLECTION HISTORY / 03', 'Search history'], graph: ['CORRELATION LAYER / 04', 'Identity graph'], terminal: ['COMMAND CONSOLE / 05', 'Terminal'] };
	$('#view-kicker').textContent = titles[view][0]; $('#view-title').textContent = titles[view][1];
	if (view === 'dashboard') loadDashboard();
	if (view === 'investigations') loadInvestigations();
	if (view === 'searches') loadSearches();
	if (view === 'graph') loadGraph();
	if (view === 'terminal') loadTerminal();
}

async function loadDashboard() {
	try {
		const data = await api('/dashboard');
		const metrics = [['Investigations', data.metrics.investigations], ['Searches run', data.metrics.searches], ['Accounts found', data.metrics.accounts], ['Sites checked', data.metrics.sites_checked]];
		$('#metrics').innerHTML = metrics.map(([label, value]) => `<div class="metric"><div class="metric-label">${label}</div><div class="metric-value">${value.toLocaleString()}</div></div>`).join('');
		$('#recent-searches').innerHTML = data.recent_searches.length ? data.recent_searches.map(searchRow).join('') : '<div class="empty">No searches yet. Start your first collection.</div>';
		const total = Object.values(data.status_distribution).reduce((a, b) => a + b, 0) || 1;
		$('#distribution').innerHTML = Object.entries(data.status_distribution).map(([key, value]) => `<div class="bar-row"><div class="bar-label"><span>${escapeHtml(key)}</span><strong>${value}</strong></div><div class="bar"><i style="width:${value / total * 100}%"></i></div></div>`).join('');
	} catch (error) { toast(error.message); }
}
function searchRow(search) { return `<div class="ledger-row" data-search-id="${search.id}"><div><div class="ledger-main">${escapeHtml(search.username)}</div><div class="ledger-meta">${date(search.created_at)} · ${search.sites_checked}/${search.total_sites || '—'} sites</div></div><span class="badge ${search.status.toLowerCase()}">${escapeHtml(search.status)}</span><strong>${search.positive_count} found</strong></div>`; }

async function loadInvestigations() {
	try {
		const values = await api('/investigations');
		const select = $('select[name="investigation_id"]');
		if (select) {
			select.innerHTML = '<option value="">Create a new investigation</option>' + values.map((item) => `<option value="${item.id}">${escapeHtml(item.title)}</option>`).join('');
		}
		$('#investigation-list').innerHTML = values.length ? values.map((item) => `<article class="case-card"><p class="eyebrow">CASE ${String(item.id).padStart(4, '0')}</p><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.primary_username || 'No primary username')}</p><p>${item.search_count} searches · ${item.result_count} findings</p><div class="case-actions"><button class="text-button" data-case-id="${item.id}">Open case →</button><button class="text-button danger" data-delete-investigation="${item.id}">Remove case</button></div></article>`).join('') : '<div class="empty">No investigations have been created.</div>';
	} catch (error) { toast(error.message); }
}
async function loadSearches() {
	try { const values = await api('/searches'); $('#search-list').innerHTML = values.length ? `<table class="data-table"><thead><tr><th>Target</th><th>Status</th><th>Progress</th><th>Found</th><th>Created</th></tr></thead><tbody>${values.map((search) => `<tr class="search-link" data-search-id="${search.id}"><td><strong>${escapeHtml(search.username)}</strong></td><td><span class="badge ${search.status.toLowerCase()}">${escapeHtml(search.status)}</span></td><td>${search.sites_checked}/${search.total_sites || '—'} (${search.progress}%)</td><td>${search.positive_count}</td><td>${date(search.created_at)}</td></tr>`).join('')}</tbody></table>` : '<div class="empty">No search history yet.</div>'; } catch (error) { toast(error.message); }
}

async function showSearch(searchId) {
	try { const [search, results] = await Promise.all([api(`/searches/${searchId}`), api(`/searches/${searchId}/results`)]); $('#detail-content').innerHTML = `<p class="eyebrow">SEARCH ${String(search.id).padStart(4, '0')}</p><h2>${escapeHtml(search.username)}</h2><div class="detail-grid"><div><dt>Status</dt><dd>${escapeHtml(search.status)}</dd></div><div><dt>Progress</dt><dd>${search.sites_checked}/${search.total_sites || '—'} sites (${search.progress}%)</dd></div><div><dt>Found</dt><dd>${search.positive_count}</dd></div><div><dt>Started</dt><dd>${date(search.started_at)}</dd></div></div><h3>Site results (${results.length})</h3><div class="table-wrap"><table class="data-table"><thead><tr><th>Site</th><th>Status</th><th>Profile</th></tr></thead><tbody>${results.map((result) => `<tr class="result-link" data-result-id="${result.id}"><td>${escapeHtml(result.site)}</td><td><span class="badge ${result.status.toLowerCase()}">${escapeHtml(result.status)}</span></td><td>${result.url ? 'Open evidence ↗' : '—'}</td></tr>`).join('')}</tbody></table></div><div class="detail-actions"><a class="text-button" href="/api/searches/${search.id}/report?format=json">Download JSON report ↗</a><a class="text-button" href="/api/searches/${search.id}/report?format=csv">Download CSV report ↗</a><a class="text-button" href="/api/searches/${search.id}/report?format=pdf">Download PDF report ↗</a></div><p class="muted">CLI command: <code>${escapeHtml(search.command || 'maigret ' + search.username)}</code></p>`; openModal('detail-modal'); if (search.status === 'running' || search.status === 'queued') watchSearch(search.id); } catch (error) { toast(error.message); }
}
async function showResult(resultId) { try { const result = await api(`/results/${resultId}`); const profile = Object.entries(result.profile || {}); $('#detail-content').innerHTML = `<p class="eyebrow">EVIDENCE RECORD</p><h2>${escapeHtml(result.site)}</h2><div class="detail-grid"><div><dt>Username</dt><dd>${escapeHtml(result.username)}</dd></div><div><dt>Status</dt><dd><span class="badge ${result.status.toLowerCase()}">${escapeHtml(result.status)}</span></dd></div><div><dt>Source</dt><dd><a href="${escapeHtml(result.url)}" target="_blank" rel="noopener">${escapeHtml(result.url || 'Unavailable')}</a></dd></div><div><dt>HTTP response</dt><dd>${result.http_status || '—'}</dd></div></div><h3>Extracted profile data</h3>${profile.length ? `<dl class="detail-grid">${profile.map(([key, value]) => `<div><dt>${escapeHtml(key.replaceAll('_', ' '))}</dt><dd>${escapeHtml(Array.isArray(value) ? value.join(', ') : value)}</dd></div>`).join('')}</dl>` : '<p class="muted">No structured profile data was extracted.</p>'}<h3>Analyst note</h3><form id="note-form"><label><textarea name="body" required placeholder="Record an observation..." rows="3"></textarea></label><button class="button button-primary">Save note</button></form><div>${(result.notes || []).map((note) => `<p class="ledger-meta">${escapeHtml(note.body)} · ${date(note.created_at)}</p>`).join('')}</div>`; openModal('detail-modal'); $('#note-form').onsubmit = async (event) => { event.preventDefault(); const body = new FormData(event.target).get('body'); await api(`/results/${result.id}/notes`, { method: 'POST', body: JSON.stringify({ body }) }); toast('Note saved'); showResult(result.id); }; } catch (error) { toast(error.message); } }

function watchSearch(searchId) { if (state.pollers.has(searchId)) return; const poll = async () => { try { const search = await api(`/searches/${searchId}/status`); if (search.status === 'completed') { toast(`Scan complete: ${search.positive_count} accounts found`); clearInterval(timer); state.pollers.delete(searchId); loadDashboard(); } else if (search.status === 'failed') { toast(`Scan failed: ${search.error_message}`); clearInterval(timer); state.pollers.delete(searchId); } } catch (_) {} }; const timer = setInterval(poll, 1800); state.pollers.set(searchId, timer); poll(); }
async function loadGraph() { try { const graph = await api('/graph'); const canvas = $('#graph-canvas'); if (!graph.nodes.length) { canvas.innerHTML = '<div class="empty" style="color:#b4c9c1">Complete a search to map identity relationships.</div>'; return; } const nodes = graph.nodes.slice(0, 24); const positions = new Map(nodes.map((node, index) => [node.id, { x: 12 + (index % 5) * 19, y: 18 + Math.floor(index / 5) * 25 }])); const lines = graph.edges.filter((edge) => positions.has(edge.source) && positions.has(edge.target)).map((edge) => { const from = positions.get(edge.source); const to = positions.get(edge.target); const length = Math.hypot(to.x - from.x, to.y - from.y); const angle = Math.atan2(to.y - from.y, to.x - from.x) * 180 / Math.PI; return `<i class="graph-line" style="left:${from.x}%;top:${from.y}%;width:${length}%;transform:rotate(${angle}deg)"></i>`; }).join(''); canvas.innerHTML = lines + nodes.map((node, index) => { const position = positions.get(node.id); return `<div class="graph-node" style="left:${position.x}%;top:${position.y}%">${escapeHtml(node.label)}<small>${escapeHtml(node.type)}${node.status ? ` · ${escapeHtml(node.status)}` : ''}</small></div>`; }).join(''); } catch (error) { toast(error.message); } }

function loadTerminal() {
	const output = $('#terminal-output');
	if (!output) return;
	if (!output.dataset.initialized) {
		output.innerHTML = '<div class="terminal-line"><span class="terminal-prompt">$</span><span class="terminal-command">python -m maigret --help</span></div>';
		output.dataset.initialized = 'true';
	}
}

function appendTerminalEntry(command, output, exitCode) {
	const outputNode = $('#terminal-output');
	if (!outputNode) return;
	const line = document.createElement('div');
	line.className = 'terminal-line terminal-entry';
	line.innerHTML = `<span class="terminal-prompt">$</span><span class="terminal-command">${escapeHtml(command)}</span>`;
	outputNode.appendChild(line);
	if (output) {
		const outputBlock = document.createElement('pre');
		outputBlock.className = 'terminal-output-block';
		outputBlock.textContent = output.trimEnd() || '(no output)';
		outputNode.appendChild(outputBlock);
	}
	const status = document.createElement('div');
	status.className = `terminal-status ${exitCode === 0 ? 'success' : 'error'}`;
	status.textContent = `Exit code ${exitCode}`;
	outputNode.appendChild(status);
	outputNode.scrollTop = outputNode.scrollHeight;
}

$('#terminal-form').onsubmit = async (event) => {
	event.preventDefault();
	const form = new FormData(event.target);
	const command = String(form.get('command') || '').trim();
	if (!command) return;
	const input = $('#terminal-input');
	input.value = '';
	try {
		const result = await api('/terminal/execute', { method: 'POST', body: JSON.stringify({ command }) });
		appendTerminalEntry(result.command, result.output, result.exit_code);
	} catch (error) {
		appendTerminalEntry(command, error.message, 1);
	}
};

$('#search-form').onsubmit = async (event) => { event.preventDefault(); const form = new FormData(event.target); const payload = { username: form.get('username'), title: form.get('title') || null, investigation_id: form.get('investigation_id') ? Number(form.get('investigation_id')) : null, timeout: Number(form.get('timeout')), top_sites: Number(form.get('top_sites')), recursive: form.has('recursive'), extract: form.has('extract'), permute: form.has('permute'), check_domains: form.has('check_domains'), all_sites: form.has('all_sites'), report_format: form.get('report_format') || 'json', print_not_found: form.has('print_not_found'), print_errors: form.has('print_errors'), verbose: form.has('verbose'), no_progressbar: form.has('no_progressbar'), use_disabled_sites: form.has('use_disabled_sites'), tags: (form.get('tags') || '').split(',').map((value) => value.trim()).filter(Boolean), excluded_tags: (form.get('excluded_tags') || '').split(',').map((value) => value.trim()).filter(Boolean), site_list: (form.get('site_list') || '').split(',').map((value) => value.trim()).filter(Boolean), keywords: (form.get('keywords') || '').split(',').map((value) => value.trim()).filter(Boolean), proxy: (form.get('proxy') || '').trim() || null, tor_proxy: (form.get('tor_proxy') || '').trim() || null, i2p_proxy: (form.get('i2p_proxy') || '').trim() || null }; try { const search = await api('/search', { method: 'POST', body: JSON.stringify(payload) }); closeModal('search-modal'); toast('Investigation started'); watchSearch(search.id); setView('searches'); } catch (error) { toast(error.message); } };
document.addEventListener('click', (event) => {
	const view = event.target.closest('[data-view]')?.dataset.view;
	if (view) { event.preventDefault(); setView(view); }
	const searchId = event.target.closest('[data-search-id]')?.dataset.searchId;
	if (searchId) showSearch(searchId);
	const resultId = event.target.closest('[data-result-id]')?.dataset.resultId;
	if (resultId) showResult(resultId);
	const investigationId = event.target.closest('[data-delete-investigation]')?.dataset.deleteInvestigation;
	if (investigationId) {
		if (!confirm('Remove this investigation and all its saved searches?')) return;
		api(`/investigations/${investigationId}`, { method: 'DELETE' }).then(() => { toast('Investigation removed'); loadInvestigations(); }).catch((error) => toast(error.message));
	}
	const close = event.target.closest('[data-close]')?.dataset.close;
	if (close) closeModal(close);
});
$('#new-search-button').onclick = () => { loadInvestigations(); openModal('search-modal'); }; $('#new-case-button').onclick = () => { loadInvestigations(); openModal('search-modal'); }; $('#refresh-button').onclick = () => setView(state.view);
loadDashboard();
loadInvestigations();
