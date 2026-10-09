<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/rainzee/tapehead/main/assets/logo-dark.svg">
    <img src="https://raw.githubusercontent.com/rainzee/tapehead/main/assets/logo.svg" width="360" alt="tapehead">
  </picture>
</p>

<h1 align="center">tapehead</h1>

<p align="center">
  基于磁带 (Tape) 的 agent 框架<br>
  名字取自录音机的磁头: 录制时写带, 回放时读带
</p>

---

agent 发生过的一切都录在磁带上, 其余的都从磁带里读出来. 下面是已经钉死的概念, 仍在讨论的见 [#1](https://github.com/rainzee/tapehead/issues/1).

## 磁带 (Tape)

唯一的事实来源, 其他概念都围绕它展开. "会话" 只是约定俗成的说法, 一盘磁带就是一个持久化的会话.

## 帧

磁带上的一条记录, 由介质信封 `Frame(recorded_at, event)` 承载, `recorded_at` 是录入时间, 不是事件的发生时间.

帧的位置就是它在磁带上的下标, 从 0 开始连续, 没有空洞, 永久稳定, 不单独存储. 翻录的 `Origin.at` 是父带前缀的排他结束位置, 续读的游标指向下一条待读的帧.

## 事件 (Event)

帧承载的事实, 用动词过去式命名, 每个事件都是某个参与者做出的, 推不出来的一件事: `Configured` (宿主), `Prompted` (用户), `Generated` / `Aborted` (模型), `Dispatched` (harness), `Returned` (工具), `Yielded` (agent 交还控制权), 以及 `Anchored` 和扩展出口 `Custom`. 能从其他事件推出来的不记录.

事件带着模型看到的消息 (Message), 带消息的事件进入上下文, 不带的只记账. `Generated` 同时存消息和产生它的增量流, 二者不一致的事件构造不出来.

## 只追加

磁带只能在末尾追加, 录上去的不修改, 不删除, 不重排.

## 单写者

同一时刻一盘磁带只有一个写入方.

## 修复靠追加

中断留下的未闭合状态, 通过追加补写来闭合, 不改动已录的帧.

## 增量不逐条上带

流式增量 (如 token 级输出) 在实时流中逐条出现, 一次模型调用结束后随 `Generated` 整体落带, 失败的调用也照样落带. 代价是进程在流的中途崩溃时, 这次调用不留痕迹.

## 回放

模型看到的消息不单独存储, 从磁带回放得出. 持久化只存磁带, 不存磁带之外的任何东西.

模型的输入只经由回放得出, 所以每一次模型调用都能精确重放: 位置 i 上的 `Generated` 的输入, 等于回放 i 之前的前缀.

## 介质

磁带存放在哪里, 由介质决定. 内存 (`mem`), 文件系统 (`fs`), 数据库 (`db`) 是平等并列的三种介质, 它们实现同一套 `Tape` 和 `Silo` 协议, 磁带的语义不随介质改变. `db` 目前只是占位.

## 磁带库 (Silo)

负责磁带的存放和出入库, 每种介质有自己的磁带库: `MemSilo`, `FsSilo`, `DbSilo`. 帧的读写只经由 `Tape` 句柄, 不经由磁带库.

## 模型提供方 (Provider)

内核只认一个 `Provider` 协议, 由 host 传入, 不内置 provider, 也不读环境变量. 随库附带一个 OpenAI 兼容的实现, 对接 vLLM 上的 Qwen, 它的依赖放在可选 extra `tapehead[openai]` 里.

## 工具 (Tool)

由 host 提供, 内核只负责派发. 参数用一个 `msgspec.Struct` 声明, schema 和校验都出自这一处, 由人来写, 不从函数签名推导. 工具失败 (未知工具, 参数不合法, 执行出错) 不中断一轮, 作为错误结果交还给模型.
