<template>
  <div class="templates">
    <el-card>
      <template #header>
        <span>报告模板管理</span>
      </template>

      <el-table :data="templates" v-loading="loading">
        <el-table-column prop="name" label="模板名称" />
        <el-table-column prop="template_type" label="类型" width="120" />
        <el-table-column label="默认" width="80">
          <template #default="{ row }">
            <el-tag v-if="row.is_default" type="success" size="small">默认</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180" />
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="handlePreview(row)">预览</el-button>
            <el-button link type="warning" size="small" @click="handleEdit(row)">编辑</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/api'

const loading = ref(false)
const templates = ref([])

onMounted(async () => {
  try {
    templates.value = await api.getTemplates()
  } catch (e) {
    ElMessage.error('加载模板失败')
  }
})

function handlePreview(row) {
  // TODO: 实现预览
}

function handleEdit(row) {
  // TODO: 实现编辑
}
</script>
