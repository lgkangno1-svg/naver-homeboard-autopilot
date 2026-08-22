# -*- coding: utf-8 -*-
import sys, json
sys.stdout.reconfigure(encoding="utf-8")
import naver

pw, browser, ctx, page = naver.launch(headless=True)
page.goto("https://blog.naver.com/issuemans/postwrite", wait_until="networkidle", timeout=60000)
page.wait_for_timeout(15000)

JS = """() => ({
  editables: Array.from(document.querySelectorAll('[contenteditable="true"]')).map(e => ({
    cls: (e.className||'').toString().slice(0,70),
    aria: e.getAttribute('aria-label') || ''
  })),
  title_ce: (() => { const t = document.querySelector('.se-title-text'); return t ? t.getAttribute('contenteditable') : 'no-elem'; })(),
  title_parent: (() => { const t = document.querySelector('.se-title-text'); return t ? t.parentElement.className.toString().slice(0,80) : 'none'; })(),
  doc_section: (() => { const d = document.querySelector('.se-section-document'); return d ? d.className.toString().slice(0,80) : 'none'; })()
})"""
info = page.evaluate(JS)
print(json.dumps(info, ensure_ascii=False, indent=1))
browser.close(); pw.stop()
