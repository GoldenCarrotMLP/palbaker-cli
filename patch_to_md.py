#!/usr/bin/env python3
"""
AI Studio / Gemini Patch to Markdown Converter
------------------------------------------------
Reads JSON tool-call payloads (from file, clipboard, or pipe),
decodes all escaped characters into their actual representations,
and writes a cleanly formatted .txt file with code blocks.
"""

import os
import sys
import json
import re
import argparse
import subprocess
from typing import List, Dict, Any, Tuple, Optional


def extract_json_blocks(raw_text: str) -> List[Dict[str, Any]]:
    """
    Extracts all JSON objects and lists from raw text, recursively unwrapping
    nested stringified JSON (like Gemini's 'queries' format) and comma-separated objects.
    """
    results = []

    def _scan_raw_string(text: str) -> List[Any]:
        found = []
        decoder = json.JSONDecoder()
        idx = 0
        n = len(text)
        while idx < n:
            if text[idx] in ('{', '['):
                try:
                    obj, end_idx = decoder.raw_decode(text, idx)
                    found.append(obj)
                    idx = end_idx
                    continue
                except json.JSONDecodeError:
                    pass
            idx += 1
        return found

    def _extract_recursive(data: Any):
        if isinstance(data, str):
            s = data.strip()
            if not s:
                return
            try:
                parsed = json.loads(s)
                _extract_recursive(parsed)
                return
            except (json.JSONDecodeError, TypeError):
                pass

            try:
                parsed = json.loads(f"[{s}]")
                _extract_recursive(parsed)
                return
            except (json.JSONDecodeError, TypeError):
                pass

            for b in _scan_raw_string(s):
                _extract_recursive(b)

        elif isinstance(data, dict):
            is_patch_or_tool = (
                any(k in data for k in ("filepath", "path", "file", "filename")) and
                any(k in data for k in ("search", "find", "old_str", "replace", "new_str", "content", "file_content"))
            )
            if is_patch_or_tool:
                results.append(data)
            else:
                for v in data.values():
                    _extract_recursive(v)

        elif isinstance(data, list):
            for item in data:
                _extract_recursive(item)

    for initial_obj in _scan_raw_string(raw_text):
        _extract_recursive(initial_obj)

    return results


def detect_language(filepath: str) -> str:
    """Infers markdown syntax highlighting tag from file extension."""
    ext = os.path.splitext(filepath)[1].lower()
    lang_map = {
        ".py": "python",
        ".ts": "typescript",
        ".tsx": "tsx",
        ".js": "javascript",
        ".jsx": "jsx",
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
        ".txt": "markdown",
    }
    return lang_map.get(ext, "")


def format_code_block(text: str, lang: str = "") -> str:
    """
    Wraps unescaped actual text into a safe markdown code fence.
    If the text contains backticks (```), expands fence size to avoid breaking Markdown formatting.
    """
    backticks = re.findall(r"`+", text)
    max_len = max([len(b) for b in backticks], default=0)
    fence_len = max(3, max_len + 1)
    fence = "`" * fence_len

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

        # Search and Replace
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

        # Whole File Write
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

        # Other JSON structure
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
        try:
            return subprocess.check_output(["powershell", "-command", "Get-Clipboard"], text=True)
        except Exception:
            pass

    if sys.platform == "darwin":
        try:
            return subprocess.check_output(["pbpaste"], text=True)
        except Exception:
            pass

    if sys.platform.startswith("linux"):
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
        help="Path for the output .txt file (default: matches input filename or 'gemini_patches.txt')."
    )
    parser.add_argument("-c", "--clipboard", action="store_true", help="Read input from clipboard.")
    parser.add_argument("--stdout", action="store_true", help="Print Markdown to stdout instead of saving to disk.")
    parser.add_argument("--no-lang", action="store_true", help="Do not add syntax highlighting tags to code fences.")

    args = parser.parse_args()

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

    patches = extract_json_blocks(combined_input)
    if not patches:
        print("[!] Error: No valid JSON tool blocks were found in the input.", file=sys.stderr)
        sys.exit(1)

    md_content, summary = generate_markdown(patches, include_lang=not args.no_lang)

    if args.output:
        out_path = args.output
    elif target_files:
        base, _ = os.path.splitext(primary_source_name)
        out_path = f"{base}.txt"
    else:
        out_path = "gemini_patches.txt"

    if args.stdout:
        print(md_content)
    else:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(md_content)

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