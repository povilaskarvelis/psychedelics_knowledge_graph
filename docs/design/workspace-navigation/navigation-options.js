(() => {
  const tabs = document.querySelector('.workspace-tabs');
  const panel = document.querySelector('.graph-panel');
  const originalAnchor = document.createComment('Original workspace navigation');
  tabs.before(originalAnchor);
  const bar = document.createElement('aside');
  bar.className = 'design-review';
  bar.setAttribute('aria-label', 'Design comparison');
  bar.innerHTML = `<div class="design-review-inner"><div class="design-options">${[['original','Current'],['a','A · Refined'],['b','B · Text'],['c','C · Header'],['d','D · Attached'],['d1','D1 · Shared corner'],['d1a','D1a · Quiet fill'],['q1','Q1 · Clean fill'],['q2','Q2 · Soft edge'],['q3','Q3 · Tonal fill'],['q4','Q4 · Open cutout'],['q4a','Q4a · Soft tint'],['q4b','Q4b · Edge marker'],['q4c','Q4c · Top glow'],['q5','Q5 · Recessed alt'],['q6','Q6 · Inverted fill'],['q6a','Q6a · Inverted flush'],['q6b','Q6b · Inverted recess'],['d1b','D1b · Accent line'],['d1c','D1c · Text only'],['d1d','D1d · Folder tab'],['d1e','D1e · Seam'],['d1f','D1f · Cutout'],['d2','D2 · Inset'],['d3','D3 · Softer']].map(([key,label])=>`<button type="button" data-design="${key}" aria-pressed="false">${label}</button>`).join('')}</div></div>`;
  document.body.prepend(bar);
  function setDesign(key) {
    document.body.dataset.design = key;
    if (key === 'c') document.querySelector('.site-header-inner').prepend(tabs);
    else originalAnchor.after(tabs);
    bar.querySelectorAll('button').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.design === key)));
    sessionStorage.setItem('navigation-study-v3',key);
    window.dispatchEvent(new Event('resize'));
  }
  bar.addEventListener('click',event => { const button = event.target.closest('[data-design]'); if(button) setDesign(button.dataset.design); });
  tabs.addEventListener('keydown',event=>{
    if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
    event.preventDefault(); const buttons = [...tabs.querySelectorAll('button')];
    const next = event.key === 'Home' ? buttons[0] : event.key === 'End' ? buttons[1] : buttons.find(b=>b!==document.activeElement);
    next?.focus(); next?.click();
  });
  setDesign(sessionStorage.getItem('navigation-study-v3') || 'd1');
})();
