"""Check public documentation, relative links, examples, and image metadata offline."""

from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

import yaml
from markdown_it import MarkdownIt
from PIL import Image, ImageSequence

ROOT = Path(__file__).resolve().parents[1]
MARKDOWN = MarkdownIt("commonmark", {"html": True}).enable("table")
IGNORED = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "node_modules", "local"}
PRIVATE_ADDRESS = re.compile(
    r"\b(?:192\.168\.\d{1,3}\.\d{1,3}|10(?:\.\d{1,3}){3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b"
)
FORBIDDEN = re.compile(
    r"cutting-edge|robust ecosystem|seamlessly integrated|comprehensive solution|leveraging technology|\bjourney\b",
    re.I,
)
SECRET = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\bgh[pousr]_[A-Za-z0-9]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,}|\bAKIA[A-Z0-9]{16}|client-key-data\s*:|client-certificate-data\s*:"
)


class HtmlLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in {"src", "href"} and value:
                self.links.append(value)


def anchors(path: Path) -> set[str]:
    found = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^#{1,6} (.+)", line)
        if match:
            found.add(re.sub(r"[^\w -]", "", match[1].lower()).replace(" ", "-"))
    return found


def check() -> list[str]:
    errors = []
    files = [
        p for p in ROOT.rglob("*") if p.is_file() and not (set(p.relative_to(ROOT).parts) & IGNORED)
    ]
    for path in files:
        relative = path.relative_to(ROOT)
        if path.suffix.lower() == ".mp4":
            if path.stat().st_size > 10_000_000:
                errors.append(f"{relative}: video exceeds publication budget")
            # Stream decoding and moving-text review are separate publication checks.
            continue
        if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".gif"}:
            with Image.open(path) as im:
                budget = 6_000_000 if path.suffix.lower() == ".gif" else 800_000
                if max(im.size) > 2000 or path.stat().st_size > budget:
                    errors.append(f"{relative}: image exceeds publication budget")
                for frame in ImageSequence.Iterator(im):
                    frame.load()
                    if frame.getexif() or any(
                        k in frame.info for k in ("exif", "xmp", "XML:com.adobe.xmp", "comment")
                    ):
                        errors.append(f"{relative}: source metadata remains")
                        break
            continue
        if path.suffix.lower() not in {
            ".md",
            ".py",
            ".ps1",
            ".yaml",
            ".yml",
            ".json",
            ".txt",
            ".toml",
        }:
            continue
        text = path.read_text(encoding="utf-8")
        if PRIVATE_ADDRESS.search(text):
            errors.append(f"{relative}: private IPv4 address found")
        if SECRET.search(text):
            errors.append(f"{relative}: credential-shaped content found")
        if path.suffix == ".md":
            if re.search(r"[\u2013\u2014\U0001f300-\U0001faff]", text) or FORBIDDEN.search(text):
                errors.append(f"{relative}: prohibited prose style")
            tokens = MARKDOWN.parse(text)
            links = []
            for token in tokens:
                for child in token.children or []:
                    if child.type in {"link_open", "image"}:
                        links.append(child.attrGet("href") or child.attrGet("src"))
            html = HtmlLinks()
            html.feed(text)
            links.extend(html.links)
            for link in links:
                parsed = urlsplit(link)
                if parsed.scheme in {"http", "https", "mailto"}:
                    continue
                target = (path.parent / unquote(parsed.path)).resolve() if parsed.path else path
                if not target.is_relative_to(ROOT) or not target.exists():
                    errors.append(f"{relative}: broken or escaping link {link}")
                elif (
                    parsed.fragment
                    and target.suffix == ".md"
                    and unquote(parsed.fragment) not in anchors(target)
                ):
                    errors.append(f"{relative}: missing anchor {link}")
        elif path.suffix in {".yaml", ".yml"}:
            list(yaml.safe_load_all(text))
    manifest = list(yaml.safe_load_all((ROOT / "kubernetes/uptime-kuma/kuma.yaml").read_text()))
    objects = {obj["kind"]: obj for obj in manifest}
    pod = objects["Deployment"]["spec"]["template"]
    if objects["Deployment"]["spec"]["selector"]["matchLabels"] != pod["metadata"]["labels"]:
        errors.append("Kuma deployment selector does not match its pod labels")
    if objects["Service"]["spec"]["selector"] != pod["metadata"]["labels"]:
        errors.append("Kuma service selector does not match its pod labels")
    claim = pod["spec"]["volumes"][0]["persistentVolumeClaim"]["claimName"]
    if claim != objects["PersistentVolumeClaim"]["metadata"]["name"]:
        errors.append("Kuma pod references a missing PVC")
    print(
        f"Checked {len(files)} files, relative links, YAML relationships, prose, and image metadata."
    )
    return errors


if __name__ == "__main__":
    problems = check()
    for problem in problems:
        print(problem, file=sys.stderr)
    raise SystemExit(bool(problems))
