# RadAgent

基于 LangGraph 的航天辐照仿真智能体。用户输入自然语言描述，系统自动完成：

**意图解析 → 屏蔽结构设计 → 轨道环境查询 → 参数确认 → Geant4 模板渲染 → 编译运行 → 结果分析 → 报告生成**

## 架构

```
用户输入
  │
  ▼
┌─────────────────────────────────────────────────┐
│  Research Subgraph                               │
│  parse_intent → design_schema → research_params  │
│  → confirm_params                                │
├─────────────────────────────────────────────────┤
│  research_gate ──(门控)──▶ parameterize           │
│                             │                    │
│                             ▼                    │
│                         build_and_run            │
│                             │                    │
│                         sim_gate ──(门控)──▶      │
│                             │                    │
│                             ▼                    │
│                      Analysis Subgraph           │
│                      (数据/能谱/热力图)           │
│                             │                    │
│                         report_gate ──(门控)──▶   │
│                             │                    │
│                      generate_report             │
│                             │                    │
│                        human_review              │
└─────────────────────────────────────────────────┘
```

## 目录结构

```
radagent/
├── main.py                  # CLI 入口（支持交互/pipe 模式）
├── config.py                # 环境变量、路径、超时配置
├── graph.py                 # 主图构建（LangGraph StateGraph）
├── schemas.py               # 所有 frozen dataclass (DTO)
├── state.py                 # 主图状态 RadAgentState
├── log.py                   # 按会话分目录的日志系统
├── nodes/                   # 主图节点
│   ├── gates.py             # 门控节点（路由决策）
│   ├── parameterize.py      # Geant4 模板渲染
│   ├── build_run.py         # 编译 + 运行 Geant4
│   └── report.py            # 报告生成 + 人工审核
├── subgraphs/
│   ├── research/            # 调研子图（意图→设计→查询→确认）
│   └── analysis/            # 分析子图（数据解析/能谱/热力图/几何可视化）
├── tools/                   # 纯工具函数
│   ├── geant4_tools.py      # 模板渲染、编译、运行、结果解析
│   ├── knowledge.py         # 材料/粒子/物理列表知识库
│   ├── orbit_query.py       # 轨道辐射环境查询
│   └── web_search.py        # DuckDuckGo 搜索
├── rag/                     # Geant4 RAG 检索（SQLite + bge-m3）
└── templates/               # Geant4 C++ 模板
    └── multilayer_shield/   # 多层屏蔽仿真模板

vis_demo/                    # 3D 可视化 Demo（Qt5 + OpenGL）
```

## 依赖

### Python 运行时

| 包 | 版本 | 用途 |
|---|---|---|
| Python | >= 3.11 | 运行时 |
| langgraph | >= 0.2 | 状态图框架 |
| langchain-openai | >= 0.1 | LLM 接口（DeepSeek） |
| langchain-core | >= 0.1 | LangChain 核心 |
| python-dotenv | >= 1.0 | 环境变量管理 |
| numpy | >= 1.24 | 数据处理 |

安装：
```bash
pip install -r requirements.txt
```

### 系统依赖

| 组件 | 版本 | 用途 |
|---|---|---|
| Geant4 | 11.3 (含 Qt 支持) | 蒙特卡罗粒子输运仿真 |
| CMake | >= 3.16 | Geant4 工程构建 |
| g++ | >= 12 (支持 C++17) | 编译 Geant4 仿真程序 |
| DeepSeek API Key | - | LLM 推理（意图解析、参数推荐） |

### 3D 可视化 Demo（vis_demo/）

| 组件 | 版本 | 用途 |
|---|---|---|
| Qt5 (Widgets + OpenGL) | 5.15+ | GUI 窗口 + OpenGL 上下文 |
| OpenGL | 3.3+ | 3D 渲染 |
| CMake | >= 3.16 | 构建系统 |
| g++ | >= 12 (支持 C++17) | C++ 编译 |

构建与运行：
```bash
cd vis_demo
mkdir -p build && cd build
cmake .. && make -j$(nproc)
./radagent_vis
```

## 环境配置

### 1. Geant4 安装

```bash
# 确保 Geant4 已安装且 source 脚本可用
source /etc/profile.d/geant4.sh
geant4-config --version  # 应输出 11.3
```

Geant4 编译时需启用以下 CMake 选项：
```cmake
-DGEANT4_USE_QT=ON          # Qt 可视化支持（vis_demo 需要）
-DGEANT4_USE_OPENGL_X11=ON  # OpenGL 渲染
-DGEANT4_INSTALL_DATADIR=   # 数据集目录
```

### 2. DeepSeek API

```bash
# .env 文件
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx
```

### 3. RAG（可选）

如需 Geant4 知识库检索功能，需安装 Ollama 并下载嵌入模型：
```bash
ollama pull bge-m3
```

## 快速开始

```bash
# 安装 Python 依赖
pip install -r requirements.txt

# 配置 API Key
echo "DEEPSEEK_API_KEY=sk-xxx" > .env

# 运行
python -m radagent

# 或 pipe 模式
echo "设计一个卫星用5层屏蔽，抗100MeV质子辐照" | python -m radagent
```

## 可视化 Demo

独立于 RadAgent 主程序，直接展示屏蔽几何 + 粒子轨迹的 3D 交互视图：

```bash
cd vis_demo
./run.sh   # 自动构建并启动（处理 VSCode snap 终端兼容性）
```

功能：
- 多层屏蔽半透明 3D 渲染（Phong 光照）
- 粒子轨迹颜色区分（质子/中子/γ/电子）
- 能量沉积碰撞点标记
- 入射方向箭头指示
- 左键旋转 / 右键平移 / 滚轮缩放

## License

MIT
