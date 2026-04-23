"""
材料管理路由 - 支持按类型上传、按医院分组、PDF上传转图片
"""
import os
import shutil
from fastapi import APIRouter, Depends, UploadFile, File, Form, Query, HTTPException, Body
from sqlalchemy.orm import Session
from typing import Optional, List

from app.database import get_db
from app.models.case import Material, MaterialGroup, MaterialType, OcrStatus
from app.schemas.case import (
    MaterialResponse, MaterialGroupResponse, MaterialGroupCreate, MaterialGroupUpdate
)
from app.config import settings

router = APIRouter(prefix="/api/materials", tags=["材料管理"])

UPLOAD_DIR = str(settings.UPLOAD_DIR)
os.makedirs(UPLOAD_DIR, exist_ok=True)


def get_material_type_label(t: str) -> str:
    return MaterialType.LABELS.get(t, t)


def material_to_response(m: Material) -> MaterialResponse:
    """统一转换 Material -> MaterialResponse"""
    # Windows 下 os.path 产生反斜杠，前端 URL 构造依赖 /uploads/ 正斜杠子串
    # 统一将 file_path 转为正斜杠，确保前端 indexOf("/uploads/") 能匹配
    normalized_path = m.file_path.replace("\\", "/") if m.file_path else None
    return MaterialResponse(
        id=m.id,
        case_id=m.case_id,
        material_type=m.material_type,
        material_type_label=get_material_type_label(m.material_type),
        group_id=m.group_id,
        description=m.description,
        page_number=m.page_number,
        file_path=normalized_path,
        original_filename=m.original_filename,
        ocr_text=m.ocr_text,
        ocr_status=m.ocr_status,
        created_at=m.created_at,
    )


def group_to_response(g: MaterialGroup) -> MaterialGroupResponse:
    """统一转换 MaterialGroup -> MaterialGroupResponse"""
    return MaterialGroupResponse(
        id=g.id,
        case_id=g.case_id,
        material_type=g.material_type,
        group_name=g.group_name,
        sort_order=g.sort_order,
        created_at=g.created_at,
        materials=[material_to_response(m) for m in g.materials],
    )


# ==================== 材料分组 API ====================

@router.post("/groups", response_model=MaterialGroupResponse)
def create_group(data: MaterialGroupCreate, db: Session = Depends(get_db)):
    """创建材料分组（如：新乡市中心医院病历）

    如果是病历或影像学报告，会自动创建配对的分组（病历↔影像学报告共用医院组名）
    """
    # 自动计算 sort_order
    max_order = db.query(MaterialGroup).filter(
        MaterialGroup.case_id == data.case_id,
        MaterialGroup.material_type == data.material_type
    ).count()

    group = MaterialGroup(
        case_id=data.case_id,
        material_type=data.material_type,
        group_name=data.group_name,
        sort_order=data.sort_order if data.sort_order else max_order + 1,
    )
    db.add(group)
    db.commit()
    db.refresh(group)

    # 如果是病历或影像学报告，自动创建配对的分组
    paired_type = None
    if data.material_type == MaterialType.MEDICAL_RECORD:
        paired_type = MaterialType.IMAGING_REPORT
    elif data.material_type == MaterialType.IMAGING_REPORT:
        paired_type = MaterialType.MEDICAL_RECORD

    if paired_type:
        # 检查配对分组是否已存在
        existing_pair = db.query(MaterialGroup).filter(
            MaterialGroup.case_id == data.case_id,
            MaterialGroup.material_type == paired_type,
            MaterialGroup.group_name == data.group_name
        ).first()

        if not existing_pair:
            max_order_pair = db.query(MaterialGroup).filter(
                MaterialGroup.case_id == data.case_id,
                MaterialGroup.material_type == paired_type
            ).count()

            paired_group = MaterialGroup(
                case_id=data.case_id,
                material_type=paired_type,
                group_name=data.group_name,
                sort_order=max_order_pair + 1,
            )
            db.add(paired_group)
            db.commit()

    return group_to_response(group)


@router.get("/groups/case/{case_id}", response_model=List[MaterialGroupResponse])
def get_case_groups(case_id: int, material_type: Optional[str] = None, db: Session = Depends(get_db)):
    """获取案件的材料分组"""
    query = db.query(MaterialGroup).filter(MaterialGroup.case_id == case_id)
    if material_type:
        query = query.filter(MaterialGroup.material_type == material_type)
    groups = query.order_by(MaterialGroup.sort_order).all()
    return [group_to_response(g) for g in groups]


