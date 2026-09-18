#!/usr/bin/env python3
"""
AI Studio / Gemini Patch to Markdown Converter
------------------------------------------------
Reads JSON tool-call payloads (from file, clipboard, or pipe),
decodes all escaped characters into their actual representations,
and writes a cleanly formatted .md file with code blocks.
"""

import os
import sys
import json
import re
import argparse
from typing import List, Dict, Any, Tuple, Optional


def extract_json_blocks(raw_text: str) -> List[Dict[str, Any]]:
    """
    Extracts all JSON objects and lists from raw text,
    ignoring markdown wrappers and separator words.
    """
    results = []
    decoder = json.JSONDecoder()
    idx = 0
    n = len(raw_text)

    while idx < n:
        char = raw_text[idx]
        if char in ('{', '['):
            try:
                obj, end_idx = decoder.raw_decode(raw_text, idx)
                if isinstance(obj, dict):
                    results.append(obj)
                elif isinstance(obj, list):
                    for item in obj:
                        if isinstance(item, dict):
                            results.append(item)
                idx = end_idx
                continue
            except json.JSONDecodeError:
                pass
        idx += 1

    return results


def detect_language(filepath: str) -> str:
    """Infers markdown syntax highlighting tag from file extension."""
    ext = os.path.splitext(filepath)[1].lower()
    lang_map = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".json": "json",
        ".cpp": "cpp",
        ".c": "c",
        ".cs": "csharp",
        ".h": "cpp",
        ".hpp": "cpp",
        ".html": "html",
        ".css": "css",
        ".sh": "bash",
        ".bat": "batch",
        ".ps1": "powershell",
        ".rs": "rust",
        ".go": "go",
        ".lua": "lua",
        ".ini": "ini",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".md": "markdown",
    }
    return lang_map.get(ext, "")


def format_code_block(text: str, lang: str = "") -> str:
    """
    Wraps actual text into a safe markdown code fence.
    If the text contains backticks (```), expands fence size (````) to avoid syntax breaks.
    """
    # Find longest sequence of consecutive backticks inside the text
    backticks = re.findall(r"`+", text)
    max_len = max([len(b) for b in backticks], default=0)
    fence_len = max(3, max_len + 1)
    fence = "`" * fence_len

    # Ensure text ends cleanly before closing fence
    clean_text = text.rstrip("\r\n")
    return f"{fence}{lang}\n{clean_text}\n{fence}"


