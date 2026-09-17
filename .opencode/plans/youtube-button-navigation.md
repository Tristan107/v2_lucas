# Plan: Fix YouTube Button Navigation on Homepage

## Problem

The YouTube card on the homepage (`streamlit_app.py`) uses an `<a href="/#/1_YouTube">` anchor tag inside `st.html()`. In Streamlit, `st.html()` renders raw HTML that does **not** integrate with Streamlit's internal page router. As a result, clicking the card does not navigate to the YouTube search page (`pages/1_YouTube.py`).

## Solution

Keep the existing HTML card visual exactly as-is for display, and add a `st.page_link()` component for the actual navigation. The `st.page_link()` is Streamlit's native API for page-to-page navigation in multi-page apps.

### File to modify

- `/home/tristan/projects/v2_lucas/streamlit_app.py`

### Changes

1. **Keep the HTML card visual** — the `<div>` inside `st.html()` stays exactly the same (YouTube logo, title, hover effects), but remove the `<a href>` wrapper around it. The card becomes display-only.

2. **Add `st.page_link()` below each card** — place a `st.page_link("pages/1_YouTube.py", ...)` immediately after the card HTML. This handles the actual navigation when clicked.

3. **Apply CSS styling** — use `st.markdown()` with `unsafe_allow_html=True` to inject CSS that:
   - Makes the `st.page_link()` fill the same width as the card (220px)
   - Removes default link styling (underline, color) to match the card aesthetic
   - Adds the same hover effects (shadow + translateY)

### Resulting structure (pseudo-code)

```python
# CSS injection (once)
st.markdown("<style>...page-link card styles...</style>", unsafe_allow_html=True)

# YouTube card (display only, no <a> tag)
st.html("""
    <div style="width:220px;height:200px;...card styles...">
        <img src="...YouTube logo..." />
        <span>YouTube</span>
    </div>
""")

# Navigation link (Streamlit-native)
st.page_link("pages/1_YouTube.py", label="▶ YouTube", icon=None, use_container_width=True)
```

Same pattern for the Sondages card (currently uses `/?sondages=1` which triggers a dialog — keep that behavior unchanged).

## Testing

1. Run the Streamlit app: `uv run streamlit run streamlit_app.py`
2. On the homepage, verify the YouTube card is displayed with the logo and title
3. Click the YouTube card/link → should navigate to the YouTube search page (`/#/1_YouTube`)
4. On the YouTube search page, verify the search functionality works
5. Navigate back to homepage → verify the Sondages button still triggers the "Coming soon" dialog
6. Verify the hover effects on the card work (shadow + translateY)
