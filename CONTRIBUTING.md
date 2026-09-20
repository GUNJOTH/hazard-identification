# 贡献指南

## 开始前

1. 阅读根目录 README、GOVERNANCE.md 和子项目 hazard-identification/README.md。
2. 使用 Python 3.12 和 uv。
3. 在 hazard-identification/ 目录执行 uv sync --locked。
4. 不要把 .env、API 密钥、真实生产图片或含个人信息的材料复制到仓库。

## 分支和 Pull Request

从 main 创建用途明确的开发分支，例如：

- feat/<short-name>
- fix/<short-name>
- docs/<short-name>
- chore/<short-name>

Pull Request 应包含：

- 变更目的和范围；
- 对 API、规则或外部依赖影响的说明；
- 实际执行的验证命令和结果；
- 风险、兼容性影响和回滚方式。

不要直接向 main 推送。与接口、规则、认证或外部服务有关的变更应让审阅者能够定位对应代码、文档和证据。

## 提交前检查

在 hazard-identification/ 目录执行：

~~~powershell
uv sync --locked
uv run python -m compileall -q python_app
~~~

当前项目未声明 pytest 测试依赖；如果新增自动化测试，应同步更新项目依赖和锁文件，并在 Pull Request 中说明覆盖范围。涉及外部模型或 Dify 的检查必须使用隔离、授权且已脱敏的样本。

## 文档同步

- API 字段变化同步更新 API.md。
- 规则和法规依据变化同步更新 knowledge-base/ 中的对应文档。
- 启动方式、环境变量或运行边界变化同步更新 README 和 .env.example。