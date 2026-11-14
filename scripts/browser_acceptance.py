"""Real Chrome smoke acceptance of the production Web bundle (no mocked browser).
Covers bilingual capture and persistence across a tab restart. Full connected
workflow is exercised separately by the real HTTP controller acceptance test.
"""
import json
from pathlib import Path
import re
import uuid
from playwright.sync_api import sync_playwright,expect

out=Path('acceptance-browser');out.mkdir(exist_ok=True)
results=[]
with sync_playwright() as p:
    browser=p.chromium.launch(channel='chrome',headless=True,args=['--no-sandbox'])
    try:
        for language in ['fa','en']:
            context=browser.new_context(viewport={'width':1440,'height':1000})
            page=context.new_page()
            def expect_project(name):
                # Flutter Web merges a ListTile's title and subtitle into one
                # semantics node, so the saved project is a button named
                # "<title> <status> · v<version>", never a text node equal to the
                # title alone. The generated title is unique, so requiring the
                # card's name to start with it still asserts exact persistence.
                expect(page.get_by_role('button',name=re.compile(rf'^{re.escape(name)}(?: |$)'))).to_be_visible(timeout=30000)
            def open_app():
                # A Flutter Web shell never reaches Playwright's network-idle heuristic:
                # the engine and its service workers keep background activity alive, so
                # page.goto(wait_until='networkidle') times out even when the app is fine.
                # Wait for the document, then require Flutter's own readiness markers;
                # a shell that fails to load or boot still fails the checks below.
                response=page.goto('http://127.0.0.1:8173/',wait_until='domcontentloaded',timeout=60000)
                if response is None or not response.ok:
                    raise RuntimeError(f'Application shell did not load: HTTP {response.status if response else "no response"}')
                placeholder=page.locator('flt-semantics-placeholder')
                placeholder.wait_for(state='attached',timeout=60000)
                placeholder.evaluate('(element) => element.click()')
                toggle=page.get_by_role('button',name='English / فارسی',exact=True)
                expect(toggle).to_be_visible(timeout=60000)
                if language=='en':toggle.click()
            capture='برداشت آفلاین' if language=='fa' else 'Capture offline'
            new='پروژه جدید' if language=='fa' else 'New project'
            title_label='عنوان' if language=='fa' else 'Title'
            save='ذخیره' if language=='fa' else 'Save'
            title=f'QA-{language}-{uuid.uuid4().hex[:8]}'
            try:
                open_app()
                page.get_by_role('button',name=capture,exact=True).click()
                # All backend traffic is unavailable while local creation takes place.
                context.route('**/api/**',lambda route:route.abort())
                page.get_by_role('button',name=new,exact=True).click()
                field=page.get_by_role('textbox',name=title_label,exact=True)
                field.fill(title)
                page.screenshot(path=str(out/f'{language}-form.png'))
                page.get_by_role('button',name=save,exact=True).click()
                expect_project(title)
                page.screenshot(path=str(out/f'{language}-saved.png'))
                page.close()
                page=context.new_page()
                open_app()
                page.get_by_role('button',name=capture,exact=True).click()
                expect_project(title)
                page.screenshot(path=str(out/f'{language}-reopened.png'))
                results.append({'language':language,'status':'PASS','scope':'Production Chrome UI local project capture, API-unavailable save, tab close/reopen recovery. Shell reload used network; not an offline shell boot claim.'})
            except Exception:
                page.screenshot(path=str(out/f'{language}-failure.png'))
                print(page.locator('body').aria_snapshot()[:12000])
                results.append({'language':language,'status':'FAIL'})
                raise
            finally:
                context.close()
    finally:
        (out/'results.json').write_text(json.dumps(results,indent=2))
        browser.close()
