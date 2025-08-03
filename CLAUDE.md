## 语言要求

- 通过中文同我沟通和对话。
- 项目日志、注释、文档等非代码采用中文。

## 通用规范

- 执行各自语言的最佳规范。
- url 的路径，必须使用使用不带尾随斜杠的形式。反模式: `/users/`，最佳实践：`/users`
- 避免使用 dict/map 等格式进行接口，数据交互，而应该使用定义的有明确字段的实体类进行交互。
- 项目的分包方式采用`垂直切片架构 (Vertical Slice Architecture)`，围绕“功能（Feature）”来组织代码，而不是围绕“技术分层（Layer）”
- 在编写条件判断逻辑时，应遵循"早期返回"和"卫语句"原则来减少代码嵌套层级：优先使用 return、break、continue 等语句处理边界条件和异常情况，避免深层嵌套的 if-else 结构；将正常的核心业务逻辑放置在函数或循环的最后部分，保持在最外层执行，从而提高代码的可读性、可维护性，并降低代码复杂度。
- 方法交互，参数传递、返回值类型，不要 使用不安全的 dict 而是封装为dataclass或者 class 等结构
- 相比于松散的 dict 类型，我更倾向于定义对应的 class 规范类型。
- 代码注释完善，关键设计点，重要代码，复杂逻辑等不容易理解的地方，都要有详细的注释，文字不容易理解，可以通过流程图等方式辅助说明。

## Python 语言要求

- Python 默认版本 `3.12 
- 默认通过 `uv` 进行项目包管理，而不是 `Virtualenv`

  uv 指令参考：

  ```
  # 项目管理
  uv init <project-name> --python 3.12  # 创建新项目
  uv add <package>                      # 添加依赖
  uv add --dev <package>                # 添加开发依赖
  uv remove <package>                   # 移除依赖
  uv sync                               # 同步依赖
  uv sync --upgrade                     # 更新依赖

  # 运行相关
  uv run <command>                      # 运行命令
  uv run python main.py                 # 运行 Python 脚本

  # 信息查看
  uv tree                               # 查看依赖树
  uv tree --outdated                    # 查看过时依赖
  uv python list                        # 查看可用 Python 版本

  # 工具管理
  uv tool install <tool>                # 安装全局工具
  uv tool list                          # 查看已安装工具
  uv tool run <tool> <args>             # 运行工具
  ```


- Python 选择的外部依赖的包，应该选择当前主流通用的版本，而不是过时版本。
- Python 有 Pydantic 的时候，你经常会错误使用 Pydantic V1 版本的用法，V2核心变化是方法命名更明确（从 parse/dict 改为 model_validate/model_dump），配置从类改为字典，验证器装饰器重新设计。

  ```
  - `parse_obj()` → `model_validate()`
  - `parse_raw()` → `model_validate_json()`  
  - `dict()` → `model_dump()`
  - `json()` → `model_dump_json()`
  - `Config` 类 → `model_config` 字典
  - `validator` 装饰器 → `field_validator`
  - `root_validator` → `model_validator`
  - `Field(alias_generator=)` → `Field(validation_alias=)`
  ```

- 通用的方法**必须**包含**类型提示 (Type Hint)** 并严格**遵循 PEP 8** 规范，且必须采用自带的内置类型，比如：int、list、dict、tuple 等。以下为范例：

  ```python
  def send_email(
      address: str | list[str],
      sender: str,
      cc: list[str] | None,
      bcc: list[str] | None,
      subject: str = '',
      body: list[str] | None = None,
  ) -> bool:
      ...

  x: Callable[[int, float], float] = f

  def register(callback: Callable[[str], int]) -> None:
      ...

  def gen(n: int) -> Iterator[int]:
      i = 0
      while i < n:
          yield i
          i += 1
  ```

- 其他未尽事宜按照各自语言项目的最佳实践进行实施

## 项目资源
已在本地创建了 2 个 redis 实例，无密码。
```
docker run -d --name redis-6378 -p 6378:6379 redis:8 redis-server 
docker run -d --name redis-6376 -p 6376:6379 redis:6 redis-server 
```