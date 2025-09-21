// static/app.js
async function postJSON(url, data){
  const res = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(data)});
  if(!res.ok){ throw new Error('Request failed'); }
  return await res.json();
}
function el(id){return document.getElementById(id)}
function tableFromRows(headers, rows){
  let h = '<table class="table"><thead><tr>' + headers.map(x=>`<th>${x}</th>`).join('') + '</tr></thead><tbody>';
  for (const r of rows){ h += '<tr>' + r.map(c=>`<td>${c}</td>`).join('') + '</tr>'; }
  h += '</tbody></table>'; return h;
}
function tableFromKeyMap(title, m){
  if(!m) return '';
  const rows = Object.keys(m).map(k=>[k, m[k]]);
  return `<h4>${title}</h4>${tableFromRows(['Key','Value'], rows)}`;
}
function selectedMarkets(){
  return Array.from(document.querySelectorAll('.mk:checked')).map(x=>x.value);
}

async function analyzeFootball(){
  const ouLines = el('ouLines').value.trim().split(',').map(v=>parseFloat(v)).filter(v=>!isNaN(v));
  const homeTG = el('homeTG').value.trim().split(',').map(v=>parseFloat(v)).filter(v=>!isNaN(v));
  const awayTG = el('awayTG').value.trim().split(',').map(v=>parseFloat(v)).filter(v=>!isNaN(v));
  const csGroups = el('csGroups').value.trim().split(',').map(x=>x.trim()).filter(x=>x.includes(':')).map(x=>x.split(':').map(Number));

  const payload = {
    league: el('league').value,
    season: parseInt(el('season').value || 2025),
    home: el('home').value,
    away: el('away').value,
    odds: {"1": parseFloat(el('odds1').value || 0), "X": parseFloat(el('oddsX').value || 0), "2": parseFloat(el('odds2').value || 0)},
    context: { derby: el('derby').checked },
    markets: selectedMarkets(),
    ou_lines: ouLines.length? ouLines : [1.5,2.5,3.5],
    team_goal_lines: {"home": (homeTG.length? homeTG:[0.5,1.5]), "away": (awayTG.length? awayTG:[0.5,1.5])},
    cs_groups: csGroups.length? csGroups : [[1,0],[2,0],[2,1]]
  };
  const data = await postJSON('/analyze/football', payload);
  renderFootball(data);
}

function renderFootball(data){
  const out = el('output'); const card = document.createElement('div'); card.className='card';
  const statusBadge = `<span class="badge ${data.status==='FINAL_PICK'?'good':(data.status==='OMITTED'?'warn':'bad')}">${data.status}</span>`;
  const agreeBadge = data.agreement ? `<span class="chip ${data.agreement==='AGREE'?'chip-ok':'chip-no'}">Agreement: ${data.agreement}</span>` : '';

  let warnHTML = '';
  if (data.warning || (data.warning_reasons && data.warning_reasons.length)){
    const w = data.warning || 'CAUTION';
    const reasons = (data.warning_reasons||[]).map(x=>`<li>${x}</li>`).join('');
    warnHTML = `
      <div class="notice warning">
        <b>${w}:</b>
        <ul>${reasons}</ul>
      </div>
    `;
  }

  let reasonHTML = '';
  if (data.reason){
    reasonHTML = `<div class="notice info"><b>Reason:</b> ${data.reason}</div>`;
  }

  let impliedHTML = '';
  if (data.bookmaker_implied){
    impliedHTML = tableFromKeyMap('Bookmaker Implied %', data.bookmaker_implied);
  }

  let marketsHTML = '';
  if(data.markets){
    for (const [k,v] of Object.entries(data.markets)){
      if(typeof v === 'object'){
        marketsHTML += tableFromKeyMap(k, flattenIfNeeded(v));
      }
    }
  }

  card.innerHTML = `
    <h2>${data.league||''} — ${data.home} vs ${data.away} ${statusBadge} ${agreeBadge}</h2>
    ${warnHTML}
    ${reasonHTML}
    ${impliedHTML}

    <div class="grid grid-2">
      <div><h3>Winner Mode</h3>
        ${tableFromRows(['Outcome','Poisson%','Bayesian%','DixonColes%','FairOdds','Notes'],
          (data.winner_mode_table?.rows||[]).map(r=>[r.outcome, r['Poisson%'], r['Bayesian%'], r['DixonColes%'], r['FairOdds']||'-', r['notes']]))}
      </div>
      <div><h3>Value Mode</h3>
        ${tableFromKeyMap('Implied %', data.value_mode_table?.implied_percent)}
        ${tableFromKeyMap('True %', data.value_mode_table?.true_percent)}
        ${tableFromKeyMap('Fair Odds', data.value_mode_table?.fair_odds)}
        ${tableFromKeyMap('Edge (pp)', data.value_mode_table?.edge_percent_points)}
        <p><small>Best Edge: ${data.value_mode_table?.best_edge_sel || '-'}</small></p>
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
    ${marketsHTML || '<p><small>No markets calculated.</small></p>'}
    <p><small>Sources: ${(data.sources || []).join(' • ')}</small></p>
  `;
  out.prepend(card);
}
function flattenIfNeeded(v){
  const out = {};
  for (const k in v){
    if (v && typeof v[k]==='object' && !Array.isArray(v[k])){
      for (const kk in v[k]) out[`${k} ${kk}`] = v[k][kk];
    } else {
      out[k] = v[k];
    }
  }
  return out;
}
