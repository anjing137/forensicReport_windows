"""
LLM 智能提取路由
OCR 识别完成后，调用 LLM 从 OCR 文本中提取结构化字段
"""
import json
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models.case import (
    Case, CaseStatus, Material, MaterialGroup, MaterialType, OcrStatus,
    Person, HospitalRecord, ImagingReport, Report,
)
from app.utils.llm import extract_fields, extract_case_summary, call_llm, extract_medical_group_fields

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/llm", tags=["LLM 智能提取"])


# ==================== 用户确认字段保护机制 ====================

def _get_confirmed_fields(obj) -> set:
    """获取对象的已确认字段集合"""
    if not obj or not hasattr(obj, 'confirmed_fields') or not obj.confirmed_fields:
        return set()
    try:
        return set(json.loads(obj.confirmed_fields))
    except (json.JSONDecodeError, TypeError):
        return set()


def _mark_fields_confirmed(obj, field_names: list):
    """标记字段为已确认（用户手动保存时调用）"""
    confirmed = _get_confirmed_fields(obj)
    confirmed.update(field_names)
    obj.confirmed_fields = json.dumps(list(confirmed), ensure_ascii=False)


def _safe_setattr(obj, field_name: str, value, confirmed_fields: set = None):
    """安全设置属性：如果字段已确认，则不覆盖"""
    if confirmed_fields is None:
        confirmed_fields = _get_confirmed_fields(obj)
    if field_name in confirmed_fields:
        return False  # 字段已确认，跳过
    if value is not None and value != "":
        setattr(obj, field_name, value)
        return True
    return False


def _write_report_field(report, field_name: str, value) -> bool:
    """安全写入报告字段：如果用户已手动保存确认过该字段，则不覆盖，返回是否写入成功"""
    if _safe_setattr(report, field_name, value):
        return True
    logger.info(f"报告字段 {field_name} 已被用户确认，跳过 LLM 生成覆盖")
    return False


@router.post("/cases/{case_id}/extract-all")
def extract_all_materials(case_id: int, db: Session = Depends(get_db)):
    """
    对案件所有已 OCR 识别的材料进行 LLM 字段提取
    提取结果写入对应的数据库表（Person, HospitalRecord, ImagingReport 等）
    """
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    # 获取所有已完成 OCR 的材料
    materials = db.query(Material).filter(
        Material.case_id == case_id,
        Material.ocr_status == OcrStatus.COMPLETED,
        Material.ocr_text.isnot(None),
        Material.ocr_text != "",
    ).all()

    if not materials:
        raise HTTPException(status_code=400, detail="没有已识别的材料，请先进行 OCR 识别")

    results = []

    for mat in materials:
        try:
            result = _extract_and_save(material=mat, case=case, db=db)
            results.append(result)
        except Exception as e:
            logger.error(f"材料 {mat.id} 提取失败: {str(e)}")
            results.append({
                "material_id": mat.id,
                "filename": mat.original_filename,
                "material_type": mat.material_type,
                "status": "failed",
                "error": str(e),
            })

    # 统计
    success_count = sum(1 for r in results if r.get("status") == "completed")
    failed_count = sum(1 for r in results if r.get("status") == "failed")

    return {
        "message": f"提取完成：成功 {success_count} 份，失败 {failed_count} 份",
        "total": len(results),
        "success": success_count,
        "failed": failed_count,
        "results": results,
    }


@router.post("/materials/{material_id}/extract")
def extract_single_material(material_id: int, db: Session = Depends(get_db)):
    """对单份材料进行 LLM 字段提取"""
    material = db.query(Material).filter(Material.id == material_id).first()
    if not material:
        raise HTTPException(status_code=404, detail="材料不存在")

    if material.ocr_status != OcrStatus.COMPLETED or not material.ocr_text:
        raise HTTPException(status_code=400, detail="材料尚未完成 OCR 识别")

    case = db.query(Case).filter(Case.id == material.case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="关联案件不存在")

    try:
        result = _extract_and_save(material=material, case=case, db=db)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM 提取失败: {str(e)}")


@router.post("/cases/{case_id}/extract-basic-info")
def extract_basic_info(case_id: int, db: Session = Depends(get_db)):
    """
    只提取「基本情况」页面相关字段：
    - 从委托书提取：委托单位、委托事项（唯一来源，不做化简）
    - 从身份证提取：被鉴定人姓名、性别、出生日期、身份证号、住址
    - 从鉴定申请书提取：委托单位（补充，委托书优先）、申请人、案件简介
    """
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    # 收集相关材料
    target_types = [MaterialType.ENTRUSTMENT_LETTER, MaterialType.ID_CARD, MaterialType.APPRAISAL_APPLICATION]
    materials = db.query(Material).filter(
        Material.case_id == case_id,
        Material.ocr_status == OcrStatus.COMPLETED,
        Material.ocr_text.isnot(None),
        Material.ocr_text != "",
        Material.material_type.in_(target_types),
    ).all()

    if not materials:
        raise HTTPException(status_code=400, detail="没有已识别的委托书/身份证/鉴定申请书材料")

    results = []
    for mat in materials:
        try:
            result = _extract_and_save(material=mat, case=case, db=db)
            results.append(result)
        except Exception as e:
            logger.error(f"材料 {mat.id} 提取失败: {str(e)}")
            results.append({"material_id": mat.id, "status": "failed", "error": str(e)})

    # 自动生成材料清单
    _generate_material_list(case_id, case, db)

    # 重新加载案件和人员数据返回
    db.refresh(case)
    person = db.query(Person).filter(Person.case_id == case_id).first()

    success_count = sum(1 for r in results if r.get("status") == "completed")

    return {
        "message": f"基本情况提取完成，成功 {success_count}/{len(results)} 份",
        "results": results,
        "case": {
            "entrusting_unit": case.entrusting_unit,
            "entrustment_matter": case.entrustment_matter,
            "material_list": case.material_list,
        },
        "person": {
            "name": person.name if person else None,
            "gender": person.gender if person else None,
            "birth_date": person.birth_date if person else None,
            "id_number": person.id_number if person else None,
            "address": person.address if person else None,
        } if person else None,
    }


