"""服务内部异常定义。"""


class UpstreamError(RuntimeError):
    """视觉模型或知识库上游调用失败。"""

    def __init__(self, message: str, *, status_code: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable
