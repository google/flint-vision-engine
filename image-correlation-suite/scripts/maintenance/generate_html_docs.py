#!/usr/bin/env python3
# Copyright 2026 Google LLC
# Licensed under Apache 2.0

"""
SYMPICS Documentation HTML Generator
==================================
Converts all Markdown documentation in docs/ and README.md into standalone,
100% offline air-gapped HTML files with modern, clean styling and navigation.
"""

import os
import re
import html

DOCS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "docs"))
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

CSS_STYLES = """
:root {
    --bg: #0f172a;
    --card-bg: #1e293b;
    --text-primary: #f8fafc;
    --text-secondary: #94a3b8;
    --border: #334155;
    --accent: #38bdf8;
    --accent-hover: #0284c7;
    --code-bg: #020617;
    --code-border: #1e293b;
    --table-header: #1e293b;
    --table-stripe: #0f172a;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: var(--bg);
    color: var(--text-primary);
    line-height: 1.6;
    padding: 0;
}

.layout {
    display: flex;
    min-height: 100vh;
}

.sidebar {
    width: 280px;
    background: #090d16;
    border-right: 1px solid var(--border);
    padding: 24px 16px;
    position: fixed;
    height: 100vh;
    overflow-y: auto;
}

.sidebar-title {
    font-size: 1.1rem;
    font-weight: 700;
    color: var(--accent);
    margin-bottom: 20px;
    padding-bottom: 12px;
    border-bottom: 1px solid var(--border);
    letter-spacing: 0.5px;
}

.nav-item {
    display: block;
    padding: 8px 12px;
    color: var(--text-secondary);
    text-decoration: none;
    border-radius: 6px;
    font-size: 0.9rem;
    margin-bottom: 4px;
    transition: all 0.15s;
}

.nav-item:hover {
    background: var(--card-bg);
    color: var(--text-primary);
}

.nav-item.active {
    background: rgba(56, 189, 248, 0.15);
    color: var(--accent);
    font-weight: 600;
}

.content-wrapper {
    margin-left: 280px;
    flex: 1;
    padding: 40px 60px;
    max-width: 1100px;
}

h1 { font-size: 2.2rem; font-weight: 800; color: #fff; margin-bottom: 12px; border-bottom: 2px solid var(--accent); padding-bottom: 10px; }
h2 { font-size: 1.5rem; font-weight: 700; color: var(--accent); margin-top: 32px; margin-bottom: 12px; }
h3 { font-size: 1.2rem; font-weight: 600; color: #e2e8f0; margin-top: 24px; margin-bottom: 8px; }
h4 { font-size: 1.05rem; font-weight: 600; color: #cbd5e1; margin-top: 18px; margin-bottom: 6px; }

p { margin-bottom: 16px; color: #cbd5e1; }
ul, ol { margin-bottom: 16px; padding-left: 24px; color: #cbd5e1; }
li { margin-bottom: 6px; }

a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }

hr { border: 0; border-top: 1px solid var(--border); margin: 30px 0; }

code {
    font-family: "JetBrains Mono", Consolas, Monaco, "Courier New", monospace;
    background: rgba(255, 255, 255, 0.08);
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 0.9em;
    color: #38bdf8;
}

pre {
    background: var(--code-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px;
    overflow-x: auto;
    margin-bottom: 20px;
}

pre code {
    background: transparent;
    padding: 0;
    color: #e2e8f0;
    font-size: 0.88rem;
    line-height: 1.5;
}

table {
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 24px;
    border-radius: 8px;
    overflow: hidden;
    border: 1px solid var(--border);
}

th, td {
    padding: 10px 14px;
    text-align: left;
    border-bottom: 1px solid var(--border);
    font-size: 0.92rem;
}

th {
    background: var(--table-header);
    color: #fff;
    font-weight: 600;
}

tr:nth-child(even) {
    background: var(--table-stripe);
}

blockquote {
    border-left: 4px solid var(--accent);
    padding: 10px 16px;
    background: rgba(56, 189, 248, 0.05);
    margin-bottom: 16px;
    border-radius: 0 6px 6px 0;
    color: #cbd5e1;
}

.badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 0.75rem;
    font-weight: 600;
    background: rgba(56, 189, 248, 0.2);
    color: var(--accent);
}

@media (max-width: 900px) {
    .sidebar { display: none; }
    .content-wrapper { margin-left: 0; padding: 20px; }
}
"""

