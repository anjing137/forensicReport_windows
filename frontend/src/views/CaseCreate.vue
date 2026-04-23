<template>
  <div class="case-create">
    <el-card>
      <template #header>
        <span>新建案件</span>
      </template>

      <el-result icon="info" title="创建案件" sub-title="只需输入案件编号，其他信息通过上传材料自动识别">
        <template #extra>
          <el-form :model="form" :rules="rules" ref="formRef" label-width="100px" style="max-width: 400px; margin: 0 auto;">
            <el-form-item label="案件编号" prop="case_number">
              <el-input v-model="form.case_number" placeholder="如：2026-XX-XXX" style="width: 250px;" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="handleSubmit" :loading="submitting">创建并上传材料</el-button>
              <el-button @click="$router.back()">取消</el-button>
            </el-form-item>
          </el-form>
        </template>
      </el-result>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '@/api'

const router = useRouter()
const formRef = ref()
const submitting = ref(false)

const form = reactive({
  case_number: '',
})

const rules = {
  case_number: [{ required: true, message: '请输入案件编号', trigger: 'blur' }],
}

async function handleSubmit() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  submitting.value = true
  try {
    const res = await api.createCase(form)
    ElMessage.success('案件创建成功，请上传材料')
    router.push(`/cases/${res.id}`)
  } catch (e) {
    console.error('创建失败', e)
  } finally {
    submitting.value = false
  }
}
</script>

<style lang="scss" scoped>
.case-create {
  max-width: 700px;
  margin: 0 auto;
}
</style>
