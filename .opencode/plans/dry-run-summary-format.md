# Fix dry-run summary display formatting

## Problem
The `_print_dry_run_summary` function in `src/lucas_v2/__init__.py` (line 165-176) prints everything on a single line per channel, making the output messy and hard to read.

## Current output
```
[INFO]   https://www.youtube.com/@lutteouvriere (Lutte ouvrière)     0              1
```

## Desired output
```
[INFO]   https://www.youtube.com/@lutteouvriere (Lutte ouvrière)
[INFO]     existing: 0          new: 1
```

## Change

**File:** `src/lucas_v2/__init__.py`, lines 170-172

Replace:
```python
    for url, title, new_c, exist_c in results:
        label: str = f"{url} ({title})" if title else url
        logger.info("  %-50s %5d          %5d", label, exist_c, new_c)
```

With:
```python
    for url, title, new_c, exist_c in results:
        label: str = f"{url} ({title})" if title else url
        logger.info("  %s", label)
        logger.info("    existing: %d          new: %d", exist_c, new_c)
```

This splits each channel into two lines:
1. Channel URL + name
2. Indented existing/new counts with labels
