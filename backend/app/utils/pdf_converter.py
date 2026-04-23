"""
PDF 转换工具 - 使用 PyMuPDF (fitz) 将 PDF 分割为 PNG 图片
Windows 兼容版：无需安装 poppler/pdftoppm，纯 Python 实现
"""
import os
import uuid
import json
import re
from pathlib import Path
from typing import List, Tuple, Optional

from app.config import settings


class PdfConverter:
    """PDF 转 PNG 转换器，使用 PyMuPDF (fitz)"""

    def __init__(self, case_id: int):
        self.case_id = case_id
        # 转换结果存放目录
        self.output_dir = os.path.join(settings.UPLOAD_DIR, str(case_id), "pdf_pages")
        os.makedirs(self.output_dir, exist_ok=True)

    def convert(self, pdf_path: str, original_filename: str = None) -> Tuple[bool, List[dict], str]:
        """
        将 PDF 转换为 PNG 图片

        Args:
            pdf_path: PDF 文件的绝对路径
            original_filename: 原始 PDF 文件名（用于返回给前端展示）

        Returns:
            (success, pages, error_message)
            pages: [{page_number: 1, filename: "page-01.png", original_filename: "原始文件名"}, ...]
        """
        if not os.path.exists(pdf_path):
            return False, [], f"PDF 文件不存在: {pdf_path}"

        try:
            import fitz  # PyMuPDF
        except ImportError:
            return False, [], "PyMuPDF 未安装，请运行: pip install PyMuPDF"

        # 生成输出文件名前缀
        prefix = f"case{self.case_id}_{uuid.uuid4().hex[:8]}"
        # 保存原始 PDF 文件名用于返回
        self._original_pdf_filename = original_filename or os.path.basename(pdf_path)
        # 保存元数据（原始 PDF 文件名）到同名 .json 文件
        meta_path = os.path.join(self.output_dir, prefix + "_meta.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump({"original_pdf_filename": self._original_pdf_filename}, f)

        try:
            doc = fitz.open(pdf_path)
            generated_files = []

            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                # 150 DPI → zoom = 150/72 ≈ 2.08
                zoom = 2.0
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat)

                # 文件名格式与 Mac 版 pdftoppm 保持一致: prefix-N.png
                output_filename = f"{prefix}-{page_num + 1}.png"
                output_path = os.path.join(self.output_dir, output_filename)
                pix.save(output_path)

                generated_files.append({
                    "page_number": page_num + 1,
                    "filename": output_filename,
                    "original_pdf_filename": self._original_pdf_filename,
                    "filepath": output_path,
                    "url": f"/uploads/{self.case_id}/pdf_pages/{output_filename}",
                })

            doc.close()

            # 按页码排序
            generated_files.sort(key=lambda x: x["page_number"])

            return True, generated_files, ""

        except Exception as e:
            return False, [], f"转换异常: {str(e)}"

    def delete_page(self, filename: str) -> Tuple[bool, str]:
        """删除指定的转换页面文件"""
        filepath = os.path.join(self.output_dir, filename)
        if os.path.exists(filepath):
            os.remove(filepath)
            return True, "删除成功"
        return False, "文件不存在"

    def delete_all(self) -> int:
        """删除所有转换页面，返回删除数量"""
        count = 0
        for f in os.listdir(self.output_dir):
            filepath = os.path.join(self.output_dir, f)
            if os.path.isfile(filepath):
                os.remove(filepath)
                count += 1
        return count

    def list_pages(self) -> List[dict]:
        """列出所有转换页面"""
        pages = []
        for f in sorted(os.listdir(self.output_dir)):
            if f.endswith(".png") or f.endswith(".jpg"):
                # 提取前缀
                match = re.match(r"^(case\d+_\w+)-\d+\.png$", f)
                if not match:
                    continue
                prefix = match.group(1)
                # 读取元数据获取原始 PDF 文件名
                meta_path = os.path.join(self.output_dir, prefix + "_meta.json")
                original_pdf_filename = prefix + ".pdf"  # 默认值
                if os.path.exists(meta_path):
                    try:
                        with open(meta_path, "r", encoding="utf-8") as mf:
                            meta = json.load(mf)
                            original_pdf_filename = meta.get("original_pdf_filename", original_pdf_filename)
                    except:
                        pass
                filepath = os.path.join(self.output_dir, f)
                pages.append({
                    "filename": f,
                    "original_pdf_filename": original_pdf_filename,
                    "filepath": filepath,
                    "url": f"/uploads/{self.case_id}/pdf_pages/{f}",
                    "size": os.path.getsize(filepath)
                })
        return pages


def convert_pdf(pdf_path: str, case_id: int) -> Tuple[bool, List[dict], str]:
    """便捷函数：转换单个 PDF"""
    converter = PdfConverter(case_id)
    return converter.convert(pdf_path)
