# Video Search Result Thumbnails

## Goal
Add a clickable YouTube thumbnail image to the left of each video search result.

## Context
- Video search results are rendered in `_render_video_row()` in `src/lucas_v2/ui/app.py` (line 130)
- Currently each row is: a tertiary button (title, full width) + meta line
- `VideoHit` dataclass has `youtube_str_id` — used to build thumbnail URL
- Thumbnail URL format: `https://i.ytimg.com/vi_webp/{youtube_str_id}/default.webp`

## Approach

### 1. Modify `_render_video_row()` (app.py, line 130)

Replace the current single-column layout with a two-column layout:

```python
def _render_video_row(v: VideoHit) -> None:
    col_thumb, col_content = st.columns([1, 4])
    with col_thumb:
        st.image(
            f"https://i.ytimg.com/vi_webp/{v.youtube_str_id}/default.webp",
            use_container_width=True,
        )
    with col_content:
        title = v.title or v.youtube_str_id
        if st.button(
            title,
            key=f"open_{v.youtube_str_id}",
            type="tertiary",
            use_container_width=True,
        ):
            st.session_state["selected_video_id"] = v.youtube_str_id
            st.session_state["chunk_page"] = 0
            st.rerun()

        meta = _video_meta_line(v)
        meta_line = f"{meta} ({v.mentions} mentions)" if meta else f"({v.mentions} mentions)"
        st.html(f'<div class="lucas-meta">{html.escape(meta_line)}</div>')
```

### 2. Add CSS for thumbnail alignment (app.py, `_inject_compact_style()`)

Add a style rule to vertically center the thumbnail with the title text:

```css
/* Thumbnail alignment in video list */
div[data-testid="stImage"] {
    margin-top: 0.15rem !important;
}
```

### 3. Making the thumbnail clickable

Since `st.image()` is not clickable in Streamlit, and `st.button()` doesn't support image labels, the thumbnail will be a **visual element** while the **title button remains the click target**. Both are in the same row, so the UX is natural — the user sees the thumbnail and clicks the title to open the video detail view.

If truly clickable thumbnails are needed later, a custom HTML/JS approach could be explored, but it would be fragile with Streamlit's rerun model.

## Files to modify

| File | Change |
|---|---|
| `src/lucas_v2/ui/app.py` | Rewrite `_render_video_row()` to use `st.columns([1, 4])` with thumbnail + content; add thumbnail CSS to `_inject_compact_style()` |

## Functional test

1. Run `uv run streamlit run streamlit_app.py`
2. Search for a term that returns video results
3. Verify each result row shows a thumbnail image on the left, with the title and meta to its right
4. Verify clicking the title still navigates to the video detail view
5. Verify thumbnails load correctly (no broken images) — the `default.webp` endpoint returns a valid image for any `youtube_str_id` in the database
