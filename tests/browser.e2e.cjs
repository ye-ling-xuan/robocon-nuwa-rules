/* Real MCP calls -> live SSE -> PDF.js canvas/text/highlight, with no model API. */
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const readline = require('node:readline');
const {chromium} = require('playwright');
const ROOT = path.resolve(__dirname, '..');
const python = process.env.NUWA_TEST_PYTHON || path.join(ROOT, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const artifacts = path.join(ROOT, 'tmp', 'browser');
fs.mkdirSync(artifacts, {recursive: true});

function host(sampling = false) {
  const child = spawn(python, [path.join(__dirname, 'browser_host.py'), ...(sampling ? ['--sampling'] : [])], {cwd: ROOT, windowsHide: true, env: {...process.env, PYTHONIOENCODING: 'utf-8'}});
  let id = 0, readyResolve, readyReject, stderr = '';
  const pending = new Map();
  const ready = new Promise((resolve, reject) => {readyResolve = resolve; readyReject = reject;});
  child.stderr.on('data', data => {stderr = (stderr + data.toString()).slice(-5000);});
  child.on('error', readyReject);
  child.on('exit', code => {
    if (code) {const e = new Error(`Test host exited ${code}: ${stderr}`); readyReject(e); for (const p of pending.values()) p.reject(e);}
  });
  readline.createInterface({input: child.stdout}).on('line', line => {
    let result; try { result = JSON.parse(line); } catch { return; }
    if (result.ready) return readyResolve();
    const request = pending.get(result.id); if (!request) return;
    pending.delete(result.id); clearTimeout(request.timer);
    if (result.error) request.reject(new Error(result.message)); else request.resolve(result.data);
  });
  return {
    ready,
    call(tool, args = {}) { return new Promise((resolve,reject) => {
      const current = ++id;
      const timer = setTimeout(() => { pending.delete(current); reject(new Error(`MCP call timed out: ${tool}`)); }, 30000);
      pending.set(current, {resolve,reject,timer}); child.stdin.write(JSON.stringify({id: current,tool,args})+'\n');
    }); },
    async close() {
      if (child.exitCode !== null) return;
      child.stdin.end(JSON.stringify({id: ++id, tool: '_quit'})+'\n');
      await new Promise(resolve => {const timer=setTimeout(()=>{child.kill();resolve();},5000);child.once('exit',()=>{clearTimeout(timer);resolve();});});
    }
  };
}

async function waitPage(page, number) {
  await page.waitForFunction(n => document.querySelector('.pdf-page')?.dataset.page === String(n) && document.querySelectorAll('.highlight-rect').length > 0, number);
}

async function main() {
  const bridge = host(), samplingHost = host(true);
  let browser;
  try {
    await Promise.all([bridge.ready, samplingHost.ready]);
    browser = await chromium.launch({headless:true, ...(process.env.NUWA_TEST_BROWSER ? {executablePath: process.env.NUWA_TEST_BROWSER} : {})});
    const page = await browser.newPage({viewport:{width:1440,height:1000},deviceScaleFactor:1});
    const errors = [], external = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.route('**/*', route => {
      if (!route.request().url().startsWith('http://127.0.0.1:')) {external.push(route.request().url()); return route.abort();}
      return route.continue();
    });
    const q = 'TR拿着五色石还能拿塔基吗？';
    const first = await bridge.call('search_rules',{query:q});
    await page.goto(first.ui_url); await waitPage(page,17);
    assert.equal(await page.locator('.turn').count(),1);
    assert.equal(await page.locator('#question-input').isDisabled(),true);
    assert.match(await page.locator('.pending').innerText(),/等待 Agent/);
    await bridge.call('sync_answer',{question:q,answer:'不能。携带五色石时不得同时携带塔基/中段/塔顶。\n依据：\n[3.6.8 · P17] 携带五色石的机器人不得携带任何塔基/中段/塔顶。\n[4.4.2 · P20] 携带五色石时不得携带其它比赛用品。',citations:first.citations,turn_id:first.turn_id});
    await page.waitForFunction(()=>document.querySelector('.answer-body')?.textContent.includes('不能'));
    assert.equal(await page.locator('.turn').count(),1);
    await page.locator('.turn').evaluate(async el=>{await Promise.all(el.getAnimations({subtree:true}).filter(a=>a.effect.getTiming().iterations!==Infinity).map(a=>a.finished));});
    await page.screenshot({path:path.join(artifacts,'first-question.png')});
    await page.locator('.citation-badge[data-clause-id="4.4.2"]').click(); await waitPage(page,20);
    await page.locator('.citation-badge[data-clause-id="3.6.8"]').click(); await waitPage(page,17);
    const before = await page.evaluate(()=>({page:document.querySelector('.pdf-page').getBoundingClientRect().width,rect:parseFloat(document.querySelector('.highlight-rect').style.left)}));
    await page.locator('#zoom-in').click();
    await page.waitForFunction(w=>document.querySelector('.pdf-page').getBoundingClientRect().width > w+10,before.page);
    const after = await page.evaluate(()=>({page:document.querySelector('.pdf-page').getBoundingClientRect().width,rect:parseFloat(document.querySelector('.highlight-rect').style.left)}));
    assert.ok(Math.abs(after.rect/before.rect-after.page/before.page)<.002,'PDF coordinate highlights must track zoom');
    const quote = await page.evaluate(async()=>{
      const {quoteRanges}=await import('/static/pdf-helpers.mjs');
      const ranges=quoteRanges(document.querySelector('.textLayer'),'携带五色石的机器人不得携带任何塔基/中段/塔顶。');
      return {text:ranges.map(r=>r.toString()).join(''),rects:ranges.reduce((n,r)=>n+r.getClientRects().length,0)};
    });
    assert.match(quote.text,/携带五色石/); assert.ok(quote.rects>0);
    const second = await bridge.call('calc_score',{items:[{kind:'塔顶'}],level:'L2',question:'L2 塔顶多少分？'});
    assert.equal(second.total,80); await waitPage(page,24);
    await bridge.call('sync_answer',{question:second.question,answer:'80 分。\n依据：[8.1.3 · P24] L2 塔顶分值为 80 分。',citations:second.citations,turn_id:second.turn_id});
    await page.waitForFunction(()=>document.querySelectorAll('.answer-body').length===2);
    const third = await bridge.call('judge_foul',{action:'TR 携带 4 个塔基会怎样？'});
    assert.equal(third.disposition,'强制重试'); await waitPage(page,23);
    await bridge.call('sync_answer',{question:third.question,answer:'超限携带犯规，强制重试。超出限制后拿取的物品须取出并禁用。\n依据：[6.5 · P23]、[4.4.2 · P20]。',citations:third.citations,turn_id:third.turn_id});
    const fourth = await bridge.call('check_protection',{towers:[{id:'a',zone:'L1_private',standing:true,complete:true,in_build_site:true,top_matches_team:true},{id:'b',zone:'L2',standing:true,complete:true,in_build_site:true,top_matches_team:true}],question:'这两座全塔满足保护法则吗？'});
    assert.equal(fourth.satisfied,true); await waitPage(page,16);
    await bridge.call('sync_answer',{question:fourth.question,answer:'满足。两座本队全塔同时耸立，且至少一座在公共区建塔处。\n依据：[3.6.1 · P16]。',citations:fourth.citations,turn_id:fourth.turn_id});
    await page.waitForFunction(()=>document.querySelectorAll('.answer-body').length===4);
    assert.equal(await page.locator('.turn').count(),4);
    await bridge.call('get_clause',{clause_id:'3.6.4'}); await waitPage(page,16);
    assert.equal(await page.locator('#cross-page-note').isVisible(),true);
    await page.locator('#next-page').click(); await waitPage(page,17);
    await page.locator('#clear-highlight').click();
    await page.waitForFunction(()=>document.querySelectorAll('.highlight-rect').length===0);
    assert.ok(!(await page.locator('#document-status').innerText()).includes('已高亮'));
    const unknown = await bridge.call('search_rules',{query:'今天食堂吃什么？'});
    await bridge.call('sync_answer',{question:unknown.question,answer:'虚构回答',citations:[],turn_id:unknown.turn_id});
    await page.waitForFunction(()=>document.querySelector('.turn:last-child .answer-body')?.textContent==='规则未明确，请以原文/裁判为准。');
    assert.equal(await page.locator('.highlight-rect').count(),0);
    // Late-open and reconnect snapshot recovery.
    await page.reload(); await page.locator('.pdf-page').waitFor();
    assert.equal(await page.locator('.turn').count(),5);
    await bridge.call('get_clause',{clause_id:'3.6.8'}); await waitPage(page,17);
    // Render through the actual quote-only branch, without trusted PDF boxes.
    const quotePage = await browser.newPage({viewport:{width:1200,height:900}});
    await quotePage.route('**/api/state?*',async route=>{
      const response=await route.fetch(); const data=await response.json();
      delete data.selected.bbox; delete data.selected.rects;
      await route.fulfill({response,json:data});
    });
    await quotePage.route('**/events?*',route=>route.abort());
    await quotePage.goto(first.ui_url); await waitPage(quotePage,17);
    assert.ok(await quotePage.locator('.highlight-rect').count()>0);
    const geometry = await quotePage.evaluate(()=>({highlight:document.querySelector('.highlight-rect').getBoundingClientRect().toJSON(),paper:document.querySelector('.pdf-page').getBoundingClientRect().toJSON()}));
    assert.ok(geometry.highlight.width>100 && geometry.highlight.height<45,'Quote matching must highlight text, not a whole page');
    await quotePage.screenshot({path:path.join(artifacts,'quote-only.png')}); await quotePage.close();
    await page.setViewportSize({width:390,height:844}); await page.locator('#fit-width').click();
    await page.waitForFunction(()=>document.querySelector('.pdf-page').getBoundingClientRect().width<390);
    const mobile = await page.evaluate(()=>({chat:document.querySelector('.chat-panel').getBoundingClientRect().bottom,doc:document.querySelector('.document-panel').getBoundingClientRect().top,width:document.body.scrollWidth}));
    assert.ok(mobile.doc>=mobile.chat && mobile.width<=390,'Mobile view stacks panels without page overflow');
    await page.locator('#conversation').evaluate(el=>{el.scrollTop=0;});
    await page.screenshot({path:path.join(artifacts,'mobile.png')});
    const ui = await samplingHost.call('open_ui');
    const inputPage = await browser.newPage(); await inputPage.goto(ui.ui_url);
    await inputPage.locator('#question-input:not([disabled])').waitFor();
    await inputPage.locator('#question-input').fill('L2 塔顶多少分？'); await inputPage.locator('#send-button').click();
    await waitPage(inputPage,24);
    await inputPage.waitForFunction(()=>document.querySelector('.answer-body')?.textContent.includes('80 分'));
    assert.equal(await inputPage.locator('.turn').count(),1); await inputPage.close();
    assert.deepEqual(errors,[]); assert.deepEqual(external,[]);
    console.log('PASS: first question, sync, citation switching, zoom, score, foul, protection, cross-page, unknown rules, reconnect, quote-only highlight, mobile, host Sampling; no external requests.');
  } finally {
    if (browser) await browser.close();
    await Promise.all([bridge.close(),samplingHost.close()]);
  }
}
main().catch(error=>{console.error(error);process.exitCode=1;});
