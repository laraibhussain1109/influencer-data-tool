"""Command-line interface for collecting Instagram deliverables."""

from __future__ import annotations

import argparse
import sys

from influencer_service.deliverables import collect_workbook, write_results
from influencer_service.instagram import InstagramAuthenticationError, InstaloaderClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect Instagram deliverable analytics from XLSX")
    parser.add_argument("workbook", help="Input XLSX containing influencer names and deliverable URLs")
    parser.add_argument("--output", default="instagram_analytics.xlsx", help="Output XLSX path")
    parser.add_argument("--max-comments", type=int, default=500, help="Maximum comments per post")
    args = parser.parse_args()
    if args.max_comments < 0:
        parser.error("--max-comments must be zero or greater")
    try:
        client = InstaloaderClient(args.max_comments)
    except InstagramAuthenticationError as error:
        print(f"Authentication required:\n{error}", file=sys.stderr)
        raise SystemExit(2) from None
    results = collect_workbook(args.workbook, client)
    output = write_results(args.output, results)
    failures = sum(item["status"] == "error" for item in results)
    print(f"Wrote {len(results)} deliverables to {output} ({failures} errors).")


if __name__ == "__main__":
    main()
