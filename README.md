# Adaptive-ILS-VRPTW

**带时间窗车辆路径问题的自适应迭代局部搜索启发式算法**  
*Adaptive Iterated Local Search Heuristic for the Vehicle Routing Problem with Time Windows*

[![Python 3.8](https://img.shields.io/badge/Python-3.8-blue.svg)](https://www.python.org/)
[![C++17](https://img.shields.io/badge/C++-17-blue.svg)](https://en.cppreference.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## 概览

本项目基于开源求解器 [PyVRP](https://github.com/PyVRP/PyVRP) 的原生迭代局部搜索（ILS）框架，针对带时间窗车辆路径问题（VRPTW）设计并实现了**三项独立的探索性改进机制**。通过系统性实验评估，验证了各机制在不同约束类型（CVRP / VRPTW）及问题规模下的有效性、适用边界与潜在局限。

本工作为ILS算法在车辆路径问题中的**前瞻性搜索策略**、**多样化算子集成**以及**自适应邻域选择**提供了可复现的实证结论与实现参考。

---

## 分支说明

本仓库的 **`main` 分支与上游 PyVRP v0.14.0 保持完全一致**，未做任何修改，便于对比和复现原始结果。

三项改进机制分别位于独立的主题分支中，每个分支仅包含对应机制的代码变更：

| 分支名称 | 对应改进机制                                      |
| -------- | ------------------------------------------------- |
| `TSLA`   | 双层前瞻性搜索（Two-Stage Lookahead）             |
| `2opt`   | 集成 2‑opt 与 2‑opt\* 算子                        |
| `UCB`    | 基于UCB的自适应邻域选择（Upper Confidence Bound） |
| `Test`   | 批量测试结果及分析                                |

> 遵循**单一变量替换原则**，各分支彼此独立，未进行多机制联合集成。如需使用某项改进，请切换到对应分支。

---

## 主要特性

- **双层前瞻性搜索（TSLA）**  
  维护成本增量最小的“恶化移动”候选列表，在局部搜索停滞时探索“先恶化后改进”的两阶段移动组合，尝试突破贪心策略的局部最优壁垒。

- **多样化局部搜索算子集成**  
  在PyVRP原生算子（nmEX、SwapTails）基础上引入 **2-opt** 与 **2-opt\*** 两类边交换算子，支持路径内序列反转与路径间后缀交换，显著增强邻域结构的重组能力。

- **基于UCB的自适应邻域选择**  
  将算子调用顺序建模为多臂老虎机问题，以算子作为首选时的历史成功率为奖励信号，采用指数加权移动平均（EWMA）与置信上界（UCB）公式动态调整算子优先级，实现在线探索与利用的平衡。

上述机制均遵循**单一变量替换原则**，以模块化形式嵌入基准框架，保证实验结论的可归因性。

---

## 算法框架

下图展示了基准ILS算法与三项改进机制的集成关系（完整流程详见论文第3章）：

```
初始解生成 → 局部搜索 → 扰动 → 接受准则 → 终止判断
                ↑
        ┌───────┴───────┐
        │               │
   TSLA两阶段探索   自适应算子排序(UCB)
        │               │
   2-opt / 2-opt* 算子扩展
```

- **局部搜索**：基于序列拼接的增量式移动评估，快速计算时间窗约束下的成本变化。
- **TSLA触发**：连续2000次迭代无改进后启用，尝试TopK恶化移动的两阶段组合。
- **UCB排序**：每次局部搜索前按UCB分数降序重排算子调用顺序，优先尝试历史表现优异的算子。

---

## 项目结构

```
AILS-VRPTW/
├── pyvrp/                       # PyVRP 核心包（基于 v0.14.0）
│   ├── cpp/                     # C++ 扩展代码
│   │   └── search/              # ⭐ 主要修改区域（TSLA / 2opt / UCB）
│   ├── search/                  # Python 搜索接口
│   └── ...
├── instances/                   # 测试实例集（CVRP / VRPTW）
├── tests/                       # 测试套件
├── benchmarks/                  # 性能基准测试
├── docs/                        # 文档源码
├── notebooks/                   # Jupyter 教程
├── buildtools/                  # 编译工具
├── pyproject.toml               # 项目配置
└── README.md
```

> **说明**：C++核心代码位于 `pyvrp/` 目录下，通过 `pybind11` 暴露Python接口。实验脚本利用Python调用编译后的扩展。

---

## 实验结果摘要

在170个标准实例（CVRP 100~30000客户，VRPTW 1000客户）上进行了严格对比，主要结果如下：

| 算法变体             | 平均 gap (%) | 胜率 (vs baseline) | 适用场景                     |
| -------------------- | ------------ | ------------------ | ---------------------------- |
| baseline (PyVRP ILS) | 0.99 ± 0.12  | –                  | –                            |
| + TSLA               | 0.98 ± 0.12  | 50.6%              | 中等规模CVRP（有限潜力）     |
| + 2-opt              | 0.96 ± 0.11  | 55.3%              | CVRP中大规模                 |
| + 2-opt*             | **0.91 ± 0.11** | **60.6%**          | **CVRP全规模（推荐）**       |
| + 2-opt + 2-opt*     | 0.93 ± 0.10  | 56.5%              | 超大规模CVRP（协同增益）     |
| + UCB (自适应排序)   | 0.98 ± 0.12  | **56.5%**          | **VRPTW（唯一稳定改进）**    |

**关键发现**：
- **2-opt\*** 在纯容量约束（CVRP）上大幅提升解质量，超大规模（30000客户）平均gap降低1.25个百分点。
- 反转类算子（2-opt / 2-opt\*）在**带时间窗（VRPTW）** 中效果退化，联合使用时甚至导致性能下降。
- UCB自适应机制在VRPTW上胜多负少（35胜24负），通过动态规避对时间窗不利的算子，在复杂约束下展现出稳健性。
- TSLA整体未取得统计显著改进，其有效性高度依赖于解的收敛状态与运行时间（负结果同样具有参考价值）。

详细实验分析、累积分布曲线及 Wilcoxon 检验结果参见论文第4章。

---

## 快速开始

### 环境要求

- Linux / macOS（推荐Ubuntu 20.04+）
- g++ 13 或更高版本（C++17支持）
- CMake ≥ 3.15
- Python 3.8 – 3.10

### 安装

```bash
# 克隆仓库
git clone https://github.com/chenmeng-lk/AILS-VRPTW.git
cd AILS-VRPTW

# 如需使用某项改进机制，请切换到对应分支（例如 TSLA）
git checkout TSLA

# 同步依赖并编译
uv sync
uv run buildtools/build_extensions.py

#测试单个实例
uv run pyvrp instance/CVRP/X-n1001-k43.vrp --seed 42 --max_runtime 60
uv run pyvrp instance/VRPTW/C1_10_10.vrp --seed 42 --max_runtime 60
```

---

## 参数配置

| 机制 | 参数 | 默认值 | 说明 |
|------|------|--------|------|
| TSLA | `K` | 10 | 第一阶段恶化移动候选列表容量 |
| TSLA | `k_neigh` | 10 | 第二阶段搜索每节点最近邻数量 |
| TSLA | `T_tsla` | 2000 | 连续无改进迭代触发阈值 |
| UCB | `c` (exploration) | 1.414 | 探索系数（√2） |
| UCB | `alpha` (EWMA) | 0.1 | 指数加权移动平均学习率 |

可在构造`LocalSearch`对象时通过set方法修改，或通过实验配置文件指定。

---

本工作基于以下开源项目与基准测试集：

- [PyVRP](https://github.com/PyVRP/PyVRP) – 高性能车辆路径问题求解器（MIT License）
- [CVRPLIB](http://vrp.atd-lab.inf.puc-rio.br/) – CVRP标准实例集（Uchoa et al., 2017）
- Gehring & Homberger VRPTW实例集（1999）

---

## 联系与问题

- 作者：廖奎
- 邮箱：U202215494@hust.edu.cn
欢迎通过邮件交流讨论。

---

**备注**：由于本工作遵循单一变量独立验证原则，仓库中各改进机制（TSLA / 2-opt / 2-opt\* / UCB）均可单独编译启用，未进行多机制联合集成。
