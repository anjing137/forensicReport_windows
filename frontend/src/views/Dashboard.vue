<template>
  <div class="dashboard">
    <el-row :gutter="16">
      <el-col :span="8">
        <div class="stat-card" @click="filterByStatus('draft')">
          <div class="stat-icon draft"><el-icon><Edit /></el-icon></div>
          <div class="stat-info">
            <div class="stat-value">{{ draftCount }}</div>
            <div class="stat-label">进行中</div>
          </div>
        </div>
      </el-col>
      <el-col :span="8">
        <div class="stat-card" @click="filterByStatus('completed')">
          <div class="stat-icon completed"><el-icon><CircleCheck /></el-icon></div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.completed || 0 }}</div>
            <div class="stat-label">已完成</div>
          </div>
        </div>
      </el-col>
      <el-col :span="8">
        <div class="stat-card" @click="filterByStatus('all')">
          <div class="stat-icon total"><el-icon><FolderOpened /></el-icon></div>
          <div class="stat-info">
            <div class="stat-value">{{ totalCases }}</div>
            <div class="stat-label">全部案件</div>
          </div>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="20" style="margin-top: 20px;">
      <el-col :span="16">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>最近案件</span>
              <el-button type="primary" size="small" @click="$router.push('/cases/create')">
                <el-icon><Plus /></el-icon> 新建案件
              </el-button>
            </div>
          </template>
          <el-table :data="recentCases" style="width: 100%">
            <el-table-column prop="case_number" label="案件编号" width="160" />
            <el-table-column prop="person_name" label="被鉴定人" width="100" />
            <el-table-column prop="entrusting_unit" label="委托单位" />
            <el-table-column prop="status" label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="row.status === 'completed' ? 'success' : 'warning'" size="small">
                  {{ row.status === 'completed' ? '已完成' : '进行中' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="80">
              <template #default="{ row }">
                <el-button link type="primary" @click="$router.push({ name: 'CaseDetail', params: { id: row.id } })">查看</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card>
          <template #header>
            <span>快捷操作</span>
          </template>
          <div class="quick-actions">
            <el-button type="primary" plain style="width: 100%; margin-bottom: 10px;" @click="$router.push('/cases/create')">
              <el-icon><Plus /></el-icon> 新建案件
            </el-button>
            <el-button type="success" plain style="width: 100%; margin-bottom: 10px;" @click="$router.push('/cases')">
              <el-icon><FolderOpened /></el-icon> 案件列表
            </el-button>
          </div>
        </el-card>

        <el-card style="margin-top: 16px;">
          <template #header>
            <span>工作流程</span>
          </template>
          <el-timeline>
            <el-timeline-item type="primary">1. 创建案件</el-timeline-item>
            <el-timeline-item type="primary">2. 上传材料（6类）</el-timeline-item>
            <el-timeline-item type="primary">3. OCR识别（可随时追加材料）</el-timeline-item>
            <el-timeline-item type="primary">4. 智能提取 + 修正内容</el-timeline-item>
            <el-timeline-item type="primary">5. 确认鉴定意见</el-timeline-item>
            <el-timeline-item type="success">6. 生成 Word 报告</el-timeline-item>
          </el-timeline>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Edit, CircleCheck, Plus, FolderOpened } from '@element-plus/icons-vue'
import api from '@/api'

const router = useRouter()
const recentCases = ref([])
const stats = ref({})

const totalCases = computed(() => {
  return Object.values(stats.value).reduce((a, b) => a + b, 0)
})

const draftCount = computed(() => {
  const s = stats.value
  return (s.pending_upload || 0) + (s.recognizing || 0) + (s.pending_review || 0) +
    (s.reviewing || 0) + (s.pending_confirm || 0)
})

onMounted(async () => {
  try {
    const res = await api.getCases({ skip: 0, limit: 50 })
    const allCases = Array.isArray(res) ? res : []
    recentCases.value = allCases.slice(0, 8)

    const result = {}
    for (const c of allCases) {
      result[c.status] = (result[c.status] || 0) + 1
    }
    stats.value = result
  } catch (e) {
    console.error('获取数据失败', e)
  }
})

function filterByStatus(status) {
  if (status === 'all') {
    router.push({ path: '/cases' })
  } else {
    router.push({ path: '/cases', query: { status } })
  }
}
</script>

<style lang="scss" scoped>
.dashboard {
  .stat-card {
    background: white;
    border-radius: 8px;
    padding: 16px;
    display: flex;
    align-items: center;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    cursor: pointer;
    transition: transform 0.2s;
    &:hover { transform: translateY(-2px); }
    .stat-icon {
      width: 48px;
      height: 48px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      margin-right: 12px;
      .el-icon { font-size: 22px; color: white; }
      &.draft { background: #e6a23c; }
      &.completed { background: #10b981; }
      &.total { background: #409EFF; }
    }
    .stat-info {
      .stat-value { font-size: 24px; font-weight: bold; color: #1f2937; }
      .stat-label { color: #6b7280; font-size: 13px; }
    }
  }
  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .quick-actions {
    .el-button { justify-content: flex-start; }
  }
}
</style>
