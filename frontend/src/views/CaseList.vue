<template>
  <div class="case-list">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>案件列表</span>
          <el-button type="primary" @click="$router.push('/cases/create')">
            <el-icon><Plus /></el-icon> 新建案件
          </el-button>
        </div>
      </template>

      <div class="filter-bar">
        <el-input
          v-model="searchKeyword"
          placeholder="搜索案件编号或被鉴定人"
          style="width: 250px; margin-right: 10px;"
          clearable
          @keyup.enter="loadCases"
        >
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-select v-model="filterStatus" placeholder="状态筛选" style="width: 140px; margin-right: 10px;" clearable>
          <el-option label="全部" value="" />
          <el-option label="进行中" value="draft" />
          <el-option label="已完成" value="completed" />
        </el-select>
        <el-button @click="loadCases">搜索</el-button>
      </div>

      <el-table :data="cases" v-loading="loading" style="margin-top: 20px;">
        <el-table-column prop="case_number" label="案件编号" width="160" />
        <el-table-column prop="person_name" label="被鉴定人" width="100" />
        <el-table-column prop="entrusting_unit" label="委托单位" />
        <el-table-column prop="status_label" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="STATUS_TAG_TYPE[row.status] || 'info'" size="small">
              {{ STATUS_LABELS[row.status] || row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="handleView(row)">查看</el-button>
            <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search } from '@element-plus/icons-vue'
import api from '@/api'
import { STATUS_LABELS, STATUS_TAG_TYPE } from '@/store'

const router = useRouter()
const route = useRoute()
const loading = ref(false)
const searchKeyword = ref('')
const filterStatus = ref('')
const cases = ref([])

onMounted(() => {
  // 从 Dashboard 跳转过来时，读取 query 参数
  if (route.query.status) {
    filterStatus.value = route.query.status
  }
  loadCases()
})

// 监听 route 变化（Dashboard 点击状态卡片跳转时）
watch(() => route.query.status, (newStatus) => {
  filterStatus.value = newStatus || ''
  loadCases()
})

async function loadCases() {
  loading.value = true
  try {
    const res = await api.getCases({
      keyword: searchKeyword.value,
      status: filterStatus.value || undefined,
    })
    cases.value = Array.isArray(res) ? res : []
  } catch (e) {
    console.error('加载失败', e)
  } finally {
    loading.value = false
  }
}

function handleView(row) {
  router.push({ name: 'CaseDetail', params: { id: row.id } })
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm('确定要删除这个案件吗？', '提示', { type: 'warning' })
    await api.deleteCase(row.id)
    ElMessage.success('删除成功')
    loadCases()
  } catch (e) {
    if (e !== 'cancel') console.error('删除失败', e)
  }
}

function formatDate(dt) {
  if (!dt) return '-'
  return new Date(dt).toLocaleString('zh-CN')
}
</script>

<style lang="scss" scoped>
.case-list {
  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .filter-bar {
    display: flex;
    align-items: center;
  }
}
</style>
