# api-image

一个给 Codex App 用的图片生成 Skill。

它的作用很简单：当你在 API 形式使用 Codex App，没法直接用官方内置 `imagegen` 时，让 Codex 改走你自己配置的 OpenAI-compatible 图片接口，例如通过 CPA 反代出来的 `gpt-image-2`。

用网页版生过图的朋友应该知道，网页端的生图不是单纯“把一句 prompt 传给图片模型”。它更像一个 agent：主模型会理解你的需求，必要时搜索资料、分析参考图、整理提示词，然后再调用图片模型。这个 Skill 就是尽量复刻这种流程：你用自然语言告诉 Codex 想要什么，Codex 负责前面的 agent 工作，最后通过你的 Provider API 生图。

## 它能做什么

- 文生图
- 参考图生图
- 局部编辑 / inpainting
- 多参考图辅助构图、风格、产品或人物一致性
- 需要真实信息的图片生成前，先让 Codex 搜索和整理参考资料
- 默认读取你 Codex 根目录里的 Provider 配置
- 临时切换本次调用使用的 URL 或 API Key

更细的调用规则和脚本参数都在 [SKILL.md](./SKILL.md) 里，README 只讲怎么用。

## 安装

把仓库放到 Codex 的 skills 目录：

```powershell
git clone <repo-url> "$env:USERPROFILE\.codex\skills\api-image"
```

如果你设置了 `CODEX_HOME`：

```powershell
git clone <repo-url> "$env:CODEX_HOME\skills\api-image"
```

然后重启 Codex App，或让 Codex 重新加载 Skills。

## 配置

默认情况下，这个 Skill 会读取你 Codex 根目录里的配置：

- `config.toml`
- `auth.json`（可选）

根目录优先使用 `--codex-home`，其次是环境变量 `CODEX_HOME`，否则使用 `~/.codex`。脚本从 `config.toml` 的 `model_provider` 选择 Provider，并读取对应的 `base_url`。

凭据按以下顺序选择：

1. 本次显式指定的 `--api-key-env` 或 `--api-key`。
2. 当前 Provider 的 `env_key` 指向的环境变量。
3. 当前 Provider 的 `experimental_bearer_token`。
4. `auth.json` 中的 `OPENAI_API_KEY`。
5. 环境变量 `OPENAI_API_KEY`。

因此，没有 `auth.json` 也可以正常使用。例如，Codex 已经在当前 Provider 下配置了 `experimental_bearer_token`，就可以直接生图，无需再复制凭据。新配置更推荐使用 `env_key`。

如果显式选择的环境变量为空或不存在，脚本会报错，不会偷偷换用其他凭据。脚本不读取 ChatGPT OAuth 登录令牌或系统凭据库，也不合并项目级或 profile 配置；仅有 Codex 登录状态并不代表有图片 API 权限。

这个仓库不会、也不应该保存你的 API Key。

## 配置自检

需要 Python 3.11 或更高版本。常规请求仅依赖 Python 标准库；安装 Pillow 可增强输入图片检查。

可以先运行不联网的自检，无需提供提示词：

```powershell
python "<skill-dir>\scripts\generate_image.py" --check-config
```

成功时显示配置目录和凭据来源，不打印密钥，不发出生图请求。自检只确认本地配置可读取；接口、模型和账户权限仍需实际请求验证。

开发时运行回归测试（使用临时配置和本机模拟接口，不访问真实 Provider）：

```powershell
python -B -m unittest discover -s tests -v
```

## 怎么用

安装后，正常和 Codex 说话就行。比如：

```text
用 api-image 生成一张 2048x1152 的电影感照片：雨夜东京街头，霓虹反光，真实摄影风格。
```

带参考图时可以这样说：

```text
参考这张图的构图和人物姿势，生成一张暖色电影感插画，保持主体姿态，但不要照抄原图。
```

需要真实地点、产品、建筑、历史服饰这类容易生成错的东西时，可以直接要求 Codex 先查资料：

```text
先查一下花江峡谷大桥的结构和地形参考，再生成一张高空俯视图，尽量保持真实桥型和峡谷环境。
```

## 临时换接口

默认会用你 Codex 根目录里的 Provider 配置。

如果只想这一次换 URL 或 key，可以直接告诉 Codex：

```text
这次生图临时用 https://example.com/v1 这个 base_url，API key 从 API_IMAGE_API_KEY 环境变量读。
```

更推荐让 key 放在环境变量里，不要在聊天里直接粘贴。临时切换只影响本次调用，不会写回你的 `auth.json` 或 `config.toml`，除非你明确要求 Codex 修改配置。

## 关于 gpt-image-2

这个 Skill 默认按 `gpt-image-2` 的官方图片 API 规则处理：

- 纯文生图走 `/images/generations`
- 有参考图、输入图或 mask 时走 `/images/edits`
- 官方 GPT Image models 默认读返回里的 `b64_json`
- `gpt-image-2` 不支持透明背景
- `gpt-image-2` 不需要、也不应该传 `input_fidelity`

如果你的 Provider 对这些参数有自己的兼容层，以 Provider 的实际报错为准。

## 目录

```text
api-image/
  SKILL.md
  README.md
  LICENSE
  agents/
  scripts/
```

## 说明

这是个人自用 Skill 的整理版，主要目标是让 Codex App 在 API 使用形态下也能比较自然地完成图片生成工作。不同反代和 Provider 的兼容程度可能不一样。

MIT License.

## 致谢

感谢 [linuxdo](https://linux.do/) 社区的交流、分享与反馈。
