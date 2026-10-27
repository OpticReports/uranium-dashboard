# Delta4 Capital memo — "Clone Robotics" — transcript of the legible pages

Supplied by Casey 2026-10-27 as full-resolution page images (`memo-p1.webp` …
`memo-p5.webp`; page 7 inline in chat). **Page 6 NOT YET SUPPLIED** (end of
"What could go right", start of "Risks"); its content is known only from the
low-resolution fragments in `legible-fragments.md`. The deck is NOT supplied.
Transcribed verbatim where quoted; tables reproduced in full. Every figure here
is the sponsor's or the company's claim (memo disclaimer, p.7: "has not been
independently verified").

---

## p.1

**INVESTMENT MEMO · CONFIDENTIAL — Clone Robotics — Bridge round: $200M
post-money valuation. Prepared by Alex Golding, Delta4 Capital · October 27, 2026**

**The TL;DR:** "Clone has created a new way of building robots. Instead of motors
and gearboxes, they use hydraulic pressure to pump water into "balloons" that act
as synthetic muscles and tendons. That makes their robots roughly one tenth the
cost to build of motor-driven competitors, and it lets them accomplish tasks
traditional robots have trouble with. By having a manufacturing cost 1/10th of
their competitors', they could pursue a pricing strategy and prevent their
competition from ever achieving economies of scale."

"The big negative is that they are behind. The leading American robotics labs had
working versions of their bipeds 12–18 months ago (1X's NEO Gamma, for example).
Clone has finished most of the upper body and is starting on the legs, with a full
biped MVP targeted for September 2027. The advancements in LLM's, VLA's, and World
Models mitigate part of this issue, but it is unknown by how much. The $200M
valuation reflects this state of play."

"However, because of the advancements in LLMs and open models, being early may not
be as big of an advantage as people think, especially once you factor in Clone's
much lower cost and the fact that it might be able to prevent its competitors from
ever achieve economies of scale and effectively end their future before they ever
hit economies of scale. That's the bet."

| | |
|---|---|
| Round | Pre-Series A bridge |
| Valuation | $200M post-money |
| Round size | **$9M target; $6.5M committed** |
| Expected close | **November 3 2026** |
| Vehicle | Delta4 Capital SPV |
| SPV terms | **2% one-time fee, 20% carried interest, plus a pro-rata share of SPV fees** |
| Next round | **Series A, $70–100M target** |
| Series A timing | Investor demos begin the week of November 9 |

**01 What Clone is building.** "Clone makes androids designed like humans: a
printed polymer skeleton, one pump, one vascular system, and a few hundred valves
and muscles. The founder's pitch is simple: if a single robot can do anything a
human can do, at human strength and speed and inside a human silhouette, people
will pay for it."

## p.2

"The core invention is the Myofiber, a hydraulic McKibben muscle: a braided sleeve
around a bladder that contracts like a real muscle when it is pressurized. Muscles
pull tendons, tendons move joints, and they work in antagonistic pairs (a flexor
and an extensor), just like ours. **A 2 kW pump in the abdomen pressurizes water to
10–40 bar, and 306 proportional microvalves meter every muscle stroke.**"

"Tesla and 1X use tendon drives, which are a muscle emulator built from motors,
pulleys and gearboxes packed into the forearm. Clone just uses muscles. There isn't
a single gear in the robot."

**Key facts about the clone:**
- **66 lb** — grip strength, 0.1 s contraction, 42 dB
- **$9** — per muscle, at 10 kW/kg vs 0.5 kW/kg for a motor
- **$1.1K** — hand bill of materials at 100 units, vs. $50k for Apptronik's hand
- **25 DoF** — in the hand, matching the human hand, vs 13 DoF in Boston Dynamics' Atlas

**"The hand is the hardest part about robotics, and it's where Clone leads."**
"Getting human-level hands inside a human silhouette is the highest technical bar
in humanoid robotics. Clone's hand can grip a slender handle, cut a pineapple, hold
a heavy cast-iron pan, open the heaviest office door and pull the trigger on a power
drill. Because it's human-sized, it also fits into tools and spaces built for
people. The hand was built in 18 months on a budget of about half a million
dollars. It is now on its fourth generation."

| Hand | Drive | DoF | Finger force | BOM at 100 units |
|---|---|---|---|---|
| Human | Musculotendons | 25 | ~40–60 N | – |
| **Clone** | **Fluidic musculotendons** | **25** | **~45 N at 10 bar** | **$1.1K** |
| 1X NEO Hand | Tendon drive (motor pulls tendon) | 25 | 45 N | ~$10–16K |
| Tesla Gen 3 | Tendon drive (motor pulls tendon) | 24 | ~30 N | ~$11–20K |
| Wuji 2 | Direct drive, no wrist | 20 | 15 N | ~$12–15K |
| Sharpa | Direct drive, no wrist | 22 | 20 N | ~$45K |

*"Source: Clone investor presentation. Competitor bills of materials are Clone's
estimates."*

"On raw fingertip force, Clone is roughly at parity with 1X. The advantage is cost,
packaging and headroom. Muscle strength scales with system pressure, so raising the
pressure 50% makes every muscle 50% stronger, and **the muscles are engineered to
survive 10x their operating pressure**. A motor-driven robot needs new motors and
gear trains to do the same."

**Manufacturing.** "This is the part I find most compelling. In a motor-driven
humanoid, actuators are the bulk of the cost, and every joint needs its own DC motor
and custom gearing. Clone retrofits industrial braiding machines to braid muscle by
the kilometer, cut to exact lengths. The founder puts actuator production capacity
for 10,000 Clones at a couple of million dollars of capex: a handful of braiding
machines, a CNC machine for valves and one machine for hydraulic power units."

## p.3

**Software.** "Clone isn't trying to reinvent the foundation model. The plan is to
do what Physical Intelligence, Skild and Generalist are doing: take an open backbone
model and post-train it with reinforcement learning on Clone's robot, simulation and
motion-capture data. Underneath that, **Clone's own control stack (a whole-body pose
controller, a muscle force controller and a valve pressure regulator) is already
running on Torso 4.** The founder expects models to run on the robot's own chips as
quantization improves."

"The founder's view is that locomotion is close to a solved problem: sim-to-real
pipelines will give every company a robot that walks. The real gap is manipulation,
which comes down to data and compute. Data is becoming a liquid market, and the
founder gets about ten emails a day from data brokers. That favors the company with
the best hands, because demonstration data from humans transfers most directly to a
body shaped like a human's."

**02 Where they are today.** "Clone spent its first years focused on the hand and
torso. **The torso that was shown publicly, Torso 3, has 164 degrees of freedom, 182
muscles and 251 sensors.** Since then the team has done a ground-up redesign, and
Torso 4 is about to be finished. Torso 4 is what they plan to deploy at the first one
or two customer sites."

"The legs are next. Clone could build motor-driven legs, but it would be a much
worse robot. **The breakthrough was bringing on Joe Hill, whose miniaturized
hydraulics let them fit the power unit, valves and actuators inside the body, so the
biped won't need a battery backpack or a tether.** The legs should be done by
June/July 2027, and the full untethered biped MVP should be ready in September 2027.
That is also the milestone they plan to raise the Series B on."

| Target | Milestone |
|---|---|
| Q3 2026 | **Bimanual Torso 4 (100K cycles); low-level joint control and teleoperation**; GPU physics simulation of the torso |
| Q4 2026 | Series A |
| Jan 2027 | Industrial Torso available to customers: drill and screw, pick and pack |
| Q3 2027 | Untethered Protoclone 2 biped; whole-body loco-manipulation; 1K hours of ground-truth data |
| Q4 2027 | Series B, $1–2B target |
| Apr 2028 | Hotel Clone: housekeeping, starting with putting a fitted sheet on a mattress |
| Q4 2028 | **Production Clone rated for 10M cycles**; 1M hours of egocentric data; Clone's first VLA model |
| Q1 2030 | $1B in sales on 10,000 Clones |

*"Source: Clone investor presentation and founder calls. Dates are company targets."*

**03 Customers and go-to-market.** "Clone will start with stationary torsos in
industrial settings, move to bipeds in hotels, and only then go into the home. The
founder wants to saturate hotels first because every room starts in a different
messy state and ends in the same clean one, which is a good training ground for the
general-purpose skills a home robot needs."

## p.4

"Clone is in the process of signing its first pilot sites. **Nothing is signed yet,
but the inbound is real:**"
- **Automotive:** "Mercedes-Benz and Volkswagen Group both reached out. Mercedes
  wants a robot that can run a power drill, drive screws and use a hammer, which
  needs a human-scale hand with a tight grip."
- **Aerospace:** "AST SpaceMobile, for soldering and other stationary assembly work."
- **Hospitality:** "Moxy Hotels, for housekeeping, introduced through Greg Racz,
  **who is also an investor in this round and a friend of Delta4 Capital's**."
- **Logistics:** "Procter & Gamble for pick-and-pack, and a path to Ranpak, a key 3PL
  for Walmart and Amazon that hasn't partnered with any humanoid company yet."
- **Manufacturing:** "a Taiwanese carbon-fiber bicycle manufacturer that supplies
  Tour de France teams."

**Unit economics.** "Clone plans to sell the Industrial Torso at **$178K on a $16K
bill of materials**, and the biped at **$214K on a $19,250 bill of materials**. Both
are about a 91% gross margin before labor. The customer paybacks below assume Clone
captures 85% of the theoretical labor savings."

| Deployment | Loaded cost per FTE | Annual savings captured | Price | Payback |
|---|---|---|---|---|
| Automotive manufacturing, two shifts (Mercedes-Benz) | $101,700 | $172,890 | $178K | ~12 months |
| 3PL pick-and-pack, two shifts (Ranpak) | $63,500 | $107,950 | $178K | ~20 months |
| NYC hotel housekeeping, 1.23 FTEs replaced | $58,000 | $60,639 | $214K | ~42 months |

*"Loaded labor cost is wage × 2,080 hours × the BLS compensation multiplier. NYC
housekeeping assumes an average wage of $22.62/hour, or about $58K a year per
housekeeper after benefits."*

"Industrial paybacks are strong. Housekeeping is a longer payback at today's NYC
wages, which is why the industrial torso comes first. The founder's target of $1B in
sales on 10,000 units works out to about $100K per robot, well below list price, so
I read that target as conservative (which is good, because it enables Clone to
underprice its competition and potentially prevent them from achieving scale)."

**04 Team.** "**Clone has 65 people, and 63 of them are engineers or technicians.
Most of the team (60 people) is in Poland**, where the company was started, and 5
are in Mountain View. The founder plans to relocate about 10 engineers to Mountain
View. The company has been run very lean: a chief of staff handles HR, finance,
accounting, compliance and legal, and there are no business or go-to-market hires
yet."

## p.5

| Dhanush Radhakrishnan — Founder & CEO · Y Combinator | Damian Lickindorf — Chief Technology Officer | Joseph Hill — Chief Engineer |
|---|---|---|
| BS in Mathematics, NYU; physics and energy background | BS in Mechanical Engineering, Politechnika Wrocławska | BS in Mechanical Engineering, University of Nevada, Reno |
| Fusion research on a DOE tokamak; published 3D MHD results in *APS* and *Nuclear Fusion* | Designed, built and sold cable-driven robot dogs comparable to Boston Dynamics' Spot, fabricating the parts himself | Founded Adaract, which builds micro-hydraulic components for prosthetics and robotics |
| Founded a company using reinforcement learning to diagnose medical symptoms while a senior at NYU | Technology lead at HYPR, Tim Kentley Klay's robotics startup | Developed stronger, higher-pressure, more durable muscles, miniaturized valves and compact hydraulic power units |
| Transformer-based patent search for molecules at Roivant | Lead inventor of Clone's Hand 36, Torso 4 and Protoclone 2 | |

"Joe matters a lot here. **Clone signed an exclusive license to Adaract's technology
for $1.5M in March 2026, credited toward a $4M acquisition of the company.
Adaract's valves are rated for 100 million cycles**, and its hardware is what makes
the untethered biped possible."

**05 Financing history.**

| Round | Amount | Post-money | Investors |
|---|---|---|---|
| Pre-seed, Nov 2021 | $0.6M | $20M | Trevor Blackwell, Balaji Srinivasan, Ethan Perez and other angels |
| Seed | $6M | $33.8M | Led by Initialized (Garry Tan's fund) |
| Mar 2025 | $10M | $150M | Access Industries (Len Blavatnik's family office) |
| **Bridge (this round)** | **$9M target** | **$200M** | **Early Game Ventures, will.i.am, Matt Bellamy, Greg Racz and others; $6.5M committed** |

"Clone has raised about $24M to date, against the hundreds of millions spent by
motor-driven competitors. Access Industries plans to take its pro-rata in the Series
A. **The company has about $2.5M in the bank and burns $750–900K a month, so the rest
of the bridge will carry them through the Series A.** I encouraged them to
oversubscribe the bridge so they have more leverage in the Series a negotiations."

**06 What could go right.**

"**The best hand and most human like form factor wins the data race.** If locomotion
commoditizes and manipulation comes down to data, the robot built most like a human
gets the most out of every video, motion-capture file and glove recording. Clone
doesn't need to be first to a biped to be first to truly useful hands."

"**Cost becomes the moat.** Clone's entire torso has a $16K bill of materials, which
is about what a single competitor's hand costs. If that holds at volume, Clone can
undercut everyone on price and still earn roughly a 91% gross margin before labor."

## p.6 — NOT SUPPLIED

Known only from the low-resolution screenshot (`legible-fragments.md`, read at 4x;
treat as leads): "Scale without heavy dilution" (~a couple of million of capex for
10,000 Clones); "Industrial pilots convert quickly" (~12-month payback; a paid pilot
plus a first humanoid deal with a 3PL would…); "The biped lands on time" (if the
untethered biped ships Sept 2027, a $1–2B Series B…); "Hotels and the consumer
market"; **07 RISKS:** "They are behind" (leaders had working bipeds 12–18 months
ago; Clone's biped about a year away; open models narrow the gap but don't close
it — "one of the biggest risks in the deal"); "Durability and battery life are
unproven at production scale" ("today's muscles are rated for 100,000 contraction
cycles…"; "depends on Adaract's valves and on reaching the 10 million-cycle target";
battery life of the untethered biped "a couple of hours" (?)); "No signed customers
yet" (pipeline is inbound interest, not contracts; converting AST SpaceMobile and
Moxy into paid pilots is the next proof point); "Key acquisition not closed" ("The
Adaract acquisition hasn't closed and closing requires Clone to hold $?M in cash, so
in practice it closes with the Series A. The biped roadmap depends on it.");
"Financing risk" ("Runway is short, and the plan depends on doing a $70–100M Series A
in the coming months."); "Thin business team" ("almost entirely technical; Clone will
need to hire for sales, finance and operations after the Series A. I think they will
be able to once they raise the money.").

## p.7

**IP and founder history.** "The original artificial muscle system was created by a
co-founder who has since left the company. Clone says its technology is patented, and
I am confirming IP assignment as part of diligence."

**Geography and policy.** "Most of the team is in Poland. The founder flagged that US
policy may require humanoids sold here to be built largely from American components.
I'm looking into what that means for where Clone manufactures."

**08 Next steps.** "The bridge closes next week, and the Series A process starts the
week of November 9, when traditional Silicon Valley VCs and PE funds will come to see
the robot. **I'm flying out to SF on November 12 to see it in person** and meet the
other investors. Before the SPV closes, I will focus on:"
- Seeing Torso 4 run live over a Zoom
- Confirming IP assignment and patent coverage
- Reviewing the Adaract acquisition terms

"If those go well, I will probably invest. If you want in at the bridge round
valuation of $200M, let me know." — Alex Golding, Delta4 Capital

*Disclaimer: "This memo is confidential and is provided for informational purposes
only to prospective investors in a Delta4 Capital special purpose vehicle. It is not
an offer to sell or a solicitation of an offer to buy any security; any offer will be
made only through the SPV's definitive documents. The information in this memo comes
from Clone Robotics' investor presentation and conversations with the company's
founder in October 2026, and has not been independently verified. Roadmap dates,
projections and unit economics are the company's estimates and are forward-looking."*