@router.post("/cases/{case_id}/extract-case-facts")
def extract_case_facts_api(case_id: int, db: Session = Depends(get_db)):
    """
    只提取「基本案情」：
    - 从委托书/交通事故认定书/鉴定申请书生成 case_facts 文本
    """
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    # 收集相关材料（委托书、交通事故认定书、鉴定申请书）
    target_types = [MaterialType.ENTRUSTMENT_LETTER, MaterialType.TRAFFIC_ACCIDENT_CERT, MaterialType.APPRAISAL_APPLICATION]
    materials = db.query(Material).filter(
        Material.case_id == case_id,
        Material.ocr_status == OcrStatus.COMPLETED,
        Material.ocr_text.isnot(None),
        Material.ocr_text != "",
        Material.material_type.in_(target_types),
    ).all()

    if not materials:
        raise HTTPException(status_code=400, detail="没有已识别的委托书/交通事故认定书/鉴定申请书材料")

    # 先提取各材料的结构化字段（确保委托书等的基本信息已入库）
    for mat in materials:
        try:
            _extract_and_save(material=mat, case=case, db=db)
        except Exception as e:
            logger.error(f"材料 {mat.id} 提取失败: {str(e)}")

    # 然后生成基本案情文本
    result = extract_case_facts_text(case_id, db)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "生成失败"))

    # 写入报告（已确认字段不覆盖）
    report = db.query(Report).filter(Report.case_id == case_id).first()
    if not report:
        report = Report(case_id=case_id)
        db.add(report)
        db.flush()

    overwritten = _write_report_field(report, "case_facts", result["case_facts"])
    db.commit()
    db.refresh(report)

    msg = "基本案情已生成" if overwritten else "基本案情已生成（您手动修改的内容已保留，未覆盖）"
    return {
        "message": msg,
        "case_facts": result["case_facts"],
        "model": result.get("model", ""),
    }


@router.get("/cases/{case_id}/medical-groups")
def get_medical_groups(case_id: int, db: Session = Depends(get_db)):
    """
    获取案件的病历医院分组信息（用于前端展示提取按钮）
    不调用LLM，纯数据库查询，瞬间返回
    """
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    # 查找所有病历类型的 MaterialGroup
    groups = db.query(MaterialGroup).filter(
        MaterialGroup.case_id == case_id,
        MaterialGroup.material_type == MaterialType.MEDICAL_RECORD,
    ).order_by(MaterialGroup.sort_order).all()

    if not groups:
        # 没有分组，看看是否有未分组的病历材料
        ungrouped = db.query(Material).filter(
            Material.case_id == case_id,
            Material.material_type == MaterialType.MEDICAL_RECORD,
            Material.group_id.is_(None),
        ).count()
        if ungrouped > 0:
            return {
                "groups": [{
                    "group_id": None,
                    "group_name": "未分组的病历",
                    "material_count": ungrouped,
                    "completed_count": db.query(Material).filter(
                        Material.case_id == case_id,
                        Material.material_type == MaterialType.MEDICAL_RECORD,
                        Material.group_id.is_(None),
                        Material.ocr_status == OcrStatus.COMPLETED,
                    ).count(),
                }],
                "total_groups": 1,
            }
        return {"groups": [], "total_groups": 0}

    result_groups = []
    for g in groups:
        all_mats = db.query(Material).filter(
            Material.group_id == g.id,
        ).all()
        completed_mats = [m for m in all_mats if m.ocr_status == OcrStatus.COMPLETED and m.ocr_text]

        # 检查是否已有住院记录（按 group_id 精确匹配）
        existing_record = db.query(HospitalRecord).filter(
            HospitalRecord.case_id == case_id,
            HospitalRecord.group_id == g.id,
        ).first()

        result_groups.append({
            "group_id": g.id,
            "group_name": g.group_name,
            "material_count": len(all_mats),
            "completed_count": len(completed_mats),
            "has_record": existing_record is not None,
            "record_id": existing_record.id if existing_record else None,
        })

    return {
        "groups": result_groups,
        "total_groups": len(result_groups),
    }


@router.post("/cases/{case_id}/extract-medical-group/{group_id}")
def extract_medical_group(case_id: int, group_id: int, db: Session = Depends(get_db)):
    """
    按医院分组提取病历：同一医院的所有页面OCR文本拼接，一次LLM调用生成一条完整住院记录
    """
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    group = db.query(MaterialGroup).filter(
        MaterialGroup.id == group_id,
        MaterialGroup.case_id == case_id,
    ).first()
    if not group:
        raise HTTPException(status_code=404, detail="分组不存在")

    # 获取该分组下所有已完成OCR的材料，按页码排序
    materials = db.query(Material).filter(
        Material.group_id == group_id,
        Material.ocr_status == OcrStatus.COMPLETED,
        Material.ocr_text.isnot(None),
        Material.ocr_text != "",
    ).order_by(Material.page_number, Material.id).all()

    if not materials:
        raise HTTPException(status_code=400, detail=f"{group.group_name} 没有已识别的病历材料")

    # 拼接OCR文本
    combined_text = ""
    for i, mat in enumerate(materials, 1):
        combined_text += f"\n\n===== 第{i}页 ({mat.original_filename}) =====\n"
        combined_text += mat.ocr_text or ""

    combined_text = combined_text.strip()

    # 限制总长度（Qwen3-8B上下文约32K，输入留12K字符安全）
    if len(combined_text) > 12000:
        combined_text = combined_text[:12000] + "\n\n[... 文本过长，已截断 ...]"

    # 调用LLM提取（用新的合并提取Prompt）
    result = _extract_medical_group_llm(group.group_name, combined_text)

    if not result.get("success"):
        return {
            "group_id": group_id,
            "group_name": group.group_name,
            "status": "failed",
            "error": result.get("error", "提取失败"),
        }

    fields = result["fields"]

    # 按 group_id 查找是否已有记录（同一group重新生成时覆盖）
    existing_record = db.query(HospitalRecord).filter(
        HospitalRecord.case_id == case.id,
        HospitalRecord.group_id == group.id,
    ).first()

    if existing_record:
        record = existing_record
        logger.info(f"重新生成住院记录: {group.group_name} group_id={group.id}, record_id={record.id}")
    else:
        record = HospitalRecord(case_id=case.id, group_id=group.id)
        db.add(record)
        db.flush()
        logger.info(f"新建住院记录: {group.group_name} group_id={group.id}, record_id={record.id}")

    # 更新字段（只更新有值的，空值不覆盖已有数据）
    field_map = {
        "hospital_name": "hospital_name",
        "admission_number": "admission_number",
        "chief_complaint": "chief_complaint",
        "present_illness_history": "present_illness_history",
        "past_history": "past_history",
        "physical_examination": "physical_examination",
        "admission_diagnosis": "admission_diagnosis",
        "treatment_process": "treatment_process",
        "medication": "medication",
        "discharge_diagnosis": "discharge_diagnosis",
        "discharge_orders": "discharge_orders",
        "admission_date": "admission_date",
        "discharge_date": "discharge_date",
    }

    for json_key, db_key in field_map.items():
        value = fields.get(json_key)
        if value is not None and value != "" and value != "null":
            setattr(record, db_key, value)

    # 住院天数
    if fields.get("hospital_days") is not None:
        try:
            record.hospital_days = int(fields["hospital_days"])
        except (ValueError, TypeError):
            pass

    db.commit()
    db.refresh(record)

    # 更新材料清单
    _generate_material_list(case_id, case, db)

    return {
        "group_id": group_id,
        "group_name": group.group_name,
        "status": "completed",
        "record_id": record.id,
        "hospital_name": record.hospital_name,
        "admission_number": record.admission_number,
        "fields": fields,
        "model": result.get("model", ""),
        "usage": result.get("usage", {}),
    }


