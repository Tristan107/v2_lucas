# Plan: Create new Python project with uv

## Goal
Instantiate a new Python project named `lucas_v2` using `uv init`.

## Steps

1. **Run uv init** in the current directory
   ```bash
   cd /home/tristan/projects/lucas_v2
   uv init
   ```

2. **Add dependencies** using uv add
   ```bash
   uv add pandas requests click
   ```

3. **Verify the setup**
   ```bash
   uv sync
   ```

## Expected output
- `pyproject.toml` with project metadata and dependencies
- `uv.lock` lock file
- `src/lucas_v2/` directory structure (if using uv's default layout)
- `.python-version` file

## Notes
- The project will be initialized in `/home/tristan/projects/lucas_v2`
- uv will use Python 3.12 by default (or whatever is configured)
