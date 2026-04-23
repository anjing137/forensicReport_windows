"""
司法鉴定意见书自动生成系统 - 后端入口
"""
import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# 跳过 PaddleOCR 模型连接检测，避免启动时卡住
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

# ==================== 日志配置 ====================
LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# 日志格式
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 文件日志：按大小轮转（10MB一个文件，保留5个备份）
log_file = os.path.join(LOG_DIR, "app.log")
file_handler = RotatingFileHandler(
    log_file,
    maxBytes=10 * 1024 * 1024,  # 10MB
    backupCount=5,
    encoding="utf-8",
)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))

# 控制台日志：INFO及以上
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))

# 全局配置
logging.basicConfig(
    level=logging.DEBUG,
    format=LOG_FORMAT,
    datefmt=DATE_FORMAT,
    handlers=[file_handler, console_handler],
)

# 第三方库日志级别调高，避免刷屏
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.INFO)

logger = logging.getLogger(__name__)
logger.info("=" * 50)
logger.info(f"司法鉴定意见书自动生成系统启动 - {datetime.now()}")
logger.info(f"日志文件: {log_file}")
logger.info("=" * 50)

# ==================== FastAPI 应用 ====================

from app.database import init_db
from app.routers import cases, materials, medical_records, imaging_reports, reports, style_logs, persons, llm_extract, settings

app = FastAPI(
    title="司法鉴定意见书自动生成系统",
    description="基于 PRD v1.0 - 上传材料 → OCR识别 → 自动生成报告",
    version="1.0.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(cases.router)
app.include_router(materials.router)
app.include_router(medical_records.router)
app.include_router(imaging_reports.router)
app.include_router(reports.router)
app.include_router(style_logs.router)
app.include_router(persons.router)
app.include_router(llm_extract.router)
app.include_router(settings.router)


@app.on_event("startup")
def startup():
    init_db()
    # 自动修复：将孤立的 PROCESSING 状态重置为 PENDING（后端重启后残留的状态）
    try:
        from app.database import SessionLocal
        from app.models.case import Material, OcrStatus
        db = SessionLocal()
        orphaned = db.query(Material).filter(Material.ocr_status == OcrStatus.PROCESSING).all()
        if orphaned:
            for m in orphaned:
                m.ocr_status = OcrStatus.PENDING
                m.ocr_text = ""
            db.commit()
            logger.info(f"启动修复：{len(orphaned)} 个 PROCESSING 材料已重置为 PENDING")
        db.close()
    except Exception as e:
        logger.warning(f"启动修复 PROCESSING 状态时出错: {e}")


# ==================== 前端静态文件托管 ====================
from pathlib import Path
from starlette.responses import FileResponse as _FileResponse

FRONTEND_DIST = Path(__file__).parent / "static"

# 上传文件目录 — 必须在 SPA fallback 之前挂载
import os as _os
from app.config import settings as _settings
UPLOAD_DIR = str(_settings.UPLOAD_DIR)
_os.makedirs(UPLOAD_DIR, exist_ok=True)
_uploads_sf = StaticFiles(directory=UPLOAD_DIR)

if FRONTEND_DIST.exists() and (FRONTEND_DIST / "index.html").exists():
    # 有前端静态文件时，托管前端SPA

    # ⚠️ 关键：/uploads 必须在 SPA fallback 路由之前挂载！
    # 否则 /{full_path:path} 会先匹配到 /uploads/ 请求，返回 index.html 而不是图片文件
    app.mount("/uploads", _uploads_sf, name="uploads")

    # 挂载静态资源目录（js/css/images等）
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="frontend-assets")

    @app.get("/")
    async def serve_index():
        return _FileResponse(FRONTEND_DIST / "index.html")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    # SPA fallback：所有非API、非uploads的GET请求返回index.html
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """SPA路由：先尝试精确文件，找不到则返回index.html"""
        # /api/ 路径：不应该走到这里，返回 404
        if full_path.startswith("api/"):
            from fastapi.responses import Response
            return Response(status_code=404)
        # 尝试精确匹配前端静态文件
        file_path = FRONTEND_DIST / full_path
        if full_path and file_path.exists() and file_path.is_file():
            return _FileResponse(file_path)
        # SPA fallback
        return _FileResponse(FRONTEND_DIST / "index.html")

else:
    # 无前端静态文件时，纯API模式
    @app.get("/")
    def root():
        return {"message": "司法鉴定意见书自动生成系统 API", "version": "1.0.0"}

    @app.get("/health")
    def health():
        return {"status": "ok"}

    # 纯 API 模式也需要 uploads
    app.mount("/uploads", _uploads_sf, name="uploads")


@app.get("/api/logs")
def get_logs(lines: int = 100, level: str = None):
    """
    查看最近的日志
    
    - lines: 返回最近N行日志（默认100，最大500）
    - level: 按级别过滤（DEBUG/INFO/WARNING/ERROR）
    """
    lines = min(lines, 500)
    
    if not os.path.exists(log_file):
        return {"logs": [], "total": 0, "message": "日志文件不存在"}
    
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
    except Exception as e:
        return {"logs": [], "error": str(e)}
    
    # 取最后N行
    recent = all_lines[-lines:]
    
    # 按级别过滤
    if level and level.upper() in ("DEBUG", "INFO", "WARNING", "ERROR"):
        level_str = f"[{level.upper()}]"
        recent = [l for l in recent if level_str in l]
    
    return {
        "logs": [l.rstrip() for l in recent],
        "total": len(recent),
        "log_file": log_file,
    }


