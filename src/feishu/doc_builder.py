from datetime import datetime, timezone

from lark_oapi.api.docx.v1 import Block

from src.models import NewsItem

CATEGORY_LABELS = {
    "ai_news": "AI News",
    "github_trending": "GitHub Trending Repos",
    "world_news": "World News",
}


def _text_run(content: str, bold: bool = False, link: str = "") -> dict:
    run: dict = {"text_run": {"content": content}}
    style: dict = {}
    if bold:
        style["bold"] = True
    if link:
        style["link"] = {"url": link}
    if style:
        run["text_run"]["text_element_style"] = style
    return run


def _block_heading(level: int, text: str) -> Block:
    """level: 3=h1, 4=h2, 5=h3, ..., 11=h9."""
    heading_method = f"heading{level - 2}"
    builder = Block.builder().block_type(level)
    builder = getattr(builder, heading_method)({"elements": [_text_run(text, bold=True)]})
    return builder.build()


def _block_divider() -> Block:
    return Block.builder().block_type(22).divider({}).build()


def _block_text(elements: list[dict]) -> Block:
    return Block.builder().block_type(2).text({"elements": elements}).build()


def _format_github_description(item: NewsItem) -> str:
    parts = []
    if item.description:
        parts.append(item.description)
    lang = item.extra.get("language", "")
    if lang:
        parts.append(f"Language: {lang}")
    stars_today = item.extra.get("stars_today", "")
    if stars_today:
        parts.append(f"Stars today: {stars_today}")
    return " | ".join(parts) if parts else "No description"


def build_monthly_header(month_str: str) -> list[Block]:
    """H1 title + divider for a new monthly document."""
    return [
        _block_heading(3, f"Daily News Digest - {month_str}"),
        _block_divider(),
    ]


def build_daily_section(
    news_by_category: dict[str, list[NewsItem]],
    date_str: str = "",
) -> list[Block]:
    """Build content blocks for one day, to be appended to the monthly doc."""
    blocks: list[Block] = []

    # H2: Date
    blocks.append(_block_heading(4, date_str))
    blocks.append(_block_divider())

    for source_name in ["ai_news", "github_trending", "world_news"]:
        items = news_by_category.get(source_name, [])
        label = CATEGORY_LABELS[source_name]

        # H3: Category
        blocks.append(_block_heading(5, label))

        if not items:
            blocks.append(_block_text([
                _text_run(f"No {label} available today.")
            ]))
        else:
            for idx, item in enumerate(items, 1):
                desc = (
                    _format_github_description(item)
                    if source_name == "github_trending"
                    else (item.description or "")
                )
                elements = [
                    _text_run(f"{idx}. ", bold=True),
                    _text_run(item.title, bold=True, link=item.url),
                ]
                if desc:
                    elements.append(_text_run(f"\n   {desc}"))
                elements.append(_text_run("\n"))
                blocks.append(_block_text(elements))

        blocks.append(_block_divider())

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    blocks.append(_block_text([_text_run(f"Updated at {now}")]))
    blocks.append(_block_divider())

    return blocks
