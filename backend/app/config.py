"""
应用配置
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings

# 项目根目录 = backend/（uvicorn 工作目录）
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """应用配置"""
    # 数据库
    DATABASE_URL: str = f"sqlite:///{BASE_DIR}/forensic_report.db"
    
    # 调试模式
    DEBUG: bool = True
    
    # 上传文件存储
    UPLOAD_DIR: Path = BASE_DIR / "uploads"
    
    # 硅基流动 API 配置（OCR + LLM 共用）
    SILICONFLOW_API_KEY: str = ""
    SILICONFLOW_BASE_URL: str = "https://api.siliconflow.cn/v1"
    OCR_MODEL: str = "PaddlePaddle/PaddleOCR-VL-1.5"
    OCR_BACKEND: str = "siliconflow"  # siliconflow | local

    # LLM 配置（硅基流动 Chat Completions）
    LLM_MODEL: str = "Qwen/Qwen3-8B"                # 免费模型，8B参数
    LLM_MODEL_BACKUP: str = "Qwen/Qwen2.5-14B-Instruct"  # 备选付费模型
    LLM_TEMPERATURE: float = 0.1                     # 信息提取用低温，减少幻觉
    LLM_MAX_TOKENS: int = 4096                       # 最大输出 token 数
    
    # 报告模板目录
    TEMPLATE_DIR: Path = BASE_DIR / "templates"
    
    # 生成的报告目录
    REPORT_DIR: Path = BASE_DIR / "reports"
    
    # API 配置
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    
    # 文件大小限制 (50MB)
    MAX_FILE_SIZE: int = 50 * 1024 * 1024
    
    class Config:
        env_file = ".env"


# 全局配置实例
settings = Settings()

# 确保目录存在
for dir_path in [settings.UPLOAD_DIR, settings.TEMPLATE_DIR, settings.REPORT_DIR]:
    dir_path.mkdir(exist_ok=True)