@router.put("/groups/{group_id}", response_model=MaterialGroupResponse)
def update_group(group_id: int, data: MaterialGroupUpdate, db: Session = Depends(get_db)):
    """更新分组名称"""
    group = db.query(MaterialGroup).filter(MaterialGroup.id == group_id).first()
    if not group:
        raise HTTPException(404, "分组不存在")
    if data.group_name is not None:
        group.group_name = data.group_name
    if data.sort_order is not None:
        group.sort_order = data.sort_order
    db.commit()
    db.refresh(group)
    return group_to_response(group)


@router.delete("/groups/{group_id}")
def delete_group(group_id: int, db: Session = Depends(get_db)):
    """删除分组及其下所有材料"""
    group = db.query(MaterialGroup).filter(MaterialGroup.id == group_id).first()
    if not group:
        raise HTTPException(404, "分组不存在")

    # 删除组内所有文件
    for m in group.materials:
        if m.file_path and os.path.exists(m.file_path):
            os.remove(m.file_path)

    db.delete(group)
    db.commit()
    return {"ok": True, "message": f"已删除分组「{group.group_name}」及其中 {len(group.materials)} 个文件"}


# ==================== 材料上传 API ====================

@router.post("/upload/{case_id}", response_model=MaterialResponse)
async def upload_material(
    case_id: int,
    file: UploadFile = File(...),
    material_type: str = Form(...),
    group_id: Optional[int] = Form(None),
    description: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """
    上传单个材料文件

    - material_type: 材料类型
    - group_id: 分组ID（病历/影像需要指定医院分组）
    - description: 文件描述（如：正面、第3页）
    """
    if material_type not in MaterialType.ALL:
        raise HTTPException(400, f"无效的材料类型: {material_type}")

    # 保存文件
    case_dir = os.path.join(UPLOAD_DIR, str(case_id))
    os.makedirs(case_dir, exist_ok=True)
    file_path = os.path.join(case_dir, file.filename)
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # 计算 page_number（同一 group 内排序）
    page_number = None
    if group_id:
        existing_count = db.query(Material).filter(
            Material.group_id == group_id
        ).count()
        page_number = existing_count + 1

    # 自动生成 description（如果未提供）
    if not description and group_id:
        description = f"第{page_number}页" if page_number else None

    material = Material(
        case_id=case_id,
        group_id=group_id,
        material_type=material_type,
        description=description,
        page_number=page_number,
        file_path=file_path,
        original_filename=file.filename,
        ocr_status=OcrStatus.PENDING,
    )
    db.add(material)
    db.commit()
    db.refresh(material)
    return material_to_response(material)


@router.post("/upload-batch/{case_id}", response_model=List[MaterialResponse])
async def upload_materials_batch(
    case_id: int,
    files: List[UploadFile] = File(...),
    material_type: str = Form(...),
    group_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    """
    批量上传材料文件（同一类型、同一分组）
    """
    if material_type not in MaterialType.ALL:
        raise HTTPException(400, f"无效的材料类型: {material_type}")

    case_dir = os.path.join(UPLOAD_DIR, str(case_id))
    os.makedirs(case_dir, exist_ok=True)

    # 计算起始页码
    existing_count = 0
    if group_id:
        existing_count = db.query(Material).filter(
            Material.group_id == group_id
        ).count()

    results = []
    for idx, file in enumerate(files):
        file_path = os.path.join(case_dir, file.filename)
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        page_number = (existing_count + idx + 1) if group_id else None
        description = f"第{page_number}页" if group_id and page_number else None

        material = Material(
            case_id=case_id,
            group_id=group_id,
            material_type=material_type,
            description=description,
            page_number=page_number,
            file_path=file_path,
            original_filename=file.filename,
            ocr_status=OcrStatus.PENDING,
        )
        db.add(material)
        results.append(material)

    db.commit()
    for m in results:
        db.refresh(m)

    return [material_to_response(m) for m in results]


# ==================== 材料查询/删除 API ====================

@router.get("/case/{case_id}", response_model=List[MaterialResponse])
def get_case_materials(case_id: int, material_type: Optional[str] = None, db: Session = Depends(get_db)):
    """获取案件材料列表"""
    query = db.query(Material).filter(Material.case_id == case_id)
    if material_type:
        query = query.filter(Material.material_type == material_type)
    materials = query.order_by(Material.id).all()
    return [material_to_response(m) for m in materials]


@router.get("/case/{case_id}/grouped")
def get_case_materials_grouped(case_id: int, db: Session = Depends(get_db)):
    """
    获取案件材料，按类型分组，分组类型内再按 group 分组
    返回结构：{ type: [ { group: {...}, files: [...] } ] }
    """
    result = {}

    for mt in MaterialType.ALL:
        # 获取该类型所有材料
        all_mats = db.query(Material).filter(
            Material.case_id == case_id,
            Material.material_type == mt
        ).all()

        # 获取该类型的分组
        groups = db.query(MaterialGroup).filter(
            MaterialGroup.case_id == case_id,
            MaterialGroup.material_type == mt
        ).order_by(MaterialGroup.sort_order).all()

        if mt in [MaterialType.MEDICAL_RECORD, MaterialType.IMAGING_REPORT]:
            # 分组类型：按 group 组织
            type_data = []
            for g in groups:
                group_mats = [m for m in all_mats if m.group_id == g.id]
                type_data.append({
                    "group": group_to_response(g),
                    "files": [material_to_response(m) for m in sorted(group_mats, key=lambda x: x.page_number or 0)],
                })
            # 没分组的孤儿材料
            orphan_mats = [m for m in all_mats if m.group_id is None]
            if orphan_mats:
                type_data.insert(0, {
                    "group": None,
                    "files": [material_to_response(m) for m in orphan_mats],
                })
            result[mt] = type_data
        else:
            # 非分组类型：直接平铺
            result[mt] = [material_to_response(m) for m in all_mats]

    return result


@router.delete("/{material_id}")
def delete_material(material_id: int, db: Session = Depends(get_db)):
    """删除材料文件"""
    material = db.query(Material).filter(Material.id == material_id).first()
    if not material:
        raise HTTPException(404, "材料不存在")

    if material.file_path and os.path.exists(material.file_path):
        os.remove(material.file_path)

    db.delete(material)
    db.commit()
    return {"ok": True}


@router.put("/{material_id}", response_model=MaterialResponse)
def update_material(material_id: int, description: Optional[str] = None, page_number: Optional[int] = None, db: Session = Depends(get_db)):
    """更新材料信息"""
    material = db.query(Material).filter(Material.id == material_id).first()
    if not material:
        raise HTTPException(404, "材料不存在")
    if description is not None:
        material.description = description
    if page_number is not None:
        material.page_number = page_number
    db.commit()
    db.refresh(material)
    return material_to_response(material)


@router.put("/{material_id}/ocr-text")
def update_ocr_text(material_id: int, data: dict = Body(...), db: Session = Depends(get_db)):
    """更新 OCR 识别文本"""
    material = db.query(Material).filter(Material.id == material_id).first()
    if not material:
        raise HTTPException(404, "材料不存在")
    material.ocr_text = data.get("ocr_text", "")
    material.ocr_status = OcrStatus.COMPLETED
    db.commit()
    return {"ok": True}


# ==================== PDF 转换 API ====================

@router.post("/upload-pdf/{case_id}")
async def upload_and_convert_pdf(
    case_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    上传 PDF 文件并转换为 PNG 图片
    - 保存 PDF 文件
    - 调用 PyMuPDF (fitz) 转换为 PNG
    - 返回转换后的页面列表
    """
    from app.utils.pdf_converter import PdfConverter

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "只支持 PDF 文件")

    # 保存 PDF 文件
    case_dir = os.path.join(UPLOAD_DIR, str(case_id))
    os.makedirs(case_dir, exist_ok=True)

    pdf_filename = file.filename
    pdf_path = os.path.join(case_dir, pdf_filename)

    with open(pdf_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # 转换为 PNG
    converter = PdfConverter(case_id)
    success, pages, error_msg = converter.convert(pdf_path, original_filename=pdf_filename)

    if not success:
        # 清理上传的 PDF
        if os.path.exists(pdf_path):
            os.remove(pdf_path)
        raise HTTPException(500, f"PDF 转换失败: {error_msg}")

    # 统一 file_path 中的斜杠方向
    for p in pages:
        if p.get("filepath"):
            p["filepath"] = p["filepath"].replace("\\", "/")

    return {
        "pdf_filename": pdf_filename,
        "pdf_path": pdf_path.replace("\\", "/"),
        "pages": pages,
        "total_pages": len(pages)
    }


@router.get("/case/{case_id}/pdf-pages")
def get_pdf_pages(case_id: int, db: Session = Depends(get_db)):
    """
    获取案件的所有 PDF 转换页面（未导入的）
    同时返回已导入的页面信息（来自 Material 表）
    """
    from app.utils.pdf_converter import PdfConverter

    converter = PdfConverter(case_id)
    all_pages = converter.list_pages()

    # 统一斜杠方向
    for p in all_pages:
        if p.get("filepath"):
            p["filepath"] = p["filepath"].replace("\\", "/")

    # 查找已导入到 Material 的页面
    existing_materials = db.query(Material).filter(
        Material.case_id == case_id,
        Material.file_path.like(f"%pdf_pages/%")
    ).all()

    imported_filenames = {m.original_filename: m for m in existing_materials}

    result = []
    for p in all_pages:
        filename = p["filename"]
        material_info = imported_filenames.get(filename)

        if material_info:
            result.append({
                **p,
                "imported": True,
                "material_id": material_info.id,
                "material_type": material_info.material_type,
                "material_type_label": get_material_type_label(material_info.material_type),
                "group_id": material_info.group_id,
                "description": material_info.description,
            })
        else:
            result.append({
                **p,
                "imported": False,
                "material_id": None,
                "material_type": None,
                "material_type_label": None,
                "group_id": None,
                "description": None,
            })

    return result


@router.delete("/pdf-page/{case_id}/{filename}")
def delete_pdf_page(case_id: int, filename: str, db: Session = Depends(get_db)):
    """删除 PDF 转换后的单个页面文件"""
    from app.utils.pdf_converter import PdfConverter

    # 检查是否有已导入的 Material
    existing = db.query(Material).filter(
        Material.case_id == case_id,
        Material.file_path.like(f"%pdf_pages/{filename}")
    ).first()

    if existing:
        raise HTTPException(400, "该页面已导入材料，请先撤销导入后再删除")

    converter = PdfConverter(case_id)
    success, msg = converter.delete_page(filename)

    if not success:
        raise HTTPException(404, msg)

    return {"ok": True, "message": msg}


@router.delete("/pdf/{case_id}/{prefix}")
def delete_pdf_all(case_id: int, prefix: str, db: Session = Depends(get_db)):
    """
    删除整个 PDF 的所有转换页面文件
    - prefix: PDF 文件名前缀（如 case123_abc）
    - 同时删除原始 PDF 文件（如果存在）
    """
    from app.utils.pdf_converter import PdfConverter

    converter = PdfConverter(case_id)

    # 删除所有转换的页面文件
    deleted_count = 0
    for f in os.listdir(converter.output_dir):
        if f.startswith(prefix) and (f.endswith(".png") or f.endswith(".jpg")):
            filepath = os.path.join(converter.output_dir, f)
            if os.path.isfile(filepath):
                os.remove(filepath)
                deleted_count += 1

    # 删除原始 PDF 文件（如果存在）
    pdf_file = os.path.join(UPLOAD_DIR, str(case_id), prefix + ".pdf")
    original_pdf_deleted = False
    if os.path.exists(pdf_file):
        os.remove(pdf_file)
        original_pdf_deleted = True

    return {
        "ok": True,
        "message": f"已删除 PDF {prefix} 的 {deleted_count} 个页面文件" + (" 和原始 PDF 文件" if original_pdf_deleted else ""),
        "deleted_pages": deleted_count,
        "deleted_original_pdf": original_pdf_deleted
    }


@router.post("/import-pdf-pages/{case_id}")
def import_pdf_pages(
    case_id: int,
    filenames: List[str] = Body(...),
    material_type: str = Body(...),
    group_id: int = Body(None),
    group_name: str = Body(None),  # 可选：同时创建新分组
    db: Session = Depends(get_db),
):
    """
    将 PDF 转换页面导入为材料

    - filenames: 要导入的页面文件名列表
    - material_type: 材料类型
    - group_id: 分组ID（病历/影像需要）
    - group_name: 如果没有 group_id，可以传这个来创建新分组
    """
    from app.utils.pdf_converter import PdfConverter

    if material_type not in MaterialType.ALL:
        raise HTTPException(400, f"无效的材料类型: {material_type}")

    # 如果需要分组但没有 group_id，先创建分组
    if group_id is None and group_name and material_type in [MaterialType.MEDICAL_RECORD, MaterialType.IMAGING_REPORT]:
        # 检查是否已存在同名分组
        existing = db.query(MaterialGroup).filter(
            MaterialGroup.case_id == case_id,
            MaterialGroup.material_type == material_type,
            MaterialGroup.group_name == group_name
        ).first()

        if existing:
            group_id = existing.id
        else:
            max_order = db.query(MaterialGroup).filter(
                MaterialGroup.case_id == case_id,
                MaterialGroup.material_type == material_type
            ).count()

            new_group = MaterialGroup(
                case_id=case_id,
                material_type=material_type,
                group_name=group_name,
                sort_order=max_order + 1,
            )
            db.add(new_group)
            db.commit()
            db.refresh(new_group)
            group_id = new_group.id

            # 自动创建配对分组
            paired_type = None
            if material_type == MaterialType.MEDICAL_RECORD:
                paired_type = MaterialType.IMAGING_REPORT
            elif material_type == MaterialType.IMAGING_REPORT:
                paired_type = MaterialType.MEDICAL_RECORD

            if paired_type:
                existing_pair = db.query(MaterialGroup).filter(
                    MaterialGroup.case_id == case_id,
                    MaterialGroup.material_type == paired_type,
                    MaterialGroup.group_name == group_name
                ).first()
                if not existing_pair:
                    max_order_pair = db.query(MaterialGroup).filter(
                        MaterialGroup.case_id == case_id,
                        MaterialGroup.material_type == paired_type
                    ).count()
                    paired_group = MaterialGroup(
                        case_id=case_id,
                        material_type=paired_type,
                        group_name=group_name,
                        sort_order=max_order_pair + 1,
                    )
                    db.add(paired_group)
                    db.commit()

    converter = PdfConverter(case_id)
    results = []

    # 计算起始页码
    existing_count = 0
    if group_id:
        existing_count = db.query(Material).filter(Material.group_id == group_id).count()

    for idx, filename in enumerate(filenames):
        page_path = os.path.join(converter.output_dir, filename)

        if not os.path.exists(page_path):
            results.append({"filename": filename, "success": False, "error": f"文件不存在: {page_path}"})
            continue

        page_number = (existing_count + idx + 1) if group_id else None

        # 检查是否已导入
        existing = db.query(Material).filter(
            Material.case_id == case_id,
            Material.file_path.like(f"%pdf_pages/{filename}")
        ).first()

        if existing:
            results.append({"filename": filename, "success": False, "error": "该页面已导入"})
            continue

        try:
            material = Material(
                case_id=case_id,
                group_id=group_id,
                material_type=material_type,
                description=filename,  # 存储文件名作为描述
                page_number=page_number,
                file_path=page_path,
                original_filename=filename,
                ocr_status=OcrStatus.PENDING,
            )
            db.add(material)
            db.flush()
            results.append({
                "filename": filename,
                "success": True,
                "material": material_to_response(material)
            })
        except Exception as e:
            db.rollback()
            results.append({"filename": filename, "success": False, "error": f"数据库错误: {str(e)}"})

    db.commit()

    return {
        "imported": [r for r in results if r["success"]],
        "failed": [r for r in results if not r["success"]],
        "group_id": group_id,
    }


@router.post("/revert-import/{case_id}/{filename}")
def revert_pdf_import(case_id: int, filename: str, db: Session = Depends(get_db)):
    """
    撤销 PDF 页面的导入（删除 Material 记录，保留文件）
    """
    material = db.query(Material).filter(
        Material.case_id == case_id,
        Material.file_path.like(f"%pdf_pages/{filename}")
    ).first()

    if not material:
        raise HTTPException(404, "未找到该导入记录")

    material_id = material.id
    db.delete(material)
    db.commit()

    return {"ok": True, "material_id": material_id, "message": "已撤销导入，文件保留"}
