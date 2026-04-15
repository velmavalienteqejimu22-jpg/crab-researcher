"""
Workspace API — 文件管理接口

让前端能查看 Agent 生成的所有文件（报告/草稿/计划等）
"""

import os
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/workspace", tags=["Workspace"])

# workspace 根目录（与 pipeline.py 中一致）
WORKSPACE_BASE = Path(".crabres/memory/global").parent / "workspace"


def _safe_path(rel_path: str) -> Path:
    """防止路径穿越攻击"""
    resolved = (WORKSPACE_BASE / rel_path).resolve()
    if not str(resolved).startswith(str(WORKSPACE_BASE.resolve())):
        raise HTTPException(status_code=403, detail="Access denied")
    return resolved


@router.get("/files")
async def list_files(path: str = Query("", description="子目录路径")):
    """列出 workspace 中的文件和目录"""
    target = _safe_path(path)
    if not target.exists():
        return {"files": [], "path": path}

    items = []
    try:
        for entry in sorted(target.iterdir()):
            if entry.name.startswith("."):
                continue
            stat = entry.stat()
            items.append({
                "name": entry.name,
                "path": str(entry.relative_to(WORKSPACE_BASE)),
                "type": "directory" if entry.is_dir() else "file",
                "size": stat.st_size if entry.is_file() else None,
                "modified": stat.st_mtime,
                "extension": entry.suffix.lstrip(".") if entry.is_file() else None,
            })
    except Exception as e:
        logger.warning(f"Failed to list workspace: {e}")

    return {"files": items, "path": path}


@router.get("/files/tree")
async def file_tree():
    """递归获取完整文件树"""
    if not WORKSPACE_BASE.exists():
        return {"tree": []}

    def _walk(dir_path: Path, depth: int = 0) -> list:
        if depth > 5:
            return []
        result = []
        try:
            for entry in sorted(dir_path.iterdir()):
                if entry.name.startswith("."):
                    continue
                node = {
                    "name": entry.name,
                    "path": str(entry.relative_to(WORKSPACE_BASE)),
                    "type": "directory" if entry.is_dir() else "file",
                }
                if entry.is_file():
                    node["size"] = entry.stat().st_size
                    node["extension"] = entry.suffix.lstrip(".")
                elif entry.is_dir():
                    node["children"] = _walk(entry, depth + 1)
                result.append(node)
        except Exception:
            pass
        return result

    return {"tree": _walk(WORKSPACE_BASE)}


@router.get("/files/read")
async def read_file(path: str = Query(..., description="文件相对路径")):
    """读取单个文件内容"""
    target = _safe_path(path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    # 只允许读取文本文件
    allowed_ext = {".md", ".txt", ".json", ".yaml", ".yml", ".csv", ".html", ".py", ".js", ".ts"}
    if target.suffix.lower() not in allowed_ext:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {target.suffix}")

    try:
        content = target.read_text(encoding="utf-8")
        return {
            "path": path,
            "name": target.name,
            "content": content,
            "size": target.stat().st_size,
            "extension": target.suffix.lstrip("."),
            "modified": target.stat().st_mtime,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {e}")


@router.delete("/files")
async def delete_file(path: str = Query(..., description="文件相对路径")):
    """删除单个文件"""
    target = _safe_path(path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="File not found")

    try:
        if target.is_file():
            target.unlink()
        return {"deleted": path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete: {e}")


@router.get("/stats")
async def workspace_stats():
    """workspace 统计信息"""
    if not WORKSPACE_BASE.exists():
        return {"total_files": 0, "total_size": 0, "categories": {}}

    total_files = 0
    total_size = 0
    categories: dict = {}

    for f in WORKSPACE_BASE.rglob("*"):
        if f.is_file() and not f.name.startswith("."):
            total_files += 1
            total_size += f.stat().st_size
            # 按父目录分类
            cat = f.parent.name if f.parent != WORKSPACE_BASE else "root"
            categories[cat] = categories.get(cat, 0) + 1

    return {
        "total_files": total_files,
        "total_size": total_size,
        "categories": categories,
    }
