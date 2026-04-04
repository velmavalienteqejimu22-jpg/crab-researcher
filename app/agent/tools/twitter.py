"""
CrabRes Twitter/X API 集成

支持两种操作模式：
1. 读取：获取用户/竞品的帖子数据、粉丝增长（用 Bearer Token，只读）
2. 写入：发布推文（用 OAuth 1.0a，需要用户授权）

Twitter API v2 参考：https://developer.x.com/en/docs/x-api
"""

import logging
import json
import hashlib
import hmac
import time
import base64
import urllib.parse
from typing import Optional, Any

import httpx

from app.agent.tools import BaseTool, ToolDefinition
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class TwitterReadTool(BaseTool):
    """读取 X/Twitter 数据：用户信息、帖子、搜索"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="twitter_read",
            description="Read data from X/Twitter: search tweets, get user info, get recent tweets from a user.",
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["search_tweets", "user_info", "user_tweets"],
                        "description": "What to do",
                    },
                    "query": {
                        "type": "string",
                        "description": "Search query (for search_tweets) or username (for user_info/user_tweets)",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Max results (10-100)",
                        "default": 10,
                    },
                },
                "required": ["action", "query"],
            },
            concurrent_safe=True,
            result_budget=20000,
        )

    async def execute(self, action: str, query: str, max_results: int = 10, **kwargs) -> Any:
        bearer_token = settings.TWITTER_BEARER_TOKEN
        if not bearer_token:
            return {
                "error": None,
                "note": "Twitter API not configured. Set TWITTER_BEARER_TOKEN in .env to enable real-time X/Twitter data.",
                "action": action,
                "query": query,
                "results": [],
            }

        headers = {"Authorization": f"Bearer {bearer_token}"}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                if action == "search_tweets":
                    return await self._search_tweets(client, headers, query, max_results)
                elif action == "user_info":
                    return await self._get_user_info(client, headers, query)
                elif action == "user_tweets":
                    return await self._get_user_tweets(client, headers, query, max_results)
                else:
                    return {"error": f"Unknown action: {action}"}
        except Exception as e:
            logger.error(f"Twitter API error: {e}")
            return {"error": str(e), "action": action, "query": query}

    async def _search_tweets(self, client, headers, query, max_results):
        """Search recent tweets (last 7 days)"""
        params = {
            "query": query,
            "max_results": min(max(max_results, 10), 100),
            "tweet.fields": "created_at,public_metrics,author_id,lang",
            "expansions": "author_id",
            "user.fields": "name,username,public_metrics",
        }
        resp = await client.get(
            "https://api.x.com/2/tweets/search/recent",
            headers=headers,
            params=params,
        )
        if resp.status_code == 429:
            return {"error": "Rate limited. Try again in a few minutes.", "query": query}
        resp.raise_for_status()
        data = resp.json()

        tweets = []
        users_map = {}
        for user in data.get("includes", {}).get("users", []):
            users_map[user["id"]] = user

        for tweet in data.get("data", []):
            author = users_map.get(tweet.get("author_id"), {})
            metrics = tweet.get("public_metrics", {})
            tweets.append({
                "text": tweet.get("text", ""),
                "author": author.get("username", ""),
                "author_name": author.get("name", ""),
                "author_followers": author.get("public_metrics", {}).get("followers_count", 0),
                "likes": metrics.get("like_count", 0),
                "retweets": metrics.get("retweet_count", 0),
                "replies": metrics.get("reply_count", 0),
                "impressions": metrics.get("impression_count", 0),
                "created_at": tweet.get("created_at", ""),
            })

        return {
            "query": query,
            "count": len(tweets),
            "tweets": tweets,
        }

    async def _get_user_info(self, client, headers, username):
        """Get user profile info"""
        username = username.lstrip("@")
        params = {
            "user.fields": "description,public_metrics,created_at,location,url,verified",
        }
        resp = await client.get(
            f"https://api.x.com/2/users/by/username/{username}",
            headers=headers,
            params=params,
        )
        if resp.status_code == 404:
            return {"error": f"User @{username} not found"}
        resp.raise_for_status()
        data = resp.json().get("data", {})
        metrics = data.get("public_metrics", {})

        return {
            "username": data.get("username", ""),
            "name": data.get("name", ""),
            "description": data.get("description", ""),
            "followers": metrics.get("followers_count", 0),
            "following": metrics.get("following_count", 0),
            "tweet_count": metrics.get("tweet_count", 0),
            "listed_count": metrics.get("listed_count", 0),
            "created_at": data.get("created_at", ""),
            "location": data.get("location", ""),
            "url": data.get("url", ""),
            "verified": data.get("verified", False),
        }

    async def _get_user_tweets(self, client, headers, username, max_results):
        """Get recent tweets from a user"""
        username = username.lstrip("@")
        # First get user ID
        user_resp = await client.get(
            f"https://api.x.com/2/users/by/username/{username}",
            headers=headers,
        )
        if user_resp.status_code == 404:
            return {"error": f"User @{username} not found"}
        user_resp.raise_for_status()
        user_id = user_resp.json().get("data", {}).get("id")
        if not user_id:
            return {"error": f"Could not find user ID for @{username}"}

        params = {
            "max_results": min(max(max_results, 5), 100),
            "tweet.fields": "created_at,public_metrics",
            "exclude": "retweets",
        }
        resp = await client.get(
            f"https://api.x.com/2/users/{user_id}/tweets",
            headers=headers,
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()

        tweets = []
        for tweet in data.get("data", []):
            metrics = tweet.get("public_metrics", {})
            tweets.append({
                "text": tweet.get("text", ""),
                "likes": metrics.get("like_count", 0),
                "retweets": metrics.get("retweet_count", 0),
                "replies": metrics.get("reply_count", 0),
                "impressions": metrics.get("impression_count", 0),
                "created_at": tweet.get("created_at", ""),
            })

        return {
            "username": username,
            "count": len(tweets),
            "tweets": tweets,
        }


class TwitterPostTool(BaseTool):
    """发布推文到 X/Twitter（需要 OAuth 1.0a 用户授权）"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="twitter_post",
            description="Post a tweet to X/Twitter. Requires user authorization (OAuth). Only use when user explicitly asks to post.",
            parameters={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Tweet text (max 280 characters)",
                    },
                    "reply_to_id": {
                        "type": "string",
                        "description": "Optional: tweet ID to reply to",
                    },
                },
                "required": ["text"],
            },
            concurrent_safe=False,
            requires_auth=True,
            result_budget=5000,
        )

    async def execute(self, text: str, reply_to_id: Optional[str] = None, **kwargs) -> Any:
        api_key = settings.TWITTER_API_KEY
        api_secret = settings.TWITTER_API_SECRET
        access_token = settings.TWITTER_ACCESS_TOKEN
        access_token_secret = settings.TWITTER_ACCESS_TOKEN_SECRET

        if not all([api_key, api_secret, access_token, access_token_secret]):
            return {
                "status": "draft",
                "text": text,
                "note": "Twitter OAuth not configured. Set TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET in .env to enable posting.",
                "action_required": "Configure Twitter API credentials to publish directly.",
            }

        # Validate tweet length
        if len(text) > 280:
            return {"error": f"Tweet too long: {len(text)} chars (max 280)"}

        try:
            # Build OAuth 1.0a signature
            url = "https://api.x.com/2/tweets"
            payload = {"text": text}
            if reply_to_id:
                payload["reply"] = {"in_reply_to_tweet_id": reply_to_id}

            oauth_header = self._build_oauth_header(
                "POST", url, api_key, api_secret, access_token, access_token_secret
            )

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    url,
                    json=payload,
                    headers={
                        "Authorization": oauth_header,
                        "Content-Type": "application/json",
                    },
                )

                if resp.status_code == 429:
                    return {"error": "Rate limited. Try again later."}
                resp.raise_for_status()
                data = resp.json()

                tweet_id = data.get("data", {}).get("id", "")
                return {
                    "status": "posted",
                    "tweet_id": tweet_id,
                    "url": f"https://x.com/i/status/{tweet_id}" if tweet_id else "",
                    "text": text,
                }

        except Exception as e:
            logger.error(f"Twitter post failed: {e}")
            return {
                "status": "failed",
                "error": str(e),
                "text": text,
                "note": "Tweet was not posted. The draft is preserved above.",
            }

    def _build_oauth_header(self, method, url, api_key, api_secret, token, token_secret):
        """Build OAuth 1.0a Authorization header"""
        import uuid

        oauth_params = {
            "oauth_consumer_key": api_key,
            "oauth_nonce": uuid.uuid4().hex,
            "oauth_signature_method": "HMAC-SHA1",
            "oauth_timestamp": str(int(time.time())),
            "oauth_token": token,
            "oauth_version": "1.0",
        }

        # Create signature base string
        params_str = "&".join(
            f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(v, safe='')}"
            for k, v in sorted(oauth_params.items())
        )
        base_string = f"{method}&{urllib.parse.quote(url, safe='')}&{urllib.parse.quote(params_str, safe='')}"

        # Create signing key
        signing_key = f"{urllib.parse.quote(api_secret, safe='')}&{urllib.parse.quote(token_secret, safe='')}"

        # Generate signature
        signature = base64.b64encode(
            hmac.new(
                signing_key.encode(), base_string.encode(), hashlib.sha1
            ).digest()
        ).decode()

        oauth_params["oauth_signature"] = signature

        # Build header
        header_parts = ", ".join(
            f'{urllib.parse.quote(k, safe="")}="{urllib.parse.quote(v, safe="")}"'
            for k, v in sorted(oauth_params.items())
        )
        return f"OAuth {header_parts}"
