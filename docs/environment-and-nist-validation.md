# RadAgent 运行环境配置与 NIST 测试复现说明

本文档说明 RadAgent 的本地运行环境、依赖库版本要求、部署步骤，以及
NIST photon attenuation 测试数据集、评测指标和复现脚本。

## 1. 运行平台

- 推荐系统：Linux x86_64，已在 Ubuntu 类 Linux shell 环境下维护。
- Python：3.11 或更高版本。`pyproject.toml` 中声明 `requires-python = ">=3.11"`。
- C/C++ 构建工具：CMake 3.16 或更高版本，用于 Geant4 benchmark 构建。
- Geant4：用于完整 NIST 仿真复现。无 Geant4 时仍可复现 NIST reference-only
  报告，但不能运行真实 Geant4 粒子输运仿真。

## 2. Python 依赖库

核心依赖来自 `pyproject.toml`：

| 依赖 | 版本约束 | 用途 |
| --- | --- | --- |
| `langgraph` | `>=0.2.0` | 主工作流图与子图调度 |
| `pydantic` | `>=2.0` | 结构化状态、IR 与响应模型 |
| `pyyaml` | `>=6.0` | 策略和配置文件解析 |
| `numpy` | `>=1.24` | 数值处理 |
| `rich` | `>=13.0` | CLI/REPL 展示 |
| `python-dotenv` | `>=1.0` | `.env` 配置加载 |
| `prompt-toolkit` | `>=3.0` | 交互式 REPL |
| `httpx` | `>=0.27` | HTTP 客户端 |
| `aep8` | `>=1.0.0` | AP8/AE8 空间辐射环境 |
| `astropy` | `>=6.0` | 天文/轨道相关计算 |
| `skyfield` | `>=1.49` | 轨道传播辅助 |
| `sgp4` | `>=2.23` | TLE/SGP4 轨道传播 |

开发与测试依赖：

| 依赖 | 版本约束 |
| --- | --- |
| `pytest` | `>=8.0` |
| `pytest-asyncio` | `>=0.23` |
| `pytest-cov` | `>=5.0` |
| `ruff` | `>=0.4` |
| `mypy` | `>=1.10` |

## 3. 一键部署

从仓库根目录执行：

```bash
./scripts/setup_radagent_env.sh
```

该脚本会：

1. 检查 Python 版本是否满足 3.11+。
2. 创建 `.venv`。
3. 升级 `pip/setuptools/wheel`。
4. 以 editable 方式安装 `.[dev]`。
5. 检查核心 Python import 是否可用。
6. 检查 `cmake` 与 Geant4 CMake package 是否可被发现。

常用变体：

```bash
./scripts/setup_radagent_env.sh --extras dev,tui
./scripts/setup_radagent_env.sh --skip-install
./scripts/setup_radagent_env.sh --check-only
```

完整 Geant4 benchmark 需要先加载 Geant4 环境，例如：

```bash
source /path/to/geant4/bin/geant4.sh
```

也可通过 `GEANT4_INSTALL`、`Geant4_DIR` 或 `CMAKE_PREFIX_PATH` 暴露 Geant4
CMake package。

## 4. NIST 测试数据集

测试数据集位于：

```text
benchmarks/nist_photon_attenuation.json
```

数据集包含 18 个 NIST XCOM photon attenuation 案例，覆盖：

| 材料 | 能量 | 厚度 |
| --- | --- | --- |
| Pb | 0.5 MeV、1.0 MeV | 0.5 cm、1 cm、2 cm |
| Al | 0.5 MeV、1.0 MeV | 1 cm、3 cm、6 cm |
| Water | 0.5 MeV、1.0 MeV | 5 cm、10 cm、20 cm |

每个 case 记录：

- `density_g_cm3`：材料密度。
- `mass_attenuation_cm2_g`：NIST 质量衰减系数。
- `thickness_cm`：均匀 slab 厚度。
- `energy_MeV`：单能 photon 入射能量。

数据来源在 manifest 的 `sources` 字段中记录，包括 NIST XCOM 数据库以及
Pb、Al、Water 的 NIST mass attenuation coefficient 页面。

## 5. 评测指标

评测脚本：

```text
scripts/physics_benchmark.py
```

对每个 case 计算：

