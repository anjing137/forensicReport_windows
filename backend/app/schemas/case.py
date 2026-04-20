"""
数据验证 schemas - 司法鉴定意见书自动生成系统
基于 PRD v1.0 设计
"""
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


# ==================== 枚举值 ====================

class CaseStatusEnum:
    PENDING_UPLOAD = "pending_upload"
    RECOGNIZING = "recognizing"
    PENDING_REVIEW = "pending_review"
    REVIEWING = "reviewing"
    PENDING_CONFIRM = "pending_confirm"
    COMPLETED = "completed"

    LABELS = {
        "pending_upload": "待上传",
        "recognizing": "识别中",
        "pending_review": "待修正",
        "reviewing": "修正中",
        "pending_confirm": "待确认",
        "completed": "已完成",
    }


class MaterialTypeEnum:
    ENTRUSTMENT_LETTER = "entrustment_letter"
    ID_CARD = "id_card"
    TRAFFIC_ACCIDENT_CERT = "traffic_accident_cert"
    APPRAISAL_APPLICATION = "appraisal_application"
    MEDICAL_RECORD = "medical_record"
    IMAGING_REPORT = "imaging_report"

    LABELS = {
        "entrustment_letter": "委托书",
        "id_card": "身份证复印件",
        "traffic_accident_cert": "道路交通事故认定书",
        "appraisal_application": "鉴定申请书",
        "medical_record": "医院病历",
        "imaging_report": "影像学报告",
    }


# ==================== Person ====================

class PersonBase(BaseModel):
    name: Optional[str] = None
    gender: Optional[str] = None
    birth_date: Optional[str] = None
    id_number: Optional[str] = None
    address: Optional[str] = None


class PersonCreate(PersonBase):
    case_id: int


class PersonUpdate(PersonBase):
    pass


class PersonResponse(PersonBase):
    id: int
    case_id: int

    class Config:
        from_attributes = True


# ==================== Case ====================

class CaseCreate(BaseModel):
    """创建案件 - 只需要案件编号"""
    case_number: Optional[str] = None


class CaseUpdate(BaseModel):
    """更新案件"""
    case_number: Optional[str] = None
    entrusting_unit: Optional[str] = None
    entrustment_matter: Optional[str] = None
    accident_date: Optional[str] = None
    accident_location: Optional[str] = None
    accident_description: Optional[str] = None
    acceptance_date: Optional[str] = None
    appraisal_date: Optional[str] = None
    appraisal_location: Optional[str] = None
    on_site_personnel: Optional[str] = None
    material_list: Optional[str] = None
    status: Optional[str] = None
    person_name: Optional[str] = None
    examination_date: Optional[str] = None
    clinical_examination: Optional[str] = None


class CaseResponse(BaseModel):
    """案件响应"""
    id: int
    case_number: Optional[str] = None
    entrusting_unit: Optional[str] = None
    entrustment_matter: Optional[str] = None
    accident_date: Optional[str] = None
    accident_location: Optional[str] = None
    accident_description: Optional[str] = None
    acceptance_date: Optional[str] = None
    appraisal_date: Optional[str] = None
    appraisal_location: Optional[str] = None
    on_site_personnel: Optional[str] = None
    material_list: Optional[str] = None
    person_name: Optional[str] = None
    examination_date: Optional[str] = None
    clinical_examination: Optional[str] = None
    status: str = "pending_upload"
    status_label: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # 嵌套关联
    person: Optional[PersonResponse] = None
    materials: List["MaterialResponse"] = []
    material_groups: List["MaterialGroupResponse"] = []
    hospital_records: List["HospitalRecordResponse"] = []
    imaging_reports: List["ImagingReportResponse"] = []
    report: Optional["ReportResponse"] = None

    class Config:
        from_attributes = True


class CaseListResponse(BaseModel):
    """案件列表响应（简洁版）"""
    id: int
    case_number: Optional[str] = None
    entrusting_unit: Optional[str] = None
    status: str = "pending_upload"
    status_label: Optional[str] = None
    person_name: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ==================== MaterialGroup ====================

class MaterialGroupBase(BaseModel):
    material_type: str
    group_name: str
    sort_order: Optional[int] = 0


