# Video script: The Supervision Cliff (target 4:30, hard limit 5:00)

About 640 words of narration at a calm ~150 words per minute = ~4:20, leaving room for the demo to breathe.
**VO** = voiceover (what you say). **ON SCREEN** = what the viewer sees. **EDIT** = cut / zoom notes.
Deck: https://claude.ai/artifact/QP6chVKJA6ccQArGn18RSP · App: https://rishil381.github.io/Datafg/

---

## 0:00 – 0:15 · Cold open (slide 1)
**ON SCREEN:** Title slide. Optionally start on a 2-second clip of the map with the clock slider dragging to 6:30.
**VO:**
> School ends at three. Most libraries and community centers close around six. But a lot of Bay Area parents don't get off work until eight, ten, or on weekends. So where can their kids actually be?

**EDIT:** Hold the title ~2 s after the last word before cutting.

## 0:15 – 0:45 · The problem (slide 2)
**ON SCREEN:** Timeline slide; the three stops appear one by one, then the 66% card.
**VO:**
> Maps measure access by distance: is there a library nearby? They never ask when it closes. And working late isn't rare. Of hourly Bay Area job postings that don't require a degree and list a schedule, two-thirds include evenings, nights or weekends. So we asked a different question: can a kid be somewhere supervised from three o'clock until their parent clocks out?

**EDIT:** Cut on "two-thirds" to a quick zoom on the 66% card.

## 0:45 – 1:15 · Data and method (slide 3)
**ON SCREEN:** Four dataset cards, then the dark "covered" rule box.
**VO:**
> We joined four datasets: about twenty-five hundred schools, thirteen hundred libraries, community centers and after-school programs with their opening hours, eighteen thousand bus stops, and Zillow rents to split neighborhoods into affordable, middle and expensive. Then one rule: a school counts as covered if a youth space within a mile and a half is open from three-thirty until the parent gets off, and a kid can reach it on foot or with a bus stop near both ends. If a place doesn't list hours, we don't count it.

## 1:15 – 1:40 · The illusion (slide 4)
**ON SCREEN:** 94% → 51%.
**VO:**
> On a normal map, ninety-four percent of schools look covered: there's something close by. But once you ask "is it open, and can a kid get there," that drops to about half. Close doesn't count.

**EDIT:** Pause half a second on "Close doesn't count." This is the title idea.

## 1:40 – 2:20 · The gap (slide 5)
**ON SCREEN:** Bar chart; bars rise in order.
**VO:**
> And it isn't equal. Near affordable housing, only thirty-eight percent of schools have a place open until six-thirty. In expensive neighborhoods, sixty-nine percent. At eight PM it's twenty-nine versus sixty-four. That's a thirty-one point gap, and it isn't luck: we resampled whole ZIP codes thousands of times and the gap never fell below about twenty points. Kids near cheaper housing are about half as likely to have somewhere to go.

**EDIT:** Optional lower-third with "p < 10⁻³⁰" for the stats-minded judges.

## 2:20 – 2:50 · Is it real? (slide 6)
**ON SCREEN:** Three check marks appear, then the "cause" card.
**VO:**
> We stress-tested it. Comparing schools with the same number of nearby places, expensive areas still have two and a half times the odds of coverage. Using family-size rentals gives the same gap. And it's not missing data. The real cause: the places near affordable schools close earlier. Only twenty-two percent are open at six-thirty, versus forty percent in wealthier areas.

## 2:50 – 4:00 · Live demo (slide 7 → screen recording)
**ON SCREEN:** Screen recording of https://rishil381.github.io/Datafg/ at desktop size, full screen.
**Record these shots (each 8–15 s, then cut together):**
1. Tap the **St. Elizabeth · Oakland** pill. Stat card shows **9 / 2 / 0**.
2. Drag the **clock-out slider** from 3 PM to 6:30 PM. The green bar walks right and the count falls to 0.
3. **Hover** the 4 PM bar: tooltip lists the two places and when they close.
4. **Click** "Oakland Public Library: César E. Chávez Branch" in the right list: the walking path draws along streets and the note says it closes 5:30.
5. Tap **Menlo-Atherton High · Atherton**. Stat card shows **13 / 7 / 5**.
6. (Optional) Type "Castlemont" in the search box: **8 / 6 / 0**.

**VO:**
> Here's our app. I pick St. Elizabeth in Oakland. A map shows nine youth spaces nearby. At three, two are open and reachable. By six-thirty, when this parent gets off work, zero. Drag the slider and you can watch the cliff. Hover a bar to see exactly which places are left. Click one and it shows how a kid would get there. Now Menlo-Atherton High, in Atherton: thirteen places, seven at three o'clock, and five still open at six-thirty. Same distance, very different evening.

**EDIT:** Speed up the slider drag 1.5× if it drags. Zoom into the stat card on each school pick. Mouse cursor on, click sounds off.

## 4:00 – 4:30 · What would help (slide 8)
**ON SCREEN:** Library table, then the before/after bars.
**VO:**
> What would help? We simulated keeping each of two hundred thirty-eight libraries open two hours later and picked the five that help the most schools in affordable areas. Together they give seventy-one schools their first option until six-thirty, and shrink the gap from thirty-one points to twenty-two: about a third of the gap, with buildings that already exist.

## 4:30 – 4:50 · Ethics and close (slide 9)
**ON SCREEN:** Ethics slide; hold on the links at the end.
**VO:**
> We chose not to use review-based safety scores, which are biased against public spaces in poorer neighborhoods. Hours can be missing or outdated, and our distances don't capture disabilities or real bus schedules. Everything is public at the link. Thanks for watching.

**EDIT:** Hold the final slide 3 s, then end. Check the total is under 5:00.

---

## Editing checklist
- Export at 1080p. Slides full screen (use the deck's Present mode or export to PowerPoint/PDF and screen-record).
- Record VO separately in a quiet room, then lay slides and demo clips under it.
- Captions on (helps accessibility and judges watching muted).
- Keep the demo clips silent except your voice.
- If over time, trim first: slide 3's dataset list, then slide 6's second check.
