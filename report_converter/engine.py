from __future__ import annotations

from pathlib import Path

from pptx import Presentation

from .common import log
from .drafting import build_drafts_and_metrics
from .layout import (
    add_content_textbox,
    add_formal_layout_content_v2,
    extract_template_slides,
    fill_table_metrics,
    insert_slide_after,
    remove_auto_shapes,
    set_slide_title_text,
    split_into_pages,
)
from .models import SlideDraft
from .parsing import detect_month_label, extract_doc_payload


def convert(
    docx_path: Path,
    template_pptx: Path,
    output_pptx: Path,
    model: str,
    ollama_url: str,
    timeout_sec: int,
    retries: int,
    use_llm: bool,
    layout_mode: str = "classic",
    theme: str = "formal_blue",
    diversity: str = "medium",
    seed: int = 0,
) -> None:
    doc_payload = extract_doc_payload(docx_path)
    month_label = detect_month_label(doc_payload["title"], docx_path.name)
    log(f"识别月份: {month_label}")

    prs = Presentation(str(template_pptx))
    template_slides = extract_template_slides(prs)

    drafts, metrics = build_drafts_and_metrics(
        use_llm=use_llm,
        ollama_url=ollama_url,
        model=model,
        timeout_sec=timeout_sec,
        retries=retries,
        report_title=doc_payload["title"],
        month_label=month_label,
        template_slides=template_slides,
        doc_payload=doc_payload,
    )

    log("开始写入 PPT（保留模板标题与版式）")
    draft_map = {draft.slide_index: draft for draft in drafts}
    offset = 0

    for slide_meta in template_slides:
        slide_pos = slide_meta.slide_index - 1 + offset
        slide = prs.slides[slide_pos]
        remove_auto_shapes(slide)
        all_bullets = draft_map[slide_meta.slide_index].bullets
        pages = split_into_pages(all_bullets, slide_meta.title, has_table=slide_meta.has_table)
        first_chunk = pages[0] if pages else []
        first_draft = SlideDraft(slide_meta.slide_index, first_chunk)

        if layout_mode == "formal":
            add_formal_layout_content_v2(
                slide=slide,
                draft=first_draft,
                has_table=slide_meta.has_table,
                title=slide_meta.title,
                theme=theme,
                diversity=diversity,
                seed=seed,
                slide_width=int(prs.slide_width),
                slide_height=int(prs.slide_height),
            )
        else:
            add_content_textbox(slide, first_draft, slide_meta.has_table, int(prs.slide_width), int(prs.slide_height))

        if slide_meta.has_table:
            fill_table_metrics(slide, metrics)
        log(f"已写入第 {slide_meta.slide_index} 页: {slide_meta.title}")

        for n, chunk in enumerate(pages[1:], start=1):
            overflow = insert_slide_after(prs, slide_pos + n - 1, slide.slide_layout)
            set_slide_title_text(overflow, slide_meta.title)
            remove_auto_shapes(overflow)
            overflow_draft = SlideDraft(slide_meta.slide_index, chunk)
            if layout_mode == "formal":
                add_formal_layout_content_v2(
                    slide=overflow,
                    draft=overflow_draft,
                    has_table=False,
                    title=slide_meta.title,
                    theme=theme,
                    diversity=diversity,
                    seed=seed + n,
                    slide_width=int(prs.slide_width),
                    slide_height=int(prs.slide_height),
                )
            else:
                add_content_textbox(overflow, overflow_draft, False, int(prs.slide_width), int(prs.slide_height))
            log(f"已新增续页: {slide_meta.title}（续{n}）")

        offset += max(len(pages) - 1, 0)

    output_pptx.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(output_pptx))
    log(f"导出完成: {output_pptx}")
