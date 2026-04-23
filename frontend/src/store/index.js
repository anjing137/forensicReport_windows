import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/api'

// 案件状态配置
export const CASE_STATUS = {
  PENDING_UPLOAD: 'pending_upload',
  RECOGNIZING: 'recognizing',
  PENDING_REVIEW: 'pending_review',
  REVIEWING: 'reviewing',
  PENDING_CONFIRM: 'pending_confirm',
  COMPLETED: 'completed',
}

export const STATUS_LABELS = {
  pending_upload: '进行中',
  recognizing: '进行中',
  pending_review: '进行中',
  reviewing: '进行中',
  pending_confirm: '进行中',
  completed: '已完成',
}

export const STATUS_TAG_TYPE = {
  pending_upload: 'warning',
  recognizing: 'warning',
  pending_review: 'warning',
  reviewing: 'warning',
  pending_confirm: 'warning',
  completed: 'success',
}

// 材料类型配置
export const MATERIAL_TYPES = {
  entrustment_letter: '委托书',
  id_card: '身份证复印件',
  traffic_accident_cert: '道路交通事故认定书',
  appraisal_application: '鉴定申请书',
  medical_record: '医院病历',
  imaging_report: '影像学报告',
}

export const OCR_STATUS_LABELS = {
  pending: '待识别',
  processing: '识别中',
  completed: '已完成',
  failed: '失败',
}

export const OCR_STATUS_TAG = {
  pending: 'info',
  processing: 'warning',
  completed: 'success',
  failed: 'danger',
}

export const useCaseStore = defineStore('case', () => {
  const currentCase = ref(null)
  const cases = ref([])
  const loading = ref(false)

  // 统计数据
  const stats = computed(() => {
    const result = {
      pending_upload: 0,
      recognizing: 0,
      pending_review: 0,
      reviewing: 0,
      pending_confirm: 0,
      completed: 0,
    }
    for (const c of cases.value) {
      if (result[c.status] !== undefined) {
        result[c.status]++
      }
    }
    return result
  })

  async function fetchCases(params) {
    loading.value = true
    try {
      const res = await api.getCases(params)
      cases.value = Array.isArray(res) ? res : []
      return res
    } finally {
      loading.value = false
    }
  }

  async function fetchCase(id) {
    loading.value = true
    try {
      const res = await api.getCase(id)
      currentCase.value = res
      return res
    } finally {
      loading.value = false
    }
  }

  async function createCase(data) {
    const res = await api.createCase(data)
    return res
  }

  async function updateCase(id, data) {
    const res = await api.updateCase(id, data)
    if (currentCase.value?.id === id) {
      currentCase.value = { ...currentCase.value, ...res }
    }
    return res
  }

  return {
    currentCase,
    cases,
    loading,
    stats,
    fetchCases,
    fetchCase,
    createCase,
    updateCase,
  }
})
