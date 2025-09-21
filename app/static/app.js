async function postJSON(url, data){
  const res = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(data)});
  if(!res.ok){ throw new Error(`Request failed: ${res.status}`); }
  return await res.json();
}
async function getJSON(url){
  const res = await fetch(url);
  if(!res.ok){ throw new Error(`GET failed: ${res.status}`); }
  return await res.json();
}
function el(id){ return document.getElementById(id); }
function fmtPct(x){ return (x!=null)? `${(+x).toFixed(2)}%`:'-'; }
function tableFromRows(headers, rows){
  let h = '<table><thead><tr>' + headers.map(x=>`<th>${x}</th>`).join('') + '</tr></thead><tbody>';
  for (const r of rows){ h += '<tr>' + r.map(c=>`<td>${c}</td>`).join('') + '</tr>'; }
  h += '</tbody></table>'; return h;
}
function tableFromKeyMap(title, m){
  if(!m) return '';
  const rows = Object.keys(m).map(k=>[k, m[k]]);
  return `<h4>${title}</h4>${tableFromRows(['Key','Value'], rows)}`;
}
function flattenIfNeeded(v){
  const out={};
  for (const k in v){
    if (v && typeof v[k]==='object' && !Array.isArray(v[k])){
      for (const kk in v[k]) out[`${k} ${kk}`] = v[k][kk];
    } else out[k]=v[k];
  }
  return out;
}

function selectedMarkets(){ return [
  "1X2","Double Chance","Draw No Bet","Over/Under","BTTS","Team Goals",
  "1X2 + O/U","DC + BTTS","Result + BTTS","Correct Score","Clean Sheet","Win to Nil","Winning Margin"
]; }

async function loadEnv(){
  try {
    const d = await getJSON('/env_status');
    el('envPanel').innerHTML = '<pre>'+JSON.stringify(d,null,2)+'</pre>';
  } catch (e){
    el('envPanel').textContent = e.message;
  }
}

async function getMatches(){
  const leagueId = parseInt(el('leagueId').value || '0');
  const season   = parseInt(el('season').value || '0');
  const date     = el('matchDate').value || '';
  const qs = new URLSearchParams();
  if (leagueId) qs.set('league_id', String(leagueId));
  if (season) qs.set('season', String(season));
  if (date) qs.set('date', date);
  const url = '/api/matches?'+qs.toString();

  el('matchesList').innerHTML = 'Loading...';
  try {
    const data = await getJSON(url);
    if (!data.items || !data.items.length){
      el('matchesList').innerHTML = '<p class="muted">No fixtures found.</p>'; return;
    }
    let html = '';
    for (const it of data.items){
      const o = it.odds || {};
      const book = it.bookmaker || '-';
      html += `
        <div class="card match-item" data-fixture="${it.fixture_id}">
          <div><b>${it.league}</b> — ${it.home} vs ${it.away} <span class="muted">(${new Date(it.utc).toLocaleString()})</span></div>
          <div class="row" style="margin-top:6px;">
            <div>Odds (${book}): 1 <code>${o["1"] || '-'}</code> • X <code>${o["X"] || '-'}</code> • 2 <code>${o["2"] || '-'}</code></div>
            <button class="btn" onclick="useMatch(${JSON.stringify(it).replace(/"/g,'&quot;')})">Use & Analyze</button>
          </div>
        </div>`;
    }
    el('matchesList').innerHTML = html;
  } catch (e){
    el('matchesList').innerHTML = `<div class="card">Error: ${e.message}</div>`;
  }
}

function useMatch(it){
  el('leagueLabel').value = it.league || '';
  el('seasonForm').value  = it.season || '';
  el('home').value = it.home || '';
  el('away').value = it.away || '';
  const o = it.odds || {};
  if (o["1"]) el('odds1').value = o["1"];
  if (o["X"]) el('oddsX').value = o["X"];
  if (o["2"]) el('odds2').value = o["2"];
  analyzeFootball(); // auto-run
}

