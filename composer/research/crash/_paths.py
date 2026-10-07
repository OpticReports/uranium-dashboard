"""Data/cache location for the crash study.  Yahoo histories, Composer backtests
and intermediate JSONs are large and reproducible, so they live OUTSIDE the repo:
set CRASH_DATA to a directory (default: this session's scratchpad path)."""
import os
SP = os.environ.get('CRASH_DATA', '/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/crash')
os.makedirs(os.path.join(SP, 'yh'), exist_ok=True)
