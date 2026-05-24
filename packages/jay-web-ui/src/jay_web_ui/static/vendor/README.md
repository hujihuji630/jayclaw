# Vendored JS

| Package | Version | License | Purpose |
|---|---|---|---|
| marked | 12 | MIT | Markdown → HTML |
| dompurify | 3 | Apache-2.0 / MPL-2.0 | XSS-safe HTML sanitisation |
| highlight.js | 11 | BSD-3-Clause | Syntax highlighting |
| fuzzysort | 3 | MIT | ⌘K palette fuzzy match (added in Task 14) |
| lucide | latest | ISC | Icon set (added in a later task) |

All loaded directly from `/static/vendor/*.js` — no build step, no network at runtime.
Re-download via the curl commands in the matching task in
docs/superpowers/plans/2026-05-24-web-ui-v1.1-warm-doc-redesign.md.