async function analyzeFootball(){
  // parse lines
  const ouLines = el('ouLines').value.trim().split(',').map(v=>parseFloat(v)).filter(v=>!isNaN(v));
  const homeTG = el('homeTG').value.trim().split(',').map(v=>parseFloat(v)).filter(v=>!isNaN(v));
  const awayTG = el('awayTG').value.trim().split(',').map(v=>parseFloat(v)).filter(v=>!isNaN(v));

  const payload = {
    league: el('leagueLabel').value,
    season: parseInt(el('seasonForm').value || 2025),
    home: el('home').value,
    away: el('away').value,
    odds: {"1": parseFloat(el('odds1').value || 0), "X": parseFloat(el('oddsX').value || 0), "2": parseFloat(el('odds2').value || 0)},
    context: { derby: el('derby').checked },
    markets: selectedMarkets(),
    ou_lines: ouLines.length? ouLines : [1.5,2.5,3.5],
    team_goal_lines: {"home": (homeTG.length? homeTG:[0.5,1.5]), "away": (awayTG.length? awayTG:[0.5,1.5])},
    cs_groups: [[1,0],[2,0],[2,1]]
  };

  const data = await postJSON('/analyze/football', payload);
  renderFootball(data);
}

function renderFootball(data){
  const out = document.getElementById('output');
  const card = document.createElement('div'); card.className='card';
  const statusClass = data.status==='FINAL_PICK' ? 'good' : (data.status==='SKIPPED' ? 'warn' : 'bad');
  const statusBadge = `<span class="badge ${statusClass}">${data.status}</span>`;

  // warnings
  let warningsHTML = '';
  if (Array.isArray(data.warnings) && data.warnings.length){
    warningsHTML = `<div class="warning"><b>Warning:</b> ${data.warnings.join(' • ')}</div>`;
  }

  // winner table
  const wrows = (data.winner_mode_table?.rows||[]).map(r=>[
    r.outcome,
    fmtPct(r['Poisson%']),
    fmtPct(r['Bayesian%']),
    fmtPct(r['DixonColes%']),
    r['FairOdds'] ?? '-',
    r['notes'] || ''
  ]);

  // markets
  let marketsHTML = '';
  if(data.markets){
    for (const [k,v] of Object.entries(data.markets)){
      if(typeof v === 'object'){
        marketsHTML += tableFromKeyMap(k, flattenIfNeeded(v));
      }
    }
  }

  card.innerHTML = `
    <h2>${data.league||''} — ${data.home} vs ${data.away} ${statusBadge}</h2>
    ${warningsHTML}
    <div class="grid grid-2">
      <div><h3>Winner Mode</h3>
        ${tableFromRows(['Outcome','Poisson%','Bayesian%','DixonColes%','FairOdds','Notes'], wrows)}
      </div>
      <div><h3>Value Mode</h3>
        ${tableFromKeyMap('Implied %', data.value_mode_table?.implied_percent)}
        ${tableFromKeyMap('True %', data.value_mode_table?.true_percent)}
        ${tableFromKeyMap('Fair Odds', data.value_mode_table?.fair_odds)}
        ${tableFromKeyMap('Edge (pp)', data.value_mode_table?.edge_percent_points)}
        <p class="muted">Best Edge: ${data.value_mode_table?.best_edge_sel || '-'}</p>
      </div>
    </div>
    <div class="grid grid-2">
      <div><h3>Alignment</h3>
        ${tableFromRows(['WM Best','VM Best','WM=VM','Edge (best, pp)','Remark'], [[
          data.alignment?.wm_best || '-', data.alignment?.vm_best || '-', data.alignment?.wm_equals_vm ? 'Yes':'No',
          data.alignment?.edge_best_pp ?? '-', data.alignment?.remark || '-'
        ]])}
      </div>
      <div><h3>Audit</h3>
        ${tableFromRows(['Parameters','Formula','EV Sim','Calibration'], [[
          data.audit?.parameters_ok ? 'OK':'Check', data.audit?.formula_ok ? 'OK':'Check', data.audit?.ev_sim ?? '-', data.audit?.calibration_note || '-'
        ]])}
      </div>
    </div>
    <h3>Markets</h3>
    ${marketsHTML || '<p class="muted">No markets calculated.</p>'}
    <p class="muted">Sources: ${(data.sources || []).join(' • ')}</p>
  `;
  out.prepend(card);
}

// wire buttons
document.getElementById('btnGetMatches').addEventListener('click', getMatches);
document.getElementById('btnEnv').addEventListener('click', loadEnv);
document.getElementById('btnAnalyze').addEventListener('click', analyzeFootball);
