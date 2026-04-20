"""
OCR 识别工具 - Windows 兼容版（接口完全兼容 ocr.py）
使用标准 OpenAI API 调用硅基流动 PaddleOCR-VL，无需 paddleocr 包

与 ocr.py 的接口完全一致：
- run_ocr(image_path, save_dir=None) → {"success", "text", "blocks", "md_path", "cropped_images"}
- extract_text_from_result(ocr_result) → str
- batch_ocr(image_paths, save_dir=None) → list

适用于 Windows/Linux/Mac 全平台（不依赖 paddleocr 包，纯 httpx 调用 API）
"""
import os
import sys
import time
import logging
import base64
from pathlib import Path
from typing import Dict, Any, List, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# 图片类 block label（与 ocr.py 保持一致）
IMAGE_BLOCK_LABELS = {'image', 'header_image', 'figure', 'seal', 'stamp', 'chart'}


def _get_mime_type(image_path: str) -> str:
    """根据文件扩展名确定 MIME 类型"""
    ext = Path(image_path).suffix.lower()
    mime_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
        ".tiff": "image/tiff",
        ".tif": "image/tiff",
    }
    return mime_types.get(ext, "image/jpeg")


def _image_to_base64(image_path: str) -> str:
    """将图片文件转为 base64 编码"""
    with open(image_path, "rb") as f:
        image_data = f.read()
    return base64.b64encode(image_data).decode("utf-8")


def _call_paddleocr_vl_api(image_path: str, timeout: float = 120.0) -> Dict[str, Any]:
    """
    通过标准 OpenAI API 调用硅基流动 PaddleOCR-VL-1.5

    Args:
        image_path: 图片文件路径
        timeout: 请求超时时间（秒）

    Returns:
        API 原始响应
    """
    api_key = settings.SILICONFLOW_API_KEY
    if not api_key:
        raise ValueError(
            "未配置 SILICONFLOW_API_KEY！\n"
            "请在 backend/.env 文件中添加：\n"
            "SILICONFLOW_API_KEY=你的API密钥"
        )

    base_url = settings.SILICONFLOW_BASE_URL.rstrip("/")
    model = settings.OCR_MODEL

    # 读取图片
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"图片文件不存在: {image_path}")

    mime_type = _get_mime_type(image_path)
    base64_image = _image_to_base64(image_path)

    # 构建请求体（参考硅基流动官方文档）
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{base64_image}",
                            "detail": "high"
                        }
                    },
                    {
                        "type": "text",
                        "text": "<image>\n<|grounding|>Convert the document to markdown."
                    }
                ]
            }
        ],
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    logger.info(f"调用 PaddleOCR-VL API (httpx): {base_url}/chat/completions")
    logger.info(f"图片: {image_path}, MIME: {mime_type}, 大小: {os.path.getsize(image_path) / 1024:.1f} KB")

    with httpx.Client(timeout=timeout) as client:
        response = client.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload
        )

    if response.status_code != 200:
        logger.error(f"API 返回错误: {response.status_code}")
        logger.error(f"响应内容: {response.text}")
        raise Exception(f"PaddleOCR-VL API 调用失败: {response.status_code} - {response.text}")

    return response.json()


def _parse_ocr_response(response: Dict[str, Any]) -> str:
    """
    解析 PaddleOCR-VL API 响应，返回 markdown 文本

    Args:
        response: API 原始响应

    Returns:
        识别出的 markdown 文本
    """
    try:
        content = response["choices"][0]["message"]["content"]
        markdown_text = content.strip()

        # 去掉 markdown 代码块标记
        if markdown_text.startswith("```json"):
            markdown_text = markdown_text[7:]
        if markdown_text.startswith("```"):
            lines = markdown_text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            markdown_text = "\n".join(lines)

        return markdown_text.strip()

    except (KeyError, IndexError) as e:
        logger.error(f"解析响应失败: {e}")
        logger.error(f"原始响应: {response}")
        raise Exception(f"解析 PaddleOCR-VL 响应失败: {e}")


