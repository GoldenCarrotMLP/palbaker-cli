#!/usr/bin/env python3
"""
AI Studio / Gemini Patch to Markdown Converter
------------------------------------------------
Reads JSON tool-call payloads (from file, clipboard, or pipe),
decodes all escaped characters into their actual representations,
and writes a cleanly formatted file with Markdown code blocks.

Supports:
 - Search-and-replace & whole file writes
 - Terminal command extraction (bash/shell)
 - Recursive unwrapping of nested 'queries' payloads
 - Smart Path Healing (resolves files across subdirectories)
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
    Matches aistudio_tool.py extraction criteria.
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
            # Check for file patch OR terminal command (identical to aistudio_tool.py)
            is_file_tool = any(k in data for k in ("filepath", "path", "file", "filename"))
            is_cmd_tool = any(k in data for k in ("command", "cmd", "bash", "shell"))

            if is_file_tool or is_cmd_tool:
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


def find_file_on_disk(base_dir: str, filepath: str) -> Optional[str]:
    """Resolves file path with auto-healing if Gemini omitted root folders."""
    direct = os.path.normpath(os.path.join(base_dir, filepath))
    if os.path.exists(direct) and os.path.isfile(direct):
        return direct

    norm_suffix = os.path.normpath(filepath).lower()
    candidates = []

    for root, _, files in os.walk(base_dir):
        if any(ign in root for ign in (".git", "node_modules", "Saved", "Cooked", "__pycache__", ".venv")):
            continue
        for file in files:
            full_path = os.path.normpath(os.path.join(root, file))
            if full_path.lower().endswith(norm_suffix):
                candidates.append(full_path)

    if len(candidates) == 1:
        return candidates[0]
    elif len(candidates) > 1:
        return min(candidates, key=len)

    return None


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
        ".toml": "toml",
        ".sql": "sql",
        ".xml": "xml",
        ".md": "markdown",
        ".txt": "markdown",
    }
    return lang_map.get(ext, "")


def format_code_block(text: Any, lang: str = "") -> str:
    """
    Wraps unescaped actual text into a safe markdown code fence.
    If the text contains backticks (```), expands fence size to avoid breaking Markdown formatting.
    """
    if not isinstance(text, str):
        text = str(text)

    backticks = re.findall(r"`+", text)
    max_len = max([len(b) for b in backticks], default=0)
    fence_len = max(3, max_len + 1)
    fence = "`" * fence_len

    clean_text = text.rstrip("\r\n")
    return f"{fence}{lang}\n{clean_text}\n{fence}" if clean_text else f"{fence}{lang}\n{fence}"


def generate_markdown(
    patches: List[Dict[str, Any]], 
    base_dir: Optional[str] = None,
    include_lang: bool = True
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Converts list of tool dictionaries (edits or commands) into a markdown document.
    Returns (markdown_content, summary_list).
    """
    md_lines = []
    summary = []

    for i, patch in enumerate(patches, start=1):
        raw_filepath = (
            patch.get("filepath") or 
            patch.get("path") or 
            patch.get("file") or 
            patch.get("filename")
        )
        search_str = patch.get("search") or patch.get("find") or patch.get("old_str")

        # Support 'content' / 'file_content' as replacement if 'search' is present
        replace_str = (
            patch.get("replace") or 
            patch.get("replacement") or 
            patch.get("new_str") or 
            ((patch.get("content") or patch.get("file_content")) if search_str is not None else None)
        )
        full_content = (patch.get("content") or patch.get("file_content")) if search_str is None else None

        cmd_str = (
            patch.get("command") or 
            patch.get("cmd") or 
            patch.get("bash") or 
            patch.get("shell")
        )

        # ---------------------------------------------------------
        # Case 1: Terminal Command
        # ---------------------------------------------------------
        if cmd_str is not None and search_str is None and full_content is None:
            cmd_text = str(cmd_str).strip()
            md_lines.append(f"## Terminal Command [#{i}]\n")
            md_lines.append("command:")
            md_lines.append(format_code_block(cmd_text, "bash" if include_lang else ""))
            md_lines.append("\n---\n")

            summary.append({
                "index": i,
                "type": "Terminal Command",
                "target": cmd_text,
                "lines": len(cmd_text.splitlines())
            })
            continue

        # ---------------------------------------------------------
        # Case 2: File Operations (Search-Replace / Full File Write)
        # ---------------------------------------------------------
        display_path = raw_filepath or f"unknown_target_{i}"
        healed_note = ""

        # Perform smart path healing if base_dir is active
        if base_dir and raw_filepath:
            healed = find_file_on_disk(base_dir, raw_filepath)
            if healed:
                rel = os.path.relpath(healed, base_dir)
                if rel.replace("\\", "/").lower() != raw_filepath.replace("\\", "/").lower():
                    healed_note = f" *(auto-resolved from `{raw_filepath}`)*"
                display_path = rel

        lang = detect_language(display_path) if include_lang else ""

        # Search and Replace
        if search_str is not None and replace_str is not None:
            md_lines.append(f"## Target File: `{display_path}`{healed_note}\n")
            md_lines.append("search:")
            md_lines.append(format_code_block(search_str, lang))
            md_lines.append("\nreplace:")
            md_lines.append(format_code_block(replace_str, lang))
            md_lines.append("\n---\n")

            summary.append({
                "index": i,
                "type": "Search & Replace",
                "filepath": display_path,
                "search_lines": len(str(search_str).splitlines()),
                "replace_lines": len(str(replace_str).splitlines()),
            })

        # Whole File Write
        elif full_content is not None:
            md_lines.append(f"## Target File: `{display_path}`{healed_note}\n")
            md_lines.append("content:")
            md_lines.append(format_code_block(full_content, lang))
            md_lines.append("\n---\n")

            summary.append({
                "index": i,
                "type": "Full File Write",
                "filepath": display_path,
                "search_lines": 0,
                "replace_lines": len(str(full_content).splitlines()),
            })

        # Unknown / Raw JSON structure
        else:
            raw_pretty = json.dumps(patch, indent=2)
            title = f"Target File: `{display_path}`" if raw_filepath else f"Payload Block [#{i}]"
            md_lines.append(f"## {title}\n")
            md_lines.append("payload:")
            md_lines.append(format_code_block(raw_pretty, "json" if include_lang else ""))
            md_lines.append("\n---\n")

            summary.append({
                "index": i,
                "type": "Raw JSON Payload",
                "filepath": display_path if raw_filepath else "JSON Object",
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
        help="Path for the output file (default: matches input filename or 'gemini_patches.txt')."
    )
    parser.add_argument(
        "-b", "--base-dir", 
        default=None,
        help="Base workspace directory to enable Smart Path Healing."
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

    md_content, summary = generate_markdown(
        patches, 
        base_dir=args.base_dir, 
        include_lang=not args.no_lang
    )

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
        if item["type"] == "Terminal Command":
            preview = item["target"].splitlines()[0][:60] if item["target"] else "(empty)"
            print(f"  • [#{item['index']}] Terminal Command -> `{preview}` ({item['lines']} line(s))")
        elif item["type"] == "Search & Replace":
            print(f"  • [#{item['index']}] {item['type']} -> `{item['filepath']}`")
            print(f"    ↳ Search: {item['search_lines']} lines | Replace: {item['replace_lines']} lines")
        else:
            print(f"  • [#{item['index']}] {item['type']} -> `{item['filepath']}`")
            print(f"    ↳ Content: {item['replace_lines']} lines")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()