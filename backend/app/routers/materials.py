"""
材料管理路由 - 支持按类型上传、按医院分组
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
    """创建材料分组（如：新乡市中心医院病历）"""
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
