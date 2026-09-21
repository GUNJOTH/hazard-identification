# 发布约定

本文档规定 `hazard-identification` 的版本、检查和 GitHub Release 流程。当前仓库没有
自动发布工作流，因此发布由仓库维护者按本约定手动完成。

## 版本与变更记录

- 版本号以 `hazard-identification/pyproject.toml` 的 `[project].version` 为准。
- 使用 `MAJOR.MINOR.PATCH` 版本格式，并使用 `vMAJOR.MINOR.PATCH` 作为 Git tag。
- 用户可见的功能、修复、API 字段、规则知识库、法规依据和外部依赖变化必须先在
  `CHANGELOG.md` 的对应版本条目中记录。
- 版本号和更新日志在同一个 Pull Request 中修改；PR 目标为 `main`，不得直接推送
  或强推 `main`。
- 尚未形成正式版本的变化写入 `[未发布]`，不要在没有实际发布内容时伪造历史版本
  条目。

## 发布前检查

合并版本 PR 前，至少在 `hazard-identification/` 目录执行与当前 CI 一致的检查：

```powershell
Set-Location hazard-identification
uv sync --locked
uv run python -m compileall -q python_app
```

涉及 API、规则或报告行为时，还要使用授权、隔离且已脱敏的样本完成接口验证，记录
接口路径、输入边界、外部依赖状态和实际结果。当前项目未声明 pytest 等自动化测试
依赖，不能把编译通过表述为完整功能测试通过。

涉及视觉模型或 Dify 知识库时，必须单独记录模型、知识库、超时和重试配置；发布说明、
日志、测试材料和 Release 附件中不得包含真实 API 密钥、Token、生产图片或个人信息。

如果本次变更只修改了根目录文档，当前 CI 的路径过滤可能不会自动触发检查，仍应按
上述命令完成本地验证，并在 Pull Request 中记录结果。

## 发布步骤

1. 从 `main` 创建版本 PR，更新 `hazard-identification/pyproject.toml` 版本号和
   `CHANGELOG.md`。
2. 等待 CI 或 PR 中记录的本地验证通过，并完成 API、规则依据、外部服务边界和敏感
   信息审查后合并。
3. 在已合并的 `main` 提交上创建对应的 `vMAJOR.MINOR.PATCH` tag，并推送该 tag；
   不修改或覆盖已有 tag。
4. 基于该 tag 创建 GitHub Release，标题使用版本号，正文引用
   `CHANGELOG.md` 中对应版本条目，并注明规则依据、外部依赖、配置变化和已知限制。
5. 发布后确认 Release、tag 和 `pyproject.toml` 版本一致；如发现问题，按补丁版本
   发布修复，不回写已发布版本。

## 回滚边界

发布回滚不得通过删除或覆盖 tag 伪造历史。应用代码、规则知识库、外部服务配置和
数据处理结果的回滚必须分别评估；如果已产生对外报告，应保留原版本证据，并通过新
版本修复或明确的重新分析说明处理。
