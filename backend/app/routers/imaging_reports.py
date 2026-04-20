"""
影像学报告管理路由
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models.case import ImagingReport, Case
from app.schemas.case import ImagingReportCreate, ImagingReportUpdate, ImagingReportResponse

router = APIRouter(prefix="/api/imaging-reports", tags=["影像学报告"])


@router.get("/case/{case_id}", response_model=List[ImagingReportResponse])
def list_imaging_reports(case_id: int, db: Session = Depends(get_db)):
    """获取案件的所有影像学报告"""
    reports = db.query(ImagingReport).filter(ImagingReport.case_id == case_id).all()
    return reports


@router.get("/{report_id}", response_model=ImagingReportResponse)
def get_imaging_report(report_id: int, db: Session = Depends(get_db)):
    """获取单条影像学报告"""
    report = db.query(ImagingReport).filter(ImagingReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="影像学报告不存在")
    return report


@router.post("", response_model=ImagingReportResponse)
def create_imaging_report(data: ImagingReportCreate, db: Session = Depends(get_db)):
    """创建影像学报告"""
    case = db.query(Case).filter(Case.id == data.case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    report = ImagingReport(**data.model_dump())
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


@router.put("/{report_id}", response_model=ImagingReportResponse)
def update_imaging_report(report_id: int, data: ImagingReportUpdate, db: Session = Depends(get_db)):
    """更新影像学报告"""
    report = db.query(ImagingReport).filter(ImagingReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="影像学报告不存在")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(report, key, value)

    db.commit()
    db.refresh(report)
    return report


@router.delete("/{report_id}")
def delete_imaging_report(report_id: int, db: Session = Depends(get_db)):
    """删除影像学报告"""
    report = db.query(ImagingReport).filter(ImagingReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="影像学报告不存在")
    db.delete(report)
    db.commit()
    return {"message": "删除成功"}
