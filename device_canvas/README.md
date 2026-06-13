# 半导体器件截面画布

把 RadAgent 对半导体器件的几何理解(`G4ModelIR` 的 `components`)渲染成 **2D 截面图**,
人工在网页上拖拽修正,再导出回 agent。解决"器件结构很难用文字对 agent 描述清楚"的问题。

## 工作流:agent 先画 → 人工修正

```text
RadAgent 跑到 g4_modeling 阶段
  → 产出 simulation_workspace/jobs/<job>/03_model_ir/g4_model_ir.json   (agent 的理解)
  → 画布渲染成 2D 截面(每个 box = 一层,按材料上色、标尺寸)
  → 你拖位置 / 拖手柄改厚度 / 右侧面板改材料 / 加层删层
  → 导出修正 JSON(回填 components),或回写到 04_human_confirmation/
```

## 两种用法

### A. 本地服务(推荐,完整闭环)

```bash
python3 device_canvas/serve.py
# 自动开浏览器 → http://127.0.0.1:8765
```

- 左上「选择 Job」下拉自动列出所有产出过 model_ir 的 job
- 选一个 → 立刻看到 agent 把器件理解成了什么样
- 修正后点「⤴ 回写到 Job」→ 写入 `04_human_confirmation/g4_model_ir.json`
  (不动 `03_model_ir/` 原始理解,便于追溯)

### B. 纯前端(零依赖,不能浏览/回写 job)

直接双击 `index.html` 用浏览器打开,把 `g4_model_ir.json` 拖进画布,改完点
「💾 导出修正 JSON」下载文件,手动替换。

## 画布操作

| 操作 | 效果 |
| --- | --- |
| 拖矩形 | 改位置(position) |
| 拖矩形边/角手柄 | 改尺寸(dimensions) |
| 滚轮 / +- / ⌂ | 缩放 / 复位视图 |
| 顶部 `截面: × ` | 切换横向轴/深度轴(默认自动选最薄方向作深度) |
| 右侧面板 | 精确改 material / type / dims / position / sensitive / roles |
| 精确变换 / 3D 对齐 | 当前截面微移、缩放、镜像、90° 旋转;按 x/y/z 输入移动量、绝对中心、目标 dx/dy/dz,或按 3D min/center/max 对齐/定位 |
| Ctrl+C / Ctrl+V | 复制选区到工作台内部剪贴板,按当前截面偏移粘贴 |
| Ctrl+A / Esc / F | 按当前列表筛选全选可见组件 / 清空选择和测量 / 聚焦选区 |
| Delete / 方向键 | 删除选区 / 按当前步长微移选区,Shift+方向键使用 5 倍步长 |
| I / Shift+H | 隔离选区 / 显示全部组件 |
| 选择集 | 保存常用选区,之后可一键恢复选择或隔离该组件组合 |
| 装配树 | 按 mother volume 浏览层级,选择/隔离/隐藏/显示整棵子树 |
| ＋ 加层 | 在最顶层上方插一个薄层 |
| 🗑 删除 | 删除选中(world volume 不可删) |
| 导出 PNG / SVG | PNG 用于快速审阅;SVG 用真实 μm 坐标输出矢量截面、组件 ID 和尺寸标注 |
| 导入 / 导出 DXF | 导入 ASCII DXF 的 LWPOLYLINE/CIRCLE/ARC 为当前截面多边形;导出 DXF 用真实 μm CAD 坐标输出组件和标注 |
| 📋 复制描述 | 生成一段自然语言,可直接粘进 RadAgent REPL/TUI |

## CAD / DRC 能力

