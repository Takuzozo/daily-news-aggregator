import logging

import requests
import trafilatura

from src import config

logger = logging.getLogger(__name__)


def _fetch_article_text(url: str) -> str:
    """Scrape the article page and extract the main text content."""
    try:
        # For Google News redirect URLs, follow redirects to get actual URL
        if "news.google.com/rss/articles" in url:
            resp = requests.get(
                url,
                timeout=15,
                allow_redirects=True,
                headers={"User-Agent": "DailyNewsAggregator/1.0"},
            )
            actual_url = resp.url
            if actual_url != url:
                logger.debug("Resolved Google News redirect: %s -> %s", url[:60], actual_url[:80])
                url = actual_url

        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return ""
        text = trafilatura.extract(downloaded, include_comments=False, include_tables=False)
        return text.strip() if text else ""
    except Exception:
        logger.debug("Failed to extract article text from %s", url[:80])
        return ""


def _summarize_with_deepseek(title: str, article_text: str) -> str | None:
    """Use DeepSeek API (OpenAI-compatible) to generate a Chinese news brief."""
    if not config.DEEPSEEK_API_KEY:
        return None

    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=config.DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com",
        )

        prompt = (
            "你是一位专业的中文新闻编辑。请根据以下新闻的标题和正文，写一篇详细的中文新闻快报"
            "（约500字）。要求：\n"
            "- 第一段：用一两句话概括事件核心\n"
            "- 第二段：展开具体细节（数据、人物、技术原理、商业背景）\n"
            "- 第三段：说明这件事为什么重要，有什么影响或趋势意义\n"
            "- 引用原文中的关键数据和直接引语\n"
            "- 语言流畅，像一篇真正的新闻快讯\n"
            "只输出快报本身，不带任何前缀或标题。\n\n"
            f"标题：{title}\n\n"
            f"正文：{article_text[:5000]}"
        )

        resp = client.chat.completions.create(
            model=config.SUMMARY_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
            temperature=0.3,
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        logger.debug("DeepSeek summarization failed", exc_info=True)
        return None


def _extract_fallback_description(text: str) -> str:
    """Extract first few sentences as fallback description."""
    cleaned = text.replace("\n", " ").strip()
    if len(cleaned) > 500:
        # Try to break at sentence boundary
        cut = cleaned[:500].rfind(". ")
        if cut > 200:
            cleaned = cleaned[:cut + 1]
        else:
            cleaned = cleaned[:500] + "..."
    return cleaned


def summarize(title: str, url: str, fallback_description: str = "") -> str:
    """Generate a Chinese news brief."""
    article_text = _fetch_article_text(url)

    # Pick the best available content
    content = article_text if article_text else fallback_description

    # Try DeepSeek with whatever content we have
    if content and config.DEEPSEEK_API_KEY:
        summary = _summarize_with_deepseek(title, content)
        if summary:
            return summary

    # Fallback: extracted article text
    if article_text:
        return _extract_fallback_description(article_text)

    # Last resort: RSS description or title
    return fallback_description or title


def summarize_batch(items: list, source_name: str = "") -> list:
    """Summarize a batch of NewsItems in parallel."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _summarize_one(item):
        try:
            item.description = summarize(item.title, item.url, item.description)
        except Exception:
            logger.debug("Summarize failed for %s", item.title)
        return item

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(_summarize_one, item): item for item in items}
        for future in as_completed(futures):
            future.result()

    return items


def filter_tech_only(items: list, limit: int = 10) -> list:
    """Use DeepSeek to filter AI news: keep only technology-focused items (new models,
    tools, research, products). Policy/ethics/society articles are removed."""
    if not config.DEEPSEEK_API_KEY:
        return items[:limit]

    try:
        from openai import OpenAI

        # Build a list of titles with indices
        title_list = "\n".join(
            f"{i}. {item.title}" for i, item in enumerate(items)
        )

        client = OpenAI(
            api_key=config.DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com",
        )

        prompt = (
            "以下是一些AI相关新闻标题。请严格筛选：\n\n"
            "【只保留】涉及以下具体技术话题的条目：\n"
            "- 新模型、新算法、新框架的发布或更新\n"
            "- 新的AI开发工具、平台、基础设施\n"
            "- AI硬件发布（芯片、服务器、机器人）\n"
            "- 具体的技术研究突破或论文发表\n"
            "- AI产品功能的具体更新\n"
            "- AI公司的技术性收购或重大融资\n\n"
            "【必须排除】以下内容（即使标题包含AI）：\n"
            "- 宗教相关（教皇、教宗、梵蒂冈、教会、encyclical、通谕）\n"
            "- 纯伦理讨论、监管政策、法律立法\n"
            "- 观点评论、人物访谈（非技术内容）\n"
            "- 大会宣传、早鸟票、促销折扣\n"
            "- 逮捕、犯罪、色情、社会新闻\n"
            "- 就业市场、招聘趋势\n"
            "- 教育、培训课程\n\n"
            "关键判断原则：条目的核心话题必须是技术本身，而非围绕技术的社会/政治/宗教讨论。"
            "如果标题的核心是教皇、政策、伦理、犯罪、招聘，即使提到AI模型名称也必须排除。\n\n"
            "返回格式：只返回符合条件的序号，用逗号分隔，如\"0,2,5,7\"。如果没有符合的，返回\"NONE\"。\n\n"
            f"{title_list}"
        )

        resp = client.chat.completions.create(
            model=config.SUMMARY_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0,
        )
        result = resp.choices[0].message.content.strip()

        if result.upper() == "NONE":
            logger.info("Tech filter: no tech items found, returning top %d by recency", limit)
            return items[:limit]

        # Parse indices
        indices = []
        for part in result.split(","):
            try:
                idx = int(part.strip())
                if 0 <= idx < len(items):
                    indices.append(idx)
            except ValueError:
                continue

        tech_items = [items[i] for i in indices[:limit]]
        if not tech_items:
            logger.info("Tech filter: no tech items found, returning top %d by recency", limit)
            return items[:limit]
        logger.info(
            "Tech filter: %d tech items out of %d total, returning top %d",
            len(indices), len(items), min(limit, len(tech_items)),
        )
        return tech_items

    except Exception:
        logger.warning("Tech filter failed, returning unfiltered items", exc_info=True)
        return items[:limit]


def summarize_github_batch(items: list) -> list:
    """Generate Chinese descriptions for GitHub trending repos in parallel."""
    if not config.DEEPSEEK_API_KEY or not items:
        return items

    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _summarize_one(item):
        try:
            from openai import OpenAI

            client = OpenAI(
                api_key=config.DEEPSEEK_API_KEY,
                base_url="https://api.deepseek.com",
            )

            desc = item.description or "暂无描述"
            lang = item.extra.get("language", "未知语言")
            stars = item.extra.get("stars_today", "")

            prompt = (
                f"请用中文写一篇详细的项目介绍（约500字），介绍以下GitHub开源项目。要求：\n"
                f"1. 第一段：这个项目是什么，解决什么核心问题\n"
                f"2. 第二段：采用的关键技术、架构设计或算法原理\n"
                f"3. 第三段：与同类项目相比有什么创新或优势，实际应用场景\n"
                f"4. 如果信息不足，请根据项目名称和描述进行合理的技术推断和补充\n\n"
                f"项目名：{item.title}\n项目描述：{desc}\n主要语言：{lang}\n今日新增Star：{stars}\n\n"
                f"只输出中文介绍，不带任何前缀或标题。"
            )

            resp = client.chat.completions.create(
                model=config.SUMMARY_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000,
                temperature=0.3,
            )
            cn_desc = resp.choices[0].message.content.strip()

            # Clean format: Chinese summary + key metadata
            parts = [cn_desc]
            parts.append(f"语言: {lang}")
            if stars:
                parts.append(f"今日Star: {stars}")
            item.description = " | ".join(parts)

        except Exception:
            logger.debug("GitHub summarize failed for %s", item.title)
        return item

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(_summarize_one, item): item for item in items}
        for future in as_completed(futures):
            future.result()

    return items
