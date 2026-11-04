"""Redis 缓存服务。"""

import json
import logging
import os
from typing import Any

import redis.asyncio as redis

logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDISURL", "redis://localhost:6379/0")

# 创建全局异步 Redis 客户端
redis_client = redis.from_url(REDIS_URL, decode_responses=True)


async def get_cache(key: str) -> Any | None:
    """读取缓存，自动反序列化 JSON。"""
    try:
        val = await redis_client.get(key)
        if val:
            return json.loads(val)
    except Exception as e:
        logger.warning(f"Redis 读取失败：{e}")
    return None


async def set_cache(key: str, value: Any, expire: int = 300):
    """写入缓存，默认 5 分钟过期。"""
    try:
        await redis_client.set(key, json.dumps(value), ex=expire)
    except Exception as e:
        logger.warning(f"Redis 写入失败：{e}")


async def delete_cache(key: str):
    """删除指定缓存。"""
    try:
        await redis_client.delete(key)
    except Exception as e:
        logger.warning(f"Redis 删除失败：{e}")


async def clear_pattern(pattern: str):
    """按前缀批量删除。"""
    try:
        keys = await redis_client.keys(pattern)  # 生产环境用 scan(pattern)
        if keys:
            await redis_client.delete(*keys)
    except Exception as e:
        logger.warning(f"Redis 批量删除失败：{e}")
