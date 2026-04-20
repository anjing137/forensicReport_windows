"""
案件管理路由
"""
import os
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.models.case import Case, CaseStatus, MaterialType, MaterialGroup, Person, Material, OcrStatus
from app.schemas.case import (
    CaseCreate, CaseUpdate, CaseResponse, CaseListResponse, PersonResponse,
    MaterialGroupResponse
)
# 平台感知 OCR 后端：Windows 用 httpx 轻量版（无需 paddleocr 包），Mac/Linux 用原生版
import sys as _sys
if _sys.platform == "win32":
    from app.utils.oc33r import run_ocr, extract_text_from_result
else:
    from app.utils.ocr import run_ocr, extract_text_from_result
from app.config import settings

router = APIRouter(prefix="/api/cases", tags=["案件管理"])


def get_status_label(status: str) -> str:
    return CaseStatus.LABELS.get(status, status)


def get_material_type_label(material_type: str) -> str:
    return MaterialType.LABELS.get(material_type, material_type)


@router.get("", response_model=List[CaseListResponse])
def list_cases(skip: int = 0, limit: int = 50, status: str = None, db: Session = Depends(get_db)):
    """获取案件列表，支持状态筛选"""
    query = db.query(Case).order_by(Case.created_at.desc())
    if status:
        if status == 'draft':
            # draft = 所有非 completed 状态
            query = query.filter(Case.status != CaseStatus.COMPLETED)
        else:
            query = query.filter(Case.status == status)
    cases = query.offset(skip).limit(limit).all()
    result = []
    for c in cases:
        item = CaseListResponse(
            id=c.id,
            case_number=c.case_number,
            entrusting_unit=c.entrusting_unit,
            status=c.status,
            status_label=get_status_label(c.status),
            person_name=c.person.name if c.person else None,
            created_at=c.created_at,
            updated_at=c.updated_at,
        )
        result.append(item)
    return result


@router.get("/{case_id}", response_model=CaseResponse)
def get_case(case_id: int, db: Session = Depends(get_db)):
    """获取案件详情"""
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    # 构建响应
    person_data = None
    if case.person:
        person_data = PersonResponse(
            id=case.person.id,
            case_id=case.person.case_id,
            name=case.person.name,
            gender=case.person.gender,
            birth_date=case.person.birth_date,
            id_number=case.person.id_number,
            address=case.person.address,
        )

    materials_data = []
    for m in case.materials:
        # Windows 下反斜杠转正斜杠，确保前端 URL 构造函数能匹配 /uploads/
        normalized_path = m.file_path.replace("\\", "/") if m.file_path else None
        materials_data.append({
            "id": m.id,
            "case_id": m.case_id,
            "material_type": m.material_type,
            "material_type_label": get_material_type_label(m.material_type),
            "group_id": m.group_id,
            "description": m.description,
            "page_number": m.page_number,
            "file_path": normalized_path,
            "original_filename": m.original_filename,
            "ocr_text": m.ocr_text,
            "ocr_status": m.ocr_status,
            "created_at": m.created_at,
        })

    material_groups_data = []
    for mg in case.material_groups:
        material_groups_data.append({
            "id": mg.id,
            "case_id": mg.case_id,
            "material_type": mg.material_type,
            "group_name": mg.group_name,
            "sort_order": mg.sort_order,
            "created_at": mg.created_at,
            "materials": [md for md in materials_data if md.get("group_id") == mg.id],
        })

    hospital_records_data = []
    for hr in case.hospital_records:
        hospital_records_data.append({
            "id": hr.id,
            "case_id": hr.case_id,
            "material_id": hr.material_id,
            "hospital_name": hr.hospital_name,
            "admission_number": hr.admission_number,
            "chief_complaint": hr.chief_complaint,
            "present_illness_history": hr.present_illness_history,
            "past_history": hr.past_history,
            "physical_examination": hr.physical_examination,
            "admission_diagnosis": hr.admission_diagnosis,
            "treatment_process": hr.treatment_process,
            "medication": hr.medication,
            "discharge_diagnosis": hr.discharge_diagnosis,
            "discharge_orders": hr.discharge_orders,
            "admission_date": hr.admission_date,
            "discharge_date": hr.discharge_date,
            "hospital_days": hr.hospital_days,
        })

    imaging_reports_data = []
    for ir in case.imaging_reports:
        imaging_reports_data.append({
            "id": ir.id,
            "case_id": ir.case_id,
            "material_id": ir.material_id,
            "report_date": ir.report_date,
            "hospital_name": ir.hospital_name,
            "exam_type": ir.exam_type,
            "exam_part": ir.exam_part,
            "film_number": ir.film_number,
            "film_count": ir.film_count,
            "report_content": ir.report_content,
        })

    report_data = None
    if case.report:
        report_data = {
            "id": case.report.id,
            "case_id": case.report.case_id,
            "case_facts": case.report.case_facts,
            "material_summary": case.report.material_summary,
            "appraisal_process": case.report.appraisal_process,
            "analysis": case.report.analysis,
            "opinion": case.report.opinion,
            "opinion_confirmed": case.report.opinion_confirmed,
            "generated_at": case.report.generated_at,
            "created_at": case.report.created_at,
            "updated_at": case.report.updated_at,
        }

    return CaseResponse(
        id=case.id,
        case_number=case.case_number,
        entrusting_unit=case.entrusting_unit,
        entrustment_matter=case.entrustment_matter,
        acceptance_date=case.acceptance_date,
        appraisal_date=case.appraisal_date,
        appraisal_location=case.appraisal_location,
        on_site_personnel=case.on_site_personnel,
        material_list=case.material_list,
        person_name=case.person_name,
        status=case.status,
        status_label=get_status_label(case.status),
        created_at=case.created_at,
        updated_at=case.updated_at,
        person=person_data,
        materials=materials_data,
        material_groups=material_groups_data,
        hospital_records=hospital_records_data,
        imaging_reports=imaging_reports_data,
        report=report_data,
    )


