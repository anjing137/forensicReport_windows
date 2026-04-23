import axios from 'axios'
import { ElMessage } from 'element-plus'

const api = axios.create({
  baseURL: '/api',
  timeout: 120000  // OCR/LLM 提取可能需要较长时间
})

// 请求拦截器
api.interceptors.request.use(
  config => config,
  error => Promise.reject(error)
)

// 响应拦截器
api.interceptors.response.use(
  response => response.data,
  error => {
    const msg = error.response?.data?.detail || '请求失败'
    ElMessage.error(msg)
    return Promise.reject(error)
  }
)

export default {
  // ===== 案件管理 =====
  getCases: (params) => api.get('/cases', { params }),
  getCase: (id) => api.get(`/cases/${id}`),
  createCase: (data) => api.post('/cases', data),
  updateCase: (id, data) => api.put(`/cases/${id}`, data),
  deleteCase: (id) => api.delete(`/cases/${id}`),
  
  // 案件状态操作
  startRecognition: (id) => api.post(`/cases/${id}/start-recognition`),
  recognizeSingle: (caseId, materialId) => api.post(`/cases/${caseId}/materials/${materialId}/recognize`),
  recognizeAll: (id) => api.post(`/cases/${id}/recognize-all`),
  stopRecognize: (id) => api.post(`/cases/${id}/stop-recognize`),
  forceStopRecognize: (id) => api.post(`/cases/${id}/force-stop-recognize`),
  getRecognizeStatus: (id) => api.get(`/cases/${id}/recognize-status`),
  submitReview: (id) => api.post(`/cases/${id}/submit-review`),
  confirmCase: (id) => api.post(`/cases/${id}/confirm`),
  reopenCase: (id) => api.post(`/cases/${id}/reopen`),

  // ===== 材料管理 =====
  uploadMaterial: (caseId, file, materialType, groupId = null, description = null) => {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('material_type', materialType)
    if (groupId) formData.append('group_id', groupId)
    if (description) formData.append('description', description)
    return api.post(`/materials/upload/${caseId}`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
  },
  uploadMaterialsBatch: (caseId, files, materialType, groupId = null, description = null) => {
    const formData = new FormData()
    for (const file of files) {
      formData.append('files', file)
    }
    formData.append('material_type', materialType)
    if (groupId) formData.append('group_id', groupId)
    if (description) formData.append('description', description)
    return api.post(`/materials/upload-batch/${caseId}`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
  },
  getCaseMaterials: (caseId, materialType = null) => {
    const params = materialType ? { material_type: materialType } : {}
    return api.get(`/materials/case/${caseId}`, { params })
  },
  getCaseMaterialsGrouped: (caseId) => api.get(`/materials/case/${caseId}/grouped`),
  deleteMaterial: (id) => api.delete(`/materials/${id}`),
  updateMaterial: (id, data) => api.put(`/materials/${id}`, data),
  updateOcrText: (id, ocrText) => api.put(`/materials/${id}/ocr-text`, { ocr_text: ocrText }),

  // 材料分组
  createMaterialGroup: (data) => api.post('/materials/groups', data),
  getMaterialGroups: (caseId, materialType = null) => {
    const params = materialType ? { material_type: materialType } : {}
    return api.get(`/materials/groups/case/${caseId}`, { params })
  },
  updateMaterialGroup: (groupId, data) => api.put(`/materials/groups/${groupId}`, data),
  deleteMaterialGroup: (groupId) => api.delete(`/materials/groups/${groupId}`),

  // ===== PDF 转换 =====
  uploadPdf: (caseId, file) => {
    const formData = new FormData()
    formData.append('file', file)
    return api.post(`/materials/upload-pdf/${caseId}`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
  },
  getPdfPages: (caseId) => api.get(`/materials/case/${caseId}/pdf-pages`),
  deletePdfPage: (caseId, filename) => api.delete(`/materials/pdf-page/${caseId}/${encodeURIComponent(filename)}`),
  deletePdf: (caseId, prefix) => api.delete(`/materials/pdf/${caseId}/${encodeURIComponent(prefix)}`),
  importPdfPages: (caseId, data) => api.post(`/materials/import-pdf-pages/${caseId}`, data),
  revertPdfImport: (caseId, filename) => api.post(`/materials/revert-import/${caseId}/${encodeURIComponent(filename)}`),

  // ===== 被鉴定人 =====
  getPerson: (caseId) => api.get(`/persons/case/${caseId}`),
  createPerson: (data) => api.post('/persons', data),
  updatePersonByCase: (caseId, data) => api.put(`/persons/case/${caseId}`, data),

  // ===== 住院记录 =====
  getHospitalRecords: (caseId) => api.get(`/hospital-records/case/${caseId}`),
  createHospitalRecord: (data) => api.post('/hospital-records', data),
  updateHospitalRecord: (id, data) => api.put(`/hospital-records/${id}`, data),
  deleteHospitalRecord: (id) => api.delete(`/hospital-records/${id}`),

  // ===== 影像学报告 =====
  getImagingReports: (caseId) => api.get(`/imaging-reports/case/${caseId}`),
  createImagingReport: (data) => api.post('/imaging-reports', data),
  updateImagingReport: (id, data) => api.put(`/imaging-reports/${id}`, data),
  deleteImagingReport: (id) => api.delete(`/imaging-reports/${id}`),

  // ===== 报告 =====
  getReport: (caseId) => api.get(`/reports/case/${caseId}`),
  createReport: (data) => api.post('/reports', data),
  updateReport: (id, data) => api.put(`/reports/${id}`, data),
  confirmOpinion: (id) => api.post(`/reports/${id}/confirm-opinion`),
  unconfirmOpinion: (id) => api.post(`/reports/${id}/unconfirm-opinion`),
  generateWord: (id) => api.post(`/reports/${id}/generate-word`),

  // ===== 风格学习 =====
  getStyleLogs: (caseId) => api.get(`/style-logs/case/${caseId}`),
  createStyleLog: (data) => api.post('/style-logs', data),
  getStyleStats: () => api.get('/style-logs/stats'),

  // ===== LLM 智能提取 =====
  // 全局提取（旧接口，保留兼容）
  extractAll: (caseId) => api.post(`/llm/cases/${caseId}/extract-all`),
  extractSingle: (materialId) => api.post(`/llm/materials/${materialId}/extract`),
  // 按页面提取（新接口）
  extractBasicInfo: (caseId) => api.post(`/llm/cases/${caseId}/extract-basic-info`),
  extractCaseFacts: (caseId) => api.post(`/llm/cases/${caseId}/extract-case-facts`),
  extractMedicalRecords: (caseId) => api.post(`/llm/cases/${caseId}/extract-medical-records`),
  // 病历按医院分组提取
  getMedicalGroups: (caseId) => api.get(`/llm/cases/${caseId}/medical-groups`),
  extractMedicalGroup: (caseId, groupId) => api.post(`/llm/cases/${caseId}/extract-medical-group/${groupId}`),
  generateMaterialSummary: (caseId) => api.post(`/llm/cases/${caseId}/generate-material-summary`),
  generateAppraisalProcess: (caseId) => api.post(`/llm/cases/${caseId}/generate-appraisal-process`),
  extractImagingReports: (caseId) => api.post(`/llm/cases/${caseId}/extract-imaging-reports`),
  generateAnalysis: (caseId) => api.post(`/llm/cases/${caseId}/generate-analysis`),
  generateOpinion: (caseId) => api.post(`/llm/cases/${caseId}/generate-opinion`),

  // ===== 系统配置 =====
  getAppraiser: () => api.get('/settings/appraiser'),
  updateAppraiser: (data) => api.put('/settings/appraiser', data),
}
