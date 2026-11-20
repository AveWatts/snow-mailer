"""
python -m skireport gate                  season gate; writes go=true|false to $GITHUB_OUTPUT
python -m skireport thursday [--dry-run]  weekly report
python -m skireport monday [--dry-run]    storm alert check + weekend observation for calibration
python -m skireport auto [--dry-run]      thursday or monday, by the Pacific weekday
python -m skireport calibrate             stated confidence vs. how often it was right
"""
import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import gate, history, mail, render, report


def _output(key, value):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a") as f:
            f.write(f"{key}={value}\n")


def _deliver(name, subject, model, dry_run, out):
    html, text = render.render(name, model)
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(html)
        Path(out).with_suffix(".txt").write_text(text)
        logging.info("wrote %s", out)
    if dry_run:
        logging.info("dry run: not sending %r", subject)
        return
    mail.send(subject, text, html)
    logging.info("sent %r", subject)


def thursday(args):
    model = report.build_thursday()
    if not args.dry_run:
        history.save_thursday(model)
    subject = f"Cascades ski report - {model['generated_local']:%a %b %-d}"
    _deliver("report", subject, model, args.dry_run, args.out)


def monday(args):
    model = report.build_storm()
    if not args.dry_run:
        history.save_observed(model)
    if not model["zones"]:
        logging.info("no storm alert this week")
        return
    subject = f"Cascades storm alert - through {model['through']:%a %b %-d}"
    _deliver("storm", subject, model, args.dry_run, args.out)


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(prog="skireport")
    p.add_argument("command", choices=["gate", "thursday", "monday", "auto", "calibrate"])
    p.add_argument("--dry-run", action="store_true", help="build and render, but do not send")
    p.add_argument("--out", help="also write the rendered email to this .html path")
    args = p.parse_args()

    if args.command == "gate":
        go = gate.has_snow()
        _output("go", str(go).lower())
        logging.info("gate: %s", "snow found, continuing" if go else "no snow, skipping")
        return
    if args.command == "calibrate":
        for (metric, bucket), (rate, n) in history.calibration().items():
            print(f"{metric:9} stated {bucket:2d}-{bucket + 9}%  actual {rate:4.0%}  (n={n})")
        return
    command = args.command
    if command == "auto":
        command = "thursday" if datetime.now(timezone.utc).astimezone(report.PACIFIC).weekday() == 3 else "monday"
    {"thursday": thursday, "monday": monday}[command](args)


if __name__ == "__main__":
    sys.exit(main())