@router.post("/cases/{case_id}/extract-medical-records")
def extract_medical_records_api(case_id: int, db: Session = Depends(get_db)):
    """
    一键提取所有医院的病历（逐个分组调用，每个医院一次LLM）
    """
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    # 获取所有病历分组
    groups = db.query(MaterialGroup).filter(
        MaterialGroup.case_id == case_id,
        MaterialGroup.material_type == MaterialType.MEDICAL_RECORD,
    ).order_by(MaterialGroup.sort_order).all()

    if not groups:
        raise HTTPException(status_code=400, detail="没有病历分组，请先上传病历材料")

    results = []
    for group in groups:
        # 获取该分组下已OCR的材料
        materials = db.query(Material).filter(
            Material.group_id == group.id,
            Material.ocr_status == OcrStatus.COMPLETED,
            Material.ocr_text.isnot(None),
            Material.ocr_text != "",
        ).order_by(Material.page_number, Material.id).all()

        if not materials:
            results.append({
                "group_id": group.id,
                "group_name": group.group_name,
                "status": "skipped",
                "error": "没有已识别的材料",
            })
            continue

        # 拼接OCR文本
        combined_text = ""
        for i, mat in enumerate(materials, 1):
            combined_text += f"\n\n===== 第{i}页 ({mat.original_filename}) =====\n"
            combined_text += mat.ocr_text or ""

        combined_text = combined_text.strip()
        if len(combined_text) > 12000:
            combined_text = combined_text[:12000] + "\n\n[... 文本过长，已截断 ...]"

        # 调用LLM
        result = _extract_medical_group_llm(group.group_name, combined_text)

        if not result.get("success"):
            results.append({
                "group_id": group.id,
                "group_name": group.group_name,
                "status": "failed",
                "error": result.get("error", "提取失败"),
            })
            continue

        fields = result["fields"]

        # 按 group_id 查找是否已有记录（重新生成时覆盖，否则新建）
        existing_record = db.query(HospitalRecord).filter(
            HospitalRecord.case_id == case.id,
            HospitalRecord.group_id == group.id,
        ).first()

        if existing_record:
            record = existing_record
            logger.info(f"重新生成住院记录: {group.group_name} group_id={group.id}, record_id={record.id}")
        else:
            record = HospitalRecord(case_id=case.id, group_id=group.id)
            db.add(record)
            db.flush()
            logger.info(f"新建住院记录: {group.group_name} group_id={group.id}, record_id={record.id}")

        field_map = {
            "hospital_name": "hospital_name",
            "admission_number": "admission_number",
            "chief_complaint": "chief_complaint",
            "present_illness_history": "present_illness_history",
            "past_history": "past_history",
            "physical_examination": "physical_examination",
            "admission_diagnosis": "admission_diagnosis",
            "treatment_process": "treatment_process",
            "medication": "medication",
            "discharge_diagnosis": "discharge_diagnosis",
            "discharge_orders": "discharge_orders",
            "admission_date": "admission_date",
            "discharge_date": "discharge_date",
        }

        for json_key, db_key in field_map.items():
            value = fields.get(json_key)
            if value is not None and value != "" and value != "null":
                setattr(record, db_key, value)

        if fields.get("hospital_days") is not None:
            try:
                record.hospital_days = int(fields["hospital_days"])
            except (ValueError, TypeError):
                pass

        db.commit()

        results.append({
            "group_id": group.id,
            "group_name": group.group_name,
            "status": "completed",
            "record_id": record.id,
            "hospital_name": record.hospital_name,
        })

    # 生成资料摘要
    summary_result = _generate_material_summary(case_id, db)
    if summary_result.get("success"):
        report = db.query(Report).filter(Report.case_id == case_id).first()
        if not report:
            report = Report(case_id=case_id)
            db.add(report)
            db.flush()
        _write_report_field(report, "material_summary", summary_result["material_summary"])
        db.commit()

    # 更新材料清单
    _generate_material_list(case_id, case, db)

    # 重新加载住院记录
    records = db.query(HospitalRecord).filter(HospitalRecord.case_id == case_id).all()

    success_count = sum(1 for r in results if r.get("status") == "completed")

    return {
        "message": f"病历提取完成，成功 {success_count}/{len(results)} 家医院",
        "results": results,
        "material_summary": summary_result.get("material_summary", ""),
        "hospital_records": [
            {
                "id": r.id,
                "hospital_name": r.hospital_name,
                "admission_number": r.admission_number,
                "chief_complaint": r.chief_complaint,
                "present_illness_history": r.present_illness_history,
                "past_history": r.past_history,
                "physical_examination": r.physical_examination,
                "admission_diagnosis": r.admission_diagnosis,
                "treatment_process": r.treatment_process,
                "medication": r.medication,
                "discharge_diagnosis": r.discharge_diagnosis,
                "discharge_orders": r.discharge_orders,
                "admission_date": r.admission_date,
                "discharge_date": r.discharge_date,
                "hospital_days": r.hospital_days,
            }
            for r in records
        ],
    }


@router.post("/cases/{case_id}/extract-imaging-reports")
def extract_imaging_reports_api(case_id: int, db: Session = Depends(get_db)):
    """
    只提取影像学报告数据到 ImagingReport 表：
    - 从影像学报告材料调用 LLM 提取各字段
    - 不自动生成鉴定过程，用户需手动点击「生成鉴定过程」
    """
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    # 收集影像学材料
    materials = db.query(Material).filter(
        Material.case_id == case_id,
        Material.ocr_status == OcrStatus.COMPLETED,
        Material.ocr_text.isnot(None),
        Material.ocr_text != "",
        Material.material_type == MaterialType.IMAGING_REPORT,
    ).all()

    if not materials:
        raise HTTPException(status_code=400, detail="没有已识别的影像学报告材料")

    results = []
    for mat in materials:
        try:
            result = _extract_and_save(material=mat, case=case, db=db)
            results.append(result)
        except Exception as e:
            logger.error(f"材料 {mat.id} 提取失败: {str(e)}")
            results.append({"material_id": mat.id, "status": "failed", "error": str(e)})

    # 更新材料清单（可能有新的影像报告）
    _generate_material_list(case_id, case, db)

    # 重新加载影像学报告
    reports = db.query(ImagingReport).filter(ImagingReport.case_id == case_id).all()

    success_count = sum(1 for r in results if r.get("status") == "completed")

    return {
        "message": f"影像学报告提取完成，成功 {success_count}/{len(results)} 份",
        "results": results,
        "imaging_reports": [
            {
                "id": r.id,
                "report_date": r.report_date,
                "hospital_name": r.hospital_name,
                "exam_type": r.exam_type,
                "exam_part": r.exam_part,
                "film_number": r.film_number,
                "film_count": r.film_count,
                "report_content": r.report_content,
            }
            for r in reports
        ],
    }


