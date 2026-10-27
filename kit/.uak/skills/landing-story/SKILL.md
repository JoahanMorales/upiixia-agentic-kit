---
name: landing-story
description: Build a landing page (home, portada, pitch page) that makes a stranger get the idea in 5 seconds and want to try it - for a hackathon jury, users or investors. Use when creating or redesigning the product's front page, a project's public page, or the page judges open first. Works from IDEA.md (the one line, the real case, the wow, numbers with sources) and the locked design; pairs with frontend-design for the look and product-ui for any app screen shown.
---

# Landing story · a page that tells the idea

A landing is not a template with your logo. It is the product's argument in one scroll: what it is, for whom, why it
matters (a real number), how it works (shown, not described), and the one thing to do now. The judges at Chilangatón
opened the landing first; a page that reads as generated costs the whole demo its credibility.

## 0. Gather the story before any pixel (10 minutes)
Pull every line from `IDEA.md`, never invent it:
| Beat | Source | What you write |
|---|---|---|
| The one line | §1 One line | "For **user**, who **pain with a number**, **product** lets them **result**." Rewritten as a headline of 8 words or fewer, in the user's words |
| The proof of pain | §10 numbers, with source | ONE number a stranger feels ("7 in 100 shops sell online"), with its source in small print |
| The wow | §4 demo flow, the wow step | The single moment that makes people lean in: shown as a real screenshot, a short loop or the live product |
| How it works | §4 steps | Three steps max, each a verb + what the user sees, each with its own real screen |
| Who it is for | §2 users | The personas by name and need, not "everyone" |
| The ask | the event or the business | One action: try the demo, watch the 60-s video, join, contact |

If a beat has no real content yet, leave it out. A missing section beats a fake one.

## 1. Structure: one scroll, one argument
1. **Hero (above the fold at 1280×720 and 390×844):** the headline, one sentence under it, the primary action, and the
   wow as the dominant visual. The wow is a real product screenshot or a looping capture of the real UI, never a
   div-built fake dashboard, a stock photo or an abstract gradient blob.
2. **The pain, in one number:** big, tabular, with its source. One line of context. No wall of stats.
3. **How it works:** three steps, each with a real screen (from `webapp-testing` captures of the app). Alternate
   image side or use one sticky screen that changes per step; never three identical cards with icons.
4. **The proof:** the demo case from §3 told as a short story (who, before, after), a quote, or a live counter from
   the product. Label demo data as demo.
5. **Who it serves:** 2–4 personas with their need, or the actors (citizen, shop, government) and what each gets.
6. **The ask, again:** the same primary action, plus the secondary (video, repo, contact). Footer: team, event, data
   sources and licenses.
Seven sections at most. Cut any section a judge would skim past.

## 2. The look: distinct, from the brief
- Start from the design lock (`web/DESIGN.md`, tokens). The landing is where the brand gets its loudest moment:
  bigger type, the brand color at full strength, the display face doing real work.
- Run `frontend-design`'s two passes: a short plan (palette as named hex values, the type pair and scale, a layout
  sketch per section), then review it against its list of AI tells and revise what reads generic, before coding.
- Ground the visuals in the subject's world: the materials, places and vernacular of the users (a market's awnings
  and hand-painted signs, a clinic's calm, a lab's precision). That is where a distinct look comes from.
- Spend boldness in ONE place (usually the hero's type or the wow visual) and keep the rest quiet and disciplined.
- Never: a centered hero over a purple or dark mesh gradient, three equal feature cards, an ALL-CAPS eyebrow over
  every heading, `A · B · C` meta strings, a `→` on every link, the same rounded card and grey shadow everywhere,
  emoji as icons, Inter/Roboto/Arial by default. `bash .uak/bin/design-lint` catches part of this; your eye the rest.

## 3. Words that sell by being specific
- Headline: the result for the user, concrete, 8 words or fewer. Not "Revolutionizing X with AI".
- Sentences in the user's language (Spanish for a CDMX audience), active voice, plain verbs, no filler.
- Every number has a unit and a source. Every claim the demo cannot show is cut.
- The action says what happens: "Arma tu ruta", "Ver la demo de 60 s", not "Empezar" or "Saber más".
- Name the product the same way everywhere (the name fixed at T0).

## 4. Motion with one job
One orchestrated entrance in the hero (the wow appearing, a number counting up once, a map tilting in), 400–800 ms,
ease-out. Scroll reveals only where they explain a step. No parallax for its own sake, no infinite loops, no bounce.
`prefers-reduced-motion` shows the final state at once.

## 5. Built to be opened by a judge
- It loads fast on venue Wi-Fi: optimized images (WebP/AVIF, sized), fonts self-hosted, no heavy video autoplay
  (a poster frame; the video plays on click).
- It is deployed with the product (`uak deploy`), at a short URL, and works on a phone.
- Accessible by construction: AA contrast, real headings in order, alt text that says what the screenshot shows,
  visible focus, the action reachable by keyboard.
- Open Graph image and title, so the link looks good when shared in the jury's chat.

## 6. Check before you call it done
1. Screenshot at 1280×720 and 390×844 (`webapp-testing`); for the human, `bash .uak/bin/uak design-gallery`.
2. The 5-second test: show only the first screen; can someone say what it is, for whom, and what to do? If not,
   rewrite the headline before touching the visuals.
3. The generic test: cover the logo; could this be any other product's page? Then the subject is not in it yet.
4. `bash .uak/bin/design-lint`, then `design-critic` on both viewports. Fix every P1.
