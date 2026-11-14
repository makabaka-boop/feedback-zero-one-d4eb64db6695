# GraphQL 局部失败后端（科研目录入湖）

按 [GraphQL October 2021 规范](https://spec.graphql.org/October2021/) §5.3.2、§6.3、§6.4
实现的子集后端：保留局部失败（partial failure）语义——字段错误沿非空链冒泡至可空边界，
只记录最初路径，外层继续执行。

## 输入 / 输出

输入为单个 JSON 对象，仅含三个成员：

```json
{"schema": "<SDL 字符串>", "query": "<查询字符串>", "root": {<源对象>}}
```

输出：

```json
{"data": ..., "errors": [["<响应键>", 0, ...], ...]}
```

- `errors` 按发生顺序记录路径：字段用响应键（别名），列表下标零基；无错为 `[]`。
- 根被撤销时 `data` 为 `null`。
- 非法请求被拒绝：`data` 为 `null`，`errors` 含单个顶层条目——出错字段的顶层响应键；
  语法错误及无法归属的错误报 `"$"`。输入 JSON 中的重复成员同样拒绝。
- 字段错误不影响结果输出（局部失败）。

示例：`type Query { a: [Int!] }` + `{ z: a }` 作用于 `{"a": [null]}`
得到 `{"data": {"z": null}, "errors": [["z", 0]]}`。

## 支持的子集

- 类型：仅 `String`、`Boolean`、`Int`、对象、接口、联合，加列表与非空包装。
  SDL 中出现 `Float`、`ID`、自定义标量、枚举、输入对象、字段参数、自定义指令即拒绝。
- 单个 query 操作：别名、命名片段与内联片段、`@skip`/`@include`（仅布尔字面量）。
- 拒绝：变量、字段参数、自定义指令、除 `__typename` 外的内省、多操作、
  mutation/subscription、重复定义（操作、片段、类型）。
- 预检整个查询：被 `@skip`/`@include(if: false)` 跳过的字段照常校验；
  响应形状检查（SameResponseShape）对互斥类型同样生效。

## 执行语义

- 源按**原字段名**取值，缺失同 `null`；标量值保证合法（仍做防御性形状检查）。
- 抽象类型（接口/联合）的源对象必须含合法 `__typename`，否则为字段错误；
  具体对象按声明类型（忽略源中的 `__typename`）；`__typename` 元字段返回运行类型名。
- 形状/类型不符（如对象位置给标量、列表位置给非列表、标量位置给对象）为字段错误。
- 按响应键**首次收集顺序**深度优先执行，列表保持原序；同键字段合并子选择。
- 非空错误冒泡至可空边界，仅记最初路径；被撤销的对象/列表停止剩余求值，外层继续。

## 代码结构

```
main.py                 入口：读 JSON（文件参数或 stdin），输出 {data, errors}
backend/
  service.py            管线：建模 → 解析 → 校验 → 执行
  restrictions.py       schema 子集限制
  validation.py         自定义规则 + 自写 §5.3.2 字段冲突检查
  execution.py          自写 §6.3 收集/执行 + §6.4 完成
acceptance.py           验收运行器
tests/                  用例（交集 / 额外规则 / fuzz）与 golden 输出
```

graphql-core 仅用于建模（`build_schema`）、解析（`parse`）及其余校验规则；
字段冲突检查、字段收集、合并、值完成均为自写，未使用执行器。

## 入口行为

```
python3 main.py [input.json] [output.json]
```

- 结果始终打印到 stdout；退出码：接受为 0（含字段错误），拒绝为 1，用法/IO 错为 2。
- 给定输出文件时：**成功替换输出，拒绝保留旧文件**（仅接受的请求才写文件）。

## 验收

```
python3 acceptance.py
```

1. **合法交集对照库**：固定用例 + 固定种子 fuzz（共 670 例），与 graphql-core
   执行器逐例比对 `data` 与错误路径。
2. **额外规则独立验**：66 例限制与后端特有行为，精确比对期望输出。
3. **入口**：退出码、stdout、文件替换/保留语义。

全部通过才替换 `tests/golden/results.json`；任一失败保留旧文件并以非零码退出。
