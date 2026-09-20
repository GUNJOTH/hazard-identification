# hazard-identification

面向工业安全流程的多模态隐患识别与分析后端 API。服务将同一隐患的多张图片交给视觉模型分析，再结合隐患规则库输出证据、识别结果和处理建议。

仓库采用单项目子目录布局，核心代码和运行环境位于 [hazard-identification/](./hazard-identification/)。

## 快速开始

前置环境：

- Python >=3.12,<3.13
- [uv](https://docs.astral.sh/uv/)

在 PowerShell 中执行：

~~~powershell
Set-Location hazard-identification
uv sync --locked
Copy-Item .env.example .env
# 仅在本地 .env 中填写实际配置，不要提交密钥
uv run uvicorn python_app.main:app --host 0.0.0.0 --port 8787
~~~

启动后可访问：

- OpenAPI 文档：http://127.0.0.1:8787/docs
- 独立前端预览：http://127.0.0.1:8787/demo/
- 健康检查：http://127.0.0.1:8787/api/v1/health

视觉模型和 Dify 规则库的配置项见 [hazard-identification/.env.example](./hazard-identification/.env.example)。真实密钥、真实生产图片和含个人信息的样本不得提交到仓库。

## 项目入口

- [核心服务说明](./hazard-identification/README.md)：启动、预览和主要输出结构。
- [API 字段说明](./hazard-identification/API.md)：接口和响应字段。
- [规则知识库](./hazard-identification/knowledge-base/)：隐患字段、分级、法规依据和整改建议。
- [治理约定](./GOVERNANCE.md)：分支、变更、证据和数据边界。
- [贡献指南](./CONTRIBUTING.md)：本地检查和 Pull Request 要求。
- [安全策略](./SECURITY.md)：漏洞、凭据和敏感样本处理方式。

## 本地验证

当前项目没有在 pyproject.toml 中声明 pytest 等自动化测试依赖。提交后端变更前至少执行：

~~~powershell
Set-Location hazard-identification
uv sync --locked
uv run python -m compileall -q python_app
~~~

行为或接口变更还应使用授权的、去标识化的样本进行接口验证，并在 Pull Request 中记录结果。仓库 CI 会执行锁文件安装和 Python 编译检查；这项检查不能替代真实模型、Dify 或生产环境联调。

## 运行边界

该服务可能向外部视觉模型和 Dify 知识库发送图片或文本。接入生产环境前，应确认数据授权、网络出口、凭据轮换、API 认证和 CORS 配置符合所在组织的安全要求。