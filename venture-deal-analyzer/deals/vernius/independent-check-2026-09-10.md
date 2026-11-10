# Independent first-principles check — done BEFORE the research fleet reported

Purpose: the house counter-agent rule protects against accepting a research
agent's numbers because they are confidently stated. So these were derived
independently from the deck's own parameters, written down first, and used to
audit the fleet's technical and demand findings rather than the reverse. Where
the fleet and this file disagree, the disagreement is logged, not silently
reconciled.

Author: analyst pass, 2026-09-10. Inputs: only the deck (24 GHz, FPV-class
airframe, HDPE radome, Shahed-class target) and standard radar/market
arithmetic.

## 1 · Radar link budget at 24 GHz from an FPV-class nose

Assumptions stated up front (all generous to the company):

| parameter | value | note |
|---|---|---|
| carrier | 24 GHz | deck (S07, twice) |
| λ | 12.5 mm | c/f |
| aperture D | 50 mm | fits an FPV interceptor nose behind a radome |
| aperture area A | 1.96e-3 m² | circular |
| gain G | ~19 dBi | 4πA/λ² at ~50% efficiency (22 dBi ideal) |
| 3 dB beamwidth | ~17.5° | ≈70λ/D — very coarse |
| Tx power | 20 dBm (0.1 W) | generous; COTS 24 GHz ICs are typically 10–13 dBm |
| target RCS σ | 0.5 m² | Shahed-class, composite airframe + metal engine; published estimates span ~0.1–1 m² |
| noise figure | 10 dB | |
| post-integration BW | 100 Hz | i.e. long coherent integration |

Radar equation Pr = Pt·G²·λ²·σ / ((4π)³·R⁴):

- Numerator: 0.1 × 6300 × 1.5625e-4 × 0.5 = **4.92e-2**
- (4π)³ = 1984 → Pr = **2.48e-5 / R⁴** W
- At R = 1,000 m: Pr = 2.48e-17 W = **−136 dBm**
- Noise floor: −174 + 10 + 10·log₁₀(100) = **−144 dBm**
- **SNR at 1 km ≈ 8 dB** — detectable, but only with that long integration
- At R = 2,000 m: 12 dB worse → **SNR ≈ −4 dB**, not detectable on these terms

**Conclusion (1): the honest detection range is ~1–1.5 km, not "beyond visual
range" in any general sense.** Doubling range costs 12 dB, which this aperture
and power budget do not have. Note the coherent-integration assumption is
itself load-bearing and hard on a maneuvering interceptor against a moving
target — motion compensation is the quiet difficulty.

**Conclusion (2): the real, defensible claim is ALL-WEATHER / NIGHT, not
RANGE.** Rain attenuation at 24 GHz is ~0.1–0.3 dB/km (vs ~1–2 dB/km at
77 GHz); fog and smoke are essentially transparent. So the seeker works when
the EO camera is blind — which is genuinely valuable and is most of the actual
value proposition. The deck's "beyond visual range" framing oversells it in
clear daylight and undersells it at night, where the comparison is not "further
than the camera" but "at all versus not at all."

**Conclusion (3): 24 GHz is a deliberate cost/availability choice with a real
cost.** Upside: mature COTS automotive silicon, cheap, better rain performance
than 77 GHz, and 24 GHz parts are far less export-controlled than purpose-built
seeker MMICs. Downside: the 24.0–24.25 GHz ISM allocation is only 200 MHz wide
(range resolution c/2B ≈ 0.75 m — adequate), and at a fixed aperture, angular
resolution scales with frequency, so 24 GHz gives ~3x worse beamwidth than
77 GHz would. 17.5° is coarse; monopulse/multi-channel angle estimation
recovers roughly beamwidth/10 (~1.75°, ≈30 m cross-range error at 1 km), which
is exactly why the architecture hands off to vision for terminal. **The
three-stage kill chain is internally coherent — but it implies the radar is a
short-range all-weather acquisition aid, not a midcourse guidance solution.**

**Conclusion (4): the engagement clock is short.** Shahed-136 ≈ 180 km/h
(50 m/s); jet Geran-3 ≈ 400–600 km/h (110–170 m/s). Interceptor ~55 m/s.
Head-on closing 100–225 m/s. At 1.5 km acquisition that is **7–15 seconds** of
engagement — enough for terminal correction, thin for "midcourse."

**Conclusion (5): an active emitter on the interceptor is a two-sided bet.**
It radiates, so it is detectable and jammable; "proven in a combat EW
environment" (S07, Jul 2026) is a claim about surviving ambient EW, which is
NOT the same as surviving *targeted* jamming or DRFM spoofing. That distinction
is a DD question, not a quibble.

## 2 · Demand arithmetic — the LOI and the 50,000/month claim

The deck never gives a unit price, so the LOI can only be read as a family of
implied volumes:

| implied unit price | units behind the $480M Ukraine LOI |
|---|---|
| $1,000 | 480,000 |
| $2,000 | 240,000 |
| $5,000 | 96,000 |
| $10,000 | 48,000 |

Sanity frame: the deck's own problem slide says Ukraine produces **100,000
interceptors/month** (1.2M/yr). Most are deliberately cheap — a few hundred to
a few thousand dollars — and a seeker only makes economic sense on the subset
whose cost can absorb it. At a **10% attach rate** and $2,000/unit, that is
120,000 units/yr ≈ **$240M/yr**. So the $480M Ukraine LOI implies roughly *two
full years of a 10%-attach, whole-country monopoly*.

**Conclusion (6): the $480M LOI is not a demand forecast, it is a ceiling
placeholder.** It is of the same order as the entire plausible Ukrainian
interceptor-subsystem budget, awarded to a pre-flight-test supplier with three
employees and $60K of lifetime revenue. The ratio that matters is
**$580M of LOIs against $60K of cash — about 10,000:1.**

**Conclusion (7): 50,000 units/month is a revenue claim in disguise.**
600,000 units/yr at even $1,000 = **$600M/yr**; at $2,000 = **$1.2B/yr** — from
a company whose first flight test is scheduled for December 2026. Nothing in
the deck's own numbers supports a demand pool of that size, and the ramp
(concept→600K units/yr in ~18 months) has no precedent in defense electronics.

**Conclusion (8): the $60K presale is the only measured demand number in the
deck**, and it is an evaluation-scale buy. Its value is as a *channel* signal
(a tier-1 SOF unit engaged at all) rather than a *volume* signal.

## 3 · What this file predicts the fleet should find

Written before results, as a calibration check on the research itself:
1. Detection range materially below "BVR"; all-weather is the real claim.
2. 24 GHz identified as COTS-automotive-derived.
3. LOI conversion rates in defense far below 100% — the fleet should find a
   defensible haircut, and it should be severe.
4. Interceptor OEM vertical integration named as the central commercial risk.
5. The "one PM replaces 200 engineers" claim unsupported by any public
   state-of-the-art in automated RF design.