@router.post("/cases/{case_id}/generate-material-summary")
def generate_material_summary_api(case_id: int, db: Session = Depends(get_db)):
    """
    独立生成「资料摘要」：
    - 从已提取的住院记录调用LLM生成资料摘要
    - 与病历提取分离，可单独执行
    """
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    # 检查是否有住院记录
    records = db.query(HospitalRecord).filter(HospitalRecord.case_id == case_id).all()
    if not records:
        raise HTTPException(status_code=400, detail="请先提取病历（住院记录为空）")

    # 生成资料摘要
    summary_result = _generate_material_summary(case_id, db)

    if summary_result.get("success"):
        # 写入报告（已确认字段不覆盖）
        report = db.query(Report).filter(Report.case_id == case_id).first()
        if not report:
            report = Report(case_id=case_id)
            db.add(report)
            db.flush()
        overwritten = _write_report_field(report, "material_summary", summary_result["material_summary"])
        db.commit()

        msg = "资料摘要生成成功" if overwritten else "资料摘要生成成功（您手动修改的内容已保留，未覆盖）"
        return {
            "message": msg,
            "material_summary": summary_result["material_summary"],
            "model": summary_result.get("model", ""),
        }
    else:
        raise HTTPException(status_code=400, detail=summary_result.get("error", "生成失败"))


@router.post("/cases/{case_id}/generate-appraisal-process")
def generate_appraisal_process_api(case_id: int, db: Session = Depends(get_db)):
    """
    独立生成「鉴定过程」：
    - 使用 LLM 根据法医临床检查和影像学报告生成规范格式文本
    - 包含套话、法医检查信息、影像复阅等内容
    """
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    # 生成鉴定过程
    result = _generate_appraisal_process(case_id, db)

    if result.get("success"):
        # 写入报告（已确认字段不覆盖）
        report = db.query(Report).filter(Report.case_id == case_id).first()
        if not report:
            report = Report(case_id=case_id)
            db.add(report)
            db.flush()
        overwritten = _write_report_field(report, "appraisal_process", result["appraisal_process"])
        db.commit()

        msg = "鉴定过程生成成功" if overwritten else "鉴定过程生成成功（您手动修改的内容已保留，未覆盖）"
        return {
            "message": "鉴定过程生成成功",
            "appraisal_process": result["appraisal_process"],
            "method": result.get("method", "unknown"),
        }
    else:
        raise HTTPException(status_code=400, detail=result.get("error", "生成失败"))


@router.post("/cases/{case_id}/generate-analysis")
def generate_analysis_api(case_id: int, db: Session = Depends(get_db)):
    """
    生成「分析说明」：
    - 基于住院记录和影像学报告综合分析
    - 生成 analysis 文本
    """
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    # 检查是否有住院记录或影像学报告
    records = db.query(HospitalRecord).filter(HospitalRecord.case_id == case_id).all()
    img_reports = db.query(ImagingReport).filter(ImagingReport.case_id == case_id).all()

    if not records and not img_reports:
        raise HTTPException(status_code=400, detail="请先提取病历和影像学报告")

    result = _generate_analysis(case_id, db)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "生成失败"))

    report = db.query(Report).filter(Report.case_id == case_id).first()
    if not report:
        report = Report(case_id=case_id)
        db.add(report)
        db.flush()

    overwritten = _write_report_field(report, "analysis", result["analysis"])
    db.commit()
    db.refresh(report)

    msg = "分析说明已生成" if overwritten else "分析说明已生成（您手动修改的内容已保留，未覆盖）"
    return {
        "message": msg,
        "analysis": result["analysis"],
        "method": result.get("method", "unknown"),
    }


@router.post("/cases/{case_id}/generate-opinion")
def generate_opinion_api(case_id: int, db: Session = Depends(get_db)):
    """
    生成「鉴定意见」：
    - 基于分析说明和委托事项生成
    - 生成 opinion 文本
    """
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    report = db.query(Report).filter(Report.case_id == case_id).first()
    if not report or not report.analysis:
        raise HTTPException(status_code=400, detail="请先生成分析说明")

    result = _generate_opinion(case_id, db)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "生成失败"))

    overwritten = _write_report_field(report, "opinion", result["opinion"])
    db.commit()
    db.refresh(report)

    msg = "鉴定意见已生成" if overwritten else "鉴定意见已生成（您手动修改的内容已保留，未覆盖）"
    return {
        "message": msg,
        "opinion": result["opinion"],
        "model": result.get("model", ""),
    }


