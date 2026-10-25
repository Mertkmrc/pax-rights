"""Download the public corpus listed in data/sources.yaml into data/raw/.

Usage: uv run python scripts/fetch_corpus.py [--force]

Sources marked `fetch: manual` are not downloaded (their sites block scripts);
the script only checks that you saved them to data/raw/ yourself.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "data" / "sources.yaml"
RAW = ROOT / "data" / "raw"
USER_AGENT = "pax-rights-corpus/0.1 (+https://github.com/Mertkmrc/pax-rights)"


def looks_like(content: bytes, content_type: str, fmt: str) -> bool:
    # Dead links on these sites often return 200 with an HTML page, so check the body.
    if fmt == "pdf":
        return content.startswith(b"%PDF")
    if fmt == "html":
        return "text/html" in content_type and not content.startswith(b"%PDF")
    raise ValueError(f"unknown format: {fmt}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true", help="re-download existing files")
    args = parser.parse_args()

    sources = yaml.safe_load(SOURCES.read_text())["sources"]
    RAW.mkdir(parents=True, exist_ok=True)
    manifest = {}
    missing_manual = []
    failed = []

    headers = {"User-Agent": USER_AGENT}
    with httpx.Client(headers=headers, follow_redirects=True, timeout=60) as client:
        for src in sources:
            path = RAW / f"{src['id']}.{src['format']}"

            if src["fetch"] == "manual":
                if not path.exists():
                    missing_manual.append(src)
                    continue
            elif args.force or not path.exists():
                try:
                    response = client.get(src["url"])
                    response.raise_for_status()
                except httpx.HTTPError as exc:
                    failed.append((src["id"], str(exc)))
                    continue
                content_type = response.headers.get("content-type", "")
                if not looks_like(response.content, content_type, src["format"]):
                    failed.append((src["id"], f"expected {src['format']}, got {content_type}"))
                    continue
                path.write_bytes(response.content)

            data = path.read_bytes()
            manifest[src["id"]] = {
                "file": path.name,
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
            print(f"ok      {path.name:28} {len(data) / 1024:8.0f} KB")

    (RAW / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    for src in missing_manual:
        print(f"manual  {src['id']:28} save from {src['url']}")
        print(f"        {'':28} to data/raw/{src['id']}.{src['format']}")
    for source_id, reason in failed:
        print(f"FAILED  {source_id:28} {reason}")

    print(f"\n{len(manifest)}/{len(sources)} documents in data/raw/")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
