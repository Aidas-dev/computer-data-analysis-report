# Paper Trim Learnings

## Changes Made
- Switched from `[preprint,review,12pt]` to `[5p,12pt]` - double-column format saves ~60% pages
- Removed `review` option (line numbers, 1.5 spacing)
- Removed 3 figures: fig5 (mw_analysis), fig7 (confidence_sources), fig10 (temporal_patterns)
- Kept 4 figures: fig1, fig2, fig6, fig8
- Removed 2 tables: geo_temporal, summary_stats
- Kept 2 tables: label_dist, by_outcome
- Condensed Lit Review from 4 to 2 subsections
- Reduced citations from ~28 to 18
- Added float placement optimization (topfraction, bottomfraction, textfraction)

## Key Decisions
- `\floatplacement` requires `float` package - avoided per "no new packages" rule
- Used `{\sloppy ... \par}` for Data Availability section to handle long URLs
- Double-column format inherently causes more overfull boxes than single-column
- 6 remaining overfull hboxes (max 9.5pt) - acceptable for double-column format

## Issues
- `\floatplacement{figure}{t}` not available without `float` package
- URL breaking in double-column still has edge cases even with `\UrlBreaks`
- CRediT statement needed manual line breaks with `\\`

## Paper Expansion (May 2026)
- Expanded paper from 7 to 10 pages via `report/main.tex` edits
- **Strategy used**: restore 2 figures (fig5, fig7) + 1 geo-temporal table + expand 3 sections + add subsection
- **Lit Review**: Added ML-driven construction risk paragraph (Abuassi, AlMnaseer, Zachares, Hovhannisyan) + new "Data Center Lifecycle and Location Analysis" subsection (Whitehead, Masanet, d'Orgeval, Kim)
- **Methodology**: Expanded event study section with estimation window rationale, Brown-Warner framework, three CAR windows, subsample analysis, non-parametric tests (Kothari, Ullah)
- **Results**: Added fig5 (MW analysis boxplot), fig7 (confidence sources by domain), geo-temporal table (8 states x 4 years)
- **Discussion**: Added "Comparison with Literature" subsection covering queue vs press data comparison, tone differential vs construction ML, market efficiency perspective
- **Citations**: 18 -> 23 (added 5, all from existing bib entries)
- **Bib**: Added 3 new references (Moodys2025Rating, Sheppard2021National, Masanet2020Global)
- **Final metrics**: 10 pages, 6 figures, 3 tables, 23 citations, 0 errors, 0 undefined refs
- **Preserved**: all existing content, no packages added, document class unchanged (elsarticle 5p)
