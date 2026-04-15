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

# workspace 根目录
# 优先使用 Render Disk 持久化路径（部署后文件不丢失）
# 如果没有 Render Disk，降级到容器内路径（部署后会丢失）
import os as _os
_render_disk = _os.environ.get("RENDER_DISK_PATH", "")
if _render_disk:
    WORKSPACE_BASE = Path(_render_disk) / "workspace"
    WORKSPACE_FALLBACK = Path(".crabres/memory/workspace")  # 容器内备用
else:
    WORKSPACE_BASE = Path(".crabres/memory/workspace")
    WORKSPACE_FALLBACK = None

# 确保目录存在
WORKSPACE_BASE.mkdir(parents=True, exist_ok=True)


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
        # 尝试从容器内路径恢复（Render Disk 可能还没同步）
        if WORKSPACE_FALLBACK:
            fallback_target = (WORKSPACE_FALLBACK / path).resolve()
            if fallback_target.exists():
                import shutil
                target.parent.mkdir(parents=True, exist_ok=True)
                if fallback_target.is_dir():
                    shutil.copytree(fallback_target, target, dirs_exist_ok=True)
                else:
                    shutil.copy2(fallback_target, target)
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
    """读取单个文件内容（支持从 memory 备份恢复）"""
    target = _safe_path(path)
    
    # 如果文件不存在，尝试从 memory 备份恢复
    if not target.exists() or not target.is_file():
        recovered = await _try_recover_from_memory(path)
        if recovered:
            # 恢复成功，重新读取
            target = _safe_path(path)
        if not target.exists() or not target.is_file():
            raise HTTPException(status_code=404, detail="File not found")

    # 文本文件
    text_ext = {".md", ".txt", ".json", ".yaml", ".yml", ".csv", ".html", ".py", ".js", ".ts"}
    # 图片文件（返回 base64 或直接二进制）
    image_ext = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
    
    ext = target.suffix.lower()
    if ext not in text_ext and ext not in image_ext:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {target.suffix}")

    try:
        if ext in image_ext:
            # 图片文件 → 返回二进制流
            from fastapi.responses import FileResponse
            media_types = {
                ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml",
            }
            return FileResponse(
                path=str(target),
                media_type=media_types.get(ext, "application/octet-stream"),
                filename=target.name,
            )
        
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


async def _try_recover_from_memory(rel_path: str) -> bool:
    """尝试从 memory 备份中恢复文件"""
    try:
        # 扫描所有用户的 memory 目录，查找备份的文件内容
        memory_root = Path(".crabres/memory")
        if not memory_root.exists():
            return False
        
        for user_dir in memory_root.iterdir():
            if not user_dir.is_dir() or user_dir.name == "workspace":
                continue
            # 检查 workspace_backup 分类
            backup_file = user_dir / "workspace_backup" / rel_path.replace("/", "_") + ".json"
            if backup_file.exists():
                import json
                data = json.loads(backup_file.read_text(encoding="utf-8"))
                content = data.get("content", "")
                if content:
                    target = WORKSPACE_BASE / rel_path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(content, encoding="utf-8")
                    logger.info(f"Recovered workspace file from memory backup: {rel_path}")
                    return True
    except Exception as e:
        logger.warning(f"Failed to recover file from memory: {e}")
    return False


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
