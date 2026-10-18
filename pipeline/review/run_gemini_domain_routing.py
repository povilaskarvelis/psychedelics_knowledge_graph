"""Read-only compatibility imports for archived model evaluations."""
from pipeline.review.run_domain_routing import *  # noqa: F401,F403
if __name__ == "__main__":
    raise SystemExit("Retired entry point. Use pipeline/review/run_domain_routing.py (Luna only).")