def generate_markdown(
    patches: List[Dict[str, Any]], 
    include_lang: bool = True
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Converts list of patch dictionaries into markdown document.
    Returns (markdown_content, summary_list).
    """
    md_lines = []
    summary = []

    for i, patch in enumerate(patches, start=1):
        filepath = (
            patch.get("filepath") or 
            patch.get("path") or 
            patch.get("file") or 
            f"unknown_target_{i}"
        )
        search_str = patch.get("search") or patch.get("find") or patch.get("old_str")
        replace_str = patch.get("replace") or patch.get("replacement") or patch.get("new_str")
        content_str = patch.get("content") or patch.get("file_content")

        lang = detect_language(filepath) if include_lang else ""

        md_lines.append(f"## Target File: `{filepath}`\n")

        # Case 1: Search and Replace
        if search_str is not None and replace_str is not None:
            md_lines.append("search:")
            md_lines.append(format_code_block(search_str, lang))
            md_lines.append("\nreplace:")
            md_lines.append(format_code_block(replace_str, lang))
            md_lines.append("\n---\n")

            summary.append({
                "index": i,
                "filepath": filepath,
                "type": "Search & Replace",
                "search_lines": len(search_str.splitlines()),
                "replace_lines": len(replace_str.splitlines()),
            })

        # Case 2: Whole File Write / Create
        elif content_str is not None:
            md_lines.append("content:")
            md_lines.append(format_code_block(content_str, lang))
            md_lines.append("\n---\n")

            summary.append({
                "index": i,
                "filepath": filepath,
                "type": "Full File Write",
                "search_lines": 0,
                "replace_lines": len(content_str.splitlines()),
            })

        # Case 3: Other / Unknown tool format
        else:
            raw_pretty = json.dumps(patch, indent=2)
            md_lines.append("payload:")
            md_lines.append(format_code_block(raw_pretty, "json"))
            md_lines.append("\n---\n")

            summary.append({
                "index": i,
                "filepath": filepath,
                "type": "Raw JSON Payload",
                "search_lines": 0,
                "replace_lines": len(raw_pretty.splitlines()),
            })

    return "\n".join(md_lines), summary


def read_clipboard() -> str:
    """Cross-platform clipboard reader."""
    try:
        import pyperclip
        return pyperclip.paste()
    except ImportError:
        pass

    if sys.platform == "win32":
        import subprocess
        try:
            return subprocess.check_output(["powershell", "-command", "Get-Clipboard"], text=True)
        except Exception:
            pass

    if sys.platform == "darwin":
        import subprocess
        try:
            return subprocess.check_output(["pbpaste"], text=True)
        except Exception:
            pass

    if sys.platform.startswith("linux"):
        import subprocess
        try:
            return subprocess.check_output(["xclip", "-selection", "clipboard", "-o"], text=True)
        except Exception:
            pass

    raise RuntimeError("Clipboard unavailable. Pass a file path or install pyperclip: pip install pyperclip")


def main():
    parser = argparse.ArgumentParser(
        description="Convert Gemini/AI Studio escaped JSON tool calls into human-readable Markdown."
    )
    parser.add_argument(
        "files", 
        nargs="*", 
        help="One or more JSON files to read (bypasses terminal length limits)."
    )
    parser.add_argument(
        "-f", "--file", "-i", "--input", 
        dest="flag_files", 
        action="append", 
        default=[],
        help="Input JSON file path."
    )
    parser.add_argument(
        "-o", "--output", 
        help="Path for the output .md file (default: matches input filename or 'gemini_patches.md')."
    )
    parser.add_argument("-c", "--clipboard", action="store_true", help="Read input from clipboard.")
    parser.add_argument("--stdout", action="store_true", help="Print Markdown to stdout instead of saving to disk.")
    parser.add_argument("--no-lang", action="store_true", help="Do not add syntax highlighting tags to code fences.")

    args = parser.parse_args()

    # Determine input
    target_files = list(args.files) + list(args.flag_files)
    raw_inputs = []
    primary_source_name = "clipboard"

    if target_files:
        primary_source_name = target_files[0]
        for fp in target_files:
            if not os.path.exists(fp):
                print(f"[!] Error: File not found: '{fp}'", file=sys.stderr)
                sys.exit(1)
            try:
                with open(fp, "r", encoding="utf-8-sig") as f:
                    raw_inputs.append(f.read())
            except Exception as e:
                print(f"[!] Error reading '{fp}': {e}", file=sys.stderr)
                sys.exit(1)
    elif args.clipboard:
        try:
            raw_inputs.append(read_clipboard())
        except Exception as e:
            print(f"[!] Error reading clipboard: {e}", file=sys.stderr)
            sys.exit(1)
    elif not sys.stdin.isatty():
        raw_inputs.append(sys.stdin.read())
        primary_source_name = "stdin"
    else:
        print("[*] No input file or pipe provided. Checking clipboard...")
        try:
            raw_inputs.append(read_clipboard())
        except Exception:
            parser.print_help()
            sys.exit(1)

    combined_input = "\n".join(raw_inputs)
    if not combined_input.strip():
        print("[!] Error: Input content is empty.", file=sys.stderr)
        sys.exit(1)

    # Extract JSON objects
    patches = extract_json_blocks(combined_input)
    if not patches:
        print("[!] Error: No valid JSON tool blocks were found in the input.", file=sys.stderr)
        sys.exit(1)

    # Convert to Markdown
    md_content, summary = generate_markdown(patches, include_lang=not args.no_lang)

    # Determine output filename
    if args.output:
        out_path = args.output
    elif target_files:
        base, _ = os.path.splitext(primary_source_name)
        out_path = f"{base}.txt"
    else:
        out_path = "gemini_patches.txt"

    # Write or print
    if args.stdout:
        print(md_content)
    else:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(md_content)

    # Output Summary Report
    print("\n" + "=" * 70)
    print(" PATCH TO MARKDOWN: [SUCCESS]")
    print("=" * 70)
    print(f"Total Blocks Processed: {len(summary)}")
    print(f"Destination:            {os.path.abspath(out_path) if not args.stdout else 'STDOUT'}\n")
    print("Processed Items:")
    for item in summary:
        print(f"  • [#{item['index']}] {item['type']} -> `{item['filepath']}`")
        if item['type'] == "Search & Replace":
            print(f"    ↳ Search: {item['search_lines']} lines | Replace: {item['replace_lines']} lines")
        else:
            print(f"    ↳ Content: {item['replace_lines']} lines")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()