- **3D 语义建模**:组件仍是完整 3D `ComponentSpec`;XY/XZ/YZ 只是二维截面视图。
- **CAD 状态栏**:画布顶部持续显示当前光标的真实 μm 坐标、截面轴、第三轴、吸附/网格状态和选区数量;切换截面、吸附、剖切或选择时会同步刷新。
- **安全重命名**:右侧属性面板可改 `component_id` / `display_name`;`component_id` 会校验唯一性和字符格式,并同步更新子组件 `mother_volume`、选择集、尺寸/间隙标注、DRC 豁免签名和当前选择。
- **命令面板**:顶部“命令”或 `Ctrl+K` 打开统一命令入口,可搜索选择、视图、截面、工具、编辑和导出命令,并按当前选择/剪贴板状态禁用不可用命令。
- **网格原点**:吸附网格支持当前截面横向/深度两个方向的原点偏移,用于和版图、工艺层或外部 CAD 坐标系对齐。
- **视图状态**:可保存/恢复隐藏、锁定、截面轴和剖切参数组成的工作视图,适合复杂模型审查时快速切换。
- **绑定尺寸 / 间隙标注**:可为选区一键创建当前截面的横向/深度尺寸标注;恰好选中两个组件时可固定当前主轴的间隙/重叠标注,也可输入目标间隙直接移动第二个组件。标注绑定组件 bbox,移动或改尺寸后自动更新,并随工作台状态、SVG 和 DXF 导出。
- **2D CAD 变换**:当前截面支持选区中心镜像和 90° 旋转;box 旋转会交换当前截面两轴尺寸,多边形逐点变换,并继续受 mother/World 边界约束。
- **多边形节点编辑**:双击组件边界附近会把 box 转为当前截面的 polycone 并在最近边投影插入节点;离边较远不会误插点。节点为小型不缩放控制点,点击热区独立放大,拖点会按网格吸附并立即更新真实 3D polygon;右侧顶点表支持精确输入当前截面的顶点坐标、顶点上移/下移、反转 winding 和安全删除,所有编辑继续受 mother/World 边界约束。
- **3D 精确变换 / 对齐**:选区可按 x/y/z 输入位移或绝对中心坐标;box 组件可按 dx/dy/dz 批量设置真实 3D 尺寸;也可按 x/y/z 的 min/center/max 对齐到 World/主选组件,直接定位到数值坐标,或保留端点组件并沿指定 3D 轴等间隙分布中间组件。默认开启 mother/World 边界约束,会阻止移动、定位、对齐或改尺寸后越界的组件;也可切换为“贴边夹紧”,移动/拖拽越界时自动停在容器边界。
- **选区 3D 测量探针**:选中组件后右侧显示真实 3D bbox、截面 bbox、AABB 体积和材料统计;恰好选中两个组件时额外显示 x/y/z 三轴间隙、重叠/接触状态、中心差和中心距,复制几何报告会保留同样的精确数值。
- **直接编辑约束**:画布拖拽、方向微移、当前截面缩放、矩形手柄缩放和多边形拖拽/顶点编辑也复用 mother/World 边界约束,避免绕过精确输入产生非法 3D 模型。
- **捕捉控制**:吸附目标可拆分控制为网格、组件边/中心、画布中心;网格步长和吸附阈值会随工作台状态保存,网格捕捉按组件中心对齐到网格交点。
- **选择隔离 / 可见性管理**:组件列表支持按选区隔离、恢复隔离前隐藏状态和显示全部;隔离期间保留原隐藏快照,适合在复杂 3D 装配里局部修改。
- **命名选择集**:可把当前多选保存为选择集,后续一键恢复选择或隔离该组件组合;选择集随工作台状态导出/恢复,组件改名或删除时会同步清理引用。
- **装配树 / 子树操作**:按 `mother_volume` 展示 World、容器和子组件层级;可对子树一键选择、隔离、隐藏或显示,用于复杂 3D 装配的局部导航和编辑。
- **安全复制 / 粘贴 / 阵列**:复制、内部剪贴板粘贴和线性阵列默认遵守 mother/World 边界,越界副本会被跳过;生成的组件保留 `duplicate_of` / `clipboard_of` / `array_of` 溯源证据。
- **三维预览 / 选取**:右上角 3D 视图显示包围盒、坐标轴和剖切平面;支持 Iso/Top/Front/Side 标准视角,点击 3D 实体可选中并同步到 2D 编辑;薄探测器边线按投影厚度收敛,避免固定线宽盖过真实厚度。
- **剖切查看**:可启用第三轴剖切,只显示穿过剖切厚度的实体。
- **3D 检查 / 规则 deck**:模型检查面板检测重复 id、缺失 mother/world、越界、真实 3D 重叠和最小间隙 DRC;3D 重叠使用 sweep broad-phase + AABB 精查,在大组件数模型里减少全量 pair 检查延迟;支持 Detector default / Tight stack / Loose assembly / Custom 规则预设,检查报告带规则名和阈值。
- **DRC 问题浏览器**:检查结果可按全部/错误/警告/可修复过滤,支持上一条/下一条和定位当前问题,会高亮当前问题并选中关联组件。
- **自动修复**:安全项可自动平移回容器、沿当前第三轴分离重叠实体、补足最小 3D 间隙。
- **层栈 / 间隙**:按当前第三轴或指定 x/y/z 轴列出真实 3D 区间,标出接触、间隙、小间隙、重叠和横向不相交;关系项可直接选中相邻组件,把相邻实体精确设为接触或当前 DRC 间隙,小间隙/重叠可在层栈里一键修复。
- **薄层渲染**:YZ/XZ 下亚像素厚度保持真实投影高度;小于 2px 的薄层不再画实体轮廓线或缩放手柄,实体填充透明度按投影厚度降低,选中态用外置刻度提示,网格和选中辅助线会降为 hairline,点击热区独立放大以便选择/拖动。