def run_ocr(image_path: str, save_dir: str = None) -> Dict[str, Any]:
    """
    OCR 识别入口函数（接口与 ocr.py 完全一致）

    Args:
        image_path: 图片文件路径
        save_dir: OCR 结果 md 文件保存目录（可选）

    Returns:
        {"success": True, "text": "识别文本(Markdown)", "blocks": [...], "md_path": "...", "cropped_images": [...]}
        或 {"success": False, "error": "错误信息"}
    """
    if not os.path.exists(image_path):
        return {"success": False, "error": f"文件不存在: {image_path}"}

    max_retries = 3
    for attempt in range(max_retries):
        try:
            # 1. 调用 API
            response = _call_paddleocr_vl_api(image_path)

            # 2. 解析结果
            full_text = _parse_ocr_response(response)

            if not full_text or not full_text.strip():
                logger.warning(f"OCR 返回空结果，第 {attempt + 1} 次重试...")
                if attempt < max_retries - 1:
                    time.sleep(2)
                continue

            # 3. 构造 blocks（简化版，httpx 方式无法获取结构化 blocks）
            all_blocks = []
            for line in full_text.split("\n"):
                line = line.strip()
                if line:
                    all_blocks.append({
                        "label": "text",
                        "content": line,
                    })

            # 4. 保存 md 文件到硬盘
            md_path = None
            if save_dir:
                os.makedirs(save_dir, exist_ok=True)
                stem = Path(image_path).stem
                md_path = os.path.join(save_dir, f"{stem}.md")
                with open(md_path, 'w', encoding='utf-8') as f:
                    f.write(full_text)
                logger.info(f"OCR 结果已保存: {md_path}")

            logger.info(f"OCR 识别成功，文字长度: {len(full_text)} 字符")

            return {
                "success": True,
                "text": full_text,
                "blocks": all_blocks,
                "md_path": md_path,
                "cropped_images": [],  # httpx 方式无法获取 bbox，不裁切图片
            }

        except Exception as e:
            error_msg = str(e)
            logger.warning(f"OCR 异常: {error_msg}，第 {attempt + 1} 次重试...")
            if "401" in error_msg or "Unauthorized" in error_msg:
                return {"success": False, "error": "API Key 无效，请检查 SILICONFLOW_API_KEY 配置"}
            if "429" in error_msg or "rate" in error_msg.lower():
                time.sleep(5)
            elif attempt < max_retries - 1:
                time.sleep(2)

    return {"success": False, "error": f"OCR 识别失败（已重试 {max_retries} 次）"}


def extract_text_from_result(ocr_result: Dict[str, Any]) -> str:
    """从 OCR 结果中提取纯文本（与 ocr.py 接口一致）"""
    if not ocr_result.get("success"):
        return ""
    return ocr_result.get("text", "")


def batch_ocr(image_paths: List[str], save_dir: str = None) -> List[Dict[str, Any]]:
    """
    批量 OCR 识别（带速率控制，与 ocr.py 接口一致）

    Args:
        image_paths: 图片路径列表
        save_dir: OCR 结果保存目录

    Returns:
        识别结果列表
    """
    MIN_GAP = 0.1  # 请求间隔秒数
    results = []
    last_time = 0

    for i, path in enumerate(image_paths):
        now = time.time()
        if now - last_time < MIN_GAP:
            time.sleep(MIN_GAP - (now - last_time))
        last_time = time.time()

        logger.info(f"OCR 识别中 ({i+1}/{len(image_paths)}): {Path(path).name}")
        result = run_ocr(path, save_dir=save_dir)
        results.append({
            "file": path,
            "filename": Path(path).name,
            "result": result,
        })

    return results


# ============ 便捷函数 ============

def ocr_image(image_path: str) -> str:
    """便捷函数：直接返回识别文字"""
    result = run_ocr(image_path)
    if result["success"]:
        return result["text"]
    else:
        raise Exception(result.get("error", "OCR 识别失败"))


def ocr_base64(image_base64: str, mime_type: str = "image/jpeg") -> str:
    """通过 base64 数据进行 OCR 识别（不依赖文件）"""
    api_key = settings.SILICONFLOW_API_KEY
    if not api_key:
        raise ValueError("未配置 SILICONFLOW_API_KEY")

    base_url = settings.SILICONFLOW_BASE_URL.rstrip("/")
    model = settings.OCR_MODEL

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{image_base64}",
                            "detail": "high"
                        }
                    },
                    {
                        "type": "text",
                        "text": "<image>\n<|grounding|>Convert the document to markdown."
                    }
                ]
            }
        ]
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    with httpx.Client(timeout=120.0) as client:
        response = client.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload
        )

    if response.status_code != 200:
        raise Exception(f"API 返回错误: {response.status_code}")

    result = response.json()
    return result["choices"][0]["message"]["content"]


# ============ 测试代码 ============
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    print("=" * 50)
    print("PaddleOCR-VL httpx 兼容版（无需 paddleocr 包）")
    print("=" * 50)

    # 检查配置
    if not settings.SILICONFLOW_API_KEY:
        print("\n⚠️  警告：未配置 SILICONFLOW_API_KEY")
        print("请在 backend/.env 文件中添加：")
        print("SILICONFLOW_API_KEY=你的API密钥\n")

    # 如果有命令行参数，当作图片路径处理
    if len(sys.argv) > 1:
        image_path = sys.argv[1]
        save_dir = sys.argv[2] if len(sys.argv) > 2 else None
        print(f"\n识别图片: {image_path}\n")

        result = run_ocr(image_path, save_dir=save_dir)

        if result["success"]:
            text = extract_text_from_result(result)
            print("=" * 50)
            print("识别结果：")
            print("=" * 50)
            print(text[:500])
            print(f"\n文本长度: {len(text)} 字符")
            if result.get('md_path'):
                print(f"MD文件: {result['md_path']}")
        else:
            print(f"\n❌ 识别失败: {result.get('error')}")
    else:
        print("\n用法：python oc33r.py <图片路径> [保存目录]")
        print("示例：python oc33r.py C:/Users/xxx/test.png")