def _extract_and_save(material: Material, case: Case, db) -> dict:
    """
    对单份材料调用 LLM 提取并保存结果到对应数据库表
    """
    material_type = material.material_type
    ocr_text = material.ocr_text

    # 调用 LLM 提取
    result = extract_fields(material_type, ocr_text)

    if not result.get("success"):
        return {
            "material_id": material.id,
            "filename": material.original_filename,
            "material_type": material_type,
            "status": "failed",
            "error": result.get("error", "提取失败"),
        }

    fields = result["fields"]

    # 根据材料类型保存到不同表
    saved_info = {}

    if material_type == MaterialType.ENTRUSTMENT_LETTER:
        # 委托书 → 更新 Case 基本情况（已确认字段不覆盖）
        case_confirmed = _get_confirmed_fields(case)
        if fields.get("entrusting_unit"):
            _safe_setattr(case, "entrusting_unit", fields["entrusting_unit"], case_confirmed)
        if fields.get("entrustment_matter"):
            _safe_setattr(case, "entrustment_matter", fields["entrustment_matter"], case_confirmed)
        if fields.get("person_name"):
            _safe_setattr(case, "person_name", fields["person_name"], case_confirmed)
        saved_info = {
            "entrusting_unit": fields.get("entrusting_unit"),
            "entrustment_matter": fields.get("entrustment_matter"),
            "person_name": fields.get("person_name"),
        }

    elif material_type == MaterialType.ID_CARD:
        # 身份证 → 更新/创建 Person（已确认字段不覆盖）
        person = db.query(Person).filter(Person.case_id == case.id).first()
        if not person:
            person = Person(case_id=case.id)
            db.add(person)
            db.flush()

        person_confirmed = _get_confirmed_fields(person)
        if fields.get("name"):
            _safe_setattr(person, "name", fields["name"], person_confirmed)
            _safe_setattr(case, "person_name", fields["name"], _get_confirmed_fields(case))
        if fields.get("gender"):
            _safe_setattr(person, "gender", fields["gender"], person_confirmed)
        if fields.get("birth_date"):
            _safe_setattr(person, "birth_date", fields["birth_date"], person_confirmed)
        if fields.get("id_number"):
            _safe_setattr(person, "id_number", fields["id_number"], person_confirmed)
        if fields.get("address"):
            _safe_setattr(person, "address", fields["address"], person_confirmed)
        saved_info = {
            "name": fields.get("name"),
            "gender": fields.get("gender"),
            "id_number": fields.get("id_number"),
        }

    elif material_type == MaterialType.TRAFFIC_ACCIDENT_CERT:
        # 交通事故认定书 → 更新 Case 事故信息（已确认字段不覆盖）
        case_confirmed = _get_confirmed_fields(case)
        if fields.get("accident_date"):
            _safe_setattr(case, "accident_date", fields["accident_date"], case_confirmed)
        if fields.get("accident_location"):
            _safe_setattr(case, "accident_location", fields["accident_location"], case_confirmed)
        if fields.get("accident_description"):
            _safe_setattr(case, "accident_description", fields["accident_description"], case_confirmed)
        saved_info = {
            "accident_date": fields.get("accident_date"),
            "accident_location": fields.get("accident_location"),
            "accident_description": fields.get("accident_description"),
            "responsibility": fields.get("responsibility"),
        }

    elif material_type == MaterialType.MEDICAL_RECORD:
        # 病历 → 创建/更新 HospitalRecord
        # 按住院号查找是否已有记录（同一住院号合并）
        admission_number = fields.get("admission_number", "")
        existing_record = None
        if admission_number:
            existing_record = db.query(HospitalRecord).filter(
                HospitalRecord.case_id == case.id,
                HospitalRecord.admission_number == admission_number,
            ).first()

        if existing_record:
            # 合并到已有记录（出院记录补充入院记录）
            record = existing_record
        else:
            record = HospitalRecord(case_id=case.id, material_id=material.id)
            db.add(record)
            db.flush()

        # 只更新有值的字段
        field_map = {
            "hospital_name": "hospital_name",
            "admission_number": "admission_number",
            "chief_complaint": "chief_complaint",
            "present_illness_history": "present_illness_history",
            "past_history": "past_history",
            "physical_examination": "physical_examination",
            "admission_diagnosis": "admission_diagnosis",
            "treatment_process": "treatment_process",
            "medication": "medication",
            "discharge_diagnosis": "discharge_diagnosis",
            "discharge_orders": "discharge_orders",
            "admission_date": "admission_date",
            "discharge_date": "discharge_date",
        }

        for json_key, db_key in field_map.items():
            value = fields.get(json_key)
            if value is not None and value != "" and value != "null":
                setattr(record, db_key, value)

        # 住院天数特殊处理
        if fields.get("hospital_days") is not None:
            try:
                record.hospital_days = int(fields["hospital_days"])
            except (ValueError, TypeError):
                pass

        saved_info = {
            "hospital_name": fields.get("hospital_name"),
            "admission_number": admission_number,
            "record_id": record.id,
        }

    elif material_type == MaterialType.IMAGING_REPORT:
        # 影像学报告 → 查找已有记录（同 material_id），有则覆盖，无则新建
        report = db.query(ImagingReport).filter(
            ImagingReport.case_id == case.id,
            ImagingReport.material_id == material.id,
        ).first()

        if not report:
            report = ImagingReport(case_id=case.id, material_id=material.id)
            db.add(report)
            db.flush()

        field_map = {
            "report_date": "report_date",
            "hospital_name": "hospital_name",
            "exam_type": "exam_type",
            "exam_part": "exam_part",
            "film_number": "film_number",
            "report_content": "report_content",
        }

        for json_key, db_key in field_map.items():
            value = fields.get(json_key)
            if value is not None and value != "" and value != "null":
                setattr(report, db_key, value)

        # film_count 特殊处理（字符串→整数）
        if fields.get("film_count") is not None:
            try:
                report.film_count = int(fields["film_count"])
            except (ValueError, TypeError):
                report.film_count = 1
        else:
            report.film_count = 1

        saved_info = {
            "hospital_name": fields.get("hospital_name"),
            "exam_type": fields.get("exam_type"),
            "report_id": report.id,
        }

    elif material_type == MaterialType.APPRAISAL_APPLICATION:
        # 鉴定申请书 → 补充委托单位（委托书优先，申请书可补充）
        # 注意：委托事项只从「司法鉴定委托书」提取，申请书不覆盖
        case_confirmed = _get_confirmed_fields(case)
        if fields.get("entrusting_unit"):
            _safe_setattr(case, "entrusting_unit", fields["entrusting_unit"], case_confirmed)
        saved_info = {
            "applicant": fields.get("applicant"),
            "entrusting_unit": fields.get("entrusting_unit"),
            "case_brief": fields.get("case_brief"),
        }

    db.commit()

    return {
        "material_id": material.id,
        "filename": material.original_filename,
        "material_type": material_type,
        "status": "completed",
        "fields": fields,
        "saved_info": saved_info,
        "model": result.get("model", ""),
        "usage": result.get("usage", {}),
    }


# ==================== 辅助生成函数 ====================

# ==================== 辅助函数 ====================

def _extract_medical_group_llm(hospital_name: str, combined_text: str) -> dict:
    """调用LLM按医院分组提取病历字段"""
    return extract_medical_group_fields(hospital_name, combined_text)


