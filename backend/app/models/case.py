"""
数据库模型 - 司法鉴定意见书自动生成系统
基于 PRD v1.0 设计
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


# ==================== 案件状态枚举 ====================
class CaseStatus:
    PENDING_UPLOAD = "pending_upload"      # 待上传
    RECOGNIZING = "recognizing"            # 识别中
    PENDING_REVIEW = "pending_review"      # 待修正
    REVIEWING = "reviewing"                # 修正中
    PENDING_CONFIRM = "pending_confirm"    # 待确认
    COMPLETED = "completed"                # 已完成

    ALL = [PENDING_UPLOAD, RECOGNIZING, PENDING_REVIEW,
           REVIEWING, PENDING_CONFIRM, COMPLETED]

    LABELS = {
        PENDING_UPLOAD: "待上传",
        RECOGNIZING: "识别中",
        PENDING_REVIEW: "待修正",
        REVIEWING: "修正中",
        PENDING_CONFIRM: "待确认",
        COMPLETED: "已完成",
    }


# ==================== 材料类型枚举 ====================
class MaterialType:
    ENTRUSTMENT_LETTER = "entrustment_letter"            # 委托书
    ID_CARD = "id_card"                                  # 身份证复印件
    TRAFFIC_ACCIDENT_CERT = "traffic_accident_cert"      # 道路交通事故认定书
    APPRAISAL_APPLICATION = "appraisal_application"       # 鉴定申请书
    MEDICAL_RECORD = "medical_record"                    # 医院病历
    IMAGING_REPORT = "imaging_report"                    # 影像学报告

    ALL = [ENTRUSTMENT_LETTER, ID_CARD, TRAFFIC_ACCIDENT_CERT,
           APPRAISAL_APPLICATION, MEDICAL_RECORD, IMAGING_REPORT]

    LABELS = {
        ENTRUSTMENT_LETTER: "委托书",
        ID_CARD: "身份证复印件",
        TRAFFIC_ACCIDENT_CERT: "道路交通事故认定书",
        APPRAISAL_APPLICATION: "鉴定申请书",
        MEDICAL_RECORD: "医院病历",
        IMAGING_REPORT: "影像学报告",
    }


# ==================== OCR 状态枚举 ====================
class OcrStatus:
    PENDING = "pending"          # 待识别
    PROCESSING = "processing"    # 识别中
    COMPLETED = "completed"      # 已完成
    FAILED = "failed"            # 识别失败

    ALL = [PENDING, PROCESSING, COMPLETED, FAILED]


# ==================== 数据表 ====================

class Case(Base):
    """案件表"""
    __tablename__ = "cases"

    id = Column(Integer, primary_key=True, index=True)
    case_number = Column(String(50), unique=True, index=True, comment="案件编号")

    # === 基本情况字段 ===
    entrusting_unit = Column(String(200), comment="委托单位（从委托书提取）")
    entrustment_matter = Column(Text, comment="委托事项（从委托书提取）")
    accident_date = Column(String(50), comment="事故发生日期（从认定书提取）")
    accident_location = Column(String(200), comment="事故发生地点（从认定书提取）")
    accident_description = Column(Text, comment="事故经过（从认定书原文摘抄）")
    acceptance_date = Column(String(20), comment="受理日期（鉴定人手动输入）")
    appraisal_date = Column(String(20), comment="鉴定日期 = 受理日期")
    appraisal_location = Column(String(200), default="新乡医学院司法鉴定中心", comment="鉴定地点")
    on_site_personnel = Column(String(200), comment="在场人员（可空）")
    material_list = Column(Text, comment="鉴定材料清单（自动生成）")
    person_name = Column(String(50), comment="被鉴定人姓名冗余（列表页展示用）")

    # === 法医临床检查 ===
    examination_date = Column(String(20), comment="法医检查日期")
    clinical_examination = Column(Text, comment="法医临床检查内容（自诉+查体等）")

    # === 用户确认标记 ===
    # 记录哪些字段已被用户手动保存确认，LLM提取/生成时不得覆盖已确认字段
    confirmed_fields = Column(Text, default="[]", comment="已确认字段列表（JSON数组）")

    # === 案件状态 ===
    status = Column(String(20), default=CaseStatus.PENDING_UPLOAD, nullable=False, comment="案件状态")

    # === 元数据 ===
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    # === 关联 ===
    person = relationship("Person", back_populates="case", uselist=False, cascade="all, delete-orphan")
    materials = relationship("Material", back_populates="case", cascade="all, delete-orphan")
    material_groups = relationship("MaterialGroup", back_populates="case", cascade="all, delete-orphan")
    hospital_records = relationship("HospitalRecord", back_populates="case", cascade="all, delete-orphan")
    imaging_reports = relationship("ImagingReport", back_populates="case", cascade="all, delete-orphan")
    report = relationship("Report", back_populates="case", uselist=False, cascade="all, delete-orphan")
    style_logs = relationship("StyleLog", back_populates="case", cascade="all, delete-orphan")


class Person(Base):
    """被鉴定人表（与案件一对一）"""
    __tablename__ = "persons"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), unique=True, nullable=False, comment="关联案件")
    name = Column(String(50), comment="姓名")
    gender = Column(String(10), comment="性别")
    birth_date = Column(String(20), comment="出生日期")
    id_number = Column(String(30), comment="身份证号")
    address = Column(Text, comment="住址")
    confirmed_fields = Column(Text, default="[]", comment="已确认字段列表（JSON数组）")

    # === 关联 ===
    case = relationship("Case", back_populates="person")


class MaterialGroup(Base):
    """材料分组表（病历按医院分组、影像学按医院分组）"""
    __tablename__ = "material_groups"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False, comment="关联案件")
    material_type = Column(String(30), nullable=False, comment="材料类型（medical_record / imaging_report）")
    group_name = Column(String(200), nullable=False, comment="分组名称（如：新乡市中心医院）")
    sort_order = Column(Integer, default=0, comment="排序序号")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")

    # === 关联 ===
    case = relationship("Case", back_populates="material_groups")
    materials = relationship("Material", back_populates="group", cascade="all, delete-orphan")


class Material(Base):
    """鉴定材料表"""
    __tablename__ = "materials"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False, comment="关联案件")
    group_id = Column(Integer, ForeignKey("material_groups.id"), comment="分组ID（病历/影像按医院分组时使用）")
    material_type = Column(String(30), nullable=False, comment="材料类型")
    description = Column(String(200), comment="材料描述（如：第1页、正面、反面）")
    page_number = Column(Integer, comment="页码（同一组内多页排序）")
    file_path = Column(String(500), nullable=False, comment="文件存储路径")
    original_filename = Column(String(200), comment="原始文件名")
    ocr_text = Column(Text, comment="OCR 原始识别文本")
    ocr_file_path = Column(String(500), comment="OCR 结果 md 文件路径")
    ocr_status = Column(String(20), default=OcrStatus.PENDING, comment="OCR 状态")
    created_at = Column(DateTime, default=datetime.now, comment="上传时间")

    # === 关联 ===
    case = relationship("Case", back_populates="materials")
    group = relationship("MaterialGroup", back_populates="materials")


class HospitalRecord(Base):
    """住院记录表"""
    __tablename__ = "hospital_records"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False, comment="关联案件")
    group_id = Column(Integer, ForeignKey("material_groups.id"), comment="来源分组（用于识别重新生成）")
    material_id = Column(Integer, ForeignKey("materials.id"), comment="来源材料")

    # === 基本信息 ===
    hospital_name = Column(String(200), comment="医院名称")
    admission_number = Column(String(50), comment="住院号")

    # === 病历内容 ===
    chief_complaint = Column(Text, comment="主诉")
    present_illness_history = Column(Text, comment="现病史")
    past_history = Column(Text, comment="既往史（可空）")
    physical_examination = Column(Text, comment="体格检查")
    admission_diagnosis = Column(Text, comment="入院诊断")

    # === 治疗过程 ===
    treatment_process = Column(Text, comment="治疗过程（可空）")
    medication = Column(Text, comment="用药情况（可空）")

    # === 出院信息 ===
    discharge_diagnosis = Column(Text, comment="出院诊断")
    discharge_orders = Column(Text, comment="出院医嘱")
    admission_date = Column(String(20), comment="入院日期")
    discharge_date = Column(String(20), comment="出院日期")
    hospital_days = Column(Integer, comment="住院天数")

    # === 关联 ===
    case = relationship("Case", back_populates="hospital_records")
    material = relationship("Material")


class ImagingReport(Base):
    """影像学报告表"""
    __tablename__ = "imaging_reports"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False, comment="关联案件")
    material_id = Column(Integer, ForeignKey("materials.id"), comment="来源材料")

    # === 报告信息 ===
    report_date = Column(String(20), comment="报告日期")
    hospital_name = Column(String(200), comment="医院名称")
    exam_type = Column(String(50), comment="检查类型（CT/X线/MRI等）")
    exam_part = Column(String(100), comment="检查部位（头颅、胸部、左锁骨等）")
    film_number = Column(String(50), comment="片子编号")
    film_count = Column(Integer, default=1, comment="片子数量")
    report_content = Column(Text, comment="报告内容")

    # === 关联 ===
    case = relationship("Case", back_populates="imaging_reports")
    material = relationship("Material")


class Report(Base):
    """报告表（与案件一对一）"""
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), unique=True, nullable=False, comment="关联案件")

    # === 报告六大部分 ===
    case_facts = Column(Text, comment="基本案情")
    material_summary = Column(Text, comment="资料摘要")
    appraisal_process = Column(Text, comment="鉴定过程")
    analysis = Column(Text, comment="分析说明")
    opinion = Column(Text, comment="鉴定意见")

    # === 确认状态 ===
    opinion_confirmed = Column(Boolean, default=False, comment="鉴定意见是否已确认")
    confirmed_fields = Column(Text, default="[]", comment="已确认字段列表（JSON数组）")

    # === 元数据 ===
    generated_at = Column(DateTime, comment="报告生成时间")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    # === 关联 ===
    case = relationship("Case", back_populates="report")


# ==================== 风格学习枚举 ====================
class ReportSection:
    """报告部分枚举"""
    CASE_FACTS = "case_facts"                # 基本案情
    MATERIAL_SUMMARY = "material_summary"    # 资料摘要
    APPRAISAL_PROCESS = "appraisal_process"  # 鉴定过程
    ANALYSIS = "analysis"                    # 分析说明
    OPINION = "opinion"                      # 鉴定意见

    ALL = [CASE_FACTS, MATERIAL_SUMMARY, APPRAISAL_PROCESS, ANALYSIS, OPINION]

    LABELS = {
        CASE_FACTS: "基本案情",
        MATERIAL_SUMMARY: "资料摘要",
        APPRAISAL_PROCESS: "鉴定过程",
        ANALYSIS: "分析说明",
        OPINION: "鉴定意见",
    }


class StyleLog(Base):
    """风格学习记录表"""
    __tablename__ = "style_logs"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False, comment="关联案件")
    section = Column(String(30), nullable=False, comment="修改的报告部分")
    original_text = Column(Text, comment="AI 自动生成的原文")
    revised_text = Column(Text, comment="鉴定人修改后的文本")
    diff_summary = Column(Text, comment="修改差异摘要（自动生成）")
    created_at = Column(DateTime, default=datetime.now, comment="记录时间")

    # === 关联 ===
    case = relationship("Case", back_populates="style_logs")


class AppSettings(Base):
    """系统配置表（键值对）"""
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False, index=True, comment="配置键")
    value = Column(Text, comment="配置值")
