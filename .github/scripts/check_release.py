"""Check a published release against this repository's conventions.

Run by .github/workflows/release.yml on every release published or edited:

    python .github/scripts/check_release.py

It reads the release from the event GitHub hands the workflow, the manifest from
the checked-out tag and the tags from git. Errors fail the job; warnings only
annotate it.

- The tag is X.Y.Z with **no "v"** — 1.1.0 to 1.6.0 all read that way, and HACS
  shows it as the version.
- It matches `version` in manifest.json at that tag: HACS installs the tag but
  Home Assistant reports the manifest's version, and a mismatch makes the two
  disagree about what is installed.
- Every `compare/A...B` link in the body names tags that exist, B being this
  release — 1.5.1 shipped with `compare/v1.5.0...v1.5.1`, a link to nothing.
- The title reads `vX.Y.Z` and the link starts from the previous tag: warnings,
  being conventions rather than anything a user is misled by.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

TAG_RE = re.compile(r"\d+\.\d+\.\d+")
COMPARE_RE = re.compile(r"/compare/([^\s/)\]]+?)\.\.\.([^\s/)\]#?]+)")
MANIFEST = Path("custom_components/klereo/manifest.json")


def _version(tag):
    return tuple(int(part) for part in tag.split("."))


def check(tag, name, body, manifest_version, tags):
    """Return (errors, warnings) for a release, as lists of sentences."""
    errors, warnings = [], []
    if not TAG_RE.fullmatch(tag or ""):
        errors.append(f"tag {tag!r} is not X.Y.Z (tags here carry no 'v')")
    if manifest_version != tag:
        errors.append(f"manifest.json says version {manifest_version!r}, "
                      f"the tag is {tag!r}")
    if name != f"v{tag}":
        warnings.append(f"title {name!r}, expected 'v{tag}'")

    links = COMPARE_RE.findall(body or "")
    if not links:
        warnings.append("no changelog link (compare/A...B) in the description")
    releases = sorted((t for t in tags if TAG_RE.fullmatch(t)), key=_version)
    previous = None
    if tag in releases and releases.index(tag) > 0:
        previous = releases[releases.index(tag) - 1]
    for base, head in links:
        for ref in (base, head):
            if ref not in tags:
                errors.append(f"changelog link compare/{base}...{head} names "
                              f"{ref!r}, which is not a tag")
        if head != tag:
            errors.append(f"changelog link compare/{base}...{head} does not end "
                          f"at this release, {tag!r}")
        if previous and base in tags and base != previous:
            warnings.append(f"changelog link starts at {base!r}, the previous "
                            f"release is {previous!r}")
    return errors, warnings


def main():
    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as event_file:
        release = json.load(event_file)["release"]
    manifest_version = json.loads(MANIFEST.read_text(encoding="utf-8")).get("version")
    tags = set(subprocess.run(["git", "tag"], capture_output=True, text=True,
                              check=True).stdout.split())
    errors, warnings = check(release["tag_name"], release.get("name") or "",
                             release.get("body") or "", manifest_version, tags)
    for warning in warnings:
        print(f"::warning::{warning}")
    for error in errors:
        print(f"::error::{error}")
    if not errors:
        print(f"Release {release['tag_name']} is consistent.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
