# Word 月报转 PPT

把月报 `docx` 转成指定模板 `pptx`。  
默认通过本地 Ollama 模型（如 `qwen2.5:7b-instruct-q4_K_M`）生成每页要点；如果模型不可用，会自动回退到规则模式，确保可产出可编辑 PPT。

当前默认行为：
- 保留模板原有标题与版式（不改标题文本）
- 只在内容区写入匹配后的要点
- 运行全过程输出日志（读取、模型调用、写入页、导出）

## 1) 安装依赖

```powershell
python -m pip install python-docx python-pptx
```

## 2) 运行

```powershell
python .\docx_to_ppt_converter.py `
  --docx "C:\Users\vegta\Desktop\25立讯技术法务工作八月报_August_V1(2).docx" `
  --template "C:\Users\vegta\Desktop\法务部月汇报总结V1(1).pptx" `
  --output "C:\Users\vegta\Desktop\法务部月汇报总结_自动填充.pptx" `
  --model "qwen2.5:14b-instruct-q4_K_M" `
  --layout-mode formal `
  --theme formal_blue `
  --diversity none `
  --seed 7
```

## 3) 可选参数

- `--ollama-url`：默认 `http://127.0.0.1:11434`
- `--timeout`：单次模型调用超时秒数，默认 `180`
- `--retries`：模型失败重试次数，默认 `2`
- `--no-llm`：关闭模型，只用规则匹配与改写
- `--layout-mode`：内容排版模式（`classic`/`formal`，默认 `classic`）
- `--theme`：正式布局主题（`formal_blue`/`corporate_gray`/`legal_red`）
- `--diversity`：版式多样化程度（`none`/`low`/`medium`/`high`，其中 `none` 为不套用多样化布局）
- `--seed`：版式随机种子（同 seed 可复现）

## 4) 实现原理

### 4.1 总体流程

1. 读取 Word，抽取段落并按“标题候选规则”切分章节。  
2. 读取 PPT 模板，识别需要填充的页面（默认第 2-11 页）。  
3. 按“页面标题关键词”从 Word 中选素材句。  
4. 调用 LLM 做“PPT 风格改写”（保留 BU/项目/案件/日期/数字）。  
5. 结果再做规则校验（页内主题匹配、去重、低质量句替换）。  
6. 回写到模板内容区并导出 `.pptx`。

### 4.2 为什么这样设计

- **LLM 做改写，程序做约束**：模型负责“怎么说”，代码负责“放在哪页、能不能放、是否重复”。  
- **模板优先**：不改标题、不改版式，避免输出偏离汇报模板。  
- **可留空**：某页素材证据不足时允许空白，不强行填错内容。  
- **可回退**：模型失败时自动走规则模式，保证链路可用。

### 4.3 页面匹配策略

- 每页先根据标题建立关键词集合（例如“知识产权页”优先专利/IP相关词）。  
- 再按评分从素材池排序抽取。  
- 对关键页应用强约束：
  - “美国劳动诉讼”页需同时命中“美国”与“劳动/诉讼/仲裁”等词。
  - “337”页只收 `337/TA1484` 相关句。
- 对专项页应用白名单/黑名单（如知识产权页过滤仲裁诉讼句）。

### 4.4 去重与清洗

- 去重分两层：
  - 页内去重（同页不重复）
  - 跨页去重（后页尽量不复用前页语句）
- 清洗内容包括：
  - 去编号前缀（如 `1.`、`（1）`）
  - 修正常见脏词
  - 去掉空白噪声与多余分隔符

### 4.5 数据页处理

- 第 5 页保留表格并填第二列。  
- 若 Word 有明确数字（如 638 / 601 / 专利提案 16 / 调查 53）则写入；  
  未出现的指标填 `-`。

## 5) 当前已知限制

- 7B 模型对长指令/长上下文稳定性有限，偶尔会输出宽泛句。  
- 若模板标题与实际文档主题偏差大，仍可能需要人工调整页面归属。  
- 强约束页（如“美国劳动诉讼”）在证据不足时会空白，这是预期行为。

## 6) 工程结构（模块化）

- `docx_to_ppt_converter.py`：CLI 入口（参数解析 + 调用引擎）
- `gui_converter.py`：GUI 入口（图形界面运行转换）
- `report_converter/constants.py`：指标与标签常量
- `report_converter/models.py`：数据结构（`TemplateSlide` / `SlideDraft`）
- `report_converter/engine.py`：核心逻辑（解析、匹配、改写、校验、写回）

## 7) GUI 使用

```powershell
python .\gui_converter.py
```

- 启动后会自动检测本机 Ollama 模型并填充下拉列表。
- 也可点击“检测模型”手动刷新模型列表。
- 可在“排版模式”选择 `formal`（正式汇报布局）或 `classic`（旧版布局）。
- `formal` 下可继续选择主题、版式多样化程度与 `seed`。
- 选择 `Word 路径`、`模板路径`、`输出路径` 后点击“开始转换”。
- 下方“运行日志”会实时显示转换过程和错误信息。

## 8) 打包成客户端（Windows/macOS）

### 8.1 Windows 一键打包 EXE

```powershell
cd C:\Users\vegta\Desktop\month_report_convert
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1
```

产物：
- `dist\MonthReportConverter.exe`

### 8.2 macOS 打包 .app

```bash
cd /path/to/month_report_convert
bash ./scripts/build_macos.sh
```

产物：
- `dist/MonthReportConverter.app`

### 8.3 GitHub 自动构建（跨电脑推荐）

仓库已提供工作流：
- `.github/workflows/build-desktop.yml`

触发方式：
- 打 tag（如 `v1.0.0`）后自动构建 Windows + macOS 产物
- 或在 GitHub Actions 手动点 `Build Desktop Packages`

### 8.4 对方电脑首次使用前置条件

客户端本身可即开即用，但推理依赖本机 Ollama：

1. 安装并启动 Ollama  
2. 拉取模型（例如）：

```bash
ollama pull qwen2.5:14b-instruct-q4_K_M
```

3. 确保 `http://127.0.0.1:11434` 可访问

> 如果未满足前置条件，GUI 会在“检测模型/运行日志”里提示失败原因。
