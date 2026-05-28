"""Binsai CLI — entry point for running demos.

Usage:
    binsai run mvp1
    binsai run mvp1 --seed 42 --speed 4 --lambda-demand 0.8
    binsai run mvp1 --no-llm        # dry_run_llm mode, no API key needed
    binsai run mvp1 --ablation-off  # start with regulation disabled
"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path


def _load_env() -> None:
    """Load .env from repo root or binsai/ directory."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    repo_root = Path(__file__).parent.parent.parent.parent
    candidates = [
        repo_root / ".env",
        repo_root / "binsai" / ".env",
        Path.cwd() / ".env",
    ]
    for path in candidates:
        if path.exists():
            load_dotenv(dotenv_path=path, override=False)
            break


def cmd_run(args: argparse.Namespace) -> None:
    _load_env()

    from .world.world import WorldConfig
    from .web.server import run

    config = WorldConfig(
        seed=args.seed,
        lambda_demand=args.lambda_demand,
        ablation_off=args.ablation_off,
        dry_run_llm=args.no_llm,
        speed=args.speed,
    )

    url = f"http://{args.host}:{args.port}/static/index.html"
    print(f"[binsai] Starting MVP1 demo: {url}")
    print(f"[binsai] seed={args.seed}  speed={args.speed}  lambda={args.lambda_demand}  ablation_off={args.ablation_off}  dry_run={args.no_llm}")

    if not args.no_browser:
        import threading
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    run(host=args.host, port=args.port, config=config)


def main() -> None:
    parser = argparse.ArgumentParser(prog="binsai", description="Binsai bio-inspired agent substrate")
    sub = parser.add_subparsers(dest="command")

    run_p = sub.add_parser("run", help="Run a demo scenario")
    run_p.add_argument("scenario", choices=["mvp1"], help="Scenario name")
    run_p.add_argument("--seed",           type=int,   default=42)
    run_p.add_argument("--speed",          type=float, default=2.0,  help="Ticks per second")
    run_p.add_argument("--lambda-demand",  type=float, default=0.5,  dest="lambda_demand")
    run_p.add_argument("--ablation-off",   action="store_true",      dest="ablation_off")
    run_p.add_argument("--no-llm",         action="store_true",      dest="no_llm", help="Dry-run LLM calls (no API key needed)")
    run_p.add_argument("--no-browser",     action="store_true",      dest="no_browser")
    run_p.add_argument("--host",           default="localhost")
    run_p.add_argument("--port",           type=int,   default=8765)

    args = parser.parse_args()

    if args.command == "run":
        cmd_run(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
