<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/rainzee/tapehead/main/assets/logo-dark.svg">
    <img src="https://raw.githubusercontent.com/rainzee/tapehead/main/assets/logo.svg" width="120" alt="tapehead">
  </picture>
</p>

<h1 align="center">tapehead</h1>

<p align="center">
  基于磁带 (Tape) 的 agent 框架<br>
  名字取自录音机的磁头: 录制时写带, 回放时读带
</p>

<p align="center">
  <a href="https://pypi.org/project/tapehead/"><img src="https://img.shields.io/pypi/v/tapehead?color=2b2118&labelColor=e9b44c&label=pypi" alt="PyPI"></a>
  <img src="https://img.shields.io/badge/python-3.13%2B-2b2118?labelColor=e9b44c" alt="Python 3.13+">
  <img src="https://img.shields.io/badge/status-sketch-2b2118?labelColor=e9b44c" alt="status: sketch">
</p>

---

## 核心概念

以下概念已经确定, 后续设计都以它们为前提. 仍在讨论中的问题见 [#1](https://github.com/rainzee/tapehead/issues/1).

### Tape

**Tape (磁带) 是 tapehead 的核心概念.** agent 发生过的一切都录在磁带上, 磁带是唯一的事实来源.

其他概念都围绕磁带展开, 而不是反过来:

- **会话**: 只是约定俗成的说法, 一盘磁带就是一个持久化的会话
- **持久化**: 存放磁带, 不存放磁带之外的任何东西
- **上下文**: 模型看到的消息从磁带回放得出, 不单独存储

### 只追加

磁带只能在末尾追加, 录上去的内容不修改, 不删除, 不重排.

- **序号**: 每一帧的序号就是它在磁带上的位置, 从 0 开始连续, 没有空洞
- **单写者**: 同一时刻一盘磁带只有一个写入方
- **修复靠追加**: 中断留下的未闭合状态, 通过追加补写来闭合, 不改动已录的帧
- **增量不上带**: 流式增量 (如 token 级输出) 只出现在实时流中, 不录上磁带

### 介质

磁带存放在哪里, 由介质决定. 内存 (`mem`), 文件系统 (`fs`), 数据库 (`db`) 是平等并列的三种介质, 它们实现同一套 `Tape` 和 `Silo` 协议, 磁带的语义不随介质改变. `db` 目前只是占位.
