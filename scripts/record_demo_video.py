"""Record the Streamlit walkthrough with burned-in captions (Playwright video)."""
import shutil
import sys
from playwright.sync_api import sync_playwright

OUT = sys.argv[1]
URL = "http://localhost:8501"
W, H = 1600, 900

CAPTION_JS = """
(text) => {
  let el = document.getElementById('cl-cap');
  if (!el) {
    el = document.createElement('div'); el.id = 'cl-cap';
    Object.assign(el.style, {position:'fixed', left:'50%', bottom:'34px', transform:'translateX(-50%)',
      maxWidth:'1150px', padding:'16px 28px', background:'rgba(31,42,46,.92)', color:'#fff',
      font:'600 26px/1.35 Inter, sans-serif', borderRadius:'14px', zIndex:99999, textAlign:'center',
      boxShadow:'0 8px 30px rgba(0,0,0,.25)', transition:'opacity .25s'});
    document.body.appendChild(el);
  }
  el.style.opacity = text ? 1 : 0;
  el.innerHTML = text || '';
}
"""

HIDE_JS = """() => { const s=document.createElement('style');
s.textContent='[data-testid=stToolbar],[data-testid=stDecoration],header{visibility:hidden!important}';
document.head.appendChild(s); }"""


def main():
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": W, "height": H}, record_video_dir="/tmp/claude-0/vid",
                            record_video_size={"width": W, "height": H})
        pg = ctx.new_page()
        pg.goto(URL)
        pg.wait_for_timeout(7000)
        pg.evaluate(HIDE_JS)

        def cap(text, ms):
            pg.evaluate(CAPTION_JS, text)
            pg.wait_for_timeout(ms)

        def say(text, caption, ms=5500, click=False):
            if click:
                pg.get_by_role("button", name=text).first.click()
            else:
                box = pg.get_by_placeholder("Type what Amma says…")
                box.click()
                box.type(text, delay=45)
                pg.keyboard.press("Enter")
            pg.wait_for_timeout(1800)
            pg.evaluate(HIDE_JS)
            cap(caption, ms)

        cap("This is a simulated Alexa+ conversation.<br>Every reply comes from the real CareLoop MCP server.", 6000)
        cap("Left: what Amma says. Right: what her family sees.<br>It's 9:10 AM on Sunday.", 5000)
        say("The doctor gave me Atorvastatin 10mg for cholesterol at bedtime, 20 tablets",
            "Medicines are added the way people actually say them.<br>“at bedtime” becomes 10 PM.", 6500)
        say("What medicine do I need to take now?",
            "Alexa+ calls whats_due_now: what to take, with instructions like “after food”.", 6000, click=True)
        say("I took my BP tablet",
            "“BP tablet” is matched to Amlodipine by its purpose. The family view updates instantly.", 6500)
        say("I took my BP tablet",
            "Said it twice by mistake? CareLoop guards against a double dose.", 6500)
        say("I'm feeling a bit dizzy today",
            "Symptoms are logged in her own words, and repeats across the week are noticed.", 6000, click=True)
        say("Do I need to buy any medicines?",
            "Refill alerts are calculated from tablets left and the schedule.", 5500, click=True)
        say("I have chest pain",
            "Warning signs skip the small talk: call 112 now.<br>In production, SNS also alerts the family immediately.", 7500,
            click=True)

        cap("Later that evening…", 2500)
        pg.get_by_role("button", name="Late · 11:00 PM").click()
        pg.wait_for_timeout(2500)
        pg.evaluate(HIDE_JS)
        cap("Her Metformin doses were never logged, so they now show as missed.", 5000)
        pg.get_by_role("button", name="How is Amma").click()
        pg.wait_for_timeout(2500)
        pg.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        pg.locator("section.main, [data-testid=stMain]").first.evaluate("e => e.scrollTo(0, e.scrollHeight)")
        cap("The family gets one calm summary: misses, symptoms, refills, and whether to call.", 8000)
        cap("In production Amazon Bedrock writes this. Here it isn't connected, so the built-in template does.", 6000)
        cap("", 800)
        path = pg.video.path()
        ctx.close()
        b.close()
        shutil.move(path, OUT)


main()
