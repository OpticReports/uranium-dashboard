"""Barbell Lab — personal quant research platform.

Design principles (from the build spec, in priority order):
1. Correctness and statistical honesty over features. A wrong number
   presented confidently is the worst output. Fail loudly.
2. Nothing downstream of the data layer is trusted until the acceptance
   gates in ``validate.acceptance`` pass.
3. Every evaluated strategy variant is logged to the trial registry;
   significance is always reported against the CUMULATIVE trial count.
4. Every reported metric carries provenance (live ETF vs spliced proxy).
"""

__version__ = "0.1.0"
