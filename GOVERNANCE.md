# 项目治理约定

## 项目范围和事实来源

本仓库维护工业安全场景的多模态隐患识别后端。项目事实以源码、pyproject.toml、uv.lock、API 文档、规则知识库、CI 结果和 Pull Request 记录为准。

- 业务代码和运行入口：hazard-identification/python_app/
- 规则与法规依据：hazard-identification/knowledge-base/
- 接口说明：hazard-identification/API.md
- 本地配置样例：hazard-identification/.env.example
- 前端预览和图片样本：hazard-identification/test/

## 分支与合并

- main 是默认交付分支，变更通过 Pull Request 合并。
- main 禁止删除、禁止强推或非 fast-forward 更新。
- 开发分支使用用途标识，推荐 feat/、fix/、docs/、chore/ 前缀。
- Pull Request 应说明变更范围、验证证据、风险和回滚方式。
- 人工审批数量是独立的治理决策，以 GitHub 当前 Ruleset 配置为准，不在本文件中预设具体人数。

## 变更证据

- API 字段或响应行为变化时同步更新 API.md。
- 规则、法规依据或整改建议变化时，说明来源、适用范围和生效影响。
- 视觉模型、Dify、超时、重试、认证和 CORS 配置变化时，说明外部依赖和失败边界。
- 不使用真实生产合同、个人信息、未脱敏图片、访问令牌或其他凭据作为提交材料。

## 自动化检查

仓库 CI 负责安装锁定依赖并执行 Python 编译检查。它不能证明外部视觉模型、Dify 知识库或生产网络联调成功；需要这些系统的验证必须单独记录环境和结果。

## 问题处理

缺陷优先通过 Issue 提供可复现步骤、期望行为、实际行为和已脱敏日志。安全漏洞、密钥泄露和敏感数据问题不要公开到 Issue 或 Pull Request，按 SECURITY.md 的方式私下报告。