def parse_markdown_to_html(md_text):
    """Converts standard markdown text to clean HTML."""
    lines = md_text.splitlines()
    html_lines = []
    
    in_code_block = False
    code_lang = ""
    code_buffer = []
    
    in_table = False
    table_headers = []
    table_rows = []

    in_list = False
    list_type = "ul"

    def flush_list():
        nonlocal in_list, html_lines
        if in_list:
            html_lines.append(f"</{list_type}>")
            in_list = False

    def flush_table():
        nonlocal in_table, table_headers, table_rows, html_lines
        if in_table:
            html_lines.append("<table>")
            if table_headers:
                html_lines.append("<thead><tr>")
                for h in table_headers:
                    html_lines.append(f"<th>{format_inline(h)}</th>")
                html_lines.append("</tr></thead>")
            if table_rows:
                html_lines.append("<tbody>")
                for row in table_rows:
                    html_lines.append("<tr>")
                    for cell in row:
                        html_lines.append(f"<td>{format_inline(cell)}</td>")
                    html_lines.append("</tr>")
                html_lines.append("</tbody>")
            html_lines.append("</table>")
            in_table = False
            table_headers = []
            table_rows = []

    def format_inline(text):
        # Escape HTML chars
        # Handle bold **text**
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        # Handle italics *text*
        text = re.sub(r'(?<!\*)\*([^*]+?)\*(?!\*)', r'<em>\1</em>', text)
        # Handle inline code `code`
        text = re.sub(r'`([^`]+?)`', r'<code>\1</code>', text)
        # Handle links [text](url) -> replace .md links with .html links
        def link_sub(match):
            lbl, url = match.group(1), match.group(2)
            if url.endswith('.md'):
                url = url[:-3] + '.html'
            return f'<a href="{url}">{lbl}</a>'
        text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', link_sub, text)
        return text

    i = 0
    while i < len(lines):
        line = lines[i]

        # 1. Code block handling
        if line.strip().startswith("```"):
            if in_code_block:
                code_content = html.escape("\n".join(code_buffer))
                html_lines.append(f"<pre><code class=\"language-{code_lang}\">{code_content}</code></pre>")
                in_code_block = False
                code_buffer = []
            else:
                flush_list()
                flush_table()
                in_code_block = True
                code_lang = line.strip()[3:].strip()
            i += 1
            continue

        if in_code_block:
            code_buffer.append(line)
            i += 1
            continue

        # 2. Table handling
        if "|" in line and (line.strip().startswith("|") or line.strip().endswith("|")):
            flush_list()
            cells = [c.strip() for c in line.split("|")]
            if cells and cells[0] == "": cells = cells[1:]
            if cells and cells[-1] == "": cells = cells[:-1]

            # Check if this is a separator line (e.g. |---|:---|)
            if all(re.match(r'^:?-+:?$', c) for c in cells):
                i += 1
                continue

            if not in_table:
                in_table = True
                table_headers = cells
            else:
                table_rows.append(cells)
            i += 1
            continue
        elif in_table:
            flush_table()

        stripped = line.strip()

        # 3. Blank line
        if not stripped:
            flush_list()
            i += 1
            continue

        # 4. Horizontal Rule
        if re.match(r'^(-{3,}|\*{3,}|_{3,})$', stripped):
            flush_list()
            html_lines.append("<hr>")
            i += 1
            continue

        # 5. Headings
        m_head = re.match(r'^(#{1,6})\s+(.*)$', stripped)
        if m_head:
            flush_list()
            level = len(m_head.group(1))
            title = format_inline(m_head.group(2))
            html_lines.append(f"<h{level}>{title}</h{level}>")
            i += 1
            continue

        # 6. Blockquotes
        if stripped.startswith(">"):
            flush_list()
            quote_text = format_inline(stripped[1:].strip())
            html_lines.append(f"<blockquote>{quote_text}</blockquote>")
            i += 1
            continue

        # 7. Unordered Lists
        m_ul = re.match(r'^[-*+]\s+(.*)$', stripped)
        if m_ul:
            if not in_list or list_type != "ul":
                flush_list()
                in_list = True
                list_type = "ul"
                html_lines.append("<ul>")
            html_lines.append(f"<li>{format_inline(m_ul.group(1))}</li>")
            i += 1
            continue

        # 8. Ordered Lists
        m_ol = re.match(r'^\d+\.\s+(.*)$', stripped)
        if m_ol:
            if not in_list or list_type != "ol":
                flush_list()
                in_list = True
                list_type = "ol"
                html_lines.append("<ol>")
            html_lines.append(f"<li>{format_inline(m_ol.group(1))}</li>")
            i += 1
            continue

        # 9. Regular Paragraph
        flush_list()
        html_lines.append(f"<p>{format_inline(stripped)}</p>")
        i += 1

    flush_list()
    flush_table()
    return "\n".join(html_lines)


