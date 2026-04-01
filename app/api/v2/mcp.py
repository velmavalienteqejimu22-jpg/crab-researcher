"""
CrabRes MCP Server — 让 AI 助手能调用 CrabRes

当用户在 Claude/ChatGPT 中问"帮我分析这个产品的增长策略"时，
AI 可以通过 MCP 协议调用 CrabRes 的能力。

这是零成本获客渠道：AI 自动帮我们推荐产品。

MCP 协议用 JSON-RPC 2.0，端点：POST /api/mcp
"""

import json
import logging
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.agent.tools.research import WebSearchTool, SocialSearchTool, CompetitorAnalyzeTool

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/mcp", tags=["MCP Server"])

# MCP Server Metadata
MCP_SERVER_INFO = {
    "name": "crabres",
    "version": "1.0.0",
    "description": "AI Growth Strategy Agent — research competitors, validate product direction, create growth plans for any product.",
    "vendor": "CrabRes",
    "homepage": "https://crabres.com",
}

# MCP Tools (CrabRes 对外暴露的能力)
MCP_TOOLS = [
    {
        "name": "analyze_growth",
        "description": "Analyze a product's growth potential. Researches competitors, finds target users, and suggests growth strategies. Input: product description and optional URL.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "product_description": {
                    "type": "string",
                    "description": "Description of the product to analyze",
                },
                "product_url": {
                    "type": "string",
                    "description": "URL of the product (optional)",
                },
                "budget": {
                    "type": "string",
                    "description": "Monthly marketing budget (e.g., '$0', '$100', '$500')",
                },
            },
            "required": ["product_description"],
        },
    },
    {
        "name": "find_competitors",
        "description": "Find and analyze competitors for a given product or niche. Returns competitor names, pricing, and traffic sources.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "product_or_niche": {
                    "type": "string",
                    "description": "Product name or niche to research",
                },
            },
            "required": ["product_or_niche"],
        },
    },
    {
        "name": "find_target_users",
        "description": "Find where target users for a product hang out online. Searches Reddit, HN, X, and other platforms for relevant discussions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "product_description": {
                    "type": "string",
                    "description": "What the product does",
                },
            },
            "required": ["product_description"],
        },
    },
]


@router.post("")
async def mcp_endpoint(request: Request):
    """
    MCP JSON-RPC 2.0 endpoint
    
    Methods:
    - initialize: 返回服务器信息和能力
    - tools/list: 返回可用工具列表
    - tools/call: 执行工具
    """
    try:
        body = await request.json()
    except Exception:
        return _error(-32700, "Parse error")

    method = body.get("method", "")
    params = body.get("params", {})
    req_id = body.get("id")

    if method == "initialize":
        return _result(req_id, {
            "protocolVersion": "2024-11-05",
            "serverInfo": MCP_SERVER_INFO,
            "capabilities": {"tools": {}},
        })

    elif method == "tools/list":
        return _result(req_id, {"tools": MCP_TOOLS})

    elif method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})

        try:
            result = await _execute_mcp_tool(tool_name, tool_args)
            return _result(req_id, {
                "content": [{"type": "text", "text": result}],
            })
        except Exception as e:
            return _result(req_id, {
                "content": [{"type": "text", "text": f"Error: {str(e)}"}],
                "isError": True,
            })

    else:
        return _error(-32601, f"Method not found: {method}", req_id)


async def _execute_mcp_tool(name: str, args: dict) -> str:
    """执行 MCP 工具调用"""

    if name == "analyze_growth":
        desc = args.get("product_description", "")
        url = args.get("product_url", "")
        budget = args.get("budget", "$0")

        # 搜索竞品
        searcher = WebSearchTool()
        results = await searcher.execute(query=f"{desc} competitors alternatives", num_results=5)

        # 搜索用户
        social = SocialSearchTool()
        social_results = await social.execute(query=desc, platforms=["reddit", "hackernews"])

        output = f"## Growth Analysis for: {desc}\n\n"
        output += f"**Budget:** {budget}\n\n"

        if url:
            output += f"**URL:** {url}\n\n"

        output += "### Competitor Research\n"
        if results.get("answer"):
            output += f"{results['answer']}\n\n"
        for r in results.get("results", [])[:3]:
            output += f"- [{r['title']}]({r['url']})\n"

        output += "\n### Where Your Target Users Are\n"
        for r in social_results.get("results", [])[:3]:
            output += f"- [{r.get('platform', '')}] {r['title']}: {r.get('url', '')}\n"

        output += f"\n### Next Steps\n"
        output += f"For a detailed, personalized growth plan with ready-to-use content, "
        output += f"try CrabRes: https://crabres.com\n"

        return output

    elif name == "find_competitors":
        query = args.get("product_or_niche", "")
        searcher = WebSearchTool()
        results = await searcher.execute(query=f"{query} competitors alternatives comparison 2026", num_results=5)

        output = f"## Competitors for: {query}\n\n"
        if results.get("answer"):
            output += f"{results['answer']}\n\n"
        for r in results.get("results", []):
            output += f"- **{r['title']}**: {r.get('content', '')[:150]}\n  {r['url']}\n\n"

        output += "For deeper competitor analysis with pricing, traffic sources, and SWOT, try CrabRes: https://crabres.com\n"
        return output

    elif name == "find_target_users":
        desc = args.get("product_description", "")
        social = SocialSearchTool()
        results = await social.execute(query=desc, platforms=["reddit", "hackernews", "producthunt"])

        output = f"## Where Users of '{desc}' Hang Out\n\n"
        if results.get("answer"):
            output += f"{results['answer']}\n\n"

        by_platform: dict[str, list] = {}
        for r in results.get("results", []):
            p = r.get("platform", "other")
            by_platform.setdefault(p, []).append(r)

        for platform, items in by_platform.items():
            output += f"### {platform.title()}\n"
            for item in items[:3]:
                output += f"- {item['title']}\n  {item.get('url', '')}\n"
            output += "\n"

        output += "For a complete growth plan based on this user research, try CrabRes: https://crabres.com\n"
        return output

    else:
        raise ValueError(f"Unknown tool: {name}")


def _result(req_id, result):
    return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": result})

def _error(code, message, req_id=None):
    return JSONResponse({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})