class MaterialGroupCreate(MaterialGroupBase):
    case_id: int


class MaterialGroupUpdate(BaseModel):
    group_name: Optional[str] = None
    sort_order: Optional[int] = None


class MaterialGroupResponse(MaterialGroupBase):
    id: int
    case_id: int
    created_at: Optional[datetime] = None
    materials: List["MaterialResponse"] = []

    class Config:
        from_attributes = True


# ==================== Material ====================

class MaterialBase(BaseModel):
    material_type: str
    group_id: Optional[int] = None
    description: Optional[str] = None
    page_number: Optional[int] = None
    original_filename: Optional[str] = None


class MaterialCreate(MaterialBase):
    case_id: int
    file_path: str


class MaterialUpdate(BaseModel):
    material_type: Optional[str] = None
    group_id: Optional[int] = None
    description: Optional[str] = None
    page_number: Optional[int] = None
    ocr_text: Optional[str] = None
    ocr_status: Optional[str] = None


class MaterialResponse(BaseModel):
    id: int
    case_id: int
    material_type: str
    material_type_label: Optional[str] = None
    group_id: Optional[int] = None
    description: Optional[str] = None
    page_number: Optional[int] = None
    file_path: str
    original_filename: Optional[str] = None
    ocr_text: Optional[str] = None
    ocr_status: str = "pending"
    ocr_file_path: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ==================== HospitalRecord ====================

class HospitalRecordBase(BaseModel):
    hospital_name: Optional[str] = None
    admission_number: Optional[str] = None
    chief_complaint: Optional[str] = None
    present_illness_history: Optional[str] = None
    past_history: Optional[str] = None
    physical_examination: Optional[str] = None
    admission_diagnosis: Optional[str] = None
    treatment_process: Optional[str] = None
    medication: Optional[str] = None
    discharge_diagnosis: Optional[str] = None
    discharge_orders: Optional[str] = None
    admission_date: Optional[str] = None
    discharge_date: Optional[str] = None
    hospital_days: Optional[int] = None


class HospitalRecordCreate(HospitalRecordBase):
    case_id: int
    material_id: Optional[int] = None


class HospitalRecordUpdate(HospitalRecordBase):
    pass


class HospitalRecordResponse(HospitalRecordBase):
    id: int
    case_id: int
    material_id: Optional[int] = None

    class Config:
        from_attributes = True


# ==================== ImagingReport ====================

class ImagingReportBase(BaseModel):
    report_date: Optional[str] = None
    hospital_name: Optional[str] = None
    exam_type: Optional[str] = None
    exam_part: Optional[str] = None
    film_number: Optional[str] = None
    film_count: Optional[int] = 1
    report_content: Optional[str] = None


class ImagingReportCreate(ImagingReportBase):
    case_id: int
    material_id: Optional[int] = None


class ImagingReportUpdate(ImagingReportBase):
    pass


class ImagingReportResponse(ImagingReportBase):
    id: int
    case_id: int
    material_id: Optional[int] = None

    class Config:
        from_attributes = True


# ==================== Report ====================

class ReportBase(BaseModel):
    case_facts: Optional[str] = None
    material_summary: Optional[str] = None
    appraisal_process: Optional[str] = None
    analysis: Optional[str] = None
    opinion: Optional[str] = None


class ReportCreate(ReportBase):
    case_id: int


class ReportUpdate(ReportBase):
    opinion_confirmed: Optional[bool] = None


class ReportResponse(ReportBase):
    id: int
    case_id: int
    opinion_confirmed: bool = False
    generated_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ==================== StyleLog ====================

class StyleLogBase(BaseModel):
    section: str
    original_text: Optional[str] = None
    revised_text: Optional[str] = None
    diff_summary: Optional[str] = None


class StyleLogCreate(StyleLogBase):
    case_id: int


class StyleLogUpdate(BaseModel):
    diff_summary: Optional[str] = None


class StyleLogResponse(StyleLogBase):
    id: int
    case_id: int
    section_label: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ==================== 修复前向引用 ====================

MaterialGroupResponse.model_rebuild()
CaseResponse.model_rebuild()
