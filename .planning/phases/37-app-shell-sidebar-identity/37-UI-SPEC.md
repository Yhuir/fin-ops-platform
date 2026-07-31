# Phase 37 UI Contract

| Surface | Contract |
| --- | --- |
| Sidebar width | expanded `232px`; collapsed `72px` |
| Brand zone | `64px`; static local mark + static status dot |
| Desktop row | `36px`; `14px/500`; active `600`; icon `16px` |
| Mobile row | `44px` |
| Group title | `12px/700` |
| Item rhythm | `4px` gap; group separation remains subtle |
| Account footer | fixed `72px`; initials, `displayName`, `username`, chevron |
| Account popover | `displayName`, OA account, optional department; no mutation action |
| Motion | shell width changes once; text/icon use transform/opacity transition; reduced-motion respected |
| Focus | visible focus ring on status, toggle, links and account trigger |

The missing Figma source image is not reconstructed as an exact asset. The brand mark is an isolated local SVG so the exact exported asset can replace it later without changing component or I/O boundaries.
