# Gridstatus ISO Availability Report

## Summary
All 7 major US ISOs have accessible interconnection queue data via gridstatus `get_interconnection_queues()`.

| ISO | Class | Queue Data | Fields | Notes |
|-----|-------|------------|--------|-------|
| CAISO | `gridstatus.CAISO` | ✅ | Queue Date, Status, Capacity (MW), County, Project Name, Withdrawn Date, Actual Completion Date | California's primary grid operator |
| MISO | `gridstatus.MISO` | ✅ | Same unified schema | Midwest, ~45M people |
| PJM | `gridstatus.PJM` | ✅ | Same unified schema | 13 states, ~65M people |
| ERCOT | `gridstatus.ERCOT` | ✅ | Same unified schema | Texas-only, ~26M |
| NYISO | `gridstatus.NYISO` | ✅ | Same unified schema | New York |
| SPP | `gridstatus.SPP` | ✅ | Same unified schema | Great Plains, 14 states |
| ISONE | `gridstatus.ISONE` | ✅ | Same unified schema | New England 6 states |

## Key Fields

From librarian research: `get_interconnection_queues()` returns a unified DataFrame with ~19K+ projects across all ISOs containing:
- **Queue Date**: When the interconnection request was submitted
- **Status**: Queue status (Operating, In Queue, Withdrawn, Suspended, etc.)
- **Capacity (MW)**: Project capacity
- **County**: Location information
- **Project Name**: Name of the interconnection project
- **Withdrawn Date**: If project was withdrawn
- **Actual Completion Date**: When project became operational

## Validation Plan (for T6)
1. Pull queue data from all accessible ISOs
2. Merge into unified DataFrame (add ISO column)
3. Filter for data center relevant projects (MW > 1, specific companies)
4. Match events by: company name, county/city, MW range (±20%), date proximity
5. Label: Operating = kept, Withdrawn = failed, In Queue = pending, No match = unmatched

## Data Quality Notes
- LBNL "Queued Up 2025" reports: ~10,300 active projects, only ~13% reach operations
- Median queue-to-COD: <2 years (2000-2007) → >4 years (2018-2024)
- Post-2024 bottleneck shifting past queue — transformer lead times 50→160 weeks
- Some ISOs may have limited historical queue data (varies by ISO)
