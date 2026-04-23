<template>
  <div class="case-detail">
    <!-- 顶部操作栏 -->
    <div class="top-bar">
      <el-page-header @back="$router.push('/cases')">
        <template #content>
          <span class="case-title">{{ caseData.case_number || '案件详情' }}</span>
          <el-tag :type="isCompleted ? 'success' : 'warning'" size="small" style="margin-left: 10px;">
            {{ isCompleted ? '已完成' : '进行中' }}
          </el-tag>
        </template>
      </el-page-header>
      <div class="top-actions">
        <el-button v-if="!isCompleted" type="success" @click="handleComplete">
          <el-icon><CircleCheck /></el-icon> 完成案件
        </el-button>
        <el-button v-if="isCompleted" type="warning" @click="handleReopen">
          <el-icon><RefreshLeft /></el-icon> 重新打开
        </el-button>
      </div>
    </div>

    <!-- 三大主 Tab -->
    <el-tabs v-model="activeMainTab" type="border-card">
      <!-- ===== Tab 1: 上传材料 ===== -->
      <el-tab-pane name="upload">
        <template #label>
          <span><el-icon><Upload /></el-icon> 上传材料</span>
        </template>
        <div class="upload-panel">
          <!-- ===== PDF 转换区 ===== -->
          <div class="pdf-section">
            <div class="pdf-section-header">
              <span class="pdf-section-title">
                <el-icon><Document /></el-icon> PDF 转换
              </span>
              <div class="pdf-view-toggle">
                <el-button-group size="small">
                  <el-button :type="pdfViewMode === 'thumbnail' ? 'primary' : ''" @click="pdfViewMode = 'thumbnail'">
                    <el-icon><Grid /></el-icon> 缩略图
                  </el-button>
                  <el-button :type="pdfViewMode === 'list' ? 'primary' : ''" @click="pdfViewMode = 'list'">
                    <el-icon><List /></el-icon> 列表
                  </el-button>
                </el-button-group>
              </div>
            </div>

            <!-- 上传区 -->
            <div class="pdf-upload-area">
              <input ref="pdfUploadInput" type="file" accept=".pdf" style="display: none;" @change="handlePdfFileSelected" />
              <el-button type="primary" size="default" @click="triggerPdfUpload">
                <el-icon><Upload /></el-icon> 上传 PDF 文件
              </el-button>
              <span class="pdf-hint">支持 .pdf 文件，点击或拖拽上传</span>

              <!-- 待转换的 PDF 列表 -->
              <div v-if="uploadedPdfs.filter(p => !p.converted).length" class="uploaded-pdfs">
                <el-divider content-position="left">待转换 PDF</el-divider>
                <div v-for="pdf in uploadedPdfs.filter(p => !p.converted)" :key="pdf.tempId" class="pdf-item">
                  <el-icon><Document /></el-icon>
                  <span class="pdf-name">{{ pdf.filename }}</span>
                  <span class="pdf-size">{{ (pdf.size / 1024).toFixed(1) }} KB</span>
                  <el-button
                    v-if="!pdf.converting"
                    type="primary"
                    size="small"
                    @click="convertPdf(pdf)"
                    :loading="pdf.converting"
                  >
                    转成图片
                  </el-button>
                  <el-button
                    link
                    type="danger"
                    size="small"
                    @click="removeUploadedPdf(pdf.tempId)"
                  >
                    删除
                  </el-button>
                </div>
              </div>

              <!-- 已转换的 PDF 列表 -->
              <div v-if="uploadedPdfs.filter(p => p.converted).length" class="converted-pdfs">
                <el-divider content-position="left">已转换 PDF</el-divider>
                <div v-for="pdf in uploadedPdfs.filter(p => p.converted)" :key="pdf.tempId" class="pdf-item">
                  <el-icon><Document /></el-icon>
                  <span class="pdf-name">{{ pdf.filename }}</span>
                  <el-tag type="success" size="small">已转换 {{ pdf.pageCount }} 页</el-tag>
                  <el-button
                    link
                    type="danger"
                    size="small"
                    @click="removeUploadedPdf(pdf.tempId)"
                  >
                    删除
                  </el-button>
                </div>
              </div>
            </div>

            <!-- 转换进度 -->
            <div v-if="pdfConverting" class="pdf-converting">
              <el-icon class="is-loading" size="20"><Loading /></el-icon>
              <span>正在转换 PDF，请稍候...</span>
            </div>

            <!-- PDF 折叠面板视图 -->
            <div v-if="uploadedPdfs.length && !pdfConverting" class="pdf-fold-view">
              <div class="pdf-fold-toolbar">
                <span class="selected-count" v-if="selectedPdfPages.length">
                  已选 {{ selectedPdfPages.length }} 张
                </span>
                <div class="import-controls" v-if="selectedPdfPages.length">
                  <el-select v-model="importTargetType" placeholder="选择类型" size="small" style="width: 140px;">
                    <el-option v-for="cat in materialCategories" :key="cat.type" :label="cat.label" :value="cat.type" />
                  </el-select>
                  <el-select
                    v-if="getCategoryGrouped(importTargetType)"
                    v-model="importTargetGroupId"
                    placeholder="选择医院"
                    size="small"
                    style="width: 160px;"
                    clearable
                  >
                    <el-option
                      v-for="g in getGroupsForType(importTargetType)"
                      :key="g.id"
                      :label="g.group_name"
                      :value="g.id"
                    />
                  </el-select>
                  <el-input
                    v-if="getCategoryGrouped(importTargetType) && !importTargetGroupId"
                    v-model="pdfNewGroupName"
                    placeholder="新建医院组名"
                    size="small"
                    style="width: 120px;"
                  />
                  <el-button type="primary" size="small" @click="importSelectedPdfPages">
                    导入选中
                  </el-button>
                </div>
              </div>

              <!-- 每个 PDF 的折叠卡片 -->
              <div v-for="pdf in uploadedPdfs" :key="pdf.tempId" class="pdf-fold-card">
                <!-- PDF 头部：可点击展开/折叠 -->
                <div class="pdf-fold-header" @click="pdf.expanded = !pdf.expanded">
                  <div class="pdf-fold-left">
                    <el-icon class="fold-arrow" :class="{ 'is-expanded': pdf.expanded }">
                      <ArrowRight />
                    </el-icon>
                    <el-icon class="pdf-icon"><Document /></el-icon>
                    <span class="pdf-filename" :title="pdf.filename">{{ pdf.filename }}</span>
                    <el-tag v-if="pdf.converted" type="success" size="small">
                      {{ pdf.pageCount }} 页
                    </el-tag>
                    <el-tag v-else type="info" size="small">待转换</el-tag>
                  </div>
                  <div class="pdf-fold-right">
                    <template v-if="pdf.converted && pdf.pages">
                      <span class="page-summary">
                        已导入 {{ pdf.pages.filter(p => p.imported).length }} / {{ pdf.pages.length }} 页
                      </span>
                      <el-checkbox
                        :model-value="getPdfSelectedCount(pdf.tempId) === pdf.pages.filter(p => !p.imported).length && pdf.pages.filter(p => !p.imported).length > 0"
                        :indeterminate="getPdfSelectedCount(pdf.tempId) > 0 && getPdfSelectedCount(pdf.tempId) < pdf.pages.filter(p => !p.imported).length"
                        @click.stop
                        @change="(checked) => toggleAllPdfPagesOfPdf(pdf, checked)"
                      />
                    </template>
                    <el-button
                      v-if="!pdf.converted && !pdf.converting"
                      type="primary"
                      size="small"
                      @click.stop="convertPdf(pdf)"
                    >
                      转成图片
                    </el-button>
                    <span v-if="pdf.converting" class="converting-text">
                      <el-icon class="is-loading"><Loading /></el-icon> 转换中...
                    </span>
                    <el-button
                      link
                      type="danger"
                      size="small"
                      @click.stop="removeUploadedPdf(pdf.tempId)"
                      title="删除"
                    >
                      <el-icon><Delete /></el-icon>
                    </el-button>
                  </div>
                </div>

                <!-- PDF 内容：缩略图/列表（展开时显示） -->
                <div v-if="pdf.expanded && pdf.converted && pdf.pages" class="pdf-fold-body">
                  <!-- 内嵌工具栏 -->
                  <div class="pdf-fold-toolbar-inline">
                    <el-checkbox
                      :model-value="getPdfSelectedCount(pdf.tempId) === pdf.pages.filter(p => !p.imported).length && pdf.pages.filter(p => !p.imported).length > 0"
                      :indeterminate="getPdfSelectedCount(pdf.tempId) > 0 && getPdfSelectedCount(pdf.tempId) < pdf.pages.filter(p => !p.imported).length"
                      @change="(checked) => toggleAllPdfPagesOfPdf(pdf, checked)"
                    >
                      全选
                    </el-checkbox>
                    <span class="selected-count" v-if="getPdfSelectedCount(pdf.tempId)">
                      已选 {{ getPdfSelectedCount(pdf.tempId) }} 张
                    </span>
                    <div class="import-controls-inline" v-if="getPdfSelectedCount(pdf.tempId)">
                      <el-select v-model="importTargetType" placeholder="选择类型" size="small" style="width: 130px;">
                        <el-option v-for="cat in materialCategories" :key="cat.type" :label="cat.label" :value="cat.type" />
                      </el-select>
                      <el-select
                        v-if="getCategoryGrouped(importTargetType)"
                        v-model="importTargetGroupId"
                        placeholder="选择医院"
                        size="small"
                        style="width: 150px;"
                        clearable
                      >
                        <el-option
                          v-for="g in getGroupsForType(importTargetType)"
                          :key="g.id"
                          :label="g.group_name"
                          :value="g.id"
                        />
                      </el-select>
                      <el-input
                        v-if="getCategoryGrouped(importTargetType) && !importTargetGroupId"
                        v-model="pdfNewGroupName"
                        placeholder="新建医院组"
                        size="small"
                        style="width: 110px;"
                      />
                      <el-button type="primary" size="small" @click="importSelectedPdfPagesOfPdf(pdf)">
                        导入选中
                      </el-button>
                    </div>
                  </div>

                  <!-- 缩略图视图 -->
                  <div v-if="pdfViewMode === 'thumbnail'" class="pdf-pages-grid">
                    <div
                      v-for="page in pdf.pages"
                      :key="page.filename"
                      class="pdf-page-thumb"
                      :class="{ 'is-imported': page.imported, 'is-selected': selectedPdfPages.some(s => s.pdfTempId === pdf.tempId && s.filename === page.filename) }"
                    >
                      <div class="thumb-select">
                        <el-checkbox
                          :model-value="selectedPdfPages.some(s => s.pdfTempId === pdf.tempId && s.filename === page.filename)"
                          :disabled="page.imported"
                          @change="togglePdfPageSelection(pdf.tempId, page.filename)"
                        />
                      </div>
                      <div class="thumb-image" @click="viewPdfPage(page)">
                        <img :src="getBackendUrl(page.url)" :alt="page.filename" />
                        <div v-if="page.imported" class="thumb-imported-badge">
                          <el-tag size="small" type="success">已导入</el-tag>
                        </div>
                      </div>
                      <div class="thumb-info">
                        <span class="thumb-filename" :title="page.filename">{{ page.filename }}</span>
                      </div>
                      <div class="thumb-actions">
                        <el-button link type="primary" size="small" @click="viewPdfPage(page)" title="查看大图">
                          <el-icon><ZoomIn /></el-icon>
                        </el-button>
                        <el-button
                          v-if="!page.imported"
                          link
                          type="danger"
                          size="small"
                          @click="deletePdfPage(page)"
                          title="删除"
                        >
                          <el-icon><Delete /></el-icon>
                        </el-button>
                        <el-button
                          v-if="page.imported"
                          link
                          type="warning"
                          size="small"
                          @click="revertPdfImport(page)"
                          title="撤销导入"
                        >
                          <el-icon><RefreshLeft /></el-icon>
                        </el-button>
                      </div>
                    </div>
                  </div>

                  <!-- 列表视图 -->
                  <div v-if="pdfViewMode === 'list'" class="pdf-list-view-inner">
                    <el-table :data="pdf.pages" size="small" stripe>
                      <el-table-column width="50">
                        <template #header>
                          <el-checkbox
                            :model-value="getPdfSelectedCount(pdf.tempId) === pdf.pages.filter(p => !p.imported).length && pdf.pages.filter(p => !p.imported).length > 0"
                            :indeterminate="getPdfSelectedCount(pdf.tempId) > 0 && getPdfSelectedCount(pdf.tempId) < pdf.pages.filter(p => !p.imported).length"
                            @change="(checked) => toggleAllPdfPagesOfPdf(pdf, checked)"
                          />
                        </template>
                        <template #default="{ row }">
                          <el-checkbox
                            :model-value="selectedPdfPages.some(s => s.pdfTempId === pdf.tempId && s.filename === row.filename)"
                            :disabled="row.imported"
                            @change="togglePdfPageSelection(pdf.tempId, row.filename)"
                          />
                        </template>
                      </el-table-column>
                      <el-table-column prop="filename" label="文件名" show-overflow-tooltip />
                      <el-table-column label="状态" width="100" align="center">
                        <template #default="{ row }">
                          <el-tag v-if="row.imported" type="success" size="small">已导入</el-tag>
                          <el-tag v-else type="info" size="small">未导入</el-tag>
                        </template>
                      </el-table-column>
                      <el-table-column label="操作" width="100" align="center">
                        <template #default="{ row }">
                          <el-button link type="primary" size="small" @click="viewPdfPage(row)">查看</el-button>
                          <el-button
                            v-if="!row.imported"
                            link
                            type="danger"
                            size="small"
                            @click="deletePdfPage(row)"
                          >删除</el-button>
                          <el-button
                            v-if="row.imported"
                            link
                            type="warning"
                            size="small"
                            @click="revertPdfImport(row)"
                          >撤销</el-button>
                        </template>
                      </el-table-column>
                    </el-table>
                  </div>
                </div>
              </div>
            </div>

            <!-- 已导入列表 -->
            <div v-if="importedPdfPages.length" class="pdf-imported-list">
              <div class="imported-header" @click="showImportedList = !showImportedList">
                <el-icon>
                  <component :is="showImportedList ? 'ArrowDown' : 'ArrowRight'" />
                </el-icon>
                <span>已导入 ({{ importedPdfPages.length }}张)</span>
              </div>
              <div v-if="showImportedList" class="imported-items">
                <div v-for="item in importedPdfPages" :key="item.filename" class="imported-item">
                  <span class="imported-icon">
                    <el-icon v-if="item.group_name"><OfficeBuilding /></el-icon>
                    <el-icon v-else><Document /></el-icon>
                  </span>
                  <span class="imported-filename">{{ item.filename }}</span>
                  <span class="imported-arrow">→</span>
                  <el-tag size="small" :type="item.group_name ? 'warning' : 'primary'">
                    {{ item.group_name ? item.group_name + ' / ' : '' }}{{ item.material_type_label }}
                  </el-tag>
                  <div class="imported-actions">
                    <el-button link type="primary" size="small" @click="viewPdfPageByFilename(item.filename)">查看</el-button>
                    <el-button link type="warning" size="small" @click="revertPdfImportByFilename(item.filename)">撤销</el-button>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 分隔线 -->
          <el-divider content-position="center">
            <span style="color: #909399; font-size: 12px;">— 已上传材料 —</span>
          </el-divider>

          <!-- 已有材料分类列表 -->
          <div v-for="cat in materialCategories" :key="cat.type" class="material-category">
            <div class="category-header">
              <div class="category-info">
                <el-icon :size="20" :color="cat.color"><component :is="cat.icon" /></el-icon>
                <span class="category-name">{{ cat.label }}</span>
                <el-tag v-if="countMaterialsForType(cat.type)" size="small" type="success">
                  {{ countMaterialsForType(cat.type) }}张
                </el-tag>
                <el-tag v-else size="small" type="info">未上传</el-tag>
              </div>
              <div class="category-actions">
                <!-- 非分组类型：直接上传 -->
                <template v-if="!cat.grouped">
                  <el-button type="primary" size="small" @click="triggerUpload(cat.type)">
                    <el-icon><Plus /></el-icon> 上传
                  </el-button>
                  <el-button size="small" plain @click="triggerBatchUpload(cat.type)">
                    <el-icon><Upload /></el-icon> 批量上传
                  </el-button>
                </template>
                <!-- 分组类型：需要先建组 -->
                <template v-else>
                  <el-button type="primary" size="small" @click="handleAddGroup(cat.type)">
                    <el-icon><Plus /></el-icon> 新增{{ cat.groupLabel }}
                  </el-button>
                </template>
              </div>
            </div>

            <!-- 非分组类型：文件列表（简化，不显示OCR状态） -->
            <div class="category-files" v-if="!cat.grouped && getFlatMaterials(cat.type).length">
              <div v-for="mat in getFlatMaterials(cat.type)" :key="mat.id" class="file-item">
                <div class="file-info">
                  <el-icon :size="16"><Document /></el-icon>
                  <span class="file-name" :title="mat.original_filename">{{ mat.description || mat.original_filename }}</span>
                </div>
                <div class="file-actions">
                  <el-button link type="danger" size="small" @click="handleDeleteMaterial(mat)" :disabled="isCompleted">删除</el-button>
                </div>
              </div>
            </div>

            <!-- 分组类型 -->
            <div v-if="cat.grouped" class="category-groups">
              <div v-for="item in getGroupedMaterials(cat.type)" :key="item.group?.id || 'orphan'" class="group-block">
                <div class="group-header" v-if="item.group">
                  <span class="group-name">🏥 {{ item.group.group_name }}</span>
                  <span class="group-count">{{ item.files.length }}张</span>
                  <el-button link type="primary" size="small" @click="handleRenameGroup(item.group)" :disabled="isCompleted">
                    <el-icon><Edit /></el-icon> 改名
                  </el-button>
                  <el-button link type="primary" size="small" @click="triggerUploadToGroup(cat.type, item.group.id)" :disabled="isCompleted">
                    <el-icon><Plus /></el-icon> 添加
                  </el-button>
                  <el-button link size="small" @click="triggerBatchUploadToGroup(cat.type, item.group.id)" :disabled="isCompleted">批量</el-button>
                  <el-button link type="danger" size="small" @click="handleDeleteGroup(item.group)" :disabled="isCompleted">删除组</el-button>
                </div>
                <div class="group-files" v-if="item.files.length">
                  <div v-for="mat in item.files" :key="mat.id" class="file-item">
                    <div class="file-info">
                      <el-icon :size="16"><Document /></el-icon>
                      <span class="file-name">{{ mat.description || mat.original_filename }}</span>
                    </div>
                    <div class="file-actions">
                      <el-button link type="danger" size="small" @click="handleDeleteMaterial(mat)" :disabled="isCompleted">删除</el-button>
                    </div>
                  </div>
                </div>
                <div v-else class="group-empty">暂无文件，点击"添加"上传</div>
              </div>
              <div v-if="!getGroupedMaterials(cat.type).length" class="category-empty">
                点击"新增{{ cat.groupLabel }}"添加医院，然后在该医院下上传病历照片
              </div>
            </div>

            <div class="category-empty" v-if="!cat.grouped && !getFlatMaterials(cat.type).length">
              点击"上传"添加{{ cat.label }}，支持多张照片
            </div>
          </div>

          <!-- 提示 -->
          <div class="upload-hint" v-if="totalMaterialCount > 0">
            <el-alert type="info" :closable="false" show-icon>
              已上传 {{ totalMaterialCount }} 张材料，请切换到「OCR识别」页进行识别
            </el-alert>
          </div>
        </div>
      </el-tab-pane>

      <!-- ===== Tab 2: OCR 识别 ===== -->
      <el-tab-pane name="ocr">
        <template #label>
          <span>
            <el-icon><VideoCamera /></el-icon> OCR识别
            <el-badge v-if="pendingCount > 0" :value="pendingCount" class="tab-badge" />
          </span>
        </template>
        <div class="ocr-panel">
          <!-- 操作栏 -->
          <div class="ocr-toolbar" v-if="!isCompleted">
            <!-- 识别中显示停止按钮 -->
            <template v-if="ocrRunning">
              <el-button type="warning" @click="handleStopRecognize">
                <el-icon><VideoCamera /></el-icon> 停止识别（等当前张完成）
              </el-button>
              <el-button type="danger" @click="handleForceStopRecognize">
                <el-icon><Switch /></el-icon> 强制停止（立刻中断）
              </el-button>
            </template>
            <!-- 非识别中显示开始按钮 -->
            <template v-else>
              <el-button type="primary" @click="handleRecognizeAll" :disabled="pendingCount === 0">
                <el-icon><VideoCamera /></el-icon> 全部识别（{{ pendingCount }}张待识别）
              </el-button>
            </template>
            <el-button @click="loadCase" :disabled="ocrRunning">
              <el-icon><Refresh /></el-icon> 刷新状态
            </el-button>
          </div>

          <!-- 材料列表 -->
          <el-table :data="allMaterials" empty-text="暂无材料，请先到「上传材料」页上传" size="small" stripe>
            <el-table-column label="类型" width="140">
              <template #default="{ row }">
                <el-tag size="small" :color="getTypeColor(row.material_type)" style="color: #fff; border: none;">
                  {{ getTypeLabel(row.material_type) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="description" label="文件名" show-overflow-tooltip>
              <template #default="{ row }">
                {{ row.description || row.original_filename }}
              </template>
            </el-table-column>
            <el-table-column label="OCR状态" width="100" align="center">
              <template #default="{ row }">
                <el-tag :type="ocrStatusTag(row.ocr_status)" size="small">
                  <el-icon v-if="row.ocr_status === 'processing'" class="is-loading"><Loading /></el-icon>
                  {{ ocrStatusLabel(row.ocr_status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="280" align="center">
              <template #default="{ row }">
                <el-button
                  link type="primary"
                  @click="handleRecognizeSingle(row)"
                  :loading="row._recognizing"
                  :disabled="isCompleted || row.ocr_status === 'processing' || row.ocr_status === 'completed'"
                >
                  {{ row.ocr_status === 'completed' ? '已识别' : '识别' }}
                </el-button>
                <el-button
                  link type="success"
                  @click="viewOcrText(row)"
                  :disabled="row.ocr_status !== 'completed'"
                >
                  查看原文
                </el-button>
                <el-button
                  link type="warning"
                  @click="viewOriginalImage(row)"
                >
                  原图
                </el-button>
                <el-button link type="danger" @click="handleDeleteMaterial(row)" :disabled="isCompleted">删除</el-button>
              </template>
            </el-table-column>
          </el-table>

          <!-- 统计 -->
          <div class="ocr-stats" v-if="allMaterials.length > 0">
            <span>共 {{ allMaterials.length }} 张</span>
            <el-divider direction="vertical" />
            <span style="color: #67C23A;">已完成 {{ completedCount }}</span>
            <el-divider direction="vertical" />
            <span style="color: #E6A23C;">待识别 {{ pendingCount }}</span>
            <el-divider direction="vertical" />
            <span style="color: #F56C6C;">失败 {{ failedCount }}</span>
          </div>
        </div>
      </el-tab-pane>

      <!-- ===== Tab 3: 修正内容 ===== -->
      <el-tab-pane name="content">
        <template #label>
          <span><el-icon><Edit /></el-icon> 修正内容</span>
        </template>
        <div class="content-panel">
          <el-alert v-if="completedCount === 0" type="warning" :closable="false" show-icon style="margin-bottom: 16px;">
            请先在「OCR识别」页完成材料识别，然后可以在此修正内容
          </el-alert>

          <!-- 6 个子 Tab -->
          <el-tabs v-model="activeSubTab" type="card">
            <!-- 子Tab 1: 基本情况 -->
            <el-tab-pane name="basic">
              <template #label>
                <span>基本情况</span>
              </template>
              <div style="margin-bottom: 12px;" v-if="!isCompleted">
                <el-button type="primary" size="small" @click="handleExtractBasicInfo" :loading="extractingBasic">
                  <el-icon><MagicStick /></el-icon> 智能提取（委托书+身份证）
                </el-button>
                <span style="color: #999; font-size: 12px; margin-left: 8px;">从委托书和身份证自动提取委托单位、被鉴定人信息</span>
              </div>
              <el-form :model="caseData" label-width="120px" :disabled="isCompleted">
                <el-row :gutter="20">
                  <el-col :span="12">
                    <el-form-item label="委托单位">
                      <el-input v-model="caseData.entrusting_unit" placeholder="从委托书提取" />
                    </el-form-item>
                  </el-col>
                  <el-col :span="12">
                    <el-form-item label="委托事项">
                      <el-input v-model="caseData.entrustment_matter" placeholder="从委托书提取" />
                    </el-form-item>
                  </el-col>
                </el-row>
                <el-row :gutter="20">
                  <el-col :span="8">
                    <el-form-item label="受理日期">
                      <el-date-picker v-model="caseData.acceptance_date" type="date" placeholder="手动输入"
                        format="YYYY年MM月DD日" value-format="YYYY年MM月DD日" style="width: 100%;" />
                    </el-form-item>
                  </el-col>
                  <el-col :span="8">
                    <el-form-item label="鉴定日期">
                      <el-input :model-value="caseData.acceptance_date" disabled placeholder="= 受理日期" />
                    </el-form-item>
                  </el-col>
                  <el-col :span="8">
                    <el-form-item label="鉴定地点">
                      <el-input v-model="caseData.appraisal_location" />
                    </el-form-item>
                  </el-col>
                </el-row>
                <el-form-item label="在场人员">
                  <el-input v-model="caseData.on_site_personnel" placeholder="可空，有就填" />
                </el-form-item>

                <el-divider>被鉴定人信息</el-divider>
                <el-row :gutter="20">
                  <el-col :span="6">
                    <el-form-item label="姓名">
                      <el-input v-model="personData.name" placeholder="从身份证提取或手动输入" />
                    </el-form-item>
                  </el-col>
                  <el-col :span="6">
                    <el-form-item label="性别">
                      <el-select v-model="personData.gender" style="width: 100%;" clearable>
                        <el-option label="男" value="男" />
                        <el-option label="女" value="女" />
                      </el-select>
                    </el-form-item>
                  </el-col>
                  <el-col :span="6">
                    <el-form-item label="出生日期">
                      <el-input v-model="personData.birth_date" placeholder="从身份证提取" />
                    </el-form-item>
                  </el-col>
                  <el-col :span="6">
                    <el-form-item label="身份证号">
                      <el-input v-model="personData.id_number" />
                    </el-form-item>
                  </el-col>
                </el-row>
                <el-form-item label="住址">
                  <el-input v-model="personData.address" />
                </el-form-item>

                <el-divider>鉴定材料清单</el-divider>
                <el-form-item label="材料清单">
                  <el-input v-model="caseData.material_list" type="textarea" :rows="6" placeholder="自动生成或手动填写" />
                </el-form-item>

                <el-form-item v-if="!isCompleted">
                  <el-button type="primary" @click="saveBasicInfo">保存基本情况</el-button>
                </el-form-item>
              </el-form>
            </el-tab-pane>

            <!-- 子Tab 2: 基本案情 -->
            <el-tab-pane name="facts">
              <template #label>
                <span>基本案情</span>
              </template>
              <div style="margin-bottom: 12px;" v-if="!isCompleted">
                <el-button type="primary" size="small" @click="handleExtractCaseFacts" :loading="extractingFacts">
                  <el-icon><MagicStick /></el-icon> 智能提取（委托书+事故认定书）
                </el-button>
                <span style="color: #999; font-size: 12px; margin-left: 8px;">从委托书和交通事故认定书自动生成基本案情</span>
              </div>
              <el-form label-width="100px" :disabled="isCompleted">
                <el-form-item label="基本案情">
                  <el-input v-model="reportData.case_facts" type="textarea" :rows="12"
                    placeholder="从委托书简要案情提取，自动拼接就医经过和收尾句" />
                </el-form-item>
                <el-form-item v-if="!isCompleted">
                  <el-button type="primary" @click="saveReport">保存基本案情</el-button>
                </el-form-item>
              </el-form>
            </el-tab-pane>

            <!-- 子Tab 3: 资料摘要 -->
            <el-tab-pane name="summary">
              <template #label>
                <span>资料摘要</span>
              </template>
              <div style="margin-bottom: 12px;" v-if="!isCompleted">
                <el-button type="primary" size="small" @click="loadMedicalGroups" :loading="loadingMedicalGroups">
                  <el-icon><MagicStick /></el-icon> 智能提取（病历材料）
                </el-button>
                <el-button type="success" size="small" @click="handleGenerateSummary" :loading="generatingSummary" :disabled="!hospitalRecords.length">
                  <el-icon><Document /></el-icon> 生成资料摘要
                </el-button>
              </div>

              <!-- 医院分组提取卡片 -->
              <div v-if="medicalGroupList.length" style="margin-bottom: 16px;">
                <div style="margin-bottom: 8px; color: #606266; font-size: 13px;">
                  检测到 {{ medicalGroupList.length }} 家医院的病历材料，可逐个提取或一键全部提取
                </div>
                <div style="display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 10px;">
                  <div v-for="g in medicalGroupList" :key="g.group_id"
                    style="border: 1px solid #e4e7ed; border-radius: 8px; padding: 12px 16px; min-width: 260px; background: #fafafa; transition: all 0.2s;"
                    :style="g.extracting ? 'border-color: #409eff; background: #ecf5ff;' : g.extracted ? 'border-color: #67c23a; background: #f0f9eb;' : ''"
                  >
                    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 6px;">
                      <el-icon :size="18" :color="g.extracted ? '#67c23a' : '#409eff'"><OfficeBuilding /></el-icon>
                      <span style="font-weight: 600; font-size: 14px;">{{ g.group_name }}</span>
                    </div>
                    <div style="font-size: 12px; color: #909399; margin-bottom: 8px;">
                      {{ g.completed_count }}/{{ g.material_count }} 页已识别
                      <span v-if="g.has_record" style="color: #67c23a; margin-left: 6px;">✓ 已提取</span>
                    </div>
                    <el-button
                      :type="g.extracted ? 'success' : 'primary'"
                      size="small"
                      @click="handleExtractOneGroup(g)"
                      :loading="g.extracting"
                      :disabled="g.completed_count === 0"
                    >
                      {{ g.extracted ? '重新提取' : '提取此医院' }}
                    </el-button>
                  </div>
                </div>
                <el-button type="primary" @click="handleExtractAllGroups" :loading="extractingAllGroups" :disabled="extractingAllGroups">
                  <el-icon><MagicStick /></el-icon> 一键全部提取
                </el-button>
                <el-button size="small" @click="medicalGroupList = []" style="margin-left: 8px;">收起</el-button>
              </div>
              <div v-for="(record, idx) in hospitalRecords" :key="record.id" class="hospital-record-card">
                <el-card>
                  <template #header>
                    <div class="record-header">
                      <span>住院记录 {{ idx + 1 }}：{{ record.hospital_name || '未命名医院' }}（住院号：{{ record.admission_number || '-' }}）</span>
                      <div v-if="!isCompleted">
                        <el-button link type="primary" @click="editHospitalRecord(record)">编辑</el-button>
                        <el-button link type="danger" @click="deleteHospitalRecord(record)">删除</el-button>
                      </div>
                    </div>
                  </template>
                  <el-descriptions :column="2" border size="small">
                    <el-descriptions-item label="主诉" :span="2">{{ record.chief_complaint || '-' }}</el-descriptions-item>
                    <el-descriptions-item label="现病史" :span="2">{{ record.present_illness_history || '-' }}</el-descriptions-item>
                    <el-descriptions-item label="既往史" :span="2" v-if="record.past_history">{{ record.past_history }}</el-descriptions-item>
                    <el-descriptions-item label="体格检查" :span="2">{{ record.physical_examination || '-' }}</el-descriptions-item>
                    <el-descriptions-item label="入院诊断">{{ record.admission_diagnosis || '-' }}</el-descriptions-item>
                    <el-descriptions-item label="出院诊断">{{ record.discharge_diagnosis || '-' }}</el-descriptions-item>
                    <el-descriptions-item label="治疗过程" :span="2" v-if="record.treatment_process">{{ record.treatment_process }}</el-descriptions-item>
                    <el-descriptions-item label="用药情况" :span="2" v-if="record.medication">{{ record.medication }}</el-descriptions-item>
                    <el-descriptions-item label="出院医嘱" :span="2">{{ record.discharge_orders || '-' }}</el-descriptions-item>
                    <el-descriptions-item label="入院日期">{{ record.admission_date || '-' }}</el-descriptions-item>
                    <el-descriptions-item label="出院日期">{{ record.discharge_date || '-' }}（{{ record.hospital_days || '-' }}天）</el-descriptions-item>
                  </el-descriptions>
                </el-card>
              </div>

              <el-empty v-if="!hospitalRecords.length" description="暂无住院记录，请先上传病历材料并执行智能提取" />

              <div style="margin-top: 16px;" v-if="!isCompleted">
                <el-button type="primary" plain @click="showAddRecordDialog = true">
                  <el-icon><Plus /></el-icon> 手动添加住院记录
                </el-button>
              </div>

              <el-divider>资料摘要全文</el-divider>
              <el-input v-model="reportData.material_summary" type="textarea" :rows="10"
                placeholder="自动从住院记录生成，可手动修改" :disabled="isCompleted" />
              <div style="margin-top: 10px;" v-if="!isCompleted">
                <el-button type="primary" @click="saveReport">保存资料摘要</el-button>
              </div>
            </el-tab-pane>

            <!-- 子Tab 4: 鉴定过程 -->
            <el-tab-pane name="process">
              <template #label>
                <span>鉴定过程</span>
              </template>

              <!-- 法医临床检查 -->
              <el-card shadow="never" style="margin-bottom: 16px;">
                <template #header>
                  <div style="display: flex; align-items: center; justify-content: space-between;">
                    <span style="font-weight: 600;">法医临床学检查</span>
                    <el-button type="primary" @click="generateAppraisalProcess" :loading="generatingProcess">
                      <el-icon><MagicStick /></el-icon> 生成鉴定过程
                    </el-button>
                  </div>
                </template>
                <el-form label-width="100px" :disabled="isCompleted" size="small">
                  <el-form-item label="检查日期">
                    <el-input v-model="caseData.examination_date" placeholder="如：2021年10月22日" style="width: 220px;" />
                  </el-form-item>
                  <el-form-item label="检查内容">
                    <el-input v-model="caseData.clinical_examination" type="textarea" :rows="5"
                      placeholder="如：即被鉴定人张金遂伤后6个月余。张金遂自行步入诊室。自诉：头痛、头晕，记忆力下降... 查体：神志清，精神可..." />
                  </el-form-item>
                  <el-form-item v-if="!isCompleted">
                    <el-button type="primary" @click="saveCaseField('examination_date', caseData.examination_date); saveCaseField('clinical_examination', caseData.clinical_examination)">保存检查信息</el-button>
                  </el-form-item>
                </el-form>
              </el-card>

              <!-- 鉴定过程文本 -->
              <el-form label-width="100px" :disabled="isCompleted">
                <el-form-item label="鉴定过程">
                  <el-input v-model="reportData.appraisal_process" type="textarea" :rows="14"
                    placeholder="点击上方[生成鉴定过程]自动生成，也可手动编辑" />
                </el-form-item>
                <el-form-item v-if="!isCompleted">
                  <el-button type="primary" @click="saveReport">保存鉴定过程</el-button>
                </el-form-item>
              </el-form>

              <el-divider>影像学报告</el-divider>
              <el-table :data="imagingReports" empty-text="暂无影像学报告" size="small">
                <el-table-column prop="report_date" label="报告日期" width="120" />
                <el-table-column prop="hospital_name" label="医院" />
                <el-table-column prop="exam_type" label="检查类型" width="80" />
                <el-table-column prop="exam_part" label="检查部位" width="100" />
                <el-table-column prop="film_number" label="片子编号" width="120" />
                <el-table-column prop="film_count" label="数量" width="60" />
                <el-table-column prop="report_content" label="报告内容" show-overflow-tooltip />
                <el-table-column label="操作" width="120" v-if="!isCompleted">
                  <template #default="{ row }">
                    <el-button link type="primary" @click="editImagingReport(row)">编辑</el-button>
                    <el-button link type="danger" @click="deleteImagingReport(row)">删除</el-button>
                  </template>
                </el-table-column>
              </el-table>
              <div style="margin-top: 10px; display: flex; gap: 10px;" v-if="!isCompleted">
                <el-button type="primary" @click="handleExtractImagingReports" :loading="extractingImaging">
                  <el-icon><MagicStick /></el-icon> 智能提取
                </el-button>
                <el-button type="primary" plain @click="showAddImagingDialog = true">
                  <el-icon><Plus /></el-icon> 添加影像学报告
                </el-button>
              </div>
            </el-tab-pane>

            <!-- 子Tab 5: 分析说明 -->
            <el-tab-pane name="analysis">
              <template #label>
                <span>分析说明</span>
              </template>
              <div style="margin-bottom: 12px;" v-if="!isCompleted">
                <el-button type="primary" size="small" @click="handleGenerateAnalysis" :loading="extractingAnalysis">
                  <el-icon><MagicStick /></el-icon> 智能生成
                </el-button>
                <span style="color: #999; font-size: 12px; margin-left: 8px;">基于住院记录和影像学报告自动生成分析说明</span>
              </div>
              <el-form label-width="100px" :disabled="isCompleted">
                <el-form-item label="分析说明">
                  <el-input v-model="reportData.analysis" type="textarea" :rows="16"
                    placeholder="自动生成：外伤史+诊断明确+委托事项草稿" />
                </el-form-item>
                <el-form-item v-if="!isCompleted">
                  <el-button type="primary" @click="saveReport">保存分析说明</el-button>
                </el-form-item>
              </el-form>
            </el-tab-pane>

            <!-- 子Tab 6: 鉴定意见 -->
            <el-tab-pane name="opinion">
              <template #label>
                <span>鉴定意见</span>
              </template>
              <div style="margin-bottom: 12px;" v-if="!isCompleted">
                <el-button type="primary" size="small" @click="handleGenerateOpinion" :loading="extractingOpinion">
                  <el-icon><MagicStick /></el-icon> 智能生成
                </el-button>
                <span style="color: #999; font-size: 12px; margin-left: 8px;">基于分析说明自动生成鉴定意见草稿</span>
              </div>
              <el-alert
                v-if="reportData.opinion_confirmed"
                title="鉴定意见已确认"
                type="success"
                :closable="false"
                show-icon
                style="margin-bottom: 16px;"
              />
              <el-form label-width="100px" :disabled="isCompleted">
                <el-form-item label="鉴定意见">
                  <el-input v-model="reportData.opinion" type="textarea" :rows="10"
                    placeholder="根据分析说明自动生成草稿，确认后方可使用" />
                </el-form-item>
                <el-form-item v-if="!isCompleted">
                  <el-button type="primary" @click="saveReport">保存鉴定意见</el-button>
                  <el-button type="success" @click="handleConfirmOpinion" :disabled="!reportData.opinion">
                    {{ reportData.opinion_confirmed ? '取消确认' : '确认鉴定意见' }}
                  </el-button>
                </el-form-item>
              </el-form>
            </el-tab-pane>

          </el-tabs>
        </div>
      </el-tab-pane>

      <!-- ===== Tab 4: 报告预览 ===== -->
      <el-tab-pane name="preview">
        <template #label>
          <span style="color: #E6A23C; font-weight: 600;"><el-icon><Document /></el-icon> 报告预览</span>
        </template>

        <!-- 预览文档 -->
        <div class="report-preview">
          <div class="report-paper">
            <!-- 标题 -->
            <h1 class="report-title">司法鉴定意见书</h1>

            <!-- 编号行 -->
            <div class="report-number">
              {{ caseData.case_number || '（编号待定）' }}
            </div>

            <div class="report-divider"></div>

            <!-- 一、基本情况 -->
            <div class="report-section">
              <h2 class="section-title">一、基本情况</h2>
              <div class="section-body">
                <table class="info-table">
                  <tr>
                    <td class="label-cell">委托单位：</td>
                    <td>{{ caseData.entrusting_unit || '（待填）' }}</td>
                  </tr>
                  <tr>
                    <td class="label-cell">委托事项：</td>
                    <td>{{ caseData.entrustment_matter || '（待填）' }}</td>
                  </tr>
                  <tr>
                    <td class="label-cell">受理日期：</td>
                    <td>{{ caseData.acceptance_date || '（待填）' }}</td>
                  </tr>
                  <tr>
                    <td class="label-cell">鉴定日期：</td>
                    <td>{{ caseData.acceptance_date || '（待填）' }}</td>
                  </tr>
                  <tr>
                    <td class="label-cell">鉴定地点：</td>
                    <td>{{ caseData.appraisal_location || '新乡医学院司法鉴定中心' }}</td>
                  </tr>
                  <template v-if="caseData.on_site_personnel">
                    <tr>
                      <td class="label-cell">在场人员：</td>
                      <td>{{ caseData.on_site_personnel }}</td>
                    </tr>
                  </template>
                </table>

                <div style="margin-top: 12px;">
                  <span class="sub-label">被鉴定人：</span>
                  <span>{{ personData.name || '（待填）' }}</span>
                  <span v-if="personData.gender" style="margin-left: 16px;">{{ personData.gender }}</span>
                  <span v-if="personData.birth_date" style="margin-left: 16px;">{{ personData.birth_date }}出生</span>
                  <span v-if="personData.id_number" style="margin-left: 16px;">身份证号：{{ personData.id_number }}</span>
                  <div v-if="personData.address" style="margin-top: 4px;">
                    <span class="sub-label">住址：</span>{{ personData.address }}
                  </div>
                </div>

                <div v-if="caseData.material_list" style="margin-top: 12px;">
                  <span class="sub-label">鉴定材料：</span>
                  <div style="white-space: pre-wrap; margin-top: 4px;">{{ caseData.material_list }}</div>
                </div>
              </div>
            </div>

            <!-- 二、基本案情 -->
            <div class="report-section">
              <h2 class="section-title">二、基本案情</h2>
              <div class="section-body">
                <div v-if="reportData.case_facts" class="text-content">{{ reportData.case_facts }}</div>
                <div v-else class="empty-hint">（待生成）</div>
              </div>
            </div>

            <!-- 三、资料摘要 -->
            <div class="report-section">
              <h2 class="section-title">三、资料摘要</h2>
              <div class="section-body">
                <div v-if="reportData.material_summary" class="text-content">{{ reportData.material_summary }}</div>
                <div v-else class="empty-hint">（待生成）</div>
              </div>
            </div>

            <!-- 四、鉴定过程 -->
            <div class="report-section">
              <h2 class="section-title">四、鉴定过程</h2>
              <div class="section-body">
                <div v-if="reportData.appraisal_process" class="text-content">{{ reportData.appraisal_process }}</div>
                <div v-else class="empty-hint">（待生成）</div>
              </div>
            </div>

            <!-- 五、分析说明 -->
            <div class="report-section">
              <h2 class="section-title">五、分析说明</h2>
              <div class="section-body">
                <div v-if="reportData.analysis" class="text-content">{{ reportData.analysis }}</div>
                <div v-else class="empty-hint">（待生成）</div>
              </div>
            </div>

            <!-- 六、鉴定意见 -->
            <div class="report-section">
              <h2 class="section-title">六、鉴定意见</h2>
              <div class="section-body">
                <div v-if="reportData.opinion" class="text-content opinion-text">{{ reportData.opinion }}</div>
                <div v-else class="empty-hint">（待生成）</div>
                <div v-if="reportData.opinion_confirmed" style="margin-top: 8px;">
                  <el-tag type="success" size="small">✅ 已确认</el-tag>
                </div>
              </div>
            </div>

            <!-- 落款 -->
            <div class="report-footer">
              <div class="footer-line">
                <span>鉴定人：</span>
                <span class="underline-blank"></span>
              </div>
              <div class="footer-line">
                <span>授权签字人：</span>
                <span class="underline-blank"></span>
              </div>
              <div class="footer-line" style="margin-top: 20px;">
                <span>{{ caseData.appraisal_location || '新乡医学院司法鉴定中心' }}</span>
              </div>
              <div class="footer-line">
                <span>{{ caseData.acceptance_date || '____年____月____日' }}</span>
              </div>
            </div>
          </div>

          <!-- 底部操作区 -->
          <div class="preview-actions" v-if="!isCompleted">
            <el-alert
              v-if="!allSectionsFilled"
              type="warning"
              :closable="false"
              show-icon
              style="margin-bottom: 16px;"
            >
              <template #title>
                报告尚有未填写的内容，请先在各页面完成填写或智能提取
              </template>
            </el-alert>
            <div class="action-buttons">
              <el-button
                type="success"
                size="large"
                @click="handleGenerateWord"
                :loading="generatingWord"
                :disabled="!allSectionsFilled"
              >
                <el-icon><Document /></el-icon> 确认无误，生成Word报告
              </el-button>
            </div>
            <div style="color: #909399; font-size: 12px; margin-top: 8px; text-align: center;">
              生成前请确认各板块内容准确无误，生成后可在Word中微调格式
            </div>
          </div>

          <!-- 已完成状态提示 -->
          <div class="preview-actions" v-if="isCompleted">
            <el-result icon="success" title="案件已完成" sub-title="报告已生成">
              <template #extra>
                <el-button type="primary" @click="handleGenerateWord" :loading="generatingWord">
                  <el-icon><Download /></el-icon> 重新下载Word报告
                </el-button>
                <el-button type="warning" @click="handleReopen">
                  <el-icon><RefreshLeft /></el-icon> 重新打开编辑
                </el-button>
              </template>
            </el-result>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 新增医院分组对话框 -->
    <el-dialog v-model="showNewGroupDialog" :title="`新增${currentGroupLabel}`" width="400px">
      <el-form @submit.prevent="confirmAddGroup">
        <el-form-item :label="currentGroupLabel + '名称'">
          <el-input v-model="newGroupName" placeholder="如：新乡市中心医院" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showNewGroupDialog = false">取消</el-button>
        <el-button type="primary" @click="confirmAddGroup" :loading="uploading">确定</el-button>
      </template>
    </el-dialog>

    <!-- 修改组名对话框 -->
    <el-dialog v-model="showRenameGroupDialog" title="修改名称" width="400px">
      <el-form @submit.prevent="confirmRenameGroup">
        <el-form-item :label="currentGroupLabel + '名称'">
          <el-input v-model="renameGroupName" placeholder="如：新乡市中心医院" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showRenameGroupDialog = false">取消</el-button>
        <el-button type="primary" @click="confirmRenameGroup" :loading="uploading">确定</el-button>
      </template>
    </el-dialog>

    <!-- 隐藏的文件上传 input -->
    <input
      ref="singleUploadInput"
      type="file"
      accept="image/*,.pdf"
      multiple
      style="display: none;"
      @change="handleFileSelected"
    />
    <input
      ref="batchUploadInput"
      type="file"
      accept="image/*,.pdf"
      multiple
      style="display: none;"
      @change="handleFileSelected"
    />

    <!-- OCR 文本查看/编辑对话框 -->
    <el-dialog v-model="showOcrDialog" :title="`OCR识别结果 - ${viewingMaterial?.description || viewingMaterial?.original_filename || ''}`" width="750px">
      <div v-if="viewingMaterial?.ocr_text || ocrViewMode === 'edit'" class="ocr-text-view">
        <!-- 视图切换 + 操作按钮 -->
        <div class="ocr-view-toggle">
          <el-radio-group v-model="ocrViewMode" size="small">
            <el-radio-button value="render">渲染视图</el-radio-button>
            <el-radio-button value="raw">原文</el-radio-button>
            <el-radio-button value="edit">编辑</el-radio-button>
          </el-radio-group>
          <el-button type="warning" size="small" plain @click="reRecognizeMaterial" :loading="reRecognizing">
            重新识别
          </el-button>
        </div>
        <!-- 渲染视图 -->
        <div v-if="ocrViewMode === 'render'" class="ocr-rendered" v-html="renderedOcrText"></div>
        <!-- 原文视图 -->
        <pre v-else-if="ocrViewMode === 'raw'" class="ocr-raw">{{ viewingMaterial.ocr_text }}</pre>
        <!-- 编辑视图 -->
        <div v-else class="ocr-edit-area">
          <el-input
            v-model="ocrEditText"
            type="textarea"
            :autosize="{ minRows: 12, maxRows: 30 }"
            placeholder="编辑OCR识别文本..."
          />
          <div class="ocr-edit-actions">
            <el-button type="primary" size="small" @click="saveOcrText" :loading="ocrSaving">保存修改</el-button>
            <el-button size="small" @click="ocrViewMode = 'render'">取消</el-button>
          </div>
        </div>
        <!-- 原图引用提示 -->
        <div v-if="ocrViewMode !== 'edit' && viewingMaterial?.file_path" class="ocr-image-ref">
          <el-divider content-position="left">引用原图</el-divider>
          <div class="ref-line">
            <code>![]({{ materialImageUrl }})</code>
            <el-button type="primary" link size="small" @click="copyImageRef">复制</el-button>
          </div>
          <div class="ref-tip">在"编辑"模式下粘贴以上语法可在渲染视图中显示原图</div>
        </div>
      </div>
      <el-empty v-else description="暂无OCR识别结果" />
    </el-dialog>

    <!-- 原图查看对话框 -->
    <el-dialog v-model="showImageDialog" :title="`原始图片 - ${viewingMaterial?.description || viewingMaterial?.original_filename || ''}`" width="80%" top="3vh">
      <div v-if="viewingMaterial?.file_path" class="original-image-view" ref="imageContainerRef"
        @mousedown="onImageDragStart"
        @mousemove="onImageDragMove"
        @mouseup="onImageDragEnd"
        @mouseleave="onImageDragEnd"
        :style="{ cursor: imageZoom > 1 ? (isDragging ? 'grabbing' : 'grab') : 'default' }">
        <img :src="getMaterialImageUrl(viewingMaterial)" :alt="viewingMaterial?.original_filename"
          :style="{ transform: `scale(${imageZoom})`, transformOrigin: 'left top' }" />
      </div>
      <el-empty v-else description="无原始图片" />
      <!-- 缩放控制栏 -->
      <div class="zoom-controls">
        <el-button size="small" @click="zoomOut" :disabled="imageZoom <= 0.5">
          <el-icon><ZoomOut /></el-icon>
        </el-button>
        <span class="zoom-label">{{ Math.round(imageZoom * 100) }}%</span>
        <el-button size="small" @click="zoomIn" :disabled="imageZoom >= 3">
          <el-icon><ZoomIn /></el-icon>
        </el-button>
        <el-button size="small" @click="zoomReset">重置</el-button>
      </div>
    </el-dialog>

    <!-- 住院记录编辑对话框 -->
    <el-dialog v-model="showRecordDialog" :title="editingRecord.id ? '编辑住院记录' : '添加住院记录'" width="700px">
      <el-form :model="editingRecord" label-width="100px">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="医院名称">
              <el-input v-model="editingRecord.hospital_name" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="住院号">
              <el-input v-model="editingRecord.admission_number" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="主诉">
          <el-input v-model="editingRecord.chief_complaint" />
        </el-form-item>
        <el-form-item label="现病史">
          <el-input v-model="editingRecord.present_illness_history" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="既往史">
          <el-input v-model="editingRecord.past_history" type="textarea" :rows="2" placeholder="可空" />
        </el-form-item>
        <el-form-item label="体格检查">
          <el-input v-model="editingRecord.physical_examination" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="入院诊断">
          <el-input v-model="editingRecord.admission_diagnosis" />
        </el-form-item>
        <el-form-item label="治疗过程">
          <el-input v-model="editingRecord.treatment_process" type="textarea" :rows="2" placeholder="可空" />
        </el-form-item>
        <el-form-item label="用药情况">
          <el-input v-model="editingRecord.medication" type="textarea" :rows="2" placeholder="可空" />
        </el-form-item>
        <el-form-item label="出院诊断">
          <el-input v-model="editingRecord.discharge_diagnosis" />
        </el-form-item>
        <el-form-item label="出院医嘱">
          <el-input v-model="editingRecord.discharge_orders" type="textarea" :rows="2" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="入院日期">
              <el-input v-model="editingRecord.admission_date" placeholder="YYYY年MM月DD日" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="出院日期">
              <el-input v-model="editingRecord.discharge_date" placeholder="YYYY年MM月DD日" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="住院天数">
              <el-input-number v-model="editingRecord.hospital_days" :min="0" style="width: 100%;" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="showRecordDialog = false">取消</el-button>
        <el-button type="primary" @click="saveHospitalRecord" :loading="saving">保存</el-button>
      </template>
    </el-dialog>

    <!-- 影像学报告编辑对话框 -->
    <el-dialog v-model="showImagingDialog" :title="editingImaging.id ? '编辑影像学报告' : '添加影像学报告'" width="600px">
      <el-form :model="editingImaging" label-width="100px">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="报告日期">
              <el-input v-model="editingImaging.report_date" placeholder="YYYY年MM月DD日" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="医院名称">
              <el-input v-model="editingImaging.hospital_name" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="检查类型">
              <el-select v-model="editingImaging.exam_type" style="width: 100%;">
                <el-option label="CT" value="CT" />
                <el-option label="X线" value="X线" />
                <el-option label="MRI" value="MRI" />
                <el-option label="其他" value="其他" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="检查部位">
              <el-input v-model="editingImaging.exam_part" placeholder="如：头颅、胸部" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="片子编号">
              <el-input v-model="editingImaging.film_number" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="片子数量">
              <el-input-number v-model="editingImaging.film_count" :min="1" style="width: 100%;" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="报告内容">
          <el-input v-model="editingImaging.report_content" type="textarea" :rows="4" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showImagingDialog = false">取消</el-button>
        <el-button type="primary" @click="saveImagingReport" :loading="saving">保存</el-button>
      </template>
    </el-dialog>

    <!-- PDF 页面查看对话框 -->
    <el-dialog v-model="showPdfImageDialog" :title="viewingPdfPage?.filename || 'PDF页面'" width="80%" top="3vh">
      <div v-if="viewingPdfPage?.url" class="original-image-view" ref="pdfImageContainerRef"
        @mousedown="onPdfImageDragStart"
        @mousemove="onPdfImageDragMove"
        @mouseup="onPdfImageDragEnd"
        @mouseleave="onPdfImageDragEnd"
        :style="{ cursor: pdfImageZoom > 1 ? (pdfIsDragging ? 'grabbing' : 'grab') : 'default' }">
        <img :src="getBackendUrl(viewingPdfPage.url)" :alt="viewingPdfPage?.filename"
          :style="{ transform: `scale(${pdfImageZoom})`, transformOrigin: 'left top' }" />
      </div>
      <el-empty v-else description="无图片" />

      <!-- 查看器控制栏 -->
      <div class="pdf-viewer-controls">
        <div class="zoom-controls">
          <el-button size="small" @click="pdfZoomOut" :disabled="pdfImageZoom <= 0.5">
            <el-icon><ZoomOut /></el-icon>
          </el-button>
          <span class="zoom-label">{{ Math.round(pdfImageZoom * 100) }}%</span>
          <el-button size="small" @click="pdfZoomIn" :disabled="pdfImageZoom >= 3">
            <el-icon><ZoomIn /></el-icon>
          </el-button>
          <el-button size="small" @click="pdfZoomReset">重置</el-button>
        </div>

        <!-- 导入控制 -->
        <div v-if="viewingPdfPage && !viewingPdfPage.imported" class="import-controls-inline">
          <el-select v-model="viewingPdfImportType" placeholder="选择类型" size="small" style="width: 140px;">
            <el-option v-for="cat in materialCategories" :key="cat.type" :label="cat.label" :value="cat.type" />
          </el-select>
          <el-select
            v-if="getCategoryGrouped(viewingPdfImportType)"
            v-model="viewingPdfImportGroupId"
            placeholder="选择医院"
            size="small"
            style="width: 140px;"
            clearable
          >
            <el-option
              v-for="g in getGroupsForType(viewingPdfImportType)"
              :key="g.id"
              :label="g.group_name"
              :value="g.id"
            />
          </el-select>
          <el-input
            v-if="getCategoryGrouped(viewingPdfImportType) && !viewingPdfImportGroupId"
            v-model="viewingPdfNewGroupName"
            placeholder="新建医院组名"
            size="small"
            style="width: 120px;"
          />
          <el-button type="primary" size="small" @click="importViewingPage" :loading="importingPdfPage">
            导入此页
          </el-button>
        </div>
        <div v-else-if="viewingPdfPage?.imported" class="imported-status">
          <el-tag type="success" size="small">已导入到: {{ viewingPdfPage.material_type_label || viewingPdfPage.material_type }}</el-tag>
          <el-button link type="warning" size="small" @click="revertViewingPdfPage" :loading="revertingPdfPage">
            撤销导入
          </el-button>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Upload, Plus, VideoCamera, Check, CircleCheck, RefreshLeft,
  Document, Refresh, PictureFilled, Files, Postcard, Notebook, FirstAidKit,
  Edit, MagicStick, Loading, Download, ZoomIn, ZoomOut, OfficeBuilding,
  Grid, List, Delete, ArrowDown, ArrowRight
} from '@element-plus/icons-vue'
import api from '@/api'

const route = useRoute()
const router = useRouter()
const caseId = parseInt(route.params.id)

// === 状态 ===
const activeMainTab = ref('upload')
const activeSubTab = ref('basic')
const caseData = ref({ person: null, materials: [], hospital_records: [], imaging_reports: [], report: null })
const personData = ref({ name: '', gender: '', birth_date: '', id_number: '', address: '' })
const hospitalRecords = ref([])
const imagingReports = ref([])
const reportData = ref({ case_facts: '', material_summary: '', appraisal_process: '', analysis: '', opinion: '', opinion_confirmed: false })

// 材料管理
const materialsByType = ref({})
const currentUploadType = ref('')
const currentGroupId = ref(null)
const singleUploadInput = ref(null)
const batchUploadInput = ref(null)
const uploading = ref(false)

// OCR 状态
const ocrRunning = ref(false)
const recognizingIds = ref(new Set())  // 正在识别的材料ID集合

// LLM 提取状态
const extracting = ref(false)  // 全局提取（旧）
const extractingBasic = ref(false)
const extractingFacts = ref(false)
const extractingMedical = ref(false)
const generatingSummary = ref(false)
const extractingImaging = ref(false)
const generatingProcess = ref(false)
const extractingAnalysis = ref(false)
const extractingOpinion = ref(false)
const generatingWord = ref(false)

// 新增分组对话框
const showNewGroupDialog = ref(false)
const newGroupName = ref('')
const currentGroupLabel = ref('医院')
const showRenameGroupDialog = ref(false)
const renameGroupId = ref(null)
const renameGroupName = ref('')

// OCR 查看
const showOcrDialog = ref(false)
const showImageDialog = ref(false)
const viewingMaterial = ref(null)
const ocrViewMode = ref('render')  // 'render' | 'raw'

// PDF 转换相关
const pdfUploadInput = ref(null)
const pdfUploadRef = ref(null)
const pdfViewMode = ref('thumbnail')  // 'thumbnail' | 'list'
// const pdfPages = ref([])  // 移除，统一从 uploadedPdfs 获取
const pdfConverting = ref(false)
const selectedPdfPages = ref([])  // [{pdfTempId, filename}]
const importTargetType = ref('')
const importTargetGroupId = ref(null)
const pdfNewGroupName = ref('')
const importedPdfPages = ref([])
const showImportedList = ref(true)
const uploadedPdfs = ref([])  // [{tempId, filename, size, file, converting, converted, pageCount, expanded, pages}]

// PDF 查看相关
const showPdfImageDialog = ref(false)
const viewingPdfPage = ref(null)
const pdfImageZoom = ref(1)
const pdfIsDragging = ref(false)
const pdfDragStart = ref({ x: 0, y: 0, scrollLeft: 0, scrollTop: 0 })
const pdfImageContainerRef = ref(null)
const viewingPdfImportType = ref('')
const viewingPdfImportGroupId = ref(null)
const viewingPdfNewGroupName = ref('')
const importingPdfPage = ref(false)
const revertingPdfPage = ref(false)

// 轻量 Markdown → HTML 渲染（覆盖OCR文本常见格式）
function renderOcrMarkdown(md) {
  if (!md) return ''
  let html = md
  // 转义HTML特殊字符（保留已有HTML标签如<table>）
  // 不转义，因为OCR文本里本身就有HTML表格，需要保留
  // 标题: # ~ ######
  html = html.replace(/^######\s+(.+)$/gm, '<h6>$1</h6>')
  html = html.replace(/^#####\s+(.+)$/gm, '<h5>$1</h5>')
  html = html.replace(/^####\s+(.+)$/gm, '<h4>$1</h4>')
  html = html.replace(/^###\s+(.+)$/gm, '<h3>$1</h3>')
  html = html.replace(/^##\s+(.+)$/gm, '<h2>$1</h2>')
  html = html.replace(/^#\s+(.+)$/gm, '<h1>$1</h1>')
  // 分隔线 ---
  html = html.replace(/^---+$/gm, '<hr>')
  // 图片 ![alt](url) — 如果src以/uploads/开头，补上后端host
  html = html.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (match, alt, src) => {
    const fullSrc = src.startsWith('/uploads/') ? getBackendUrl(src) : src
    return `<img src="${fullSrc}" alt="${alt}" style="max-width:100%;border-radius:4px;margin:8px 0;">`
  })
  // 粗体 **text**
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  // 斜体 *text*
  html = html.replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, '<em>$1</em>')
  // 段落：双换行分段（但不在已有HTML标签内分段）
  // 先把已有HTML块标记出来，避免被段落包裹打断
  const blocks = []
  let blockId = 0
  // 保护已有HTML块级元素（table, hr, h1-h6, div等）
  html = html.replace(/<(table|hr|h[1-6]|div|ul|ol|li|blockquote|pre)[^>]*>[\s\S]*?<\/\1>|<hr[^>]*\/?>/gi, (match) => {
    const placeholder = `<!--BLOCK_${blockId}-->`
    blocks.push({ placeholder, html: match })
    blockId++
    return placeholder
  })
  // 非HTML块之间的双换行分段
  html = html.replace(/\n{2,}/g, '</p><p>')
  // 单换行→br
  html = html.replace(/\n/g, '<br>')
  // 包裹段落
  html = '<p>' + html + '</p>'
  // 清理空段落
  html = html.replace(/<p>\s*<\/p>/g, '')
  // 还原HTML块
  blocks.forEach(b => {
    html = html.replace(b.placeholder, b.html)
  })
  // 清理段落标签包裹HTML块级元素的情况
  html = html.replace(/<p>\s*(<(?:table|hr|h[1-6]|div|ul|ol|li|blockquote|pre)[^>]*>)/g, '$1')
  html = html.replace(/(<\/(?:table|h[1-6]|div|ul|ol|li|blockquote|pre)>)\s*<\/p>/g, '$1')
  return html
}

// 渲染后的OCR文本
const renderedOcrText = computed(() => {
  if (!viewingMaterial.value?.ocr_text) return ''
  return renderOcrMarkdown(viewingMaterial.value.ocr_text)
})

// OCR 编辑
const ocrEditText = ref('')
const ocrSaving = ref(false)

// 重新OCR识别
const reRecognizing = ref(false)
async function reRecognizeMaterial() {
  if (!viewingMaterial.value) return
  const mat = viewingMaterial.value
  try {
    await ElMessageBox.confirm(
      '重新识别会覆盖当前OCR结果，确定要重新识别吗？',
      '确认重新识别',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return  // 取消
  }
  reRecognizing.value = true
  try {
    const caseId = mat.case_id
    await api.recognizeSingle(caseId, mat.id)
    // 刷新案件材料列表获取完整 ocr_text
    await loadCase()
    // 重新定位到该材料
    const updated = allMaterials.value.find(m => m.id === mat.id)
    if (updated) {
      viewingMaterial.value = updated
      ocrEditText.value = updated.ocr_text || ''
    }
    ocrViewMode.value = 'render'
    ElMessage.success('重新识别完成')
  } catch (e) {
    console.error('重新识别失败', e)
    ElMessage.error('重新识别失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    reRecognizing.value = false
  }
}

// 原图URL
const materialImageUrl = computed(() => {
  if (!viewingMaterial.value?.file_path) return ''
  const fp = viewingMaterial.value.file_path
  // file_path 是绝对路径或相对路径，提取 /uploads/... 部分
  const idx = fp.indexOf('/uploads/')
  if (idx >= 0) {
    return getBackendUrl(fp.substring(idx))
  }
  // 如果 file_path 已经是 /uploads/ 开头
  if (fp.startsWith('/uploads/')) {
    return getBackendUrl(fp)
  }
  return getBackendUrl('uploads/' + fp.split('/uploads/').pop())
})

// 复制图片引用
function copyImageRef() {
  const ref = `![](${materialImageUrl.value})`
  navigator.clipboard.writeText(ref).then(() => {
    ElMessage.success('已复制图片引用语法')
  }).catch(() => {
    ElMessage.warning('复制失败，请手动复制')
  })
}

// 保存OCR文本
async function saveOcrText() {
  if (!viewingMaterial.value) return
  ocrSaving.value = true
  try {
    await api.updateOcrText(viewingMaterial.value.id, ocrEditText.value)
    viewingMaterial.value.ocr_text = ocrEditText.value
    ElMessage.success('OCR文本已保存')
    ocrViewMode.value = 'render'
  } catch (e) {
    console.error('保存OCR文本失败', e)
    ElMessage.error('保存失败')
  } finally {
    ocrSaving.value = false
  }
}

// 图片缩放与拖动
const imageZoom = ref(1)
const isDragging = ref(false)
const dragStart = ref({ x: 0, y: 0, scrollLeft: 0, scrollTop: 0 })
const imageContainerRef = ref(null)

function zoomIn() {
  if (imageZoom.value < 3) imageZoom.value = Math.min(3, Math.round((imageZoom.value + 0.25) * 100) / 100)
}
function zoomOut() {
  if (imageZoom.value > 0.5) imageZoom.value = Math.max(0.5, Math.round((imageZoom.value - 0.25) * 100) / 100)
}
function zoomReset() {
  imageZoom.value = 1
  if (imageContainerRef.value) {
    imageContainerRef.value.scrollLeft = 0
    imageContainerRef.value.scrollTop = 0
  }
}
function onImageDragStart(e) {
  if (imageZoom.value <= 1) return
  isDragging.value = true
  dragStart.value = {
    x: e.clientX,
    y: e.clientY,
    scrollLeft: imageContainerRef.value?.scrollLeft || 0,
    scrollTop: imageContainerRef.value?.scrollTop || 0
  }
  e.preventDefault()
}
function onImageDragMove(e) {
  if (!isDragging.value) return
  const dx = e.clientX - dragStart.value.x
  const dy = e.clientY - dragStart.value.y
  if (imageContainerRef.value) {
    imageContainerRef.value.scrollLeft = dragStart.value.scrollLeft - dx
    imageContainerRef.value.scrollTop = dragStart.value.scrollTop - dy
  }
}
function onImageDragEnd() {
  isDragging.value = false
}

// PDF 查看相关（复用图片缩放逻辑）
function pdfZoomIn() {
  if (pdfImageZoom.value < 3) pdfImageZoom.value = Math.min(3, Math.round((pdfImageZoom.value + 0.25) * 100) / 100)
}
function pdfZoomOut() {
  if (pdfImageZoom.value > 0.5) pdfImageZoom.value = Math.max(0.5, Math.round((pdfImageZoom.value - 0.25) * 100) / 100)
}
function pdfZoomReset() {
  pdfImageZoom.value = 1
  if (pdfImageContainerRef.value) {
    pdfImageContainerRef.value.scrollLeft = 0
    pdfImageContainerRef.value.scrollTop = 0
  }
}
function onPdfImageDragStart(e) {
  if (pdfImageZoom.value <= 1) return
  pdfIsDragging.value = true
  pdfDragStart.value = {
    x: e.clientX,
    y: e.clientY,
    scrollLeft: pdfImageContainerRef.value?.scrollLeft || 0,
    scrollTop: pdfImageContainerRef.value?.scrollTop || 0
  }
  e.preventDefault()
}
function onPdfImageDragMove(e) {
  if (!pdfIsDragging.value) return
  const dx = e.clientX - pdfDragStart.value.x
  const dy = e.clientY - pdfDragStart.value.y
  if (pdfImageContainerRef.value) {
    pdfImageContainerRef.value.scrollLeft = pdfDragStart.value.scrollLeft - dx
    pdfImageContainerRef.value.scrollTop = pdfDragStart.value.scrollTop - dy
  }
}
function onPdfImageDragEnd() {
  pdfIsDragging.value = false
}

// PDF 上传与转换
function triggerPdfUpload() {
  pdfUploadInput.value?.click()
}
function handlePdfFileSelected(event) {
  const file = event.target.files?.[0]
  if (!file) return
  const rawFile = file
  if (!rawFile.name?.toLowerCase().endsWith('.pdf')) {
    ElMessage.error('只支持 PDF 文件')
    return
  }
  // 只是添加到待转换列表，不自动转换
  const tempId = Date.now() + Math.random()
  uploadedPdfs.value.push({
    tempId,
    filename: rawFile.name,
    size: rawFile.size || 0,
    file: rawFile,
    converting: false,
    converted: false,
    pageCount: 0
  })
}
async function convertPdf(pdfItem) {
  // 找到对应的 PDF 项并标记为转换中
  const target = uploadedPdfs.value.find(p => p.tempId === pdfItem.tempId)
  if (!target) return
  target.converting = true
  try {
    const result = await api.uploadPdf(caseId, target.file)
    if (result.pages && result.pages.length > 0) {
      // 存储到该 PDF 的 pages 中
      target.pages = result.pages.map(p => ({ ...p, imported: false, material_id: null }))
      target.converted = true
      target.pageCount = result.total_pages
      target.filename = result.pdf_filename  // 使用返回的原始文件名
      target.expanded = true  // 转换后默认展开
      // 保存文件名前缀，用于删除时定位文件
      const firstPage = result.pages[0]
      const prefixMatch = firstPage.filename.match(/^(case\d+_\w+)-\d+\.png$/)
      target.prefix = prefixMatch ? prefixMatch[1] : null
      ElMessage.success(`PDF 转换完成，共 ${result.total_pages} 页`)
    }
    await refreshImportedPdfPages()
  } catch (e) {
    console.error('PDF 转换失败', e)
    ElMessage.error('PDF 转换失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    target.converting = false
  }
}
async function removeUploadedPdf(tempId) {
  const pdf = uploadedPdfs.value.find(p => p.tempId === tempId)
  if (!pdf) return
  // 如果已转换，删除后端的文件和数据库记录
  if (pdf.converted && pdf.prefix) {
    try {
      await ElMessageBox.confirm(`确定要删除 "${pdf.filename}" 吗？将同时删除所有页面和原始 PDF 文件`, '确认删除', { type: 'warning' })
      const result = await api.deletePdf(caseId, pdf.prefix)
      ElMessage.success(result.message || '已删除')
    } catch (e) {
      if (e !== 'cancel') {
        ElMessage.error('删除失败: ' + (e.response?.data?.detail || e.message))
      }
      return
    }
  }
  // 从前端列表移除
  const idx = uploadedPdfs.value.findIndex(p => p.tempId === tempId)
  if (idx >= 0) {
    uploadedPdfs.value.splice(idx, 1)
  }
}
async function loadPdfPages() {
  try {
    const pages = await api.getPdfPages(caseId)
    // 按 PDF 前缀分组到 uploadedPdfs
    const pdfMap = {}
    pages.forEach(p => {
      // 从 filename 提取 PDF 前缀，如 case123_abc-1.png -> case123_abc
      const match = p.filename.match(/^(case\d+_\w+)-\d+\.png$/)
      if (match) {
        const prefix = match[1]
        if (!pdfMap[prefix]) {
          pdfMap[prefix] = {
            tempId: 'loaded_' + prefix,
            filename: p.original_pdf_filename || (prefix + '.pdf'),
            prefix: prefix,
            size: 0,
            file: null,
            converting: false,
            converted: true,
            pageCount: 0,
            expanded: true,
            pages: []
          }
        }
        pdfMap[prefix].pages.push({ ...p, imported: p.imported, material_id: p.material_id })
        pdfMap[prefix].pageCount++
      }
    })
    uploadedPdfs.value = Object.values(pdfMap)
    await refreshImportedPdfPages()
  } catch (e) {
    console.error('加载 PDF 页面失败', e)
  }
}
async function refreshImportedPdfPages() {
  const pages = await api.getPdfPages(caseId)
  importedPdfPages.value = pages
    .filter(p => p.imported)
    .map(p => ({
      filename: p.filename,
      material_id: p.material_id,
      material_type: p.material_type,
      material_type_label: p.material_type_label,
      group_id: p.group_id,
      group_name: null  // 暂不获取分组名
    }))
}
function viewPdfPage(page) {
  viewingPdfPage.value = page
  pdfImageZoom.value = 1
  showPdfImageDialog.value = true
}
function viewPdfPageByFilename(filename) {
  const found = findPdfAndPage(filename)
  if (found) {
    viewingPdfPage.value = found.page
    pdfImageZoom.value = 1
    showPdfImageDialog.value = true
  }
}
function togglePdfPageSelection(pdfTempId, filename) {
  const key = pdfTempId + '::' + filename
  const idx = selectedPdfPages.value.findIndex(s => s.pdfTempId === pdfTempId && s.filename === filename)
  if (idx >= 0) {
    selectedPdfPages.value.splice(idx, 1)
  } else {
    selectedPdfPages.value.push({ pdfTempId, filename })
  }
}
function togglePdfPageSelectionByKey(key) {
  const idx = selectedPdfPages.value.findIndex(s => (s.pdfTempId + '::' + s.filename) === key)
  if (idx >= 0) {
    selectedPdfPages.value.splice(idx, 1)
  } else {
    const [pdfTempId, filename] = key.split('::')
    selectedPdfPages.value.push({ pdfTempId, filename })
  }
}
function toggleAllPdfPagesOfPdf(pdf, checked) {
  if (checked) {
    pdf.pages.forEach(p => {
      if (!p.imported && !selectedPdfPages.value.some(s => s.pdfTempId === pdf.tempId && s.filename === p.filename)) {
        selectedPdfPages.value.push({ pdfTempId: pdf.tempId, filename: p.filename })
      }
    })
  } else {
    selectedPdfPages.value = selectedPdfPages.value.filter(s => s.pdfTempId !== pdf.tempId)
  }
}
function toggleAllPdfPages(checked) {
  if (checked) {
    uploadedPdfs.value.forEach(pdf => {
      pdf.pages.forEach(p => {
        if (!p.imported && !selectedPdfPages.value.some(s => s.pdfTempId === pdf.tempId && s.filename === p.filename)) {
          selectedPdfPages.value.push({ pdfTempId: pdf.tempId, filename: p.filename })
        }
      })
    })
  } else {
    selectedPdfPages.value = []
  }
}
function getPdfSelectedCount(pdfTempId) {
  return selectedPdfPages.value.filter(s => s.pdfTempId === pdfTempId).length
}
const isAllPdfPagesSelected = computed(() => {
  const allNotImported = []
  uploadedPdfs.value.forEach(pdf => {
    pdf.pages.forEach(p => {
      if (!p.imported) allNotImported.push(pdf.tempId + '::' + p.filename)
    })
  })
  if (allNotImported.length === 0) return false
  return allNotImported.every(key => selectedPdfPages.value.some(s => (s.pdfTempId + '::' + s.filename) === key))
})
const isSomePdfPagesSelected = computed(() => {
  const allNotImported = []
  uploadedPdfs.value.forEach(pdf => {
    pdf.pages.forEach(p => {
      if (!p.imported) allNotImported.push(pdf.tempId + '::' + p.filename)
    })
  })
  const selected = allNotImported.filter(key => selectedPdfPages.value.some(s => (s.pdfTempId + '::' + s.filename) === key))
  return selected.length > 0 && selected.length < allNotImported.length
})
// 辅助函数：在所有 PDF 中查找页面
function findPdfAndPage(filename) {
  for (const pdf of uploadedPdfs.value) {
    const page = pdf.pages?.find(p => p.filename === filename)
    if (page) return { pdf, page }
  }
  return null
}
async function deletePdfPage(page) {
  try {
    await ElMessageBox.confirm('确定要删除该页面吗？删除后不可恢复', '确认删除', { type: 'warning' })
    await api.deletePdfPage(caseId, page.filename)
    // 从对应 PDF 中移除
    for (const pdf of uploadedPdfs.value) {
      const idx = pdf.pages?.findIndex(p => p.filename === page.filename)
      if (idx >= 0) {
        pdf.pages.splice(idx, 1)
        pdf.pageCount--
        break
      }
    }
    selectedPdfPages.value = selectedPdfPages.value.filter(s => s.filename !== page.filename)
    ElMessage.success('已删除')
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error('删除失败: ' + (e.response?.data?.detail || e.message))
    }
  }
}
async function revertPdfImport(page) {
  try {
    await ElMessageBox.confirm('确定要撤销导入吗？文件将保留在转换结果中', '确认撤销', { type: 'warning' })
    await api.revertPdfImport(caseId, page.filename)
    // 更新本地状态
    const found = findPdfAndPage(page.filename)
    if (found) {
      found.page.imported = false
      found.page.material_id = null
      found.page.material_type = null
      found.page.material_type_label = null
    }
    await refreshImportedPdfPages()
    // 刷新材料列表
    await loadMaterialsGrouped()
    ElMessage.success('已撤销导入')
  } catch (e) {
    ElMessage.error('撤销失败: ' + (e.response?.data?.detail || e.message))
  }
}
async function revertPdfImportByFilename(filename) {
  const found = findPdfAndPage(filename)
  if (found) {
    await revertPdfImport(found.page)
  }
}

// 快速导入单个页面
function onQuickImportTypeChange(row, type) {
  // 分组类型需要选择医院组，暂时不支持快速导入分组类型
  const cat = materialCategories.find(c => c.type === type)
  if (cat?.grouped) {
    ElMessage.warning('分组类型（病历/影像学报告）暂不支持单页快速导入，请使用批量导入')
    row.quickImportType = null
    return
  }
}

async function quickImportSingle(row) {
  if (!row.quickImportType) {
    ElMessage.warning('请先选择导入类型')
    return
  }
  try {
    const data = {
      filenames: [row.filename],
      material_type: row.quickImportType,
      group_id: null,
      group_name: null
    }
    const result = await api.importPdfPages(caseId, data)
    if (result.imported && result.imported.length > 0) {
      ElMessage.success(`已导入: ${row.filename}`)
    }
    if (result.failed && result.failed.length > 0) {
      ElMessage.warning(`${result.failed.length} 张导入失败`)
    }
    await loadPdfPages()
    await loadMaterialsGrouped()
  } catch (e) {
    ElMessage.error('导入失败: ' + (e.response?.data?.detail || e.message))
  }
}

// 查看对话框中的导入
async function importViewingPage() {
  if (!viewingPdfPage.value) return
  if (!viewingPdfImportType.value) {
    ElMessage.warning('请选择导入类型')
    return
  }
  const cat = materialCategories.find(c => c.type === viewingPdfImportType.value)
  if (cat?.grouped && !viewingPdfImportGroupId.value && !viewingPdfNewGroupName.value) {
    ElMessage.warning('分组类型需要选择医院组或输入新建组名')
    return
  }

  importingPdfPage.value = true
  try {
    const data = {
      filenames: [viewingPdfPage.value.filename],
      material_type: viewingPdfImportType.value,
      group_id: viewingPdfImportGroupId.value || null,
      group_name: viewingPdfNewGroupName.value || null
    }
    const result = await api.importPdfPages(caseId, data)
    if (result.imported && result.imported.length > 0) {
      ElMessage.success('已导入')
    }
    // 刷新
    await loadPdfPages()
    await loadMaterialsGrouped()
    // 更新对话框中的页面信息
    const updated = pdfPages.value.find(p => p.filename === viewingPdfPage.value.filename)
    if (updated) {
      viewingPdfPage.value = updated
    }
    // 清空
    viewingPdfImportType.value = ''
    viewingPdfImportGroupId.value = null
    viewingPdfNewGroupName.value = ''
  } catch (e) {
    ElMessage.error('导入失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    importingPdfPage.value = false
  }
}

async function revertViewingPdfPage() {
  if (!viewingPdfPage.value) return
  try {
    await ElMessageBox.confirm('确定要撤销导入吗？文件将保留', '确认撤销', { type: 'warning' })
    revertingPdfPage.value = true
    await api.revertPdfImport(caseId, viewingPdfPage.value.filename)
    ElMessage.success('已撤销导入')
    await loadPdfPages()
    await loadMaterialsGrouped()
    // 更新对话框中的页面信息
    const updated = pdfPages.value.find(p => p.filename === viewingPdfPage.value.filename)
    if (updated) {
      viewingPdfPage.value = updated
    }
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error('撤销失败: ' + (e.response?.data?.detail || e.message))
    }
  } finally {
    revertingPdfPage.value = false
  }
}

async function importSelectedPdfPages() {
  if (!selectedPdfPages.value.length) {
    ElMessage.warning('请先选择要导入的页面')
    return
  }
  if (!importTargetType.value) {
    ElMessage.warning('请选择导入类型')
    return
  }
  // 分组类型检查
  const cat = materialCategories.find(c => c.type === importTargetType.value)
  if (cat?.grouped && !importTargetGroupId.value && !pdfNewGroupName.value) {
    ElMessage.warning('分组类型需要选择医院组或输入新建组名')
    return
  }

  try {
    const data = {
      filenames: selectedPdfPages.value.map(s => s.filename),
      material_type: importTargetType.value,
      group_id: importTargetGroupId.value || null,
      group_name: pdfNewGroupName.value || null
    }
    const result = await api.importPdfPages(caseId, data)
    if (result.imported && result.imported.length > 0) {
      ElMessage.success(`成功导入 ${result.imported.length} 张`)
    }
    if (result.failed && result.failed.length > 0) {
      ElMessage.warning(`${result.failed.length} 张导入失败`)
    }
    // 刷新 PDF 页面状态
    await loadPdfPages()
    // 刷新材料列表（让导入的材料显示到对应分类下）
    await loadMaterialsGrouped()
    selectedPdfPages.value = []
    pdfNewGroupName.value = ''
    importTargetGroupId.value = null
  } catch (e) {
    console.error('导入失败', e)
    ElMessage.error('导入失败: ' + (e.response?.data?.detail || e.message))
  }
}
async function importSelectedPdfPagesOfPdf(pdf) {
  // 导入该 PDF 下选中的页面
  const selected = selectedPdfPages.value.filter(s => s.pdfTempId === pdf.tempId)
  if (!selected.length) {
    ElMessage.warning('请先选择要导入的页面')
    return
  }
  if (!importTargetType.value) {
    ElMessage.warning('请选择导入类型')
    return
  }
  const cat = materialCategories.find(c => c.type === importTargetType.value)
  if (cat?.grouped && !importTargetGroupId.value && !pdfNewGroupName.value) {
    ElMessage.warning('分组类型需要选择医院组或输入新建组名')
    return
  }
  try {
    const data = {
      filenames: selected.map(s => s.filename),
      material_type: importTargetType.value,
      group_id: importTargetGroupId.value || null,
      group_name: pdfNewGroupName.value || null
    }
    const result = await api.importPdfPages(caseId, data)
    if (result.imported && result.imported.length > 0) {
      ElMessage.success(`成功导入 ${result.imported.length} 张`)
    }
    if (result.failed && result.failed.length > 0) {
      ElMessage.warning(`${result.failed.length} 张导入失败`)
    }
    await loadPdfPages()
    await loadMaterialsGrouped()
    // 清除该 PDF 的选中
    selectedPdfPages.value = selectedPdfPages.value.filter(s => s.pdfTempId !== pdf.tempId)
  } catch (e) {
    ElMessage.error('导入失败: ' + (e.response?.data?.detail || e.message))
  }
}

// 辅助函数
function getCategoryGrouped(type) {
  const cat = materialCategories.find(c => c.type === type)
  return cat?.grouped || false
}
function getGroupsForType(type) {
  if (!materialsByType.value[type]) return []
  return materialsByType.value[type]
    .filter(g => g.group)
    .map(g => g.group)
}

// 对话框
const showRecordDialog = ref(false)
const showAddRecordDialog = ref(false)
const showAddImagingDialog = ref(false)
const showImagingDialog = ref(false)
const saving = ref(false)

// 编辑中的住院记录
const editingRecord = ref({})
// 编辑中的影像学报告
const editingImaging = ref({ exam_type: 'CT', film_count: 1, exam_part: '' })

// === 材料类型配置 ===
const materialCategories = [
  { type: 'entrustment_letter', label: '司法鉴定委托书', icon: 'Postcard', color: '#409EFF', grouped: false },
  { type: 'id_card', label: '身份证复印件', icon: 'PictureFilled', color: '#67C23A', grouped: false },
  { type: 'traffic_accident_cert', label: '道路交通事故认定书', icon: 'Document', color: '#E6A23C', grouped: false },
  { type: 'appraisal_application', label: '鉴定申请书', icon: 'Notebook', color: '#F56C6C', grouped: false },
  { type: 'medical_record', label: '医院病历', icon: 'FirstAidKit', color: '#909399', grouped: true, groupLabel: '医院' },
  { type: 'imaging_report', label: '影像学报告', icon: 'PictureFilled', color: '#9B59B6', grouped: true, groupLabel: '医院' },
]

// === 计算属性 ===
const isCompleted = computed(() => caseData.value.status === 'completed')

const allSectionsFilled = computed(() => {
  return !!(
    caseData.value.entrusting_unit &&
    personData.value.name &&
    reportData.value.case_facts &&
    reportData.value.material_summary &&
    reportData.value.appraisal_process &&
    reportData.value.analysis &&
    reportData.value.opinion
  )
})

const allMaterials = computed(() => {
  // 把 materialsByType 展平为列表，加 _recognizing 标记
  const list = []
  for (const type in materialsByType.value) {
    const data = materialsByType.value[type]
    if (!data) continue
    if (Array.isArray(data) && data.length > 0 && data[0].group !== undefined) {
      // 分组类型
      data.forEach(item => {
        (item.files || []).forEach(f => {
          list.push({ ...f, _recognizing: recognizingIds.value.has(f.id) })
        })
      })
    } else if (Array.isArray(data)) {
      data.forEach(f => {
        list.push({ ...f, _recognizing: recognizingIds.value.has(f.id) })
      })
    }
  }
  return list
})

const totalMaterialCount = computed(() => allMaterials.value.length)

const pendingCount = computed(() => allMaterials.value.filter(m => m.ocr_status === 'pending' || m.ocr_status === 'failed').length)

const completedCount = computed(() => allMaterials.value.filter(m => m.ocr_status === 'completed').length)

const failedCount = computed(() => allMaterials.value.filter(m => m.ocr_status === 'failed').length)

// === 材料分组和查询 ===
function countMaterialsForType(type) {
  const data = materialsByType.value[type]
  if (!data) return 0
  if (Array.isArray(data) && data.length > 0 && data[0].group !== undefined) {
    return data.reduce((sum, item) => sum + (item.files?.length || 0), 0)
  }
  return data.length || 0
}

function getFlatMaterials(type) {
  const data = materialsByType.value[type]
  if (!data) return []
  if (Array.isArray(data) && data.length > 0 && data[0].group !== undefined) {
    return data.flatMap(item => item.files || [])
  }
  return data
}

function getGroupedMaterials(type) {
  const data = materialsByType.value[type]
  if (!data) return []
  if (Array.isArray(data) && data.length > 0 && data[0].group !== undefined) {
    return data
  }
  return []
}

function getTypeLabel(type) {
  const cat = materialCategories.find(c => c.type === type)
  return cat ? cat.label : type
}

function getTypeColor(type) {
  const cat = materialCategories.find(c => c.type === type)
  return cat ? cat.color : '#909399'
}

function ocrStatusLabel(status) {
  const map = { pending: '待识别', processing: '识别中', completed: '已完成', failed: '识别失败' }
  return map[status] || status
}

function ocrStatusTag(status) {
  const map = { pending: 'info', processing: 'warning', completed: 'success', failed: 'danger' }
  return map[status] || 'info'
}

// === 加载数据 ===
onMounted(async () => {
  await loadCase()
})

async function loadCase() {
  try {
    const data = await api.getCase(caseId)
    caseData.value = data
    hospitalRecords.value = data.hospital_records || []
    imagingReports.value = data.imaging_reports || []
    if (data.person) {
      personData.value = { ...data.person }
    }
    if (data.report) {
      reportData.value = data.report
    }
    await loadMaterialsGrouped()
    // 加载 PDF 转换页面
    await loadPdfPages()
  } catch (e) {
    ElMessage.error('加载案件失败')
  }
}

async function loadMaterialsGrouped() {
  try {
    const grouped = await api.getCaseMaterialsGrouped(caseId)
    materialsByType.value = grouped
  } catch (e) {
    const mats = caseData.value.materials || []
    const grouped = {}
    mats.forEach(m => {
      if (!grouped[m.material_type]) grouped[m.material_type] = []
      grouped[m.material_type].push(m)
    })
    materialsByType.value = grouped
  }
}

// === 案件完成/重开 ===
async function handleComplete() {
  try {
    await ElMessageBox.confirm('确认完成此案件？完成后将不可再修改（除非重新打开）。', '提示', { type: 'warning' })
    await api.confirmCase(caseId)
    ElMessage.success('案件已完成')
    await loadCase()
  } catch (e) { /* 取消 */ }
}

async function handleReopen() {
  try {
    await ElMessageBox.confirm('确定重新打开此案件？', '提示', { type: 'warning' })
    await api.reopenCase(caseId)
    ElMessage.success('案件已重新打开')
    await loadCase()
  } catch (e) { /* 取消 */ }
}

// === 单字段保存案件 ===
async function saveCaseField(field, value) {
  try {
    await api.updateCase(caseId, { [field]: value })
    ElMessage.success('保存成功')
  } catch (e) { /* 错误已在拦截器中处理 */ }
}

// === 基本情况保存 ===
async function saveBasicInfo() {
  try {
    const updateData = {
      entrusting_unit: caseData.value.entrusting_unit,
      entrustment_matter: caseData.value.entrustment_matter,
      acceptance_date: caseData.value.acceptance_date,
      appraisal_location: caseData.value.appraisal_location,
      on_site_personnel: caseData.value.on_site_personnel,
      material_list: caseData.value.material_list,
    }
    await api.updateCase(caseId, updateData)

    const hasPersonData = personData.value.name || personData.value.gender ||
      personData.value.birth_date || personData.value.id_number || personData.value.address
    if (hasPersonData) {
      await api.updatePersonByCase(caseId, { ...personData.value })
    }

    ElMessage.success('保存成功')
    await loadCase()
  } catch (e) { /* 错误已在拦截器中处理 */ }
}

// === 报告保存 ===
async function saveReport() {
  try {
    if (!reportData.value.id) {
      const res = await api.createReport({
        case_id: caseId,
        ...reportData.value,
      })
      reportData.value = res
    } else {
      const res = await api.updateReport(reportData.value.id, {
        case_facts: reportData.value.case_facts,
        material_summary: reportData.value.material_summary,
        appraisal_process: reportData.value.appraisal_process,
        analysis: reportData.value.analysis,
        opinion: reportData.value.opinion,
      })
      reportData.value = res
    }
    ElMessage.success('保存成功')
  } catch (e) { /* 错误已在拦截器中处理 */ }
}

// === 鉴定意见确认 ===
async function handleConfirmOpinion() {
  try {
    if (reportData.value.opinion_confirmed) {
      await api.unconfirmOpinion(reportData.value.id)
      ElMessage.success('鉴定意见确认已取消')
    } else {
      await ElMessageBox.confirm('确认鉴定意见无误？确认后不可随意修改。', '确认鉴定意见', { type: 'warning' })
      await api.confirmOpinion(reportData.value.id)
      ElMessage.success('鉴定意见已确认')
    }
    await loadCase()
  } catch (e) { /* 取消 */ }
}

// === OCR 操作 ===
async function handleRecognizeSingle(mat) {
  try {
    recognizingIds.value.add(mat.id)
    // 强制触发响应式更新
    recognizingIds.value = new Set(recognizingIds.value)
    await api.recognizeSingle(caseId, mat.id)
    ElMessage.success(`识别完成：${mat.description || mat.original_filename}`)
    await loadCase()
  } catch (e) {
    ElMessage.error('识别失败')
  } finally {
    recognizingIds.value.delete(mat.id)
    recognizingIds.value = new Set(recognizingIds.value)
  }
}

async function handleRecognizeAll() {
  if (pendingCount.value === 0) {
    ElMessage.info('没有待识别的材料')
    return
  }
  try {
    ocrRunning.value = true
    const result = await api.recognizeAll(caseId)
    if (result.status === 'stopped') {
      const completed = result.results?.filter(r => r.status === 'completed').length || 0
      const failed = result.results?.filter(r => r.status === 'failed').length || 0
      ElMessage.warning(`识别已停止（${result.stop_type === 'force' ? '强制' : '正常'}），已完成 ${completed} 张，失败 ${failed} 张`)
    } else {
      const completed = result.results?.filter(r => r.status === 'completed').length || 0
      const failed = result.results?.filter(r => r.status === 'failed').length || 0
      ElMessage.success(`识别完成：${completed}张成功，${failed}张失败`)
    }
    await loadCase()
  } catch (e) {
    ElMessage.error('批量识别失败')
  } finally {
    ocrRunning.value = false
  }
}

async function handleStopRecognize() {
  try {
    await api.stopRecognize(caseId)
    ElMessage.info('已发出停止请求，当前张识别完后将停止')
  } catch (e) {
    ElMessage.error('停止请求失败')
  }
}

async function handleForceStopRecognize() {
  try {
    await api.forceStopRecognize(caseId)
    ocrRunning.value = false
    ElMessage.warning('已强制停止，进程已中断')
    await loadCase()
  } catch (e) {
    ElMessage.error('强制停止失败')
  }
}

// === LLM 智能提取 ===

// 全局提取（旧接口，保留兼容）
async function handleExtractAll() {
  try {
    extracting.value = true
    const result = await api.extractAll(caseId)
    ElMessage.success('智能提取完成，请检查各板块内容')
    await loadCase()
  } catch (e) {
    ElMessage.error('智能提取失败：' + (e.response?.data?.detail || '未知错误'))
  } finally {
    extracting.value = false
  }
}

// 基本情况：从委托书+身份证提取
async function handleExtractBasicInfo() {
  try {
    extractingBasic.value = true
    const result = await api.extractBasicInfo(caseId)
    ElMessage.success(result.message || '基本情况提取完成')
    await loadCase()
  } catch (e) {
    ElMessage.error('基本情况提取失败：' + (e.response?.data?.detail || '未知错误'))
  } finally {
    extractingBasic.value = false
  }
}

// 基本案情：从委托书+事故认定书生成
async function handleExtractCaseFacts() {
  try {
    extractingFacts.value = true
    const result = await api.extractCaseFacts(caseId)
    ElMessage.success(result.message || '基本案情已生成')
    if (result.case_facts) {
      reportData.value.case_facts = result.case_facts
    }
    await loadCase()
  } catch (e) {
    ElMessage.error('基本案情提取失败：' + (e.response?.data?.detail || '未知错误'))
  } finally {
    extractingFacts.value = false
  }
}

// 资料摘要：从病历提取住院记录
// 病历按医院分组提取
const medicalGroupList = ref([])  // 医院分组列表
const loadingMedicalGroups = ref(false)
const extractingAllGroups = ref(false)

// 加载医院分组信息（不调LLM，瞬间返回）
async function loadMedicalGroups() {
  try {
    loadingMedicalGroups.value = true
    const result = await api.getMedicalGroups(caseId)
    if (result.groups && result.groups.length > 0) {
      medicalGroupList.value = result.groups.map(g => ({
        ...g,
        extracting: false,
        extracted: g.has_record || false,
      }))
    } else {
      ElMessage.warning('没有已识别的病历材料，请先进行OCR识别')
    }
  } catch (e) {
    ElMessage.error('获取病历分组失败：' + (e.response?.data?.detail || '未知错误'))
  } finally {
    loadingMedicalGroups.value = false
  }
}

// 提取单个医院
async function handleExtractOneGroup(g) {
  const idx = medicalGroupList.value.findIndex(item => item.group_id === g.group_id)
  if (idx === -1) return

  medicalGroupList.value[idx].extracting = true
  try {
    const result = await api.extractMedicalGroup(caseId, g.group_id)
    if (result.status === 'completed') {
      ElMessage.success(`${g.group_name} 提取成功`)
      medicalGroupList.value[idx].extracted = true
      medicalGroupList.value[idx].has_record = true
      medicalGroupList.value[idx].record_id = result.record_id
      await loadCase()
    } else {
      ElMessage.error(`${g.group_name} 提取失败：${result.error || '未知错误'}`)
    }
  } catch (e) {
    ElMessage.error(`${g.group_name} 提取失败：` + (e.response?.data?.detail || '未知错误'))
  } finally {
    medicalGroupList.value[idx].extracting = false
  }
}

// 一键全部提取
async function handleExtractAllGroups() {
  extractingAllGroups.value = true
  const groups = medicalGroupList.value.filter(g => g.completed_count > 0)
  let successCount = 0

  for (const g of groups) {
    const idx = medicalGroupList.value.findIndex(item => item.group_id === g.group_id)
    if (idx === -1) continue

    medicalGroupList.value[idx].extracting = true
    try {
      const result = await api.extractMedicalGroup(caseId, g.group_id)
      if (result.status === 'completed') {
        successCount++
        medicalGroupList.value[idx].extracted = true
        medicalGroupList.value[idx].has_record = true
        medicalGroupList.value[idx].record_id = result.record_id
      }
    } catch (e) {
      logger.error(`提取 ${g.group_name} 失败: ${e.message}`)
    } finally {
      medicalGroupList.value[idx].extracting = false
    }
  }

  await loadCase()
  extractingAllGroups.value = false
  ElMessage.success(`病历提取完成，成功 ${successCount}/${groups.length} 家医院`)
}

// 兼容旧接口（保留）
async function handleExtractMedicalRecords() {
  try {
    extractingMedical.value = true
    const result = await api.extractMedicalRecords(caseId)
    ElMessage.success(result.message || '病历提取完成')
    await loadCase()
  } catch (e) {
    ElMessage.error('病历提取失败：' + (e.response?.data?.detail || '未知错误'))
  } finally {
    extractingMedical.value = false
  }
}

// 资料摘要：独立生成摘要文本
async function handleGenerateSummary() {
  try {
    generatingSummary.value = true
    const result = await api.generateMaterialSummary(caseId)
    ElMessage.success(result.message || '资料摘要生成成功')
    if (result.material_summary) {
      reportData.value.material_summary = result.material_summary
    }
    await loadCase()
  } catch (e) {
    ElMessage.error('资料摘要生成失败：' + (e.response?.data?.detail || '未知错误'))
  } finally {
    generatingSummary.value = false
  }
}

// 鉴定过程：LLM生成（法医临床检查套话 + 影像复阅）
async function generateAppraisalProcess() {
  try {
    generatingProcess.value = true
    // 先保存法医检查信息
    await api.updateCase(caseId, {
      examination_date: caseData.value.examination_date,
      clinical_examination: caseData.value.clinical_examination,
    })
    const result = await api.generateAppraisalProcess(caseId)
    if (result.appraisal_process) {
      reportData.value.appraisal_process = result.appraisal_process
    }
    // 提示用户生成方式
    if (result.method === 'fallback') {
      ElMessage.warning('LLM服务暂不可用，已使用拼接模式生成，建议稍后重试')
    } else {
      ElMessage.success('鉴定过程生成成功')
    }
  } catch (e) {
    ElMessage.error('鉴定过程生成失败：' + (e.response?.data?.detail || '未知错误'))
  } finally {
    generatingProcess.value = false
  }
}

// 鉴定过程：智能提取影像学报告（只提取数据到表格，不自动生成鉴定过程）
async function handleExtractImagingReports() {
  try {
    extractingImaging.value = true
    const result = await api.extractImagingReports(caseId)
    ElMessage.success(result.message || '影像学报告提取完成')
    await loadCase()
  } catch (e) {
    ElMessage.error('影像学报告提取失败：' + (e.response?.data?.detail || '未知错误'))
  } finally {
    extractingImaging.value = false
  }
}

// 分析说明：基于住院记录和影像学报告生成
async function handleGenerateAnalysis() {
  try {
    extractingAnalysis.value = true
    const result = await api.generateAnalysis(caseId)
    if (result.analysis) {
      reportData.value.analysis = result.analysis
    }
    // 提示用户生成方式
    if (result.method === 'fallback') {
      ElMessage.warning('LLM服务暂不可用，已使用拼接模式生成，建议稍后重试')
    } else {
      ElMessage.success('分析说明已生成')
    }
    await loadCase()
  } catch (e) {
    ElMessage.error('分析说明生成失败：' + (e.response?.data?.detail || '未知错误'))
  } finally {
    extractingAnalysis.value = false
  }
}

// 鉴定意见：基于分析说明生成
async function handleGenerateOpinion() {
  try {
    extractingOpinion.value = true
    const result = await api.generateOpinion(caseId)
    ElMessage.success(result.message || '鉴定意见已生成')
    if (result.opinion) {
      reportData.value.opinion = result.opinion
    }
    // 不再调用 loadCase()，避免用数据库旧值覆盖刚生成的内容
  } catch (e) {
    ElMessage.error('鉴定意见生成失败：' + (e.response?.data?.detail || '未知错误'))
  } finally {
    extractingOpinion.value = false
  }
}

// === 生成 Word 报告 ===
async function handleGenerateWord() {
  if (!reportData.value.id) {
    ElMessage.warning('请先保存报告内容')
    return
  }
  try {
    generatingWord.value = true
    // 使用 fetch 直接下载文件
    const resp = await fetch(`/api/reports/${reportData.value.id}/generate-word`, {
      method: 'POST',
    })
    if (!resp.ok) {
      const err = await resp.json()
      throw new Error(err.detail || '生成失败')
    }
    const blob = await resp.blob()
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    const contentDisposition = resp.headers.get('content-disposition')
    let filename = '鉴定报告.docx'
    if (contentDisposition) {
      const match = contentDisposition.match(/filename\*?=(?:UTF-8'')?(.+)/)
      if (match) filename = decodeURIComponent(match[1])
    }
    link.download = filename
    link.click()
    window.URL.revokeObjectURL(url)
    ElMessage.success('报告生成成功')
  } catch (e) {
    ElMessage.error('生成报告失败：' + (e.message || '未知错误'))
  } finally {
    generatingWord.value = false
  }
}

// === 材料上传（按类型） ===
function triggerUpload(materialType) {
  currentUploadType.value = materialType
  currentGroupId.value = null
  singleUploadInput.value?.click()
}

function triggerBatchUpload(materialType) {
  currentUploadType.value = materialType
  currentGroupId.value = null
  batchUploadInput.value?.click()
}

function triggerUploadToGroup(materialType, groupId) {
  currentUploadType.value = materialType
  currentGroupId.value = groupId
  singleUploadInput.value?.click()
}

function triggerBatchUploadToGroup(materialType, groupId) {
  currentUploadType.value = materialType
  currentGroupId.value = groupId
  batchUploadInput.value?.click()
}

async function handleFileSelected(event) {
  const files = Array.from(event.target.files)
  if (!files.length) return

  uploading.value = true
  try {
    if (files.length === 1) {
      await api.uploadMaterial(caseId, files[0], currentUploadType.value, currentGroupId.value)
    } else {
      await api.uploadMaterialsBatch(caseId, files, currentUploadType.value, currentGroupId.value)
    }
    ElMessage.success(`成功上传 ${files.length} 张`)
    await loadCase()
  } catch (e) {
    ElMessage.error('上传失败')
  } finally {
    uploading.value = false
    event.target.value = ''
  }
}

// === 材料分组操作 ===
function handleAddGroup(materialType) {
  currentUploadType.value = materialType
  const cat = materialCategories.find(c => c.type === materialType)
  currentGroupLabel.value = cat?.groupLabel || '医院'
  newGroupName.value = ''
  showNewGroupDialog.value = true
}

async function confirmAddGroup() {
  if (!newGroupName.value.trim()) {
    ElMessage.warning('请输入名称')
    return
  }
  uploading.value = true
  try {
    await api.createMaterialGroup({
      case_id: caseId,
      material_type: currentUploadType.value,
      group_name: newGroupName.value.trim(),
    })
    ElMessage.success('分组创建成功')
    showNewGroupDialog.value = false
    await loadCase()
  } catch (e) {
    ElMessage.error('创建分组失败')
  } finally {
    uploading.value = false
  }
}

function handleRenameGroup(group) {
  renameGroupId.value = group.id
  renameGroupName.value = group.group_name
  showRenameGroupDialog.value = true
}

async function confirmRenameGroup() {
  if (!renameGroupName.value.trim()) {
    ElMessage.warning('请输入名称')
    return
  }
  uploading.value = true
  try {
    await api.updateMaterialGroup(renameGroupId.value, {
      group_name: renameGroupName.value.trim(),
    })
    ElMessage.success('名称修改成功')
    showRenameGroupDialog.value = false
    await loadCase()
  } catch (e) {
    ElMessage.error('修改名称失败')
  } finally {
    uploading.value = false
  }
}

async function handleDeleteGroup(group) {
  try {
    await ElMessageBox.confirm(
      `确定删除「${group.group_name}」及其下所有文件？`,
      '提示', { type: 'warning' }
    )
    await api.deleteMaterialGroup(group.id)
    ElMessage.success('删除成功')
    await loadCase()
  } catch (e) { /* 取消 */ }
}

// === 删除材料 ===
async function handleDeleteMaterial(mat) {
  try {
    await ElMessageBox.confirm(`确定删除「${mat.description || mat.original_filename}」？`, '提示', { type: 'warning' })
    await api.deleteMaterial(mat.id)
    ElMessage.success('删除成功')
    await loadCase()
  } catch (e) { /* 取消 */ }
}

// === 查看 OCR 文本 ===
function viewOcrText(mat) {
  viewingMaterial.value = mat
  ocrEditText.value = mat.ocr_text || ''  // 填充编辑框
  ocrViewMode.value = 'render'  // 默认渲染视图
  showOcrDialog.value = true
}

// 统一的图片URL生成函数
function getBackendUrl(relativePath) {
  if (!relativePath) return ''
  const baseUrl = `${window.location.protocol}//${window.location.hostname}:8000`
  return relativePath.startsWith('/') ? `${baseUrl}${relativePath}` : `${baseUrl}/${relativePath}`
}

// 获取材料图片URL
function getMaterialImageUrl(mat) {
  if (!mat?.file_path) return ''
  // file_path 格式: /Users/.../backend/uploads/4/page-02.png
  // 转为: http://localhost:8000/uploads/4/page-02.png
  const uploadsIndex = mat.file_path.indexOf('/uploads/')
  if (uploadsIndex === -1) {
    console.warn('[OCR] file_path 不含 /uploads/，无法生成预览URL:', mat.file_path)
    return ''
  }
  const relativePath = mat.file_path.substring(uploadsIndex)
  return getBackendUrl(relativePath)
}

// 查看原图
function viewOriginalImage(mat) {
  viewingMaterial.value = mat
  imageZoom.value = 1
  showImageDialog.value = true
  // 重置滚动位置（对话框渲染后）
  nextTick(() => {
    if (imageContainerRef.value) {
      imageContainerRef.value.scrollLeft = 0
      imageContainerRef.value.scrollTop = 0
    }
  })
}

// === 住院记录 ===
function editHospitalRecord(record) {
  editingRecord.value = { ...record }
  showRecordDialog.value = true
}

async function deleteHospitalRecord(record) {
  try {
    await ElMessageBox.confirm('确定删除此住院记录？', '提示', { type: 'warning' })
    await api.deleteHospitalRecord(record.id)
    ElMessage.success('删除成功')
    await loadCase()
  } catch (e) { /* 取消 */ }
}

async function saveHospitalRecord() {
  saving.value = true
  try {
    if (editingRecord.value.id) {
      await api.updateHospitalRecord(editingRecord.value.id, editingRecord.value)
    } else {
      await api.createHospitalRecord({ case_id: caseId, ...editingRecord.value })
    }
    ElMessage.success('保存成功')
    showRecordDialog.value = false
    editingRecord.value = {}
    await loadCase()
  } catch (e) {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

watch(showAddRecordDialog, (val) => {
  if (val) {
    editingRecord.value = {}
    showRecordDialog.value = true
    showAddRecordDialog.value = false
  }
})

// === 影像学报告 ===
function editImagingReport(record) {
  editingImaging.value = { ...record }
  showImagingDialog.value = true
}

async function deleteImagingReport(record) {
  try {
    await ElMessageBox.confirm('确定删除此影像学报告？', '提示', { type: 'warning' })
    await api.deleteImagingReport(record.id)
    ElMessage.success('删除成功')
    await loadCase()
  } catch (e) { /* 取消 */ }
}

async function saveImagingReport() {
  saving.value = true
  try {
    if (editingImaging.value.id) {
      await api.updateImagingReport(editingImaging.value.id, editingImaging.value)
    } else {
      await api.createImagingReport({ case_id: caseId, ...editingImaging.value })
    }
    ElMessage.success('保存成功')
    showImagingDialog.value = false
    editingImaging.value = { exam_type: 'CT', film_count: 1, exam_part: '' }
    await loadCase()
  } catch (e) {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

watch(showAddImagingDialog, (val) => {
  if (val) {
    editingImaging.value = { exam_type: 'CT', film_count: 1, exam_part: '' }
    showImagingDialog.value = true
    showAddImagingDialog.value = false
  }
})
</script>

<style lang="scss" scoped>
.case-detail {
  .top-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
    .case-title {
      font-size: 16px;
      font-weight: bold;
    }
  }

  .hospital-record-card {
    margin-bottom: 16px;
    .record-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
  }
}

/* PDF 转换区 */
.pdf-section {
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
  background: #fafbfc;

  .pdf-section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;

    .pdf-section-title {
      display: flex;
      align-items: center;
      gap: 6px;
      font-weight: 600;
      font-size: 14px;
      color: #303133;
    }

    .pdf-view-toggle {
      display: flex;
      gap: 8px;
    }
  }

  .pdf-upload-area {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 20px;
    background: #f5f7fa;
    border: 2px dashed #dcdfe6;
    border-radius: 8px;
    margin-bottom: 12px;

    .pdf-upload-trigger {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 8px;
    }

    .pdf-hint {
      font-size: 12px;
      color: #909399;
    }
  }

  .pdf-converting {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 16px;
    color: #409eff;
    font-size: 14px;
    justify-content: center;
  }

  // 缩略图视图
  .pdf-thumbnail-view {
    .pdf-thumb-toolbar {
      display: flex;
      align-items: center;
      gap: 16px;
      margin-bottom: 16px;
      padding: 12px 16px;
      background: #f5f7fa;
      border-radius: 8px;

      .selected-count {
        font-size: 13px;
        color: #409eff;
        font-weight: 500;
      }

      .import-controls {
        display: flex;
        align-items: center;
        gap: 8px;
        flex: 1;
      }
    }

    .pdf-pages-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
      gap: 12px;
      margin-bottom: 12px;
    }

    .pdf-page-thumb {
      position: relative;
      border: 1px solid #e4e7ed;
      border-radius: 6px;
      overflow: hidden;
      background: #fff;
      transition: all 0.2s;

      &:hover {
        border-color: #409eff;
        box-shadow: 0 2px 8px rgba(64, 158, 255, 0.2);
      }

      &.is-imported {
        background: #f0f9eb;
        border-color: #67c23a;
      }

      &.is-selected {
        border-color: #409eff;
        box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.3);
      }

      .thumb-select {
        position: absolute;
        top: 4px;
        left: 4px;
        z-index: 3;
        background: rgba(255, 255, 255, 0.9);
        border-radius: 4px;
        padding: 2px;
        :deep(.el-checkbox) {
          display: block;
          --el-checkbox-size: 14px;
          .el-checkbox__inner {
            width: 16px;
            height: 16px;
          }
        }
      }

      .thumb-image {
        position: relative;
        height: 120px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: #f5f7fa;
        cursor: pointer;
        overflow: hidden;

        img {
          max-width: 100%;
          max-height: 100%;
          object-fit: contain;
        }

        .thumb-imported-badge {
          position: absolute;
          top: 4px;
          right: 4px;
        }
      }

      .thumb-info {
        padding: 6px 8px;
        border-top: 1px solid #f0f0f0;

        .thumb-filename {
          font-size: 12px;
          color: #606266;
          display: block;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
      }

      .thumb-actions {
        display: flex;
        justify-content: center;
        gap: 4px;
        padding: 4px 8px 6px;
        border-top: 1px solid #f0f0f0;
      }
    }
  }

  // PDF 折叠面板视图
  .pdf-fold-view {
    margin-top: 12px;
  }

  .pdf-fold-toolbar {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 12px 16px;
    background: #f5f7fa;
    border-radius: 8px;
    margin-bottom: 12px;

    .selected-count {
      font-size: 13px;
      color: #606266;
    }

    .import-controls {
      display: flex;
      align-items: center;
      gap: 8px;
      flex: 1;
    }
  }

  .pdf-fold-card {
    border: 1px solid #e4e7ed;
    border-radius: 8px;
    margin-bottom: 10px;
    overflow: hidden;
    background: #fff;

    &:hover {
      border-color: #c0c4cc;
    }
  }

  .pdf-fold-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 16px;
    cursor: pointer;
    background: #fafafa;
    transition: background 0.2s;

    &:hover {
      background: #f0f0f0;
    }

    .pdf-fold-left {
      display: flex;
      align-items: center;
      gap: 10px;

      .fold-arrow {
        transition: transform 0.3s;
        color: #909399;

        &.is-expanded {
          transform: rotate(90deg);
        }
      }

      .pdf-icon {
        color: #409eff;
        font-size: 18px;
      }

      .pdf-filename {
        font-weight: 500;
        color: #303133;
        max-width: 300px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
    }

    .pdf-fold-right {
      display: flex;
      align-items: center;
      gap: 12px;

      .page-summary {
        font-size: 12px;
        color: #909399;
      }

      .converting-text {
        color: #409eff;
        font-size: 13px;
        display: flex;
        align-items: center;
        gap: 4px;
      }
    }
  }

  .pdf-fold-body {
    padding: 12px 16px;
    border-top: 1px solid #f0f0f0;
    background: #fff;

    .pdf-fold-toolbar-inline {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 12px;
      padding: 8px 12px;
      background: #f5f7fa;
      border-radius: 6px;

      .selected-count {
        font-size: 12px;
        color: #606266;
      }

      .import-controls-inline {
        display: flex;
        align-items: center;
        gap: 6px;
        flex: 1;
      }
    }

    .pdf-pages-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
      gap: 12px;

      .pdf-page-thumb {
        position: relative;
        border: 1px solid #e4e7ed;
        border-radius: 6px;
        overflow: hidden;
        background: #fff;
        transition: all 0.2s;

        &:hover {
          border-color: #409eff;
          box-shadow: 0 2px 8px rgba(64, 158, 255, 0.2);
        }

        &.is-imported {
          background: #f0f9eb;
          border-color: #67c23a;
        }

        &.is-selected {
          border-color: #409eff;
          box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.3);
        }

        .thumb-select {
          position: absolute;
          top: 4px;
          left: 4px;
          z-index: 3;
          background: rgba(255, 255, 255, 0.9);
          border-radius: 4px;
          padding: 2px;
          :deep(.el-checkbox) {
            display: block;
            --el-checkbox-size: 14px;
            .el-checkbox__inner {
              width: 16px;
              height: 16px;
            }
          }
        }

        .thumb-image {
          position: relative;
          height: 120px;
          display: flex;
          align-items: center;
          justify-content: center;
          background: #f5f7fa;
          cursor: pointer;
          overflow: hidden;

          img {
            max-width: 100%;
            max-height: 100%;
            object-fit: contain;
          }

          .thumb-imported-badge {
            position: absolute;
            top: 4px;
            right: 4px;
          }
        }

        .thumb-info {
          padding: 6px 8px;
          border-top: 1px solid #f0f0f0;

          .thumb-filename {
            font-size: 11px;
            color: #909399;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            display: block;
          }
        }

        .thumb-actions {
          display: flex;
          justify-content: center;
          gap: 4px;
          padding: 4px 8px 6px;
          border-top: 1px solid #f0f0f0;
        }
      }
    }
  }

  // 列表视图
  .pdf-list-view {
    margin-bottom: 12px;
  }

  .pdf-list-view-inner {
    margin-bottom: 8px;
  }

  // 导入操作栏
  .pdf-import-bar {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 16px;
    background: #ecf5ff;
    border-radius: 6px;
    margin-bottom: 12px;

    .selected-count {
      font-size: 13px;
      color: #409eff;
      font-weight: 500;
    }

    .import-controls {
      display: flex;
      align-items: center;
      gap: 8px;
      flex: 1;
    }
  }

  // 已导入列表
  .pdf-imported-list {
    border: 1px solid #e4e7ed;
    border-radius: 6px;
    overflow: hidden;

    .imported-header {
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 10px 12px;
      background: #f5f7fa;
      cursor: pointer;
      font-size: 13px;
      font-weight: 500;
      color: #606266;
      user-select: none;

      &:hover {
        background: #ebeef5;
      }
    }

    .imported-items {
      padding: 8px 12px;
      background: #fff;
    }

    .imported-item {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 6px 0;
      border-bottom: 1px dashed #f0f0f0;
      font-size: 13px;

      &:last-child {
        border-bottom: none;
      }

      .imported-icon {
        color: #909399;
      }

      .imported-filename {
        color: #606266;
        flex: 1;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      .imported-arrow {
        color: #c0c4cc;
      }

      .imported-actions {
        display: flex;
        gap: 4px;
        flex-shrink: 0;
      }
    }
  }
}

/* 待转换 PDF 列表 */
.uploaded-pdfs {
  margin-top: 16px;

  .pdf-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 12px;
    background: #fff;
    border: 1px solid #e4e7ed;
    border-radius: 6px;
    margin-bottom: 8px;

    .pdf-name {
      flex: 1;
      font-size: 13px;
      color: #606266;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .pdf-size {
      font-size: 12px;
      color: #909399;
    }
  }
}

/* 已转换 PDF 列表 */
.converted-pdfs {
  margin-top: 16px;

  .pdf-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 12px;
    background: #f0f9eb;
    border: 1px solid #67c23a;
    border-radius: 6px;
    margin-bottom: 8px;

    .pdf-name {
      flex: 1;
      font-size: 13px;
      color: #606266;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
  }
}

/* 上传面板 */
.upload-panel {
  .material-category {
    border: 1px solid #ebeef5;
    border-radius: 8px;
    margin-bottom: 16px;
    overflow: hidden;

    .category-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 12px 16px;
      background: #f5f7fa;
      border-bottom: 1px solid #ebeef5;

      .category-info {
        display: flex;
        align-items: center;
        gap: 8px;
        .category-name { font-weight: 600; font-size: 14px; }
      }

      .category-actions {
        display: flex;
        gap: 8px;
      }
    }

    .category-files {
      padding: 8px 16px;
      .file-item {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 8px 0;
        border-bottom: 1px solid #f0f0f0;
        &:last-child { border-bottom: none; }
        .file-info {
          display: flex;
          align-items: center;
          gap: 8px;
          flex: 1;
          min-width: 0;
          .file-name {
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            max-width: 400px;
            font-size: 13px;
          }
        }
        .file-actions { display: flex; gap: 4px; flex-shrink: 0; }
      }
    }

    .category-groups {
      .group-block {
        border-bottom: 1px solid #f0f0f0;
        &:last-child { border-bottom: none; }
        .group-header {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 8px 16px;
          background: #fafafa;
          border-bottom: 1px solid #f5f5f5;
          .group-name { font-weight: 600; font-size: 13px; }
          .group-count { color: #909399; font-size: 12px; }
        }
        .group-files {
          padding: 4px 16px 4px 32px;
          .file-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 6px 0;
            border-bottom: 1px dashed #f0f0f0;
            &:last-child { border-bottom: none; }
            .file-info {
              display: flex;
              align-items: center;
              gap: 6px;
              flex: 1;
              min-width: 0;
              .file-name {
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                max-width: 360px;
                font-size: 13px;
              }
            }
            .file-actions { display: flex; gap: 4px; flex-shrink: 0; }
          }
        }
        .group-empty {
          padding: 8px 16px 8px 32px;
          color: #c0c4cc;
          font-size: 12px;
        }
      }
    }

    .category-empty {
      padding: 12px 16px;
      color: #909399;
      font-size: 13px;
      text-align: center;
    }
  }

  .upload-hint {
    margin-top: 16px;
  }
}

/* OCR 面板 */
.ocr-panel {
  .ocr-toolbar {
    margin-bottom: 16px;
    display: flex;
    gap: 8px;
  }

  .ocr-stats {
    margin-top: 16px;
    padding: 12px;
    background: #f5f7fa;
    border-radius: 8px;
    font-size: 14px;
    text-align: center;
  }
}

/* 内容面板 */
.content-panel {
  .content-toolbar {
    margin-bottom: 16px;
    display: flex;
    gap: 8px;
  }
}

/* Tab badge */
.tab-badge {
  margin-left: 4px;
  :deep(.el-badge__content) {
    font-size: 10px;
  }
}

/* 原图查看 */
.original-image-view {
  height: 75vh;
  overflow: auto;
  background: #f0f0f0;
  border-radius: 8px;
  padding: 12px;
  user-select: none;

  img {
    object-fit: contain;
    border-radius: 4px;
    transition: transform 0.15s ease;
  }
}

/* 缩放控制栏 */
.zoom-controls {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 10px 0 2px;
  border-top: 1px solid #ebeef5;

  .zoom-label {
    font-size: 14px;
    font-weight: 600;
    color: #606266;
    min-width: 50px;
    text-align: center;
  }
}

/* PDF 查看器控制栏 */
.pdf-viewer-controls {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 16px;
  border-top: 1px solid #ebeef5;
  background: #f5f7fa;
  border-radius: 0 0 8px 8px;

  .zoom-controls {
    border-top: none;
    padding: 0;
  }

  .import-controls-inline {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .imported-status {
    display: flex;
    align-items: center;
    gap: 12px;
  }
}

/* OCR 文本查看 */
.ocr-text-view {
  max-height: 500px;
  overflow-y: auto;
  background: #f5f7fa;
  padding: 16px;
  border-radius: 8px;

  .ocr-view-toggle {
    margin-bottom: 12px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .ocr-raw {
    white-space: pre-wrap;
    word-break: break-all;
    font-size: 13px;
    line-height: 1.6;
    margin: 0;
  }

  .ocr-rendered {
    font-size: 14px;
    line-height: 1.8;
    color: #303133;

    h1 { font-size: 20px; font-weight: 700; margin: 16px 0 8px; color: #1a1a1a; border-bottom: 2px solid #dcdfe6; padding-bottom: 6px; }
    h2 { font-size: 18px; font-weight: 700; margin: 14px 0 6px; color: #1a1a1a; }
    h3 { font-size: 16px; font-weight: 600; margin: 12px 0 4px; color: #303133; }
    h4 { font-size: 15px; font-weight: 600; margin: 10px 0 4px; color: #303133; }
    h5, h6 { font-size: 14px; font-weight: 600; margin: 8px 0 4px; color: #606266; }

    hr { border: none; border-top: 1px solid #dcdfe6; margin: 16px 0; }

    p { margin: 6px 0; }

    strong { font-weight: 600; color: #1a1a1a; }
    em { font-style: italic; }

    img {
      max-width: 100%;
      border-radius: 4px;
      margin: 8px 0;
      border: 1px solid #ebeef5;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      margin: 10px 0;
      font-size: 13px;

      td, th {
        border: 1px solid #dcdfe6;
        padding: 6px 10px;
        text-align: left;
        word-break: break-word;
      }

      th {
        background: #ebeef5;
        font-weight: 600;
      }

      tr:nth-child(even) {
        background: #fafafa;
      }
    }
  }

  .ocr-edit-area {
    .el-textarea__inner {
      font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
      font-size: 13px;
      line-height: 1.6;
    }

    .ocr-edit-actions {
      margin-top: 10px;
      text-align: right;
    }
  }

  .ocr-image-ref {
    margin-top: 16px;
    padding-top: 8px;

    .ref-line {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 6px;

      code {
        background: #f0f2f5;
        padding: 4px 10px;
        border-radius: 4px;
        font-size: 12px;
        color: #409eff;
        word-break: break-all;
        flex: 1;
      }
    }

    .ref-tip {
      font-size: 12px;
      color: #909399;
      margin-top: 4px;
    }
  }
}

/* 报告预览 */
.report-preview {
  max-width: 900px;
  margin: 0 auto;

  .report-paper {
    background: #fff;
    border: 1px solid #dcdfe6;
    border-radius: 4px;
    padding: 48px 56px;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
    font-family: 'SimSun', 'FangSong', serif;
    color: #303133;
    line-height: 1.8;
  }

  .report-title {
    text-align: center;
    font-size: 24px;
    font-weight: bold;
    letter-spacing: 6px;
    margin: 0 0 12px;
    color: #000;
  }

  .report-number {
    text-align: center;
    font-size: 14px;
    color: #606266;
    margin-bottom: 16px;
  }

  .report-divider {
    border: none;
    border-top: 2px solid #303133;
    margin: 16px 0 24px;
  }

  .report-section {
    margin-bottom: 24px;
  }

  .section-title {
    font-size: 16px;
    font-weight: bold;
    color: #000;
    margin: 0 0 8px;
  }

  .section-body {
    text-indent: 2em;
    font-size: 15px;
    line-height: 2;
  }

  .info-table {
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 8px;

    td {
      padding: 4px 8px;
      font-size: 15px;
      line-height: 2;
      vertical-align: top;
    }

    .label-cell {
      white-space: nowrap;
      width: 100px;
      text-indent: 0;
      font-weight: 500;
      color: #606266;
    }
  }

  .sub-label {
    font-weight: 500;
    color: #606266;
  }

  .text-content {
    white-space: pre-wrap;
    word-break: break-all;
  }

  .opinion-text {
    font-weight: 500;
    color: #000;
  }

  .empty-hint {
    color: #c0c4cc;
    font-style: italic;
    text-indent: 0;
  }

  .report-footer {
    margin-top: 48px;
    text-align: right;
    padding-right: 60px;

    .footer-line {
      margin-bottom: 8px;
      font-size: 15px;
    }

    .underline-blank {
      display: inline-block;
      width: 120px;
      border-bottom: 1px solid #303133;
    }
  }

  .preview-actions {
    margin-top: 24px;
    padding: 20px;
    background: #f5f7fa;
    border-radius: 8px;

    .action-buttons {
      text-align: center;
    }
  }
}
</style>
