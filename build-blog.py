#!/usr/bin/env python3
"""
Men of Oregon — Blog Builder

Usage:
    python3 build-blog.py                   # Rebuild blog index from all posts
    python3 build-blog.py new draft.md      # Create a new post from a markdown draft
    python3 build-blog.py list              # List all published posts

Drafts go in:     blog/drafts/
Published posts:  blog/posts/

Markdown front matter format:
---
title: Your Post Title
date: 2026-03-15
author: Kevin Jenson
excerpt: Brief summary for the blog index.
---
"""

import os
import re
import sys
from datetime import datetime
from pathlib import Path

SITE_DIR = Path(__file__).parent
POSTS_DIR = SITE_DIR / "blog" / "posts"
DRAFTS_DIR = SITE_DIR / "blog" / "drafts"
BLOG_INDEX = SITE_DIR / "blog.html"

# ─── Markdown Parsing (simple, no dependencies) ──────────────────────

def parse_front_matter(text):
    """Extract YAML-like front matter from markdown."""
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n', text, re.DOTALL)
    if not match:
        return {}, text
    meta = {}
    for line in match.group(1).strip().split('\n'):
        if ':' in line:
            key, val = line.split(':', 1)
            meta[key.strip()] = val.strip()
    body = text[match.end():]
    return meta, body


def markdown_to_html(md_text):
    """Convert simple markdown to HTML (handles paragraphs, headers, bold, italic, blockquotes, lists)."""
    lines = md_text.strip().split('\n')
    html_parts = []
    in_list = False
    in_blockquote = False
    paragraph_lines = []

    def flush_paragraph():
        if paragraph_lines:
            text = ' '.join(paragraph_lines)
            text = inline_formatting(text)
            html_parts.append(f'    <p>{text}</p>')
            paragraph_lines.clear()

    def flush_list():
        nonlocal in_list
        if in_list:
            html_parts.append('    </ul>')
            in_list = False

    def flush_blockquote():
        nonlocal in_blockquote
        if in_blockquote:
            html_parts.append('    </blockquote>')
            in_blockquote = False

    def inline_formatting(text):
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
        text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
        return text

    for line in lines:
        stripped = line.strip()

        # Empty line = flush
        if not stripped:
            flush_paragraph()
            flush_list()
            flush_blockquote()
            continue

        # Headers
        header_match = re.match(r'^(#{1,3})\s+(.+)$', stripped)
        if header_match:
            flush_paragraph()
            flush_list()
            flush_blockquote()
            level = len(header_match.group(1)) + 1  # h2, h3, h4
            text = inline_formatting(header_match.group(2))
            html_parts.append(f'    <h{level}>{text}</h{level}>')
            continue

        # Blockquote
        if stripped.startswith('>'):
            flush_paragraph()
            flush_list()
            quote_text = inline_formatting(stripped.lstrip('> ').strip())
            if not in_blockquote:
                html_parts.append('    <blockquote>')
                in_blockquote = True
            html_parts.append(f'      <p>{quote_text}</p>')
            continue
        else:
            flush_blockquote()

        # Unordered list
        if re.match(r'^[-*]\s+', stripped):
            flush_paragraph()
            if not in_list:
                html_parts.append('    <ul>')
                in_list = True
            item_text = inline_formatting(re.sub(r'^[-*]\s+', '', stripped))
            html_parts.append(f'      <li>{item_text}</li>')
            continue
        else:
            flush_list()

        # Regular paragraph text
        paragraph_lines.append(stripped)

    flush_paragraph()
    flush_list()
    flush_blockquote()

    return '\n'.join(html_parts)


# ─── Post Template ────────────────────────────────────────────────────

POST_TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} — Men of Oregon</title>
  <meta name="description" content="{excerpt}">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Libre+Baskerville:ital,wght@0,400;0,700;1,400&family=Oswald:wght@400;600;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="../../css/styles.css">
  <link rel="icon" href="../../images/logo.png" type="image/png">
</head>
<body>

  <!-- Navigation -->
  <nav class="site-nav">
    <div class="nav-container">
      <a href="../../index.html" class="nav-brand">
        <img src="../../images/logo.png" alt="Men of Oregon logo">
        <span>Men of Oregon</span>
      </a>
      <button class="nav-toggle" aria-label="Toggle navigation" onclick="document.querySelector('.nav-links').classList.toggle('open')">
        <span></span><span></span><span></span>
      </button>
      <ul class="nav-links">
        <li><a href="../../index.html">Home</a></li>
        <li><a href="../../about.html">About</a></li>
        <li><a href="../../blog.html" class="active">Blog</a></li>
      </ul>
    </div>
  </nav>

  <!-- Post Header -->
  <section class="page-header">
    <h1>{title}</h1>
  </section>

  <!-- Post Content -->
  <article class="post-content">
    <div class="post-meta">{date_formatted} &middot; {author}</div>

