<h1 align="center">MotorFit</h1>

<p align="center">
  <strong>采集电机运动，辨识动力学参数，验证模型表现。</strong>
</p>

<p align="center">
  <a href="pyproject.toml"><img src="https://img.shields.io/badge/Version-0.1.0-607D8B?style=flat-square&amp;labelColor=334155" alt="Version 0.1.0"></a>
  <a href="https://motorfit.github.io/reference/backends.html"><img src="https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&amp;labelColor=334155&amp;logo=python&amp;logoColor=white" alt="Python 3.12"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache--2.0-607D8B?style=flat-square&amp;labelColor=334155" alt="License: Apache-2.0"></a>
  <a href="https://motorfit.github.io/guide/acquisition.html"><img src="https://img.shields.io/badge/SocketCAN-Linux-607D8B?style=flat-square&amp;labelColor=334155&amp;logo=linux&amp;logoColor=white" alt="SocketCAN acquisition on Linux"></a>
</p>

<p align="center">
  <a href="#快速开始">快速开始</a> ·
  <a href="#支持的电机">支持的电机</a> ·
  <a href="https://motorfit.github.io/">文档</a> ·
  <a href="README.md">English</a>
</p>

MotorFit 在 [Rhoban BAM](https://github.com/Rhoban/bam) 基础上补充独立电机驱动、台架数据采集与模型验证。记录指令和实测运动，辨识执行器动力学，再通过实测轨迹与受支持的物理仿真后端检验预测结果。

<p align="center">
  <a href="docs/images/overview.png">
    <img src="docs/images/overview.png" width="100%" alt="MotorFit 三阶段流程：1 RS05 台架真机实验；2 Rhoban BAM M1–M6 参数辨识与模型保存；3 对照实测的仿真验证，支持 MuJoCo、Newton、mjlab 的 M1 torque-MIT 回放。">
  </a>
</p>

## 主要功能

- **独立驱动采集。** 支持 RobStride 和达妙电机，保存原始 CAN 帧、带时间戳的反馈和完整实验配置。
- **基于 BAM 辨识。** 使用 M1–M6 摩擦模型进行参数拟合、独立数据评估，以及模型快照保存与重载。
- **对照实测验证。** 比较模型预测与实测轨迹，并在 MuJoCo、Newton 或 mjlab 中回放受支持的 M1 模型。

## 快速开始

需要 **Python 3.12** 和 [uv](https://docs.astral.sh/uv/getting-started/installation/)。先运行仓库自带的离线示例，无需电机或 GPU。

```bash
git clone --recurse-submodules git@github.com:motorfit/motorfit.git
cd motorfit
uv sync --frozen
uv run --no-sync motorfit demo \
  --dataset tests/fixtures/offline/manifest.json --output outputs/demo
```

示例使用冻结模型检验三条完整记录，将对照图、误差指标和预测轨迹写入 `outputs/demo/`。当前仓库为私有，克隆需要访问权限。MotorFit 尚未发布，版本保持为 0.1.0。

运行成功会输出 `PASS: 3 complete recordings; frozen references reproduced.`。
打开 `outputs/demo/comparison.png` 和 `metrics.csv` 查看预测误差。
[快速上手](https://motorfit.github.io/main/getting-started/quickstart.html)解释了各项输出和预期数值。
这条命令回放已有模型；要采集数据并辨识自己的电机，请从[实验流程](https://motorfit.github.io/main/getting-started/workflow.html)开始。

<details>
<summary><strong>在 MuJoCo 中回放示例</strong></summary>

```bash
uv sync --frozen --extra simulation
uv run --no-sync motorfit replay \
  --dataset tests/fixtures/offline/manifest.json --engine mujoco \
  --dt 0.002 --output outputs/mujoco
```

Newton 与 mjlab 的安装见[可选环境](https://motorfit.github.io/reference/backends.html)，支持的模型和回放设置见[验证指南](https://motorfit.github.io/guide/validation.html)。

</details>

## 支持的电机

| 系列 | 接入方式 |
| :--- | :--- |
| [RobStride](configs/motors/robstride) | RS00–RS06 · 电机端 MIT 控制 |
| [达妙 Damiao](configs/motors/damiao) | 16 个 MIT 型号配置，含 DM4310、DM4340 和 DM8009 |

## 文档

- **[采集自己的电机](https://motorfit.github.io/guide/configuration.html)** — 选择型号、测量夹具、配置设备并[采集数据](https://motorfit.github.io/guide/acquisition.html)。
- **[辨识与评估](https://motorfit.github.io/getting-started/workflow.html)** — 整理记录、拟合候选模型，在独立数据上评估。
- **[复现 RS05 实验](https://motorfit.github.io/case-studies/rs05.html)** — 111 条记录、三档负载、三个物理仿真后端。Git 包含三条完整示例，全部数据与视频[单独保存](https://motorfit.github.io/case-studies/rs05.html#what-to-reproduce)。
- **[扩展 MotorFit](https://motorfit.github.io/development/architecture.html)** — 了解驱动、控制器、夹具和数据集接口。

全部指南见[文档索引](https://motorfit.github.io/index.html)；文件存放与 Git 跟踪规则见[仓库规范](https://motorfit.github.io/development/contributing.html)。

## Coding agent 使用

在 Codex 或 Claude Code 中打开本仓库，直接描述要完成的任务。仓库提供四个共享 [skills](.agents/skills)：

| Skill | 任务 |
| :--- | :--- |
| [motorfit-setup](.agents/skills/motorfit-setup/SKILL.md) | 安装依赖并跑通离线示例 |
| [motorfit-record](.agents/skills/motorfit-record/SKILL.md) | 配置已安装的电机并采集台架数据 |
| [motorfit-identify](.agents/skills/motorfit-identify/SKILL.md) | 处理记录、拟合候选模型并选型 |
| [motorfit-validate](.agents/skills/motorfit-validate/SKILL.md) | 评估固定模型并运行受支持的物理回放 |

例如：“使用 motorfit-setup 安装 MotorFit，并跑通离线示例。”技能正文直接存放在 `.agents/skills/`，由 Codex 自动发现；Claude Code 通过 `.claude/skills` 相对软链接读取同一份文件，其他 agent 也可直接读取正文目录。

## 致谢

感谢 [Rhoban BAM](https://github.com/Rhoban/bam) 的作者提供本项目使用的执行器模型与参数辨识工具。

## 许可证

MotorFit 采用 [Apache License 2.0](LICENSE) 许可证。
