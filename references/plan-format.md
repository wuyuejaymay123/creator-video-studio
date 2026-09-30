# 计划格式与导出

完整方案反复修改时，保存一份 JSON，让纯口播和拍摄表共用同一个 speech。局部改一句话无需建立 JSON。

脚本要求 Python 3.10+，无额外包。以下命令在本技能目录运行：

```text
python scripts/plan.py examples/workflow.plan.json --check
python scripts/plan.py examples/workflow.plan.json --out "你的项目/方案-v2"
```

导出两个文件：口播稿.md、拍摄与后期.md。后者用日常语言说明怎么拍、图片怎么动、两段怎么接和需要准备什么；内部英文分类和 ID 不展示，图片生成提示词折叠。已有任一同名文件则默认退出；有意覆盖时加 --overwrite，或使用新目录。

JSON 是 Codex 使用的内部记录。delivery、screen、visual 的过程描述以及转场拍法仍要写成用户听得懂的话，不能指望导出程序自动改写生硬的内容。素材可以加 name 作为对外名称，例如“纸条和小册子”；不填则显示“素材 1”。

## 版本 2 的根字段

schema_version 为整数 2；title 为非空文本；brief 包含 audience、problem、payoff、action 四个非空文本字段。segments 是非空列表，transitions 是列表，没有特殊边界时写 []。assumptions 是可选的字符串列表，列明制作假设。

assets、promises、takeaway 的定义见下。它们按内容需要填写，不为了过校验制造虚构承诺。

## 逐句记录 segments

| 字段 | 内容 |
|---|---|
| id | 唯一字符串，如 s01 |
| speech | 完整口播，所有输出共用的台词来源 |
| visibility | face 或 voice；同一行不混用 |
| delivery | 简短可执行的表演/声音提示 |
| screen | 观众实际看到什么 |
| purpose | 本句对观众疑问或内容推进的作用 |
| assets | 可选素材 ID 列表 |
| visual | 下面的语义对象，版本 2 每行必填 |

visual 的 relation 取 hold、contrast、cause、sequence、correction、zoom、analogy、summary、evidence、context 之一，详见 [语义规则](meaning.md)。其余字段都是非空文本：
object（持续对象）、before（起态）、change（变化）、after（终态）、cue（触发词或动作）、hold（稳定阅读窗口）。

普通露脸也填写 hold 类型：自然讲述、关键词与停顿即可。不要为了填字段凭空增加动画。跨句状态由相邻行衔接，后期以逐句 visual 为时间和状态依据；素材 motion 只概括该资产用途。拍前用口播/动作锚点，拍后使用工程或剪辑记录的真实时间。

## 转场记录 transitions

一条记录连接相邻且向前的 from/to 行，每个边界只保留一张执行卡；需要多种技巧时在 edit 描述组合。

必填文本：id、from、to、reason、cue、outgoing、incoming、continuity、edit、audio、fallback。它们分别说明标识、边界、理由、触发、出镜头、入镜头、连续性、剪法、声音和替代方案。

枚举：
- technique：cut、occlusion、whip、match、push、pull、graphic_handoff、audio_bridge。
- mode：capture、post、hybrid。
- status：planned、ready、fallback。

ready 另需 checked_media，记录实际查看的源文件与剪点；文字存在只能通过结构检查，仍须真实查看素材。fallback 状态执行 fallback 字段的方案；保持计划和工程记录一致。详见 [转场](transitions.md)。

## 素材 assets

每项需 id、type、status、purpose、source。
type 取 imagegen / recording / screenshot / diagram / audio；status 取 planned / available / generated。source 写实际路径、来源或明确待采集动作，计划中的来源不能当现成文件。

第三方视频或用户录屏使用 recording，静态截图使用 screenshot。待补素材设为 planned，source 写明具体页面或对象、需要截到的内容或录制起止动作、已知来源和缺少时的处理；每句通过 assets 引用对应素材。导出时自动汇总为“需要你补充的截图或视频”，并带上对应台词。具体要求见 [补素材规则](production.md#需要用户补充的截图或视频)。

imagegen 另需 prompt、非空 layers 字符串列表、animate 布尔值。动画为 true 时，motion 含 before、change、after、cue 非空文本。分层清单意味着逐层制作，每层生成后记录实际文件；不代表一张输出已经能独立拆层。

## 承诺与结尾

promises 每项有 text、setup（提出承诺的行 ID）、payoff（非空兑现行 ID 列表）。兑现位置不能早于提出位置。程序验证引用，是否真兑现要读内容。

takeaway 可选；若有，需 title、segment 和非空 items 字符串列表。items 是观众实际看到的内容，不是“这里放清单”的占位。

## 兼容与能力范围

旧 schema_version: 1 仍可导出；旧记录不要求 brief、purpose、visual 或 transitions，新加入这些可选字段时会检查其结构。旧示例保留在 [周报示例](../examples/weekly-report.plan.json)，完整新示例在 [流程示例](../examples/workflow.plan.json)。

脚本检查结构、引用、相邻边界和输出覆盖保护；不能核实事实、素材是否真实可用、语义是否匹配、表演是否自然或视频是否好看。它不生成图片、配音或视频。实际制作和检查遵循 [制作](production.md) 与 [验收](quality.md)。