{content_html}

    <a href="../../blog.html" class="back-to-blog">&larr; Back to Blog</a>
  </article>

  <!-- Footer -->
  <footer class="site-footer">
    <div class="footer-container">
      <div class="footer-brand">Men of Oregon</div>
      <p>&copy; 2026 menoforegon.org &middot; All rights reserved.</p>
    </div>
  </footer>

</body>
</html>'''


# ─── Blog Index Rebuilder ─────────────────────────────────────────────

def get_post_meta(post_path):
    """Extract front-matter-like info from an existing post HTML file."""
    content = post_path.read_text()

    title_match = re.search(r'<h1>(.+?)</h1>', content)
    title = title_match.group(1) if title_match else post_path.stem

    date_match = re.search(r'class="post-meta">(.+?)&middot;', content)
    date_str = date_match.group(1).strip() if date_match else ""

    desc_match = re.search(r'name="description" content="(.+?)"', content)
    excerpt = desc_match.group(1) if desc_match else ""

    # Parse date for sorting
    try:
        date_obj = datetime.strptime(date_str.strip(), "%B %d, %Y")
    except:
        date_obj = datetime.min

    return {
        'title': title,
        'date_str': date_str,
        'date_obj': date_obj,
        'excerpt': excerpt,
        'filename': post_path.name,
    }


def rebuild_blog_index():
    """Scan all posts and regenerate blog.html index."""
    posts = []
    for f in POSTS_DIR.glob('*.html'):
        posts.append(get_post_meta(f))

    posts.sort(key=lambda p: p['date_obj'], reverse=True)

    # Build post cards HTML
    if posts:
        cards = []
        for p in posts:
            cards.append(f'''    <article class="blog-post-card">
      <div class="post-date">{p['date_str']}</div>
      <h3><a href="blog/posts/{p['filename']}">{p['title']}</a></h3>
      <p class="post-excerpt">{p['excerpt']}</p>
      <a href="blog/posts/{p['filename']}" class="read-more">Read More &rarr;</a>
    </article>''')
        posts_html = '\n\n'.join(cards)
    else:
        posts_html = '''    <div class="empty-state">
      <p>First posts coming soon. The trail is being blazed.</p>
    </div>'''

    # Read and update blog.html
    blog_html = BLOG_INDEX.read_text()
    updated = re.sub(
        r'(<div class="blog-grid" id="blog-posts">).*?(</div>\s*\n\s*<!-- Footer)',
        rf'\1\n{posts_html}\n  \2',
        blog_html,
        flags=re.DOTALL
    )
    BLOG_INDEX.write_text(updated)
    print(f"Blog index rebuilt with {len(posts)} post(s).")


# ─── New Post from Draft ──────────────────────────────────────────────

def create_post(draft_filename):
    """Convert a markdown draft into a published HTML post."""
    draft_path = DRAFTS_DIR / draft_filename
    if not draft_path.exists():
        print(f"Error: Draft not found: {draft_path}")
        sys.exit(1)

    raw = draft_path.read_text()
    meta, body = parse_front_matter(raw)

    title = meta.get('title', draft_path.stem)
    date = meta.get('date', datetime.now().strftime('%Y-%m-%d'))
    author = meta.get('author', 'Kevin Jenson')
    excerpt = meta.get('excerpt', '')

    # Format date
    try:
        date_obj = datetime.strptime(date, '%Y-%m-%d')
        date_formatted = date_obj.strftime('%B %d, %Y')
    except:
        date_formatted = date

    # Convert markdown body to HTML
    content_html = markdown_to_html(body)

    # Generate slug
    slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')

    # Write post HTML
    post_html = POST_TEMPLATE.format(
        title=title,
        excerpt=excerpt,
        date_formatted=date_formatted,
        author=author,
        content_html=content_html,
    )

    out_path = POSTS_DIR / f"{slug}.html"
    out_path.write_text(post_html)
    print(f"Published: {out_path.name}")

    # Rebuild index
    rebuild_blog_index()
    print("Done!")


def list_posts():
    """List all published posts."""
    posts = []
    for f in POSTS_DIR.glob('*.html'):
        meta = get_post_meta(f)
        posts.append(meta)

    posts.sort(key=lambda p: p['date_obj'], reverse=True)

    if not posts:
        print("No posts published yet.")
        return

    print(f"{'Date':<20} {'Title'}")
    print("-" * 60)
    for p in posts:
        print(f"{p['date_str']:<20} {p['title']}")


# ─── CLI ──────────────────────────────────────────────────────────────

if __name__ == '__main__':
    if len(sys.argv) < 2:
        rebuild_blog_index()
    elif sys.argv[1] == 'new' and len(sys.argv) >= 3:
        create_post(sys.argv[2])
    elif sys.argv[1] == 'list':
        list_posts()
    else:
        print(__doc__)
