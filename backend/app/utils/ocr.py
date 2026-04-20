"""
OCR 识别工具 - 使用硅基流动 PaddleOCR-VL API
通过 PaddleOCRVL 客户端调用，免费、高精度
"""
import os
import logging
import time
from pathlib import Path
from typing import List, Dict, Any

from app.config import settings

logger = logging.getLogger(__name__)

# 图片类 block label（需要裁切保存为独立图片）
IMAGE_BLOCK_LABELS = {'image', 'header_image', 'figure', 'seal', 'stamp', 'chart'}

# 模块级 OCR 实例缓存
_ocr_pipeline = None


def _get_ocr_pipeline():
    """获取或创建 PaddleOCRVL 实例（单例模式，避免重复初始化）"""
    global _ocr_pipeline
    if _ocr_pipeline is not None:
        return _ocr_pipeline

    # 跳过 PaddleOCR 的模型连接检测
    os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

    from paddleocr import PaddleOCRVL

    api_key = settings.SILICONFLOW_API_KEY
    if not api_key:
        raise ValueError("未配置 SILICONFLOW_API_KEY，请在 .env 文件中设置")

    logger.info("正在初始化 PaddleOCRVL pipeline...")
    _ocr_pipeline = PaddleOCRVL(
        vl_rec_backend="vllm-server",
        vl_rec_server_url=settings.SILICONFLOW_BASE_URL,
        vl_rec_api_model_name=settings.OCR_MODEL,
        vl_rec_api_key=api_key,
    )
    logger.info("PaddleOCRVL pipeline 初始化完成")
    return _ocr_pipeline


