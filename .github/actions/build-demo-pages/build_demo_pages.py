#!/usr/bin/env python3
"""Build a customized index.html for each demo_* folder under sub_pages/.

For every sub_pages/demo_* folder containing a replace.txt, this copies the
root index.html into that folder and, for each "key = value" line in
replace.txt, overwrites the line in the copy whose text before " = " matches
that key. A <base> tag is inserted so the copy's relative references to
css/, assets/ and data/ still resolve to the site root once the page is
deployed one level down from it (see the "Prepare deployment" step, which
publishes each sub_pages/demo_*/index.html back at the site's top level).
"""
import pathlib

ROOT = pathlib.Path.cwd()
INDEX_HTML = ROOT / "index.html"
SUB_PAGES_DIR = ROOT / "sub_pages"


def line_key(line: str) -> str:
    return line.split(" = ")[0]


def build_demo_page(demo_dir: pathlib.Path, replace_file: pathlib.Path) -> None:
    dest = demo_dir / "index.html"
    dest.write_text(INDEX_HTML.read_text(encoding="utf-8"), encoding="utf-8")

    replacements = {}
    for line in replace_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        replacements[line_key(line)] = line

    lines = dest.read_text(encoding="utf-8").splitlines(keepends=True)
    for i, line in enumerate(lines):
        ending = ""
        text = line
        if text.endswith("\r\n"):
            ending, text = "\r\n", text[:-2]
        elif text.endswith("\n"):
            ending, text = "\n", text[:-1]

        replacement = replacements.get(line_key(text))
        if replacement is not None:
            lines[i] = replacement + ending

    content = "".join(lines).replace("<head>", '<head>\n  <base href="../">', 1)
    dest.write_text(content, encoding="utf-8")
    print(f"Built {dest}")


def main() -> None:
    if not SUB_PAGES_DIR.is_dir():
        return
    for demo_dir in sorted(SUB_PAGES_DIR.glob("demo_*")):
        if not demo_dir.is_dir():
            continue
        replace_file = demo_dir / "replace.txt"
        if not replace_file.is_file():
            continue
        build_demo_page(demo_dir, replace_file)


if __name__ == "__main__":
    main()
