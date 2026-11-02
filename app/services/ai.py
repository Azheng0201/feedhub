"""大模型服务封装。兼容 OpenAI 接口格式。"""
import os
import logging
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("LLM_API_KEY", "")
BASE_URL = os.environ.get("LLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
MODEL = os.environ.get("LLM_MODEL", "glm-v4-flash")

# 初始化异步客户端
client = AsyncOpenAI(api_key=API_KEY, base_url=BASE_URL) if API_KEY else None

SYSTEM_PROMPT = """你是一个专业的新闻摘要助手。请用简练的3句话总结用户提供的文章内容。
要求：
1. 直接输出摘要内容，不要任何前缀或废话。
2. 语言精炼，突出核心观点。
"""

async def generate_summary(text: str) -> str:
    """调用大模型生成摘要。"""
    if not client:
        logging.warning("未配置 LLM_API_KEY，跳过 AI 摘要生成。")
        return ""

    # 截断过长的正文
    text = text[:4000]

    try:
        response = await client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text}
            ],
            temperature=0.3,
            max_tokens=200,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"AI 摘要生成失败：{e}")
        return ""