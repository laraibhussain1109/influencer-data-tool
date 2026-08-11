"""Command-line interface for collecting Instagram deliverables."""

from __future__ import annotations

import argparse

from influencer_service.deliverables import collect_workbook, write_results
from influencer_service.instagram import InstaloaderClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect Instagram deliverable analytics from XLSX")
    parser.add_argument("workbook", help="Input XLSX containing influencer names and deliverable URLs")
    parser.add_argument("--output", default="instagram_analytics.xlsx", help="Output XLSX path")
    parser.add_argument("--max-comments", type=int, default=500, help="Maximum comments per post")
    args = parser.parse_args()
    if args.max_comments < 0:
        parser.error("--max-comments must be zero or greater")
    results = collect_workbook(args.workbook, InstaloaderClient(args.max_comments))
    output = write_results(args.output, results)
    failures = sum(item["status"] == "error" for item in results)
    print(f"Wrote {len(results)} deliverables to {output} ({failures} errors).")


if __name__ == "__main__":
    main()