| 指标 | 公式 |
| --- | --- |
| 参考线衰减系数 | `mu_ref = density_g_cm3 * mass_attenuation_cm2_g` |
| 参考透过率 | `T_ref = exp(-mu_ref * thickness_cm)` |
| 观测线衰减系数 | `mu_observed = -ln(observed_transmission) / thickness_cm` |
| 相对误差 | `abs(mu_observed - mu_ref) / mu_ref` |
| 重复运行变异系数 | 多次重复时为 transmission 样本 CV；单次运行时用二项统计估算 |

验收阈值来自 manifest：

- `max_relative_error = 0.05`，即观测线衰减系数相对 NIST 参考值误差不超过 5%。
- `max_cv = 0.02`，即重复运行或单次二项估算 CV 不超过 2%。

汇总指标包括：

- case 总数；
- observed case 数；
- reference-only case 数；
- 通过 case 数；
- pass rate；
- median relative error；
- max relative error。

## 6. 复现脚本

一键复现入口：

```bash
./scripts/reproduce_nist_benchmark.sh
```

默认行为：

1. 生成 reference-only JSON/Markdown 报告。
2. 检测 Geant4 是否可用。
3. 若 Geant4 可用，构建并运行 `benchmarks/geant4_photon_attenuation`。
4. 生成 Geant4 observations JSON。
5. 将 observations overlay 到 NIST manifest，输出 evaluated JSON/Markdown 报告。
6. 若 Geant4 不可用，保留 reference-only 输出并给出诊断信息。

仅复现 NIST 参考数据：

```bash
./scripts/reproduce_nist_benchmark.sh --reference-only --output-dir benchmarks/reports
```

运行快速 Geant4 smoke：

```bash
./scripts/reproduce_nist_benchmark.sh \
  --events 1000 \
  --case-limit 2 \
  --output-dir benchmarks/reports/nist_smoke
```

运行完整 Geant4 100k histories/case：

```bash
./scripts/reproduce_nist_benchmark.sh \
  --events 100000 \
  --repeats 1 \
  --seed 12345 \
  --geant4-required \
  --output-dir benchmarks/reports
```

推荐高统计量设置：

```bash
./scripts/reproduce_nist_benchmark.sh \
  --events 1000000 \
  --repeats 3 \
  --seed 12345 \
  --geant4-required \
  --output-dir benchmarks/reports/nist_1m_x3
```

Makefile 快捷入口：

```bash
make setup-env
make nist-reference
make nist-geant4-smoke
make nist-reproduce
```

## 7. 已有可验证结果

仓库已保存一组 Geant4 100k histories/case 的 NIST 报告：

```text
benchmarks/reports/nist_photon_attenuation_geant4_100k_observations.json
benchmarks/reports/nist_photon_attenuation_geant4_100k_report.json
benchmarks/reports/nist_photon_attenuation_geant4_100k_report.md
```

该报告的汇总结果：

| 指标 | 数值 |
| --- | ---: |
| Cases | 18 |
| Observed cases | 18 |
| Reference-only cases | 0 |
| Pass count | 18 |
| Pass rate | 1.0 |
| Median relative error | 0.004537 |
| Max relative error | 0.011678 |

这些结果满足 manifest 中的 5% 相对误差阈值；100k 单次运行下所有 case 的
CV 也满足 2% 阈值。

## 8. 复现产物说明

reference-only 模式输出：

```text
nist_photon_attenuation_reference_report.json
nist_photon_attenuation_reference_report.md
```

Geant4 模式额外输出：

```text
nist_photon_attenuation_geant4_<events>[_x<repeats>][_first<case_limit>]_observations.json
nist_photon_attenuation_geant4_<events>[_x<repeats>][_first<case_limit>]_report.json
nist_photon_attenuation_geant4_<events>[_x<repeats>][_first<case_limit>]_report.md
```

其中 observations 文件记录每个 case 的 `observed_transmission`、`observed_cv`、
重复次数、每次 histories 数、透过粒子数、原始 Geant4 JSON 输出和随机种子。

## 9. 验证命令

脚本契约测试：

```bash
pytest tests/unit/test_nist_reproduction_scripts.py -v
```

NIST benchmark 评测逻辑测试：

```bash
pytest tests/unit/test_physics_benchmark.py tests/unit/test_photon_attenuation_geant4_runner.py -v
```

reference-only 复现：

```bash
./scripts/reproduce_nist_benchmark.sh --reference-only --output-dir /tmp/radagent_nist_reference
```

Geant4 环境检测：

```bash
./scripts/setup_radagent_env.sh --check-only
```
