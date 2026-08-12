# disasters-tracking

Schedule and milestone tracking for the **NASA Disasters Learning Portal** launch
(target: **September 30, 2026**).

These issues are migrated from the launch Smartsheet Gantt. Code lives elsewhere
([disasters-portal](https://github.com/Disasters-Learning-Portal/disasters-portal),
[veda-disasters](https://github.com/Disasters-Learning-Portal/veda-disasters),
[disasters-product-algorithms](https://github.com/Disasters-Learning-Portal/disasters-product-algorithms));
this repo holds only the schedule.

## How it's organized

Every issue title starts with its Smartsheet WBS ID, so the outline survives the move:

| Title | Meaning |
|---|---|
| `[6.2] PORTAL content review` | top-level group (header row) |
| `[6.2c] Complete development tasks…` | child of 6.2 |
| `[6.1c1a] Review June STM feedback docs` | 4th-level row (6.1 › c › 1 › a) |

Hierarchy is real GitHub **sub-issues**, so each header row shows a live progress bar.
The whole tree hangs off
[disasters-portal#332](https://github.com/Disasters-Learning-Portal/disasters-portal/issues/332).

## How to filter

Schedule attributes live where GitHub can actually filter on them.

**Labels** (work in issue search *and* in project-board filters):

| Label | Meaning |
|---|---|
| `owner: Disasters` | Disasters owns the row |
| `owner: VEDA` | VEDA owns the row |
| `EPIC` | top-level 6.x header row |
| `smartsheet` | migrated from the launch Smartsheet |

Owner labels are **additive** — a jointly-owned row carries *both*:

- `label:"owner: VEDA"` → everything VEDA touches, including joint rows
- `label:"owner: Disasters" label:"owner: VEDA"` → only the jointly-owned rows

**Project board fields** on
[Disasters Learning Portal](https://github.com/orgs/Disasters-Learning-Portal/projects/5) —
`Status`, `Priority`, `Start Date`, `End Date`, `Program Increment`. The board's roadmap views
render the original Gantt from the date fields.

`Sprint` is intentionally left empty for migrated rows — it's set during PI planning.

## Notes on the source data

- The Smartsheet **Ticket#** column is stale: those numbers resolve to unrelated closed items in
  `veda-disasters`. They're recorded as plain text in issue bodies and deliberately **not** linked.
- **Assigned To** is copied verbatim into the body. GitHub assignees are set only where a person
  maps to a known handle; group placeholders (*VEDA Dev*, *Dev Team*, *GRAs*) stay text-only.