def _generate_material_list(case_id: int, case: Case, db) -> None:
    """
    根据案件已上传的所有材料，自动生成材料清单文本
    规则：
    1. 每类材料默认"壹份"，不按图片张数算
    2. 数字用大写（壹、贰、叁...）
    3. 委托书=原件，其他=复印件（影像除外）
    4. 身份证格式：XXX居民身份证复印件壹份
    5. 影像学资料：被鉴定人带胶片给法医查看，从ImagingReport读exam_type+film_count，
       如"CT贰张、MRI叁张"，不写原件/复印件
    """
    all_materials = db.query(Material).filter(
        Material.case_id == case_id,
    ).all()

    if not all_materials:
        return

    # 大写数字映射
    num_cn = {0: "零", 1: "壹", 2: "贰", 3: "叁", 4: "肆", 5: "伍",
              6: "陆", 7: "柒", 8: "捌", 9: "玖", 10: "拾"}

    def to_cn(n: int) -> str:
        if n in num_cn:
            return num_cn[n]
        return str(n)

    # 按材料类型分组统计（是否有上传即可，不按图片数）
    uploaded_types = set()
    for mat in all_materials:
        uploaded_types.add(mat.material_type)

    # 获取被鉴定人姓名
    person = db.query(Person).filter(Person.case_id == case_id).first()
    person_name = person.name if person and person.name else ""

    # 获取住院记录（用于按医院列病历）
    hospital_records = db.query(HospitalRecord).filter(
        HospitalRecord.case_id == case_id,
    ).all()

    # 获取影像学报告（用于列影像资料详情）
    imaging_reports = db.query(ImagingReport).filter(
        ImagingReport.case_id == case_id,
    ).all()

    # 生成清单
    list_items = []
    idx = 1

    # 1. 司法鉴定委托书（原件）
    if MaterialType.ENTRUSTMENT_LETTER in uploaded_types:
        list_items.append(f"{idx}. 司法鉴定委托书原件壹份")
        idx += 1

    # 2. 身份证复印件
    if MaterialType.ID_CARD in uploaded_types:
        name_prefix = f"{person_name}" if person_name else ""
        list_items.append(f"{idx}. {name_prefix}居民身份证复印件壹份")
        idx += 1

    # 3. 交通事故认定书复印件
    if MaterialType.TRAFFIC_ACCIDENT_CERT in uploaded_types:
        list_items.append(f"{idx}. 道路交通事故认定书复印件壹份")
        idx += 1

    # 4. 鉴定申请书复印件
    if MaterialType.APPRAISAL_APPLICATION in uploaded_types:
        list_items.append(f"{idx}. 鉴定申请书复印件壹份")
        idx += 1

    # 5. 住院病历复印件（按医院分组合并，同一家医院多次住院合并为一条）
    if hospital_records:
        # 按医院名分组统计住院次数
        hospital_count = {}
        for r in hospital_records:
            hospital = r.hospital_name or "某医院"
            hospital_count[hospital] = hospital_count.get(hospital, 0) + 1
        for hospital, count in hospital_count.items():
            count_str = to_cn(count)
            list_items.append(f"{idx}. {hospital}住院病历复印件{count_str}份")
            idx += 1
    elif MaterialType.MEDICAL_RECORD in uploaded_types:
        # 有上传但还没提取出住院记录
        list_items.append(f"{idx}. 住院病历复印件壹份")
        idx += 1

    # 6. 影像学资料（被鉴定人带胶片给法医查看，按检查类型+张数列，不写原件/复印件）
    if imaging_reports:
        # 按exam_type汇总张数
        exam_type_counts = {}
        for r in imaging_reports:
            et = r.exam_type or "影像学检查"
            fc = r.film_count or 1
            exam_type_counts[et] = exam_type_counts.get(et, 0) + fc

        # 按医院分组
        hospital_exams = {}
        for r in imaging_reports:
            hospital = r.hospital_name or "某医院"
            if hospital not in hospital_exams:
                hospital_exams[hospital] = {}
            et = r.exam_type or "影像学检查"
            fc = r.film_count or 1
            hospital_exams[hospital][et] = hospital_exams[hospital].get(et, 0) + fc

        # 如果只有一个医院或没医院名，直接列检查类型
        if len(hospital_exams) == 1:
            hospital = list(hospital_exams.keys())[0]
            exams = hospital_exams[hospital]
            exam_parts = []
            for et, count in exams.items():
                exam_parts.append(f"{et}{to_cn(count)}张")
            exam_str = "、".join(exam_parts)
            if hospital and hospital != "某医院":
                list_items.append(f"{idx}. {hospital}{exam_str}")
            else:
                list_items.append(f"{idx}. 影像学资料{exam_str}")
            idx += 1
        else:
            # 多个医院，每个医院一行
            for hospital, exams in hospital_exams.items():
                exam_parts = []
                for et, count in exams.items():
                    exam_parts.append(f"{et}{to_cn(count)}张")
                exam_str = "、".join(exam_parts)
                list_items.append(f"{idx}. {hospital}{exam_str}")
                idx += 1
    elif MaterialType.IMAGING_REPORT in uploaded_types:
        # 有上传但还没提取出影像报告，暂列占位
        list_items.append(f"{idx}. 影像学资料（待提取详情）")
        idx += 1

    material_list_text = "；".join(list_items) + "。"

    case.material_list = material_list_text
    db.commit()
    logger.info(f"案件 {case_id} 材料清单已自动生成: {material_list_text}")


def _generate_material_summary(case_id: int, db) -> dict:
    """从住院记录生成资料摘要全文（拼接方式，不调用LLM）"""
    records = db.query(HospitalRecord).filter(HospitalRecord.case_id == case_id).all()
    if not records:
        return {"success": False, "error": "没有住院记录"}

    # 中文序号列表
    cn_nums = ["（一）", "（二）", "（三）", "（四）", "（五）", "（六）", "（七）", "（八）", "（九）", "（十）"]

    # 拼接住院记录信息
    record_parts = []
    for idx, r in enumerate(records):
        prefix = cn_nums[idx] if idx < len(cn_nums) else f"（{idx + 1}）"
        part = f"{prefix}据{r.hospital_name or '某医院'}住院病案（住院号：{r.admission_number or '-'})记载："
        if r.admission_date:
            part += f"患者{r.admission_date}入院，"
        if r.discharge_date:
            part += f"{r.discharge_date}出院，"
        if r.hospital_days:
            part += f"住院{r.hospital_days}天。"
        if r.chief_complaint:
            part += f"主诉：{r.chief_complaint}。"
        if r.present_illness_history:
            part += f"现病史：{r.present_illness_history}。"
        if r.past_history:
            part += f"既往史：{r.past_history}。"
        if r.physical_examination:
            part += f"体格检查：{r.physical_examination}。"
        if r.admission_diagnosis:
            part += f"入院诊断：{r.admission_diagnosis}。"
        if r.treatment_process:
            part += f"治疗过程：{r.treatment_process}。"
        if r.medication:
            part += f"用药情况：{r.medication}。"
        if r.discharge_diagnosis:
            part += f"出院诊断：{r.discharge_diagnosis}。"
        if r.discharge_orders:
            part += f"出院医嘱：{r.discharge_orders}。"
        record_parts.append(part)

    summary_text = "\n\n".join(record_parts)
    logger.info(f"案件 {case_id} 资料摘要拼接完成，长度: {len(summary_text)} 字符，{len(records)} 条记录")

    return {"success": True, "material_summary": summary_text}