def generate_all_html():
    doc_files = [
        ("index.html", "README.md", "Overview & Quickstart"),
        ("01_executive_brief.html", "01_executive_brief_data_migration_strategy.md", "1. Executive Brief"),
        ("02_migration_architecture.html", "02_four_phase_migration_architecture.md", "2. Four-Phase Migration"),
        ("03_cas_whitepaper.html", "03_content_addressable_storage_whitepaper.md", "3. CAS Whitepaper"),
        ("04_quickstart_guide.html", "04_analyst_and_operator_quickstart_guide.md", "4. Operations Manual"),
        ("05_windows_setup_guide.html", "05_windows_workstation_setup_guide.md", "5. Windows Setup Guide"),
        ("06_git_training.html", "06_investigator_git_training_guide.md", "6. Git SOP & Training"),
    ]

    out_dir = os.path.join(DOCS_DIR, "html")
    os.makedirs(out_dir, exist_ok=True)

    for out_name, src_name, title in doc_files:
        if src_name == "README.md":
            src_path = os.path.join(PROJECT_ROOT, src_name)
        else:
            src_path = os.path.join(DOCS_DIR, src_name)

        if not os.path.exists(src_path):
            print(f"[!] Warning: {src_path} not found.")
            continue

        with open(src_path, "r", encoding="utf-8") as f:
            md_content = f.read()

        body_html = parse_markdown_to_html(md_content)

        # Build Sidebar Navigation
        nav_html = []
        for nav_out, _, nav_label in doc_files:
            active_cls = ' active' if nav_out == out_name else ''
            nav_html.append(f'<a class="nav-item{active_cls}" href="{nav_out}">{nav_label}</a>')
        sidebar_str = "\n".join(nav_html)

        full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SYMPICS Documentation - {title}</title>
    <style>
{CSS_STYLES}
    </style>
</head>
<body>
    <div class="layout">
        <nav class="sidebar">
            <div class="sidebar-title">SYMPICS DOCUMENTATION</div>
            {sidebar_str}
        </nav>
        <main class="content-wrapper">
            {body_html}
        </main>
    </div>
</body>
</html>"""

        out_path = os.path.join(out_dir, out_name)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(full_html)
        print(f"[+] Generated: docs/html/{out_name}")

    # Also generate Windows launchers/open_documentation.bat
    bat_path = os.path.join(PROJECT_ROOT, "launchers", "open_documentation.bat")
    os.makedirs(os.path.dirname(bat_path), exist_ok=True)
    with open(bat_path, "w", encoding="utf-8") as f:
        f.write('@echo off\nstart "" "%~dp0..\\docs\\html\\index.html"\n')
    print(f"[+] Generated: launchers/open_documentation.bat")

if __name__ == "__main__":
    generate_all_html()
