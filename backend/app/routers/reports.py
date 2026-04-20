"""
报告管理路由
"""
import os
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.case import Case, Report, CaseStatus
from app.schemas.case import ReportCreate, ReportUpdate, ReportResponse

router = APIRouter(prefix="/api/reports", tags=["报告管理"])


@router.get("/case/{case_id}", response_model=ReportResponse)
def get_report(case_id: int, db: Session = Depends(get_db)):
    """获取案件的报告"""
    report = db.query(Report).filter(Report.case_id == case_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    return report


@router.post("", response_model=ReportResponse)
def create_report(data: ReportCreate, db: Session = Depends(get_db)):
    """创建报告"""
    case = db.query(Case).filter(Case.id == data.case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    existing = db.query(Report).filter(Report.case_id == data.case_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="该案件已有报告")

    report = Report(**data.model_dump())
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


@router.put("/{report_id}", response_model=ReportResponse)
def update_report(report_id: int, data: ReportUpdate, db: Session = Depends(get_db)):
    """更新报告"""
    import json as _json
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")

    update_data = data.model_dump(exclude_unset=True)

    # 标记用户确认的字段（只有非空值才标记，空值不算确认）
    report_editable_fields = {
        "case_facts", "material_summary", "appraisal_process",
        "analysis", "opinion",
    }
    confirmed = set()
    try:
        confirmed = set(_json.loads(report.confirmed_fields or "[]"))
    except (ValueError, TypeError):
        pass
    for key, value in update_data.items():
        if key in report_editable_fields and value:  # 只有非空值才标记为已确认
            confirmed.add(key)
    report.confirmed_fields = _json.dumps(list(confirmed), ensure_ascii=False)

    for key, value in update_data.items():
        setattr(report, key, value)

    report.updated_at = datetime.now()
    db.commit()
    db.refresh(report)
    return report


@router.post("/{report_id}/confirm-opinion")
def confirm_opinion(report_id: int, db: Session = Depends(get_db)):
    """确认鉴定意见"""
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")

    if not report.opinion:
        raise HTTPException(status_code=400, detail="鉴定意见为空，无法确认")

    report.opinion_confirmed = True
    db.commit()
    return {"message": "鉴定意见已确认"}


@router.post("/{report_id}/unconfirm-opinion")
def unconfirm_opinion(report_id: int, db: Session = Depends(get_db)):
    """取消确认鉴定意见"""
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")

    report.opinion_confirmed = False
    db.commit()
    return {"message": "鉴定意见确认已取消"}


@router.post("/{report_id}/generate-word")
def generate_word(report_id: int, db: Session = Depends(get_db)):
    """生成 Word 报告"""
    from app.utils.report_generator import generate_report_docx
    from fastapi.responses import FileResponse

    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")

    case = db.query(Case).filter(Case.id == report.case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="关联案件不存在")

    try:
        file_path = generate_report_docx(case, db)
        return FileResponse(
            file_path,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=os.path.basename(file_path)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成报告失败: {str(e)}")
