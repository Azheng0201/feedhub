"""网页正文提取服务。"""
import logging

import httpx
import trafilatura

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

class ExtractError(Exception):
    """提取失败。"""
    pass


async def extract_full_text(url: str) -> str:
    """访问 URL 并提取正文。"""
    try:
        # 1. 抓取网页源码
        async with httpx.AsyncClient(
            timeout=15,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text

        # 2. 使用 trafilatura 提取正文
        extracted = trafilatura.extract(
            html,
            include_links=True,      # 保留正文中的超链接
            include_images=True,     # 保留图片
            include_formatting=True, # 保留格式
            favor_recall=True
        )

        if not extracted:
            raise ExtractError("未能从该网页识别出正文内容")

        return extracted

    except httpx.HTTPStatusError as e:
        logger.warning(f"提取正文失败 HTTP {e.response.status_code}: {url}")
        raise ExtractError(f"网页访问失败 (HTTP {e.response.status_code})") from None
    except httpx.RequestError:
        logger.warning(f"提取正文网络错误: {url}")
        raise ExtractError("网络连接失败，无法访问原网页") from None
    except Exception as e:
        logger.error(f"提取异常 {e}")
        raise ExtractError("网页解析失败") from None