def _generate_appraisal_process(case_id: int, db) -> dict:
    """使用 LLM 生成鉴定过程文本，LLM失败时回退到拼接（fallback）"""
    from app.utils.llm import call_llm

    img_reports = db.query(ImagingReport).filter(ImagingReport.case_id == case_id).all()
    case = db.query(Case).filter(Case.id == case_id).first()
    person = db.query(Person).filter(Person.case_id == case_id).first()

    if not case:
        return {"success": False, "error": "案件不存在"}

    person_name = person.name if person and person.name else "被鉴定人"

    # ===== 尝试 LLM 生成 =====
    imaging_data = []
    for r in img_reports:
        item = {
            "报告日期": r.report_date or "",
            "医院名称": r.hospital_name or "",
            "检查类型": r.exam_type or "",
            "检查部位": r.exam_part or "",
            "片子编号": r.film_number or "",
            "片子数量": r.film_count or "",
            "报告内容": r.report_content or "",
        }
        imaging_data.append(item)

    exam_date = case.examination_date or ""
    clinical_examination = case.clinical_examination or ""

    system_prompt = """你是一位资深法医临床学鉴定人，擅长撰写司法鉴定意见书中的"鉴定过程"部分。
请严格按照司法鉴定意见书的规范格式生成文本。"""

    user_prompt = f"""请根据以下案件信息，撰写司法鉴定意见书的"鉴定过程"部分。

被鉴定人：{person_name}
检查日期：{exam_date}
法医临床学检查内容：{clinical_examination}

影像学报告数据（共{len(img_reports)}份）：
{json.dumps(imaging_data, ensure_ascii=False, indent=2)}

要求：
1. 鉴定过程分为两部分：
   第一部分：法医临床学检查
   - 以"按照《法医临床检验规范》（SF/Z JD0103003-2011）对{person_name}进行法医临床学检查。"开头
   - 如果有检查日期，写明日期
   - 然后是检查内容（如被鉴定人伤后多久、自行步入诊室、自诉症状、查体结果等）

   第二部分：影像学资料复阅
   - 每份影像报告一行，格式为：复阅 日期 医院 姓名 部位+类型片（号XX）示：描述
   - 例如：复阅 2021年4月22日 新乡市中心医院 张金遂 头颅CT片（号12345）示：左侧颞叶挫裂伤
   - 部位和检查类型合并，如"头颅CT片""左锁骨正位X线片""胸部正位X线片"

2. 语言规范严谨，符合司法鉴定文书格式
3. 不要加"一、""二、"等编号，不要加小标题
4. 只输出鉴定过程正文，不要加标题、不要加说明性文字
5. 影像学报告的描述内容要完整保留，不要缩写或省略"""

    llm_result = call_llm(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0.3,
        max_tokens=2000,
    )

    if llm_result.get("success"):
        process_text = llm_result["content"].strip()
        # 去除 LLM 返回的 markdown 代码块标记
        if process_text.startswith("```"):
            lines = process_text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            process_text = "\n".join(lines).strip()
        logger.info(f"案件 {case_id} 鉴定过程 LLM 生成成功")
        return {"success": True, "appraisal_process": process_text, "method": "llm"}

    # ===== Fallback：LLM 失败，回退到拼接 =====
    logger.warning(f"案件 {case_id} 鉴定过程 LLM 生成失败（{llm_result.get('error')}），回退到拼接模式")
    process_parts = []

    # 一、法医临床学检查
    if clinical_examination:
        process_parts.append(
            f"按照《法医临床检验规范》（SF/Z JD0103003-2011）对{person_name}进行法医临床学检查。"
        )
        if exam_date:
            process_parts.append(f"{exam_date}。")
        process_parts.append(clinical_examination)

    # 二、影像学资料复阅
    if img_reports:
        for r in img_reports:
            hospital = r.hospital_name or "某医院"
            exam_type = r.exam_type or "影像学检查"
            exam_part = r.exam_part or ""
            date = r.report_date or ""
            content = r.report_content or ""
            film_info = f"（号 {r.film_number}）" if r.film_number else ""

            parts = ["复阅"]
            if date:
                parts.append(date)
            parts.append(hospital)
            if person_name:
                parts.append(person_name)
            if exam_part and exam_type:
                parts.append(f"{exam_part}{exam_type}片")
            elif exam_type:
                parts.append(f"{exam_type}片")
            parts.append(film_info)
            parts.append("示：")
            parts.append(content)

            line = " ".join(parts).replace("  ", " ").strip()
            process_parts.append(line)

    process_text = "\n".join(process_parts)
    return {"success": True, "appraisal_process": process_text, "method": "fallback"}


def _generate_analysis(case_id: int, db) -> dict:
    """使用 LLM 生成分析说明，失败时回退到拼接（fallback）"""
    from app.utils.llm import call_llm

    case = db.query(Case).filter(Case.id == case_id).first()
    records = db.query(HospitalRecord).filter(HospitalRecord.case_id == case_id).all()
    img_reports = db.query(ImagingReport).filter(ImagingReport.case_id == case_id).all()
    person = db.query(Person).filter(Person.case_id == case_id).first()

    if not case:
        return {"success": False, "error": "案件不存在"}

    person_name = person.name if person and person.name else "被鉴定人"
    entrustment = case.entrustment_matter or ""

    # 构建住院记录数据
    hospital_data = []
    for r in records:
        item = {
            "医院名称": r.hospital_name or "",
            "住院号": r.admission_number or "",
            "入院日期": r.admission_date or "",
            "出院日期": r.discharge_date or "",
            "住院天数": r.hospital_days or "",
            "入院诊断": r.admission_diagnosis or "",
            "出院诊断": r.discharge_diagnosis or "",
            "治疗经过": r.treatment_process or "",
            "出院医嘱": r.discharge_orders or "",
        }
        hospital_data.append(item)

    # 构建影像学报告数据
    imaging_data = []
    for r in img_reports:
        item = {
            "报告日期": r.report_date or "",
            "医院名称": r.hospital_name or "",
            "检查类型": r.exam_type or "",
            "检查部位": r.exam_part or "",
            "片子编号": r.film_number or "",
            "报告内容": r.report_content or "",
        }
        imaging_data.append(item)

    # ===== 尝试 LLM 生成 =====
    system_prompt = """你是一位资深法医临床学鉴定人，擅长撰写司法鉴定意见书中的"分析说明"部分。
请严格按照司法鉴定意见书的规范格式生成文本。"""

    user_prompt = f"""请根据以下案件信息，撰写司法鉴定意见书的"分析说明"部分。

【权威信息】（已由鉴定人确认，必须以此为准）
被鉴定人：{person_name}
委托鉴定事项：{entrustment}

住院记录数据（共{len(records)}份）：
{json.dumps(hospital_data, ensure_ascii=False, indent=2)}

影像学报告数据（共{len(img_reports)}份）：
{json.dumps(imaging_data, ensure_ascii=False, indent=2)}

要求：
分析说明必须遵循以下三段逻辑结构：

第一段：确认外伤来源
- 以"根据委托单位提供的现有材料，结合本鉴定中心检验所见，现分析如下："开头
- 第1条：确认被鉴定人外伤史确切，系何种事故所致（从事故认定书等材料中提取事故类型）

第二段：确认所有伤情
- 第2条：列出被鉴定人的全部诊断/伤情
- 综合入院诊断、出院诊断、影像学检查结果
- 注明诊断"明确"，并标注经何种检查证实（如"经X线、CT、临床检查及手术证实"）

第三段：按委托鉴定事项逐一分析
- 第3条起，每条对应上方"委托鉴定事项"中的一个事项
- 必须严格按照委托鉴定事项的内容和顺序逐一分析，不得自行增减鉴定事项
- 伤残等级分析：需引用具体鉴定标准条款（如《人体损伤致残程度分级》），写明"参照第X条X项规定，应评为X级伤残"
- 误工期分析：引用《人身损害误工期、护理期、营养期评定规范》(GA/T1193-2014)，结合年龄、治疗经过、恢复情况给出具体天数
- 后续治疗费分析：如内固定物在位，需说明二次手术取出的费用估算，参考河南省地市级三级医院收费情况

格式要求：
1. 每条以阿拉伯数字编号（1. 2. 3. 等）
2. 语言规范严谨，符合司法鉴定文书格式
3. 诊断名称必须使用病历中的原始表述，不要改写
4. 影像学检查发现需融入伤情分析中（如"复阅其2021年8月25日头颅MRI片提示..."）
5. 只输出分析说明正文，不要加标题、不要加说明性文字"""

    llm_result = call_llm(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0.3,
        max_tokens=3000,
    )

    if llm_result.get("success"):
        analysis_text = llm_result["content"].strip()
        # 去除 markdown 代码块标记
        if analysis_text.startswith("```"):
            lines = analysis_text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            analysis_text = "\n".join(lines).strip()
        logger.info(f"案件 {case_id} 分析说明 LLM 生成成功")
        return {"success": True, "analysis": analysis_text, "method": "llm"}

    # ===== Fallback：LLM 失败，回退到拼接 =====
    logger.warning(f"案件 {case_id} 分析说明 LLM 生成失败（{llm_result.get('error')}），回退到拼接模式")
    analysis_parts = []

    if person_name:
        analysis_parts.append(f"被鉴定人{person_name}，")

    if entrustment:
        analysis_parts.append(f"因{entrustment}，")

    if records:
        analysis_parts.append("伤后到医院就诊治疗。")
        analysis_parts.append("")
        analysis_parts.append("根据送鉴病历资料记载：")

        for r in records:
            hospital = r.hospital_name or "某医院"
            if r.admission_diagnosis:
                analysis_parts.append(f"1. {hospital}入院诊断：{r.admission_diagnosis}。")
            if r.discharge_diagnosis:
                analysis_parts.append(f"   出院诊断：{r.discharge_diagnosis}。")
            if r.treatment_process:
                analysis_parts.append(f"   治疗过程：{r.treatment_process}。")

    if img_reports:
        analysis_parts.append("")
        analysis_parts.append("根据送鉴影像学资料复阅：")
        for r in img_reports:
            hospital = r.hospital_name or "某医院"
            exam_type = r.exam_type or "影像学检查"
            content = r.report_content or ""
            analysis_parts.append(f"{hospital}{exam_type}示：{content}。")

    if records:
        discharge_diag = records[0].discharge_diagnosis if records else ""
        if discharge_diag:
            analysis_parts.append("")
            analysis_parts.append(f"综合分析认为，被鉴定人的诊断明确，与外伤之间存在直接因果关系。")

    analysis_text = "\n".join(analysis_parts)
    return {"success": True, "analysis": analysis_text, "method": "fallback"}


