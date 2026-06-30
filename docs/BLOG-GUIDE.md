# Writing and publishing a blog post

This is the step-by-step for adding a post to the Vahini blog. Every post is a
standalone HTML file in `site/`, and all posts share one data file so the index,
filters, "read next" rail, search and SEO stay in sync automatically.

## How the blog fits together

- **`site/blog-data.js`** is the single source of truth. It holds the list of
  posts (`VahiniPosts`), the per-post SEO keywords (`VahiniPostKW`), and the
  cover-art generator (`VahiniPostArt`, with a per-post motif map `THUMB`).
- **`site/blog.html`** is the index: it reads `VahiniPosts`, renders the featured
  card plus the filterable grid, and powers the category chips.
- **`site/blog-<slug>.html`** is one article per file.
- **`site/blog.css`** styles posts (AI summary, table of contents, share bar,
  highlights, cover art).
- **`site/site.js`** auto-injects the nav, footer, favicons, analytics, the
  share bar, and the per-post SEO/Open Graph tags. You do not hand-write any of
  those into a post.

## Step 1: add the post to the data file

Open `site/blog-data.js` and add an entry at the **top** of the `VahiniPosts`
array (newest first). The first entry becomes the featured card on the index.

```js
{
  slug: "my-new-post",                       // unique, kebab-case
  url: "blog-my-new-post.html",              // must match the file you create
  cat: "signals",                            // research | signals | technology | health | explainer
  title: "My new post title",
  date: "Jul 2026", read: "6 min read",
  author: "Vishnu Kosuri",                   // or "Malli Kosuri"
  excerpt: "One or two sentences that sell the post on the index card."
},
```

Then add SEO keywords for it in the `VahiniPostKW` map (same file):

```js
"my-new-post": "primary keyword, secondary keyword, long-tail phrase, related term",
```

Optionally add a unique cover motif in the `THUMB` map inside `VahiniPostArt`
(keyed by the same slug). If you skip this, the post falls back to its
category's default art, which is fine.

## Step 2: create the post file

Copy an existing post as a starting point. The closest match to your topic is
easiest, e.g. `site/blog-reading-pressure.html` for a "signals" post.

```
cp "site/blog-reading-pressure.html" "site/blog-my-new-post.html"
```

Then edit the new file and update, in order:

1. **`<title>`** and **`<meta name="description">`** in the `<head>`.
2. The **category tag**: `<span class="btag btag--signals">Signals</span>`.
3. The **`<h1>`** headline.
4. The **author byline** in `.post-meta` (`VK` teal avatar for Vishnu, add the
   `malli` class for Malli's `MK` crimson avatar).
5. The **AI summary** card (`.post-ai`), two or three plain sentences.
6. The **table of contents** (`.post-toc`), one list item per `<h2>` plus a
   final link to `#takeaways`. Make the `href` anchors match the `id`s you give
   each `<h2>`.
7. The **body**: `<h2 id="s1">`, `<h2 id="s2">`, paragraphs, an optional
   `<figure class="post-fig">` diagram, and the `.post-key` highlights box
   (give it `id="takeaways"`).
8. At the very bottom, the small `<script>` that renders "read next": set
   `var SLUG="my-new-post";` to match.

You do **not** add the share bar, nav, footer, favicons or analytics. `site.js`
injects those on load.

## Step 3: house style

- **No em dashes.** Use commas, or a middot ( · ) for separators in titles.
- Write like a person, not a brochure. Short sentences. One idea per paragraph.
- Link the original research with a `.source-box` when a post summarises a paper,
  and never reproduce the source text, link to it.
- Keep diagrams as inline SVG (no external images) so they stay crisp and offline.

## Step 4: preview

Open `site/blog.html` and your new `site/blog-my-new-post.html` in a browser
(or via the Docker image below). Check: the card shows on the index, the right
category filter includes it, the table of contents anchors jump correctly, and
the share + read-next rails render.

## Step 5: publish

The site is static, so "publishing" is just shipping the files.

- **Local / Docker:**
  ```
  docker build -t vahini-site .
  docker run --rm -p 8080:80 vahini-site
  # http://localhost:8080/site/blog.html
  ```
- **Any static host** (Netlify, Vercel, S3 + CloudFront, GitHub Pages, nginx):
  deploy the repository as-is. The marketing site is under `/site`; the Analyser
  app and printable HTML sit at the root. `deploy/nginx.conf` shows the routing
  we use (bare domain redirects to `/site/index.html`).
- Commit and push. If you use a CI deploy, the new files go live on merge.

That is the whole loop: add to `blog-data.js`, create one HTML file from a
template, preview, deploy.