## 导出

- **修正 JSON** — 严格匹配 `ComponentSpec`;若载入的是完整 model_ir,会回填
  `components` 并标记 `human_confirmation.confirmed_via=device_canvas`、
  `assumptions_confirmed=true`。
- **工作台状态** — 隐藏/锁定、剖切参数、DRC 规则 deck、层栈轴、捕捉设置、3D 变换边界约束、选择集、尺寸标注等 UI 状态写入
  `device_canvas_state`,不混进 Geant4 `components`。旧版
  `device_canvas_annotations` 仍同步输出,用于向后兼容。
- **PNG** — 截面图,交给视觉子代理辅助理解。
- **SVG** — 当前截面的矢量 CAD 交付物,使用真实 μm 坐标和 `data-component-id`,保留多边形、薄层真实厚度和绑定尺寸标注。
- **DXF** — 当前截面的 ASCII DXF 交付物,使用 CAD 坐标 `X=横向轴`、`Y=深度轴`,单位为 μm;组件按图层输出闭合 `LWPOLYLINE`,尺寸标注输出为 `LINE`/`TEXT`,便于导入外部 CAD。
- **DXF 导入** — 支持 ASCII DXF 中的 `LWPOLYLINE`、`CIRCLE`、`ARC`;按当前截面把 CAD `X/Y` 映射到横向/深度轴,bulge/圆/圆弧会近似为多段线,导入为可编辑多边形组件并保留 `dxf_import:<layer>` 证据。
- **CSV 报告** — DRC CSV 输出 active/waived 状态、问题签名、关联组件和豁免理由;组件 CSV 输出所有非 world 组件的 3D 中心、尺寸、bbox、隐藏/锁定/敏感状态、角色和来源证据,便于审计和外部表格检查。
- **自然语言描述** — 按深度从下到上列出每层的材料/厚度/横向尺寸/中心坐标。

## 文件结构

- `index.html` — 页面结构和样式。
- `cad_core.js` — 无 DOM 依赖的材料、轴、几何、AABB、3D 重叠/间隙 DRC、层栈/间隙、序列化辅助。
- `app.js` — CAD 交互、几何检查、2D/3D 渲染、导入导出逻辑。
- `serve.py` — 本地 job 浏览和回写服务。
- `tests/` — 核心几何和 Playwright 浏览器回归,覆盖 2D/3D 变换、复制粘贴/阵列、DRC、层栈和薄层渲染。

## 验证

```bash
python3 device_canvas/tests/run_all.py
```

该命令会运行 DOM-free 核心几何测试和 Playwright 浏览器回归;用于确认 2D/3D 编辑、复制粘贴/阵列、DRC、规则状态导出/恢复、层栈精确间隙命令和薄层渲染没有回退。

## 数据对接

画布读写的就是 `agent_core/g4_modeling/schemas/g4_model_ir.py` 的 `G4ModelIR`,
每个组件是 `ComponentSpec`(box `{dx,dy,dz}` + `position[x,y,z]` μm + `material_id`)。
坐标轴语义见 `CoordinateSystem.axis_definition`
(典型:x=sensor_width, y=sensor_length, z=beam_direction)。

`serve.py` 只读 `simulation_workspace/`,job_id 做了字符白名单过滤,路径遍历会被拒。
回写只写 `04_human_confirmation/`,不覆盖 `03_model_ir/`。
