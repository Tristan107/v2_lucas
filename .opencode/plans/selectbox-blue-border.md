# Plan: Blue border on selectbox focus

## Goal
Add a `#457B9D` blue border to the candidate filter `st.selectbox` when focused, matching the search field's focus style.

## File to modify
`src/lucas_v2/ui/app.py` — `_inject_compact_style()` function (lines 53-112)

## Change
Add CSS rules after the existing `stTextInput` reset block (line 67), before the vertical layout spacing rules (line 69).

### CSS to inject (inside the existing `<style>` block)

```css
/* Reset selectbox border/shadow */
div[data-testid="stSelectbox"] div[data-baseweb="select"] {
    border-color: transparent !important;
    box-shadow: none !important;
}
div[data-testid="stSelectbox"]:focus-within div[data-baseweb="select"] {
    border-color: #457B9D !important;
    box-shadow: 0 0 0 1px #457B9D !important;
}
```

### Where exactly
Insert after line 67 (`}` closing the stTextInput focus rule) and before line 69 (`/* Adjust vertical layout spacing */`).

## Verification
1. `uv run streamlit run streamlit_app.py`
2. Navigate to YouTube page
3. Click the "Filtrer par candidat" selectbox → blue border should appear
4. Click away / select an option → blue border should disappear
5. Search field still works as before (blue border on focus)
6. `uv run pyright` — no new type errors (CSS is a string, no type impact)