def run_ocr(image_path: str, save_dir: str = None) -> Dict[str, Any]:
    """
    调用硅基流动 PaddleOCR-VL 识别图片文字

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
            pipeline = _get_ocr_pipeline()
            output = pipeline.predict(image_path)

            all_blocks = []
            markdown_texts = []
            image_blocks = []  # 图片块的bbox信息，用于后续裁切

            for res in output:
                # 从 res.json['res']['parsing_res_list'] 提取结构化块
                json_data = res.json
                if json_data and 'res' in json_data:
                    inner = json_data['res']
                    parsing_list = inner.get('parsing_res_list', [])
                    for block in parsing_list:
                        label = block.get('block_label', '')
                        content = block.get('block_content', '')
                        bbox = block.get('block_bbox', None)

                        # 图片类块：记录bbox用于裁切，不在文本中输出
                        if label in IMAGE_BLOCK_LABELS and bbox and len(bbox) == 4:
                            image_blocks.append({
                                "label": label,
                                "bbox": bbox,
                                "block_id": block.get('block_id', 0),
                            })
                            continue

                        if content:
                            all_blocks.append({
                                "label": label,
                                "content": content,
                            })

                # 从 res.markdown['markdown_texts'] 提取 Markdown 文本
                md_data = res.markdown
                if md_data and 'markdown_texts' in md_data:
                    md_text = md_data['markdown_texts']
                    if md_text and isinstance(md_text, str) and md_text.strip():
                        markdown_texts.append(md_text.strip())

            # 优先使用 markdown 文本（更完整，含表格格式）
            if markdown_texts:
                full_text = "\n\n---\n\n".join(markdown_texts)
            elif all_blocks:
                # fallback: 从 blocks 拼接
                full_text = "\n\n".join(b["content"] for b in all_blocks)
            else:
                logger.warning(f"OCR 返回空结果，第 {attempt + 1} 次重试...")
                if attempt < max_retries - 1:
                    time.sleep(2)
                continue

            # 裁切图片块并嵌入OCR文本
            cropped_images = []
            if image_blocks and save_dir:
                try:
                    from PIL import Image
                    img = Image.open(image_path)
                    img_w, img_h = img.size
                    images_dir = os.path.join(save_dir, "images")
                    os.makedirs(images_dir, exist_ok=True)
                    stem = Path(image_path).stem

                    for ib in image_blocks:
                        x1, y1, x2, y2 = ib['bbox']
                        # 确保坐标在图片范围内
                        x1, y1 = max(0, int(x1)), max(0, int(y1))
                        x2, y2 = min(img_w, int(x2)), min(img_h, int(y2))
                        if x2 - x1 < 10 or y2 - y1 < 10:
                            continue  # 太小跳过
                        cropped = img.crop((x1, y1, x2, y2))
                        crop_filename = f"{stem}_crop_{ib['label']}_{ib['block_id']}.png"
                        crop_path = os.path.join(images_dir, crop_filename)
                        cropped.save(crop_path)
                        # 相对于 save_dir 的路径，用于URL访问
                        rel_path = os.path.join("images", crop_filename)
                        cropped_images.append({
                            "label": ib['label'],
                            "filename": crop_filename,
                            "path": crop_path,
                            "rel_path": rel_path,
                        })
                        logger.info(f"裁切图片块: {ib['label']} -> {crop_filename}")

                    img.close()
                except ImportError:
                    logger.warning("PIL未安装，无法裁切图片块")
                except Exception as e:
                    logger.warning(f"裁切图片块失败: {e}")

            # 替换 PaddleOCR Markdown 中的 imgs/ 图片引用为实际裁切图URL
            if cropped_images:
                # 从 save_dir 提取 case_id 构建 URL
                # save_dir 格式: .../uploads/{case_id}/ocr_result
                case_id = None
                parts = save_dir.replace('\\', '/').split('/')
                for i, p in enumerate(parts):
                    if p == 'uploads' and i + 1 < len(parts):
                        try:
                            case_id = int(parts[i + 1])
                        except ValueError:
                            pass
                        break

                # 建立 bbox → 裁切图URL 的映射
                bbox_url_map = {}
                for ci in cropped_images:
                    if case_id:
                        url = f"/uploads/{case_id}/ocr_result/{ci['rel_path']}"
                    else:
                        url = ci['rel_path']
                    bbox_url_map[ci['filename']] = url

                # 替换 PaddleOCR 生成的 <img src="imgs/img_in_image_box_x1_y1_x2_y2.jpg"> 引用
                # 这些引用指向不存在的 imgs/ 目录，需要替换为裁切后的实际路径
                import re
                def replace_imgs_src(match):
                    original_src = match.group(1)
                    # 从文件名提取 bbox 坐标: img_in_image_box_620_286_780_528.jpg
                    m = re.search(r'img_in_image_box_(\d+)_(\d+)_(\d+)_(\d+)', original_src)
                    if m:
                        x1, y1, x2, y2 = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
                        # 匹配裁切图文件名中的 bbox 信息
                        stem = Path(image_path).stem
                        target_prefix = f"{stem}_crop_"
                        for ci in cropped_images:
                            # 检查 bbox 是否匹配（允许小范围误差）
                            ci_bbox_match = re.search(r'_(\d+)$', ci['filename'].replace('.png', ''))
                            # 更可靠的匹配：通过文件名中的 block_id 匹配
                            # 直接用坐标在bbox_url_map中查找
                            pass
                        # 直接用坐标构建查找key
                        crop_key = f"{stem}_crop_image_"
                        # 找到最近的bbox匹配
                        for ci in cropped_images:
                            fn = ci['filename']
                            # 提取裁切图文件名中的 bbox
                            fn_match = re.search(r'crop_\w+_(\d+)\.png', fn)
                            if fn_match:
                                # 尝试通过block_id的顺序来匹配
                                pass
                    # 如果无法精确匹配，返回原始 src
                    return match.group(0)

                # 更简单的方法：直接按顺序替换
                # PaddleOCR 的 imgs/ 引用与 image_blocks 的顺序一致
                # 先收集所有 <img src="imgs/..."> 标签
                img_tags = list(re.finditer(r'<img\s+src="imgs/([^"]+)"[^>]*/?\s*>', full_text))
                if img_tags and len(img_tags) == len(cropped_images):
                    # 按位置倒序替换，避免偏移
                    for tag_match, ci in zip(reversed(img_tags), reversed(cropped_images)):
                        if case_id:
                            url = f"/uploads/{case_id}/ocr_result/{ci['rel_path']}"
                        else:
                            url = ci['rel_path']
                        # 用 Markdown 图片语法替换 HTML img 标签
                        replacement = f"![{ci['label']}]({url})"
                        full_text = full_text[:tag_match.start()] + replacement + full_text[tag_match.end():]
                    logger.info(f"替换了 {len(img_tags)} 个 imgs/ 图片引用")
                elif img_tags:
                    # 数量不匹配时，尝试通过 bbox 坐标匹配
                    for tag_match in reversed(img_tags):
                        src = tag_match.group(1)
                        m = re.search(r'(\d+)_(\d+)_(\d+)_(\d+)', src)
                        if m:
                            tag_x1, tag_y1, tag_x2, tag_y2 = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
                            # 在裁切图中查找 bbox 匹配的
                            for ib in image_blocks:
                                bx1, by1, bx2, by2 = ib['bbox']
                                if abs(tag_x1 - bx1) < 10 and abs(tag_y1 - by1) < 10:
                                    # 找到匹配的图片块，查找对应的裁切图
                                    for ci in cropped_images:
                                        if f"_{ib['block_id']}.png" in ci['filename']:
                                            if case_id:
                                                url = f"/uploads/{case_id}/ocr_result/{ci['rel_path']}"
                                            else:
                                                url = ci['rel_path']
                                            replacement = f"![{ci['label']}]({url})"
                                            full_text = full_text[:tag_match.start()] + replacement + full_text[tag_match.end():]
                                            logger.info(f"通过bbox匹配替换图片: {src} -> {url}")
                                            break
                                    break
                    logger.info(f"通过bbox匹配替换了 imgs/ 图片引用")
                else:
                    # 没有找到 imgs/ 引用，在文本前添加裁切图片引用
                    img_refs = []
                    for ci in cropped_images:
                        if case_id:
                            url = f"/uploads/{case_id}/ocr_result/{ci['rel_path']}"
                        else:
                            url = ci['rel_path']
                        img_refs.append(f"\n\n![{ci['label']}]({url})")
                    full_text = "".join(img_refs) + "\n\n---\n\n" + full_text

            # 保存 md 文件到硬盘
            md_path = None
            if save_dir:
                os.makedirs(save_dir, exist_ok=True)
                stem = Path(image_path).stem
                md_path = os.path.join(save_dir, f"{stem}.md")
                with open(md_path, 'w', encoding='utf-8') as f:
                    f.write(full_text)
                logger.info(f"OCR 结果已保存: {md_path}")

            return {
                "success": True,
                "text": full_text,
                "blocks": all_blocks,
                "md_path": md_path,
                "cropped_images": cropped_images,
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
    """从 OCR 结果中提取纯文本"""
    if not ocr_result.get("success"):
        return ""
    return ocr_result.get("text", "")


def batch_ocr(image_paths: List[str], save_dir: str = None) -> List[Dict[str, Any]]:
    """
    批量 OCR 识别（带速率控制）

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


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python ocr.py <图片路径> [保存目录]")
        sys.exit(1)

    image_path = sys.argv[1]
    save_dir = sys.argv[2] if len(sys.argv) > 2 else None

    result = run_ocr(image_path, save_dir=save_dir)
    if result.get("success"):
        text = extract_text_from_result(result)
        print(f"✅ 识别成功，文本长度: {len(text)} 字符")
        print(f"Blocks: {len(result.get('blocks', []))} 个")
        print(text[:500])
        if result.get('md_path'):
            print(f"MD文件: {result['md_path']}")
    else:
        print(f"❌ 识别失败: {result.get('error')}")
