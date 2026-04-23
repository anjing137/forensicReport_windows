<template>
  <el-container class="layout-container">
    <el-aside width="220px" class="sidebar">
      <div class="logo">
        <el-icon><Document /></el-icon>
        <span>鉴定报告系统</span>
      </div>
      <el-menu
        :default-active="$route.path"
        router
        class="sidebar-menu"
      >
        <el-menu-item index="/dashboard">
          <el-icon><House /></el-icon>
          <span>工作台</span>
        </el-menu-item>
        <el-menu-item index="/cases">
          <el-icon><FolderOpened /></el-icon>
          <span>案件列表</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="header">
        <div class="header-left">
          <el-breadcrumb separator="/">
            <el-breadcrumb-item :to="{ path: '/' }">首页</el-breadcrumb-item>
            <el-breadcrumb-item>{{ $route.meta.title }}</el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <div class="header-right">
          <span class="user-info" @click="showAppraiserDialog = true">
            <el-icon><User /></el-icon>
            {{ appraiserDisplay }}
          </span>
        </div>
      </el-header>

      <el-main class="main-content">
        <router-view />
      </el-main>
    </el-container>

    <!-- 鉴定人信息编辑对话框 -->
    <el-dialog v-model="showAppraiserDialog" title="鉴定人信息" width="450px">
      <el-form :model="appraiserForm" label-width="80px">
        <el-form-item label="姓名">
          <el-input v-model="appraiserForm.name" placeholder="鉴定人姓名" />
        </el-form-item>
        <el-form-item label="职称">
          <el-input v-model="appraiserForm.title" placeholder="如：副教授、主任法医师" />
        </el-form-item>
        <el-form-item label="工作单位">
          <el-input v-model="appraiserForm.unit" placeholder="如：新乡医学院司法鉴定中心" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAppraiserDialog = false">取消</el-button>
        <el-button type="primary" @click="saveAppraiser" :loading="saving">保存</el-button>
      </template>
    </el-dialog>
  </el-container>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { House, FolderOpened, Document, User } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import api from '@/api'

const showAppraiserDialog = ref(false)
const saving = ref(false)

const appraiserForm = ref({
  name: '',
  title: '',
  unit: '',
})

// 右上角显示文字
const appraiserDisplay = computed(() => {
  if (appraiserForm.value.name) {
    return appraiserForm.value.name
  }
  return '鉴定人'
})

onMounted(async () => {
  await loadAppraiser()
})

async function loadAppraiser() {
  try {
    const data = await api.getAppraiser()
    appraiserForm.value = {
      name: data.name || '',
      title: data.title || '',
      unit: data.unit || '',
    }
  } catch (e) {
    // 首次可能还没数据，忽略
  }
}

async function saveAppraiser() {
  saving.value = true
  try {
    await api.updateAppraiser(appraiserForm.value)
    ElMessage.success('保存成功')
    showAppraiserDialog.value = false
  } catch (e) {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<style lang="scss" scoped>
.layout-container {
  height: 100vh;
}

.sidebar {
  background: #1d4ed8;
  .logo {
    height: 60px;
    display: flex;
    align-items: center;
    padding: 0 20px;
    color: white;
    font-size: 18px;
    font-weight: bold;
    .el-icon {
      margin-right: 10px;
      font-size: 24px;
    }
  }
  .sidebar-menu {
    border-right: none;
    background: transparent;
    :deep(.el-menu-item) {
      color: rgba(255,255,255,0.8);
      &.is-active {
        background: rgba(255,255,255,0.2);
        color: white;
      }
      &:hover {
        background: rgba(255,255,255,0.1);
        color: white;
      }
    }
  }
}

.header {
  background: white;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #e4e7ed;
  .user-info {
    display: flex;
    align-items: center;
    cursor: pointer;
    padding: 6px 12px;
    border-radius: 6px;
    transition: background 0.2s;
    &:hover {
      background: #f0f2f5;
    }
    .el-icon {
      margin-right: 5px;
    }
    color: #409EFF;
    font-weight: 500;
  }
}

.main-content {
  background: #f5f7fa;
  padding: 20px;
}
</style>
