"""
风格学习记录路由
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models.case import Case, StyleLog, ReportSection
from app.schemas.case import StyleLogCreate, StyleLogUpdate, StyleLogResponse

router = APIRouter(prefix="/api/style-logs", tags=["风格学习"])


def get_section_label(section: str) -> str:
    return ReportSection.LABELS.get(section, section)


@router.get("/case/{case_id}", response_model=List[StyleLogResponse])
def list_style_logs(case_id: int, db: Session = Depends(get_db)):
    """获取案件的风格学习记录"""
    logs = db.query(StyleLog).filter(
        StyleLog.case_id == case_id
    ).order_by(StyleLog.created_at).all()
    
    return [
        StyleLogResponse(
            id=log.id,
            case_id=log.case_id,
            section=log.section,
            section_label=get_section_label(log.section),
            original_text=log.original_text,
            revised_text=log.revised_text,
            diff_summary=log.diff_summary,
            created_at=log.created_at,
        )
        for log in logs
    ]


@router.post("", response_model=StyleLogResponse)
def create_style_log(data: StyleLogCreate, db: Session = Depends(get_db)):
    """创建风格学习记录"""
    case = db.query(Case).filter(Case.id == data.case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    if data.section not in ReportSection.ALL:
        raise HTTPException(status_code=400, detail=f"不支持的报告部分: {data.section}")

    log = StyleLog(
        case_id=data.case_id,
        section=data.section,
        original_text=data.original_text,
        revised_text=data.revised_text,
        diff_summary=data.diff_summary,
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    return StyleLogResponse(
        id=log.id,
        case_id=log.case_id,
        section=log.section,
        section_label=get_section_label(log.section),
        original_text=log.original_text,
        revised_text=log.revised_text,
        diff_summary=log.diff_summary,
        created_at=log.created_at,
    )


@router.get("/stats")
def get_style_stats(db: Session = Depends(get_db)):
    """获取风格学习统计信息"""
    total = db.query(StyleLog).count()
    by_section = {}
    for section in ReportSection.ALL:
        count = db.query(StyleLog).filter(StyleLog.section == section).count()
        if count > 0:
            by_section[ReportSection.LABELS[section]] = count
    
    return {
        "total": total,
        "by_section": by_section,
    }