@router.post("", response_model=CaseResponse)
def create_case(data: CaseCreate, db: Session = Depends(get_db)):
    """创建案件"""
    case = Case(
        case_number=data.case_number,
        status=CaseStatus.PENDING_UPLOAD,
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return get_case(case.id, db)


@router.put("/{case_id}", response_model=CaseResponse)
def update_case(case_id: int, data: CaseUpdate, db: Session = Depends(get_db)):
    """更新案件"""
    import json as _json
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    update_data = data.model_dump(exclude_unset=True)

    # 如果更新了受理日期，自动更新鉴定日期
    if "acceptance_date" in update_data and update_data["acceptance_date"]:
        update_data["appraisal_date"] = update_data["acceptance_date"]

    # 标记用户确认的字段（排除 status 等非用户编辑字段）
    user_editable_fields = {
        "entrusting_unit", "entrustment_matter", "accident_date",
        "accident_location", "accident_description",
        "acceptance_date",
        "appraisal_location", "on_site_personnel", "material_list",
        "person_name", "examination_date", "clinical_examination",
    }
    confirmed = set()
    try:
        confirmed = set(_json.loads(case.confirmed_fields or "[]"))
    except (ValueError, TypeError):
        pass
    for key, value in update_data.items():
        if key in user_editable_fields and value:  # 只有非空值才标记为已确认
            confirmed.add(key)
    case.confirmed_fields = _json.dumps(list(confirmed), ensure_ascii=False)

    for key, value in update_data.items():
        setattr(case, key, value)

    # 如果 person_name 被更新，直接同步
    # 如果没有显式传 person_name 但 Person 关联存在且 name 不为空，也确保同步
    if case.person and case.person.name:
        case.person_name = case.person.name

    db.commit()
    db.refresh(case)
    return get_case(case.id, db)


@router.delete("/{case_id}")
def delete_case(case_id: int, db: Session = Depends(get_db)):
    """删除案件"""
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")
    db.delete(case)
    db.commit()
    return {"message": "删除成功"}


@router.post("/{case_id}/start-recognition")
def start_recognition(case_id: int, db: Session = Depends(get_db)):
    """批量 OCR 识别所有材料（同步执行，硅基流动API每张约3秒）"""
    import traceback as _tb
    try:
        case = db.query(Case).filter(Case.id == case_id).first()
        if not case:
            raise HTTPException(status_code=404, detail="案件不存在")

        if not case.materials:
            raise HTTPException(status_code=400, detail="请先上传材料")

        case.status = CaseStatus.RECOGNIZING
        db.commit()

        save_dir = os.path.join(str(settings.UPLOAD_DIR), str(case_id), "ocr_result")
        results = []

        for mat in case.materials:
            if not mat.file_path or not os.path.exists(mat.file_path):
                mat.ocr_status = OcrStatus.FAILED
                mat.ocr_text = "文件不存在"
                db.commit()
                results.append({"material_id": mat.id, "status": "failed", "error": "文件不存在"})
                continue

            mat.ocr_status = OcrStatus.PROCESSING
            db.commit()

            try:
                result = run_ocr(mat.file_path, save_dir=save_dir)
                text = extract_text_from_result(result)

                if text:
                    mat.ocr_text = text
                    mat.ocr_status = OcrStatus.COMPLETED
                    if result.get("md_path"):
                        mat.ocr_file_path = result["md_path"]
                    results.append({"material_id": mat.id, "filename": mat.original_filename, "status": "completed", "text_length": len(text)})
                else:
                    mat.ocr_text = ""
                    mat.ocr_status = OcrStatus.FAILED
                    results.append({"material_id": mat.id, "filename": mat.original_filename, "status": "failed", "error": result.get("error", "无识别结果")})
            except Exception as e:
                mat.ocr_text = f"OCR错误: {str(e)}"
                mat.ocr_status = OcrStatus.FAILED
                results.append({"material_id": mat.id, "filename": mat.original_filename, "status": "failed", "error": str(e)})

            db.commit()

        # 识别完成，案件状态改为"待修正"
        case.status = CaseStatus.PENDING_REVIEW
        db.commit()

        return {
            "message": f"识别完成，共 {len(results)} 份材料",
            "status": "completed",
            "results": results
        }
    except HTTPException:
        raise
    except Exception as e:
        _tb.print_exc()
        try:
            case = db.query(Case).filter(Case.id == case_id).first()
            if case and case.status == CaseStatus.RECOGNIZING:
                case.status = CaseStatus.PENDING_UPLOAD
                db.commit()
        except:
            pass
        raise HTTPException(status_code=500, detail=f"OCR识别失败: {str(e)}")


@router.post("/{case_id}/recognize-all")
def recognize_all_pending(case_id: int, db: Session = Depends(get_db)):
    """批量 OCR 识别所有待识别材料（不改变案件状态，支持增量识别）"""
    import traceback as _tb
    try:
        case = db.query(Case).filter(Case.id == case_id).first()
        if not case:
            raise HTTPException(status_code=404, detail="案件不存在")

        # 只识别 pending 和 failed 状态的材料
        pending_materials = [m for m in case.materials if m.ocr_status in (OcrStatus.PENDING, OcrStatus.FAILED)]
        if not pending_materials:
            return {"message": "没有待识别的材料", "status": "skipped", "results": []}

        save_dir = os.path.join(str(settings.UPLOAD_DIR), str(case_id), "ocr_result")
        results = []

        for mat in pending_materials:
            if not mat.file_path or not os.path.exists(mat.file_path):
                mat.ocr_status = OcrStatus.FAILED
                mat.ocr_text = "文件不存在"
                db.commit()
                results.append({"material_id": mat.id, "status": "failed", "error": "文件不存在"})
                continue

            mat.ocr_status = OcrStatus.PROCESSING
            db.commit()

            try:
                result = run_ocr(mat.file_path, save_dir=save_dir)
                text = extract_text_from_result(result)

                if text:
                    mat.ocr_text = text
                    mat.ocr_status = OcrStatus.COMPLETED
                    if result.get("md_path"):
                        mat.ocr_file_path = result["md_path"]
                    results.append({"material_id": mat.id, "filename": mat.original_filename, "status": "completed", "text_length": len(text)})
                else:
                    mat.ocr_text = ""
                    mat.ocr_status = OcrStatus.FAILED
                    results.append({"material_id": mat.id, "filename": mat.original_filename, "status": "failed", "error": result.get("error", "无识别结果")})
            except Exception as e:
                mat.ocr_text = f"OCR错误: {str(e)}"
                mat.ocr_status = OcrStatus.FAILED
                results.append({"material_id": mat.id, "filename": mat.original_filename, "status": "failed", "error": str(e)})

            db.commit()

        return {
            "message": f"识别完成，共处理 {len(results)} 份材料",
            "status": "completed",
            "results": results
        }
    except HTTPException:
        raise
    except Exception as e:
        _tb.print_exc()
        raise HTTPException(status_code=500, detail=f"OCR识别失败: {str(e)}")


@router.post("/{case_id}/materials/{material_id}/recognize")
def recognize_single_material(case_id: int, material_id: int, db: Session = Depends(get_db)):
    """单张材料 OCR 识别（同步执行）"""
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    material = db.query(Material).filter(
        Material.id == material_id,
        Material.case_id == case_id
    ).first()
    if not material:
        raise HTTPException(status_code=404, detail="材料不存在")

    if not material.file_path or not os.path.exists(material.file_path):
        raise HTTPException(status_code=400, detail="材料文件不存在")

    save_dir = os.path.join(str(settings.UPLOAD_DIR), str(case_id), "ocr_result")

    try:
        result = run_ocr(material.file_path, save_dir=save_dir)
        text = extract_text_from_result(result)

        if text:
            material.ocr_text = text
            material.ocr_status = OcrStatus.COMPLETED
            if result.get("md_path"):
                material.ocr_file_path = result["md_path"]
            db.commit()
            return {
                "message": f"识别完成: {material.original_filename}",
                "material_id": material_id,
                "status": "completed",
                "text_length": len(text),
                "text_preview": text[:200],
            }
        else:
            material.ocr_text = ""
            material.ocr_status = OcrStatus.FAILED
            db.commit()
            return {
                "message": f"识别失败: {material.original_filename}",
                "material_id": material_id,
                "status": "failed",
                "error": result.get("error", "无识别结果"),
            }
    except Exception as e:
        material.ocr_text = f"OCR错误: {str(e)}"
        material.ocr_status = OcrStatus.FAILED
        db.commit()
        raise HTTPException(status_code=500, detail=f"OCR识别失败: {str(e)}")


@router.post("/{case_id}/submit-review")
def submit_review(case_id: int, db: Session = Depends(get_db)):
    """提交审核（修正中 → 待确认）"""
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    if case.status != CaseStatus.REVIEWING:
        raise HTTPException(status_code=400, detail="当前状态不允许提交审核")

    case.status = CaseStatus.PENDING_CONFIRM
    db.commit()
    return {"message": "已提交审核", "status": case.status}


@router.post("/{case_id}/confirm")
def confirm_case(case_id: int, db: Session = Depends(get_db)):
    """确认完成（任意状态 → 已完成）"""
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    if case.status == CaseStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="案件已完成")

    # 检查鉴定意见是否已确认
    if case.report and not case.report.opinion_confirmed:
        raise HTTPException(status_code=400, detail="鉴定意见尚未确认")

    case.status = CaseStatus.COMPLETED
    db.commit()
    return {"message": "案件已完成", "status": case.status}


@router.post("/{case_id}/reopen")
def reopen_case(case_id: int, db: Session = Depends(get_db)):
    """重新打开（已完成 → 进行中）"""
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    if case.status != CaseStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="当前状态不允许重新打开")

    case.status = CaseStatus.PENDING_UPLOAD
    db.commit()
    return {"message": "案件已重新打开", "status": case.status}