def _generate_opinion(case_id: int, db) -> dict:
    """基于分析说明生成鉴定意见"""
    case = db.query(Case).filter(Case.id == case_id).first()
    report = db.query(Report).filter(Report.case_id == case_id).first()
    person = db.query(Person).filter(Person.case_id == case_id).first()

    if not report or not report.analysis:
        return {"success": False, "error": "请先生成分析说明"}

    person_name = person.name if person else "被鉴定人"
    entrustment = case.entrustment_matter if case else ""

    # 基于分析说明自动提取关键结论
    prompt = f"""请根据以下"分析说明"内容，提炼出鉴定意见。

【权威信息】（已由鉴定人确认，必须以此为准）
被鉴定人：{person_name}
委托事项：{entrustment}

【写作要求】
鉴定意见是分析说明的简化版，只给结论，不写理由。

【核心原则】
1. 分析说明的结构通常是：第1条确认外伤来源，第2条确认伤情诊断，第3条起才是委托事项的结论
2. 鉴定意见只需提炼第3条及之后的内容（委托事项结论），前两条（外伤来源确认、伤情确认）不写入鉴定意见
3. 分析说明中有的结论才写入，没有的不可凭空编造
4. 如果委托事项中包含某项但分析说明未涉及该项，则不生成该条意见

【格式规范】
- 每条意见对应分析说明中第3条起的一个分析结论，必须用阿拉伯数字编号（1. 2. 3. 等）
- 不要加分类标签（如"伤残等级""误工期""护理期"等），不要用箭头，直接写结论
- 不要加粗体、标题等Markdown格式
- 示例格式：
  "1. 被鉴定人{person_name}右侧额叶脑挫裂伤后遗脑软化灶形成评为十级伤残。"
  "2. 被鉴定人{person_name}出院后的误工期拟定为60日。"
  "3. 被鉴定人{person_name}后续治疗费用约需人民币捌仟圆（¥8000.0元）。"
- 以上仅为格式参考，实际只输出分析说明中存在的结论，编号连续即可

其他要求：
1. 只给结论，不写分析过程和理由（理由在分析说明中已有）
2. 数字金额需同时写大写和小写，如"捌仟圆（¥8000.0元）"
3. 语言简洁、明确、断句干脆
4. 输出纯文本，不要JSON，不要Markdown格式，不要加"六、鉴定意见"标题

分析说明内容：
{report.analysis[:3000]}"""

    result = call_llm(
        system_prompt="你是一个司法鉴定意见书撰写助手。请根据分析说明提炼鉴定意见。",
        user_prompt=prompt,
        temperature=0.2,
    )

    if not result.get("success"):
        return {"success": False, "error": result.get("error", "生成失败")}

    return {
        "success": True,
        "opinion": result["content"],
        "model": result.get("model", ""),
    }


def extract_case_facts_text(case_id: int, db) -> dict:
    """从数据库已有字段拼接生成基本案情文本（纯拼接，不调用LLM）

    基本案情结构：
    1. 事故经过：照抄交通事故认定书中"道路交通事故发生经过"原文
    2. 就医经过：被鉴定人受伤后被送至XX医院治疗（按住院记录的医院去重排列）
    3. 委托语句：现为处理案件需要，{委托单位}特委托我鉴定中心{委托事项}。
    """
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        return {"success": False, "error": "案件不存在"}

    person = db.query(Person).filter(Person.case_id == case_id).first()
    person_name = person.name if person and person.name else "被鉴定人"

    parts = []

    # === 第一段：事故经过（认定书原文） ===
    if case.accident_description:
        parts.append(case.accident_description)

    # === 第二段：就医经过 ===
    hospital_records = db.query(HospitalRecord).filter(
        HospitalRecord.case_id == case_id,
    ).order_by(HospitalRecord.admission_date).all()

    if hospital_records:
        # 按医院名去重，保持顺序
        seen = set()
        hospital_names = []
        for r in hospital_records:
            name = r.hospital_name or "某医院"
            if name not in seen:
                seen.add(name)
                hospital_names.append(name)

        if len(hospital_names) == 1:
            hospital_str = hospital_names[0]
        elif len(hospital_names) == 2:
            hospital_str = f"{hospital_names[0]}和{hospital_names[1]}"
        else:
            hospital_str = "、".join(hospital_names[:-1]) + f"和{hospital_names[-1]}"

        parts.append(f"{person_name}受伤后被送至{hospital_str}治疗。")

    # === 第三段：委托语句（固定格式） ===
    entrusting_unit = case.entrusting_unit or "委托单位"
    entrustment_matter = case.entrustment_matter or "进行鉴定"
    parts.append(f"现为处理案件需要，{entrusting_unit}特委托我鉴定中心{entrustment_matter}。")

    case_facts = "".join(parts)

    if not case_facts.strip():
        return {"success": False, "error": "缺少事故信息和委托信息，请先提取委托书和交通事故认定书"}

    return {
        "success": True,
        "case_facts": case_facts,
        "model": "拼接（无LLM）",
    